from __future__ import annotations

from collections import defaultdict
import importlib
from pathlib import Path
import sys

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "blender_goh_gem_exporter"

DEFAULT_MODELS = [
    Path(r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\resource\entity\-vehicle\germany\tank_heavy\tiger1e\tiger1e.mdl"),
    Path(r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\resource\entity\-vehicle\germany\tank_medium\panzer4h\panzer4h.mdl"),
    Path(r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\mods\macecopy\resource\entity\-vehicle\+eng\tank_heavy\conqueror_mk2\conqueror_mk2.mdl"),
    Path(r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\mods\macecopy\resource\entity\-vehicle\+eng\tank_medium\centurion_mk10\centurion_mk10.mdl"),
]


def import_local_addon():
    loaded_addon = sys.modules.get(PACKAGE)
    if loaded_addon is not None and getattr(loaded_addon, "__file__", None):
        try:
            loaded_addon.unregister()
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
    print(f"local_addon={addon_module.__file__}")
    return addon_module


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def category_for(obj: bpy.types.Object) -> str:
    key = " ".join(
        str(value or "").lower()
        for value in (
            obj.name,
            obj.get("goh_volume_name"),
            obj.get("goh_volume_bone"),
        )
    )
    if any(token in key for token in ("gun", "barrel", "cannon", "muzzle")):
        return "gun"
    if any(token in key for token in ("turret", "mantlet", "mantled")):
        return "turret"
    if any(token in key for token in ("track", "wheel", "suspension")):
        return "track"
    if any(token in key for token in ("body", "hull", "root", "x_root", "chassis")):
        return "body"
    return "other"


def is_volume(obj: bpy.types.Object) -> bool:
    if obj.get("goh_is_volume"):
        return True
    if obj.name.lower().endswith("_vol"):
        return True
    return any(collection.name == "GOH_VOLUMES" for collection in obj.users_collection)


def world_vertices(obj: bpy.types.Object) -> list[Vector]:
    if obj.type != "MESH" or obj.data is None:
        return [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def bounds(points: list[Vector]) -> tuple[Vector, Vector, Vector, float]:
    if not points:
        zero = Vector((0.0, 0.0, 0.0))
        return zero, zero.copy(), zero.copy(), 0.0
    min_corner = Vector((
        min(point.x for point in points),
        min(point.y for point in points),
        min(point.z for point in points),
    ))
    max_corner = Vector((
        max(point.x for point in points),
        max(point.y for point in points),
        max(point.z for point in points),
    ))
    size = max_corner - min_corner
    volume = max(size.x, 1e-6) * max(size.y, 1e-6) * max(size.z, 1e-6)
    return min_corner, max_corner, size, volume


def face_stats(obj: bpy.types.Object) -> tuple[int, int, int, int]:
    if obj.type != "MESH" or obj.data is None:
        return 0, 0, 0, 0
    tris = sum(1 for polygon in obj.data.polygons if len(polygon.vertices) == 3)
    quads = sum(1 for polygon in obj.data.polygons if len(polygon.vertices) == 4)
    ngons = sum(1 for polygon in obj.data.polygons if len(polygon.vertices) > 4)
    return len(obj.data.polygons), tris, quads, ngons


def analyze_model(path: Path) -> None:
    if not path.exists():
        print(f"MODEL_MISSING {path}")
        return
    clear_scene()
    result = bpy.ops.import_scene.goh_model(filepath=str(path))
    volumes = sorted(
        [obj for obj in bpy.context.scene.objects if is_volume(obj)],
        key=lambda obj: obj.name.lower(),
    )
    visual_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not is_volume(obj)]
    print(f"MODEL {path}")
    print(f"  import={sorted(result)} visual_meshes={len(visual_meshes)} volumes={len(volumes)}")
    aggregates: dict[str, list[tuple[float, int, Vector, str]]] = defaultdict(list)
    rows: list[tuple[float, str]] = []
    for obj in volumes:
        points = world_vertices(obj)
        _min_corner, _max_corner, size, bbox_volume = bounds(points)
        faces, tris, quads, ngons = face_stats(obj)
        category = category_for(obj)
        kind = str(obj.get("goh_volume_kind") or "polyhedron").lower()
        bone = str(obj.get("goh_volume_bone") or obj.get("goh_volume_name") or "")
        aggregates[category].append((bbox_volume, faces, size, obj.name))
        rows.append((
            bbox_volume,
            f"  VOL cat={category:<6} kind={kind:<10} name={obj.name:<42} bone={bone:<24} "
            f"verts={len(points):>4} faces={faces:>4} tri={tris:>4} quad={quads:>4} ngon={ngons:>3} "
            f"size=({size.x:.3f},{size.y:.3f},{size.z:.3f}) bbox={bbox_volume:.3f}",
        ))
    for _volume, line in sorted(rows, key=lambda item: item[0], reverse=True)[:24]:
        print(line)
    for category, items in sorted(aggregates.items()):
        total_bbox = sum(item[0] for item in items)
        face_counts = sorted(item[1] for item in items)
        largest = max(items, key=lambda item: item[0])
        median_faces = face_counts[len(face_counts) // 2] if face_counts else 0
        print(
            f"  SUMMARY cat={category:<6} count={len(items):>3} total_bbox={total_bbox:.3f} "
            f"median_faces={median_faces} largest={largest[3]} largest_size=({largest[2].x:.3f},{largest[2].y:.3f},{largest[2].z:.3f})"
        )


def main() -> None:
    addon = import_local_addon()
    addon.register()
    try:
        args = sys.argv
        model_args = args[args.index("--") + 1:] if "--" in args else []
        model_paths = [Path(arg) for arg in model_args] if model_args else DEFAULT_MODELS
        for model_path in model_paths:
            analyze_model(model_path)
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
