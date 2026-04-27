from __future__ import annotations

from collections import Counter
import importlib
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "blender_goh_gem_exporter"


def import_local_addon():
    loaded_addon = sys.modules.get(PACKAGE)
    if loaded_addon is not None and getattr(loaded_addon, "__file__", None):
        try:
            loaded_addon.unregister()
            print(f"unregistered_preloaded_addon={loaded_addon.__file__}")
        except Exception as exc:
            print(f"preloaded_addon_unregister_warning={exc}")

    for module_name in list(sys.modules):
        if module_name == PACKAGE or module_name.startswith(f"{PACKAGE}."):
            del sys.modules[module_name]

    root_string = str(ROOT)
    while root_string in sys.path:
        sys.path.remove(root_string)
    sys.path.insert(0, root_string)

    addon_module = importlib.import_module(PACKAGE)
    exporter = importlib.import_module(f"{PACKAGE}.blender_exporter")
    print(f"local_addon={addon_module.__file__}")
    return addon_module, exporter


def is_helper(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH":
        return False
    if obj.get("goh_auto_convex_source") or obj.get("goh_is_volume") or obj.get("Volume"):
        return True
    if obj.name.lower().endswith("_vol"):
        return True
    if obj.get("goh_is_obstacle") or obj.get("goh_is_area"):
        return True
    return any(collection.name in {"GOH_VOLUMES", "GOH_OBSTACLES", "GOH_AREAS"} for collection in obj.users_collection)


def bbox_volume(points) -> float:
    if not points:
        return 0.0
    min_x = min(point.x for point in points)
    min_y = min(point.y for point in points)
    min_z = min(point.z for point in points)
    max_x = max(point.x for point in points)
    max_y = max(point.y for point in points)
    max_z = max(point.z for point in points)
    return max(max_x - min_x, 1e-6) * max(max_y - min_y, 1e-6) * max(max_z - min_z, 1e-6)


def clear_generated() -> int:
    removed = 0
    for obj in list(bpy.context.scene.objects):
        if obj.get("goh_auto_convex_source"):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    return removed


def selected_sources() -> list[bpy.types.Object]:
    sources = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not is_helper(obj)
    ]
    return sorted(sources, key=lambda item: item.name.lower())


def analyze_groups(
    exporter_module,
    sources: list[bpy.types.Object],
    min_vertices: int,
) -> list[tuple[str, str, int, float]]:
    groups: list[tuple[str, str, int, float]] = []
    for obj in sources:
        for group in exporter_module._mesh_world_point_groups(
            bpy.context,
            obj,
            True,
            True,
            min_vertices,
        ):
            groups.append((obj.name, group.label or "whole", group.vertex_count, bbox_volume(group.points)))
    return sorted(groups, key=lambda item: item[3], reverse=True)


def run_config(
    sources: list[bpy.types.Object],
    *,
    max_hulls: int,
    min_vertices: int,
    target_faces: int,
    optimize_iterations: int = 12,
    split_loose_parts: bool = True,
    template: str = "AUTO",
    fit_mode: str = "OBB",
) -> None:
    clear_generated()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in sources:
        obj.select_set(True)
    if sources:
        bpy.context.view_layer.objects.active = sources[0]

    settings = bpy.context.scene.goh_tool_settings
    settings.auto_convex_template = template
    settings.auto_convex_fit_mode = fit_mode
    settings.auto_convex_source_scope = "SELECTED"
    settings.auto_convex_clear_existing = True
    settings.auto_convex_use_evaluated = True
    settings.auto_convex_split_loose_parts = split_loose_parts
    settings.auto_convex_output_topology = "MIXED"
    settings.auto_convex_target_faces = target_faces
    settings.auto_convex_optimize_iterations = optimize_iterations
    settings.auto_convex_max_hulls = max_hulls
    settings.auto_convex_min_part_vertices = min_vertices
    settings.auto_convex_margin = 0.005

    result = bpy.ops.object.goh_create_auto_convex_volume()
    helpers = [
        obj for obj in bpy.context.scene.objects
        if obj.get("goh_auto_convex_source")
    ]
    face_counts = sorted((len(obj.data.polygons) for obj in helpers), reverse=True)
    modes = Counter(str(obj.get("goh_auto_convex_mode") or "") for obj in helpers)
    source_counts = Counter(str(obj.get("goh_auto_convex_source") or "") for obj in helpers)
    quad_helpers = sum(1 for obj in helpers if obj.get("goh_auto_quad_cage"))
    illegal_faces = sum(
        1
        for obj in helpers
        for polygon in obj.data.polygons
        if len(polygon.vertices) not in {3, 4}
    )
    validation_errors = sum(1 for obj in helpers if "ERROR:" in str(obj.get("goh_auto_quad_validation") or ""))
    print(
        f"CONFIG max_hulls={max_hulls} min_vertices={min_vertices} "
        f"target_faces={target_faces} optimize_iterations={optimize_iterations} split_loose_parts={split_loose_parts} "
        f"template={template} fit_mode={fit_mode} result={sorted(result)}"
    )
    print(f"  helpers={len(helpers)} total_faces={sum(face_counts)} max_face={max(face_counts) if face_counts else 0} min_face={min(face_counts) if face_counts else 0}")
    print(f"  cage_helpers={quad_helpers} illegal_faces={illegal_faces} validation_errors={validation_errors}")
    print(f"  modes={dict(sorted(modes.items()))}")
    print(f"  top_sources={source_counts.most_common(10)}")
    print(f"  top_faces={face_counts[:12]}")
    clear_generated()


def main() -> None:
    addon, exporter_module = import_local_addon()
    addon.register()
    try:
        old_helpers = sum(1 for obj in bpy.context.scene.objects if obj.get("goh_auto_convex_source"))
        print(f"SCENE {bpy.data.filepath}")
        print(f"existing_auto_convex_helpers={old_helpers}")
        removed = clear_generated()
        print(f"removed_existing_auto_convex_helpers={removed}")

        sources = selected_sources()
        print(f"source_meshes={len(sources)}")
        for obj in sources[:20]:
            print(f"  source {obj.name} vertices={len(obj.data.vertices)} polygons={len(obj.data.polygons)}")
        if len(sources) > 20:
            print(f"  ... {len(sources) - 20} more source mesh(es)")

        for min_vertices in (5, 20, 50):
            groups = analyze_groups(exporter_module, sources, min_vertices)
            print(f"GROUPS min_vertices={min_vertices} count={len(groups)}")
            for source_name, label, vertex_count, volume in groups[:15]:
                print(f"  group source={source_name} label={label} vertices={vertex_count} bbox_volume={volume:.6f}")

        run_config(sources, max_hulls=10, min_vertices=20, target_faces=96)
        run_config(sources, max_hulls=24, min_vertices=20, target_faces=150)
        run_config(sources, max_hulls=48, min_vertices=50, target_faces=216)
        run_config(sources, max_hulls=24, min_vertices=20, target_faces=216, split_loose_parts=False)
        run_config(sources, max_hulls=24, min_vertices=20, target_faces=216, split_loose_parts=False, fit_mode="RAY")
        run_config(sources, max_hulls=24, min_vertices=20, target_faces=150, split_loose_parts=False, template="LOFT")
        run_config(sources, max_hulls=24, min_vertices=20, target_faces=150, split_loose_parts=False, template="ROUNDED_BOX")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
