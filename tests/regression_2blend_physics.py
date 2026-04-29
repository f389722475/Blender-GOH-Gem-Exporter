from __future__ import annotations

from pathlib import Path
import sys

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for module_name in list(sys.modules):
    if module_name == "blender_goh_gem_exporter" or module_name.startswith("blender_goh_gem_exporter."):
        del sys.modules[module_name]

import blender_goh_gem_exporter as addon  # noqa: E402
from blender_goh_gem_exporter import blender_exporter as exporter_module  # noqa: E402


def _action_frame_range(obj: bpy.types.Object) -> tuple[int, int]:
    animation_data = getattr(obj, "animation_data", None)
    action = getattr(animation_data, "action", None) if animation_data else None
    if action is None:
        return (1, 1)
    frames = [
        int(round(keyframe.co.x))
        for fcurve in exporter_module._action_fcurves(action)
        for keyframe in fcurve.keyframe_points
    ]
    return (min(frames), max(frames)) if frames else (1, 1)


def _dominant_component(values: list[Vector]) -> list[float]:
    components = [[value[index] for value in values] for index in range(3)]
    return max(components, key=lambda series: max(series) - min(series))


def _sign_changes(values: list[float], threshold: float) -> int:
    signs: list[int] = []
    for value in values:
        if abs(value) <= threshold:
            continue
        sign = 1 if value > 0.0 else -1
        if not signs or signs[-1] != sign:
            signs.append(sign)
    return max(0, len(signs) - 1)


def _smoothness_ratio(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    steps = [abs(values[index + 1] - values[index]) for index in range(len(values) - 1)]
    curvature = [
        abs(values[index + 1] - 2.0 * values[index] + values[index - 1])
        for index in range(1, len(values) - 1)
    ]
    return max(curvature, default=0.0) / max(max(steps, default=0.0), 1e-6)


def _evaluate_body(source: bpy.types.Object, body: bpy.types.Object, source_axis: Vector) -> None:
    scene = bpy.context.scene
    start, end = _action_frame_range(body)
    end = min(end, start + 72)
    rest_location = body.location.copy()
    rotations: list[Vector] = []
    same_direction_motion = 0.0
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        rotations.append(Vector((body.rotation_euler.x, body.rotation_euler.y, body.rotation_euler.z)))
        same_direction_motion = max(
            same_direction_motion,
            (body.matrix_world.to_translation() - rest_location).dot(source_axis),
        )
    rest_rotation = rotations[0].copy()
    rotations = [rotation - rest_rotation for rotation in rotations]
    series = _dominant_component(rotations)
    amplitude = max(series) - min(series)
    if amplitude <= 0.002:
        raise RuntimeError(f"{body.name} body swing amplitude is too small after bake.")
    if _sign_changes(series, max(0.001, amplitude * 0.035)) < 2:
        raise RuntimeError(f"{body.name} body swing does not rebound enough.")
    if _smoothness_ratio(series) > 1.85:
        raise RuntimeError(f"{body.name} body swing has a frame-to-frame jerk spike.")
    if same_direction_motion <= 0.0005:
        raise RuntimeError(f"{body.name} body motion no longer follows the recoil direction.")


def _evaluate_antenna(source: bpy.types.Object, antenna: bpy.types.Object, source_axis: Vector) -> None:
    mesh = antenna.data if antenna.type == "MESH" else None
    shape_keys = getattr(mesh, "shape_keys", None) if mesh else None
    if shape_keys is None:
        raise RuntimeError(f"{antenna.name} did not keep antenna shape keys.")
    antenna_keys = [
        key for key in shape_keys.key_blocks
        if key.name.startswith("GOH_AntennaWhip_")
    ]
    if not antenna_keys:
        raise RuntimeError(f"{antenna.name} did not generate Antenna Whip keys.")
    anchor_data = exporter_module._physics_antenna_anchor_axis(mesh)
    if anchor_data is None:
        raise RuntimeError(f"{antenna.name} has no usable antenna axis.")
    anchor_axis, min_anchor, max_anchor = anchor_data
    length = max(max_anchor - min_anchor, 1e-6)
    source_local = antenna.matrix_world.to_3x3().inverted_safe() @ exporter_module._physics_antenna_drive_axis_world(source, source_axis)
    bend_axis = exporter_module._physics_perpendicular_axis(source_local, anchor_axis, Vector((1.0, 0.0, 0.0)))
    base_positions = [vertex.co.copy() for vertex in mesh.vertices]
    projections = [base.dot(anchor_axis) for base in base_positions]
    tip_threshold = max_anchor - length * 0.01
    tip_indices = [index for index, projection in enumerate(projections) if projection >= tip_threshold]
    if not tip_indices:
        raise RuntimeError(f"{antenna.name} has no tip vertices for direction check.")
    tip_motion = []
    for key in antenna_keys:
        delta = Vector((0.0, 0.0, 0.0))
        for index in tip_indices:
            delta += key.data[index].co - base_positions[index]
        delta /= float(len(tip_indices))
        tip_motion.append(delta.dot(bend_axis))
    if min(tip_motion[: max(4, len(tip_motion) // 2)]) >= -0.001:
        raise RuntimeError(f"{antenna.name} free tip is not lagging opposite the recoil direction.")
    if _sign_changes(tip_motion, max(0.001, max(abs(value) for value in tip_motion) * 0.05)) < 1:
        raise RuntimeError(f"{antenna.name} antenna swing lost its visible rebound.")


def main() -> None:
    if not Path(bpy.data.filepath).name.lower().endswith("2.blend"):
        raise RuntimeError("Open tests/2.blend before running this regression.")
    addon.register()
    try:
        scene = bpy.context.scene
        settings = scene.goh_tool_settings
        settings.physics_include_scene_links = True
        source = next((obj for obj in bpy.data.objects if obj.get("goh_physics_role") == "SOURCE"), None)
        if source is None:
            raise RuntimeError("2.blend does not contain a GOH physics SOURCE object.")
        scene.frame_set(1)
        bpy.ops.object.select_all(action="DESELECT")
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        result = bpy.ops.object.goh_bake_linked_recoil()
        if "FINISHED" not in result:
            raise RuntimeError(f"2.blend linked recoil bake failed: {result}")
        source_axis = exporter_module._physics_axis_world(source, settings.recoil_axis)
        bodies = [obj for obj in bpy.data.objects if obj.get("goh_physics_role") == "BODY_SPRING"]
        antennas = [obj for obj in bpy.data.objects if obj.get("goh_physics_role") == "ANTENNA_WHIP"]
        if not bodies or not antennas:
            raise RuntimeError("2.blend is missing Body Spring or Antenna Whip links.")
        for body in bodies:
            _evaluate_body(source, body, source_axis)
        for antenna in antennas:
            _evaluate_antenna(source, antenna, source_axis)
        print(f"OK 2.blend physics regression: {len(bodies)} body link(s), {len(antennas)} antenna link(s)")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
