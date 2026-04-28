from __future__ import annotations

import importlib
from pathlib import Path
import sys

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "blender_goh_gem_exporter"


def import_local_addon():
    for module_name in list(sys.modules):
        if module_name == PACKAGE or module_name.startswith(f"{PACKAGE}."):
            del sys.modules[module_name]
    root_string = str(ROOT)
    while root_string in sys.path:
        sys.path.remove(root_string)
    sys.path.insert(0, root_string)
    return importlib.import_module(PACKAGE)


def is_helper(obj: bpy.types.Object) -> bool:
    return bool(obj.get("goh_auto_convex_source") or obj.get("goh_is_volume") or obj.name.lower().endswith("_vol"))


def world_points(obj: bpy.types.Object | None) -> list[Vector]:
    if obj is None or obj.type != "MESH" or obj.data is None:
        return []
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def bounds_volume(points: list[Vector]) -> float:
    if not points:
        return 0.0
    size = Vector((
        max(point.x for point in points) - min(point.x for point in points),
        max(point.y for point in points) - min(point.y for point in points),
        max(point.z for point in points) - min(point.z for point in points),
    ))
    return max(size.x, 1e-6) * max(size.y, 1e-6) * max(size.z, 1e-6)


def barrel_centerline_deviation(obj: bpy.types.Object) -> float:
    if obj.type != "MESH" or obj.data is None or len(obj.data.vertices) < 10:
        return 0.0
    vertices = world_points(obj)
    sides = 0
    for polygon in obj.data.polygons:
        indices = list(polygon.vertices)
        if 0 not in indices or 1 not in indices:
            continue
        candidates = sorted(index for index in indices if index not in {0, 1} and index < len(vertices) - 2)
        if not candidates:
            continue
        candidate = candidates[0]
        if candidate >= 4 and (len(vertices) - 2) % candidate == 0:
            sides = candidate
            break
    if sides <= 0:
        for candidate in (6, 8, 10, 12, 14, 16):
            if (len(vertices) - 2) % candidate == 0:
                sides = candidate
                break
    if sides <= 0:
        return 0.0
    rings = (len(vertices) - 2) // sides
    if rings < 3:
        return 0.0
    centers: list[Vector] = []
    for ring in range(rings):
        center = Vector((0.0, 0.0, 0.0))
        for index in range(ring * sides, (ring + 1) * sides):
            center += vertices[index]
        centers.append(center / sides)
    axis = centers[-1] - centers[0]
    axis_length_sq = axis.length_squared
    if axis_length_sq <= 1e-10:
        return 0.0
    max_deviation = 0.0
    for center in centers:
        t = max(0.0, min(1.0, (center - centers[0]).dot(axis) / axis_length_sq))
        closest = centers[0] + axis * t
        max_deviation = max(max_deviation, (center - closest).length)
    return max_deviation


def main() -> None:
    addon = import_local_addon()
    addon.register()
    try:
        for obj in list(bpy.context.scene.objects):
            if obj.get("goh_auto_convex_source"):
                bpy.data.objects.remove(obj, do_unlink=True)

        sources = [obj for obj in bpy.context.selected_objects if obj.type == "MESH" and not is_helper(obj)]
        if not sources:
            sources = []
            for required_name in ("vehicle#x_root_101", "vehicle#bone_turret_58", "vehicle#gun_barrel_67"):
                obj = bpy.data.objects.get(required_name)
                if obj is not None and obj.type == "MESH" and not is_helper(obj):
                    sources.append(obj)
            for obj in sorted(
                [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not is_helper(obj) and obj not in sources],
                key=lambda item: len(item.data.vertices),
                reverse=True,
            ):
                sources.append(obj)
                if len(sources) >= 6:
                    break
        if not sources:
            raise RuntimeError("No source meshes found in 2.blend scale regression scene.")

        bpy.ops.object.select_all(action="DESELECT")
        for obj in sources:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = sources[0]

        settings = bpy.context.scene.goh_tool_settings
        settings.auto_convex_template = "AUTO"
        settings.auto_convex_fit_mode = "OBB"
        settings.auto_convex_output_topology = "MIXED"
        settings.auto_convex_source_scope = "SELECTED"
        settings.auto_convex_clear_existing = True
        settings.auto_convex_use_evaluated = True
        settings.auto_convex_split_loose_parts = False
        settings.auto_convex_target_faces = 200
        settings.auto_convex_max_hulls = 8
        settings.auto_convex_margin = 0.005
        settings.auto_convex_smooth_iterations = 5
        settings.auto_convex_planarize_quads = True
        settings.auto_convex_planarize_strength = 0.35
        settings.auto_convex_optimize_iterations = 5

        result = bpy.ops.object.goh_create_auto_convex_volume()
        if "FINISHED" not in result:
            raise RuntimeError(f"Auto cage scale regression failed to generate helpers: {result}")

        helpers = [obj for obj in bpy.context.scene.objects if obj.get("goh_auto_convex_source")]
        if not helpers:
            raise RuntimeError("Auto cage scale regression did not create helpers.")

        worst_ratio = 0.0
        topology_checked = 0
        for helper in helpers:
            if any(len(polygon.vertices) not in {3, 4} for polygon in helper.data.polygons):
                raise RuntimeError(f"{helper.name} contains illegal face topology.")
            validation = str(helper.get("goh_auto_quad_validation") or "")
            if "ERROR:" in validation:
                raise RuntimeError(f"{helper.name} failed validation: {validation}")
            source = bpy.data.objects.get(str(helper.get("goh_auto_convex_source") or ""))
            source_volume = max(bounds_volume(world_points(source)), 1e-6)
            helper_volume = bounds_volume(world_points(helper))
            ratio = helper_volume / source_volume
            worst_ratio = max(worst_ratio, ratio)
            if ratio > 20.0:
                raise RuntimeError(f"{helper.name} grew too large: bbox volume ratio {ratio:.3f}.")
            source_name = (source.name if source else helper.name).lower()
            mode = str(helper.get("goh_auto_convex_mode") or "").lower()
            if "x_root" in source_name or ("turret" in source_name and source_volume > 0.02):
                topology_checked += 1
                if "loft" not in mode:
                    raise RuntimeError(f"{helper.name} regressed to {mode}; large hull/turret helpers should use loft topology.")
            if "gun_barrel" in source_name:
                topology_checked += 1
                if "barrel" not in mode:
                    raise RuntimeError(f"{helper.name} regressed to {mode}; long gun barrels should use barrel topology.")
                centerline_deviation = barrel_centerline_deviation(helper)
                if centerline_deviation > 0.05:
                    raise RuntimeError(f"{helper.name} barrel centerline drifted too much: {centerline_deviation:.4f}.")
            print(f"helper={helper.name} source={source_name} mode={mode} ratio={ratio:.3f}")

        if topology_checked <= 0:
            raise RuntimeError("2.blend regression did not exercise any large hull or turret source.")
        print(f"2.blend auto cage scale regression passed; helpers={len(helpers)} worst_ratio={worst_ratio:.3f}")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
