from __future__ import annotations

from collections import Counter
import importlib
import os
from pathlib import Path
import sys

import bpy


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


def is_helper(obj: bpy.types.Object) -> bool:
    if obj.get("goh_is_volume") or obj.get("goh_auto_convex_source"):
        return True
    if obj.name.lower().endswith("_vol"):
        return True
    return any(collection.name in {"GOH_VOLUMES", "GOH_OBSTACLES", "GOH_AREAS"} for collection in obj.users_collection)


def run_model(path: Path) -> None:
    clear_scene()
    result = bpy.ops.import_scene.goh_model(filepath=str(path))
    sources = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not is_helper(obj)]
    sources.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
    bpy.ops.object.select_all(action="DESELECT")
    source_limit = max(1, int(os.environ.get("GOH_PROBE_SOURCE_LIMIT", "8")))
    for obj in sources[:source_limit]:
        obj.select_set(True)
    if sources:
        bpy.context.view_layer.objects.active = sources[0]
    settings = bpy.context.scene.goh_tool_settings
    settings.auto_convex_template = "AUTO"
    settings.auto_convex_fit_mode = "OBB"
    settings.auto_convex_source_scope = "SELECTED"
    settings.auto_convex_clear_existing = True
    settings.auto_convex_use_evaluated = True
    settings.auto_convex_split_loose_parts = False
    settings.auto_convex_min_part_vertices = 20
    settings.auto_convex_output_topology = "MIXED"
    settings.auto_convex_target_faces = max(12, int(os.environ.get("GOH_PROBE_TARGET_FACES", "500")))
    settings.auto_convex_optimize_iterations = max(1, int(os.environ.get("GOH_PROBE_ITERATIONS", "12")))
    settings.auto_convex_max_hulls = max(1, int(os.environ.get("GOH_PROBE_MAX_HULLS", "8")))
    settings.auto_convex_margin = 0.005
    cage_result = bpy.ops.object.goh_create_auto_convex_volume()
    helpers = [obj for obj in bpy.context.scene.objects if obj.get("goh_auto_convex_source")]
    modes = Counter(str(obj.get("goh_auto_convex_mode") or "") for obj in helpers)
    illegal_faces = sum(1 for obj in helpers for polygon in obj.data.polygons if len(polygon.vertices) not in {3, 4})
    validation_errors = sum(1 for obj in helpers if "ERROR:" in str(obj.get("goh_auto_quad_validation") or ""))
    scores = [float(obj.get("goh_auto_convex_score") or 0.0) for obj in helpers]
    iterations = [int(obj.get("goh_auto_convex_iterations") or 0) for obj in helpers]
    print(
        f"MDL_AUTO_QUAD {path.name} import={sorted(result)} cage={sorted(cage_result)} "
        f"sources={len(sources)} helpers={len(helpers)} faces={sum(len(obj.data.polygons) for obj in helpers)} "
        f"illegal_faces={illegal_faces} validation_errors={validation_errors} "
        f"max_face={max((len(obj.data.polygons) for obj in helpers), default=0)} "
        f"avg_score={(sum(scores) / len(scores)) if scores else 0.0:.3f} "
        f"iterations={max(iterations) if iterations else 0} modes={dict(sorted(modes.items()))}"
    )


def main() -> None:
    addon = import_local_addon()
    addon.register()
    try:
        args = sys.argv
        model_args = args[args.index("--") + 1:] if "--" in args else []
        model_paths = [Path(arg) for arg in model_args] if model_args else DEFAULT_MODELS
        for path in model_paths:
            run_model(path)
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
