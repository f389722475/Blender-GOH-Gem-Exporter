from __future__ import annotations

from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for module_name in list(sys.modules):
    if module_name == "blender_goh_gem_exporter" or module_name.startswith("blender_goh_gem_exporter."):
        del sys.modules[module_name]

import blender_goh_gem_exporter as addon  # noqa: E402
from blender_goh_gem_exporter import blender_exporter as exporter_module  # noqa: E402
from blender_goh_gem_exporter.physics import D6LiteLimit, InertiaSolverSettings, integrate_inertia_samples  # noqa: E402


def max_axis(samples: list[tuple[Vector, Vector]], axis: Vector) -> float:
    axis = axis.normalized()
    return max((offset.dot(axis) for offset, _angle in samples), default=0.0)


def min_axis(samples: list[tuple[Vector, Vector]], axis: Vector) -> float:
    axis = axis.normalized()
    return min((offset.dot(axis) for offset, _angle in samples), default=0.0)


def solver_settings(*, mass: float = 1.0, max_offset: float = 1.0, end_fade: float = 0.16) -> InertiaSolverSettings:
    return InertiaSolverSettings(
        frequency=2.0,
        damping_ratio=0.22,
        mass=mass,
        substeps=6,
        end_fade=end_fade,
        d6_limit=D6LiteLimit(
            linear_axes=Vector((1.0, 1.0, 1.0)),
            angular_axes=Vector((1.0, 1.0, 1.0)),
            max_offset=Vector((max_offset, max_offset, max_offset)),
            max_angle=Vector((1.0, 1.0, 1.0)),
        ),
    )


def assert_solver_core() -> None:
    recoil_axis = Vector((-1.0, 0.0, 0.0))
    accelerations = [recoil_axis * 80.0 for _ in range(4)] + [Vector((0.0, 0.0, 0.0)) for _ in range(20)]
    samples = integrate_inertia_samples(accelerations, None, solver_settings(), 24.0)
    if max_axis(samples, recoil_axis) <= 0.001:
        raise RuntimeError("Inertial solver should move in the same direction as a recoil-force proxy.")
    if samples[-1][0].length > 1e-7:
        raise RuntimeError("Inertial solver end fade did not force the last frame back to rest.")

    clamped = integrate_inertia_samples(accelerations, None, solver_settings(max_offset=0.035), 24.0)
    if max(offset.length for offset, _angle in clamped) > 0.03501:
        raise RuntimeError("D6-lite max offset clamp was exceeded.")

    light = integrate_inertia_samples(accelerations, None, solver_settings(mass=1.0, end_fade=0.0), 24.0)
    heavy = integrate_inertia_samples(accelerations, None, solver_settings(mass=3.0, end_fade=0.0), 24.0)
    if max(offset.length for offset, _angle in heavy) >= max(offset.length for offset, _angle in light):
        raise RuntimeError("Higher physics mass should reduce linked inertial displacement.")

    accel_24 = [recoil_axis * 80.0 if index < 4 else Vector((0.0, 0.0, 0.0)) for index in range(24)]
    accel_60 = [recoil_axis * 80.0 if index < 10 else Vector((0.0, 0.0, 0.0)) for index in range(60)]
    amp_24 = max(offset.length for offset, _angle in integrate_inertia_samples(accel_24, None, solver_settings(end_fade=0.0), 24.0))
    amp_60 = max(offset.length for offset, _angle in integrate_inertia_samples(accel_60, None, solver_settings(end_fade=0.0), 60.0))
    if abs(amp_24 - amp_60) / max(amp_24, amp_60, 1e-6) > 0.32:
        raise RuntimeError("Inertial solver amplitude changed too much across FPS/substep rates.")


def assert_bake_sign_policy() -> None:
    scene = bpy.context.scene
    settings = scene.goh_tool_settings
    settings.physics_solver_space = "WORLD"
    settings.physics_substeps = 6
    settings.physics_force_limit = 0.0
    settings.physics_end_fade = 0.12

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 0.0, 0.0))
    source = bpy.context.active_object
    source.name = "SolverSignSource"
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 0.0, 0.0))
    body = bpy.context.active_object
    body.name = "SolverSignBody"
    body["goh_physics_solver_space"] = "WORLD"

    frames = list(range(1, 25))
    recoil_axis = Vector((-1.0, 0.0, 0.0))
    accelerations = [recoil_axis * 90.0 if index < 4 else Vector((0.0, 0.0, 0.0)) for index in range(len(frames))]
    response = exporter_module._physics_inertial_response_samples(
        body,
        "BODY_SPRING",
        recoil_axis,
        Vector((0.0, 1.0, 0.0)),
        Vector((0.0, 0.0, 1.0)),
        accelerations,
        [],
        frames,
        0,
        settings,
        source,
        1.85,
        0.16,
        0.25,
        1.0,
        8.0,
    )
    if max_axis(response, recoil_axis) <= 0.001:
        raise RuntimeError("Body Spring did not follow the recoil force direction for a -X barrel impulse.")
    swing_values = [
        exporter_module._physics_body_crank_swing(index / 32.0, 1.85, 0.16)
        for index in range(1, 33)
    ]
    swing_signs = []
    for value in swing_values:
        if abs(value) <= 0.025:
            continue
        sign = 1 if value > 0.0 else -1
        if not swing_signs or swing_signs[-1] != sign:
            swing_signs.append(sign)
    if min(swing_values[:9]) >= -0.08 or max(swing_values[8:20]) <= 0.08 or min(swing_values[18:29]) >= -0.03:
        raise RuntimeError("Body Spring crank swing should lift, dip, and rebound.")
    if max(0, len(swing_signs) - 1) < 3:
        raise RuntimeError("Body Spring crank swing should include an extra small rebound cycle.")
    if max(abs(swing_values[index + 1] - 2.0 * swing_values[index] + swing_values[index - 1]) for index in range(1, len(swing_values) - 1)) > 0.38:
        raise RuntimeError("Body Spring crank swing curve is too sharp for smooth playback.")

    rest_spine = [Vector((0.0, 0.0, index * 0.25)) for index in range(9)]
    antenna_frames = exporter_module._physics_simulate_antenna_spine(
        rest_spine,
        Vector((0.0, 0.0, 1.0)),
        Vector((1.0, 0.0, 0.0)),
        Vector((0.0, 1.0, 0.0)),
        0.25,
        1,
        28,
        26,
        10,
        0,
        4.8,
        0.18,
        0.0,
        0.75,
        28.0,
        "ANTENNA_WHIP",
        body,
        1,
    )
    tip_motion = [
        (antenna_frames[frame][-1] - rest_spine[-1]).dot(Vector((1.0, 0.0, 0.0)))
        for frame in sorted(antenna_frames)
    ]
    if min(tip_motion[:18]) >= -0.01:
        raise RuntimeError("Antenna Whip free tip should lag opposite the recoil/root acceleration direction.")

    parent = bpy.data.objects.new("RotatedSolverParent", None)
    bpy.context.collection.objects.link(parent)
    parent.rotation_euler[2] = 1.57079632679
    body.parent = parent
    rotated_axis = parent.matrix_world.to_3x3() @ Vector((-1.0, 0.0, 0.0))
    body["goh_physics_solver_space"] = "PARENT_LOCAL"
    rotated_accelerations = [rotated_axis * 90.0 if index < 4 else Vector((0.0, 0.0, 0.0)) for index in range(len(frames))]
    rotated_response = exporter_module._physics_inertial_response_samples(
        body,
        "BODY_SPRING",
        rotated_axis,
        parent.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0)),
        Vector((0.0, 0.0, 1.0)),
        rotated_accelerations,
        [],
        frames,
        0,
        settings,
        source,
        1.85,
        0.16,
        0.25,
        1.0,
        8.0,
    )
    if max_axis(rotated_response, rotated_axis) <= 0.001:
        raise RuntimeError("Parent-local solver space did not preserve recoil direction under vehicle rotation.")

    for obj in (body, source, parent):
        bpy.data.objects.remove(obj, do_unlink=True)


def main() -> None:
    addon.register()
    try:
        assert_solver_core()
        assert_bake_sign_policy()
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
