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


def main() -> None:
    addon = import_local_addon()
    addon.register()
    try:
        for obj in list(bpy.context.scene.objects):
            if obj.get("goh_auto_convex_source"):
                bpy.data.objects.remove(obj, do_unlink=True)

        sources = [obj for obj in bpy.context.selected_objects if obj.type == "MESH" and not is_helper(obj)]
        if not sources:
            sources = sorted(
                [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not is_helper(obj)],
                key=lambda item: len(item.data.vertices),
                reverse=True,
            )[:6]
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
        settings.auto_convex_target_faces = 500
        settings.auto_convex_max_hulls = 8
        settings.auto_convex_margin = 0.005
        settings.auto_convex_optimize_iterations = 3

        result = bpy.ops.object.goh_create_auto_convex_volume()
        if "FINISHED" not in result:
            raise RuntimeError(f"Auto cage scale regression failed to generate helpers: {result}")

        helpers = [obj for obj in bpy.context.scene.objects if obj.get("goh_auto_convex_source")]
        if not helpers:
            raise RuntimeError("Auto cage scale regression did not create helpers.")

        worst_ratio = 0.0
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

        print(f"2.blend auto cage scale regression passed; helpers={len(helpers)} worst_ratio={worst_ratio:.3f}")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
