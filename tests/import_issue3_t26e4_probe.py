from __future__ import annotations

from math import isfinite
from pathlib import Path
import sys

import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
ADDON_PARENT = ROOT
if str(ADDON_PARENT) not in sys.path:
    sys.path.insert(0, str(ADDON_PARENT))

import blender_goh_gem_exporter as addon  # noqa: E402


T26E4_MODEL_CANDIDATES = (
    Path(
        r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\resource\!!!codex learning\entity\-vehicle\usa\tank_heavy\t26e4\t26e4.mdl"
    ),
    Path(
        r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\resource\entity\-vehicle\usa\tank_heavy\t26e4\t26e4.mdl"
    ),
)
T26E4_MODEL = next((path for path in T26E4_MODEL_CANDIDATES if path.exists()), T26E4_MODEL_CANDIDATES[0])


def _assert_finite_matrix(obj: bpy.types.Object) -> None:
    for row in obj.matrix_world:
        for value in row:
            if not isfinite(float(value)):
                raise RuntimeError(f"{obj.name} imported with a non-finite transform value.")


def main() -> None:
    if not T26E4_MODEL.exists():
        print(f"SKIP issue #3 probe: sample model not found: {T26E4_MODEL}")
        return

    addon.register()
    try:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

        result = bpy.ops.import_scene.goh_model(
            filepath=str(T26E4_MODEL),
            axis_mode="NONE",
            scale_factor=20.0,
            flip_v=True,
            import_materials=True,
            load_textures=False,
            import_volumes=True,
            import_shapes=True,
            import_lod0_only=True,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"T26E4 import failed: {result}")

        imported_objects = [
            obj for obj in bpy.data.objects
            if str(obj.get("goh_source_mdl") or "") == str(T26E4_MODEL)
        ]
        if len(imported_objects) < 20:
            raise RuntimeError(f"T26E4 import produced too few tagged objects: {len(imported_objects)}")

        mesh_objects = [obj for obj in imported_objects if obj.type == "MESH" and obj.get("goh_import_ply")]
        if not mesh_objects:
            raise RuntimeError("T26E4 import did not produce visual mesh objects.")

        missing_normals = [
            obj.name for obj in mesh_objects
            if len(obj.data.loops) and not obj.data.get("goh_imported_custom_normals")
        ]
        if missing_normals:
            preview = ", ".join(missing_normals[:8])
            raise RuntimeError(f"T26E4 meshes skipped imported custom normals: {preview}")

        bad_loop_counts = [
            obj.name for obj in mesh_objects
            if obj.data.get("goh_imported_custom_normal_loops") != len(obj.data.loops)
        ]
        if bad_loop_counts:
            preview = ", ".join(bad_loop_counts[:8])
            raise RuntimeError(f"T26E4 custom normal loop counts are inconsistent: {preview}")

        flat_polygons = [
            obj.name for obj in mesh_objects
            if any(not polygon.use_smooth for polygon in obj.data.polygons)
        ]
        if flat_polygons:
            preview = ", ".join(flat_polygons[:8])
            raise RuntimeError(f"T26E4 meshes contain flat polygons after custom normal import: {preview}")

        basis = next((obj for obj in imported_objects if obj.get("goh_bone_name") == "basis"), None)
        if basis is None or not basis.get("goh_deferred_basis_flip"):
            raise RuntimeError("Default T26E4 import did not defer the mirrored basis for game-matching Blender display.")
        if basis.matrix_world.to_3x3().determinant() < 0.0:
            raise RuntimeError("Default T26E4 import still displays a mirrored basis in Blender.")
        rest_values = basis.get("goh_rest_matrix_local")
        if rest_values is None:
            raise RuntimeError("Default T26E4 import did not keep the original GOH basis matrix for export.")
        rest_matrix = Matrix((rest_values[0:4], rest_values[4:8], rest_values[8:12], rest_values[12:16]))
        if rest_matrix.to_3x3().determinant() >= 0.0:
            raise RuntimeError("Default T26E4 import lost the original mirrored GOH basis metadata.")

        for obj in imported_objects:
            _assert_finite_matrix(obj)

        max_dimension = max(max(obj.dimensions) for obj in mesh_objects)
        if max_dimension <= 0.0 or max_dimension > 250.0:
            raise RuntimeError(f"T26E4 visual mesh dimensions look broken after import: {max_dimension:g}")

        issue_names = [obj.name.lower() for obj in imported_objects]
        if not any("gun" in name for name in issue_names):
            raise RuntimeError("T26E4 issue probe did not import any gun-related objects.")
        if not any("turret" in name for name in issue_names):
            raise RuntimeError("T26E4 issue probe did not import any turret-related objects.")

        print(
            f"OK issue #3 T26E4 probe: {len(imported_objects)} objects, "
            f"{len(mesh_objects)} visual meshes with custom split normals."
        )
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
