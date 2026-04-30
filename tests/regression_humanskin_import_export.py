from __future__ import annotations

import shutil
import sys
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "tests" / "_tmp_humanskin_roundtrip"
SAMPLES = (
    {
        "name": "ger_heer_39_at",
        "source": Path(
            r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\resource\!!!codex learning\entity\humanskin\[germans]\ger_heer_39\ger_heer_39_at.mdl"
        ),
        "min_vertices": 20000,
        "required_groups": ("body", "foot1r", "head", "clavicle_left", "clavicle_right"),
    },
    {
        "name": "us_m41_medic",
        "source": Path(
            r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\resource\!!!codex learning\entity\humanskin\[united_states]\us_m41\us_m41_medic.mdl"
        ),
        "min_vertices": 17000,
        "required_groups": ("body", "foot1r", "head", "clavicle_left", "clavicle_right"),
    },
)


def load_addon():
    for name in list(sys.modules):
        if name == "blender_goh_gem_exporter" or name.startswith("blender_goh_gem_exporter."):
            del sys.modules[name]
    sys.path.insert(0, str(REPO_ROOT))
    import blender_goh_gem_exporter as addon

    addon.register()
    return addon


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in list(bpy.data.collections):
        if not collection.users:
            bpy.data.collections.remove(collection)


def group_weighted_vertices(obj: bpy.types.Object, group_name: str) -> int:
    group = obj.vertex_groups.get(group_name)
    if group is None:
        return 0
    count = 0
    for vertex in obj.data.vertices:
        if any(item.group == group.index and item.weight > 1e-6 for item in vertex.groups):
            count += 1
    return count


def world_bbox(obj: bpy.types.Object) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    coords = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    mins = tuple(min(coord[index] for coord in coords) for index in range(3))
    maxs = tuple(max(coord[index] for coord in coords) for index in range(3))
    return mins, maxs


def assert_humanskin_points_are_soedit_aligned(sample_name: str, skin: bpy.types.Object) -> None:
    bbox_min, bbox_max = world_bbox(skin)
    height = max(1e-6, bbox_max[2] - bbox_min[2])
    upper_z = bbox_min[2] + (height * 0.72)
    mid_z = bbox_min[2] + (height * 0.55)
    foot_z = bbox_min[2] + (height * 0.12)

    for name in ("head", "clavicle_left", "clavicle_right", "hand1l", "hand1r"):
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise RuntimeError(f"{sample_name} import is missing skeleton point {name!r}.")
        if obj.matrix_world.translation.z < upper_z:
            raise RuntimeError(
                f"{sample_name} skeleton point {name!r} is below the SOEdit-aligned upper body zone: "
                f"z={obj.matrix_world.translation.z:.4f}, expected >= {upper_z:.4f}."
            )
        if obj.type == "EMPTY" and obj.empty_display_size > 0.12:
            raise RuntimeError(f"{sample_name} skeleton point {name!r} display size is too large for humanskin editing.")

    for name in ("hand2l", "hand2r"):
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise RuntimeError(f"{sample_name} import is missing skeleton point {name!r}.")
        if obj.matrix_world.translation.z < mid_z:
            raise RuntimeError(
                f"{sample_name} skeleton point {name!r} is below the SOEdit-aligned arm zone: "
                f"z={obj.matrix_world.translation.z:.4f}, expected >= {mid_z:.4f}."
            )

    for name in ("foot3l", "foot3r"):
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise RuntimeError(f"{sample_name} import is missing skeleton point {name!r}.")
        if obj.matrix_world.translation.z > foot_z:
            raise RuntimeError(
                f"{sample_name} skeleton point {name!r} is above the SOEdit-aligned foot zone: "
                f"z={obj.matrix_world.translation.z:.4f}, expected <= {foot_z:.4f}."
            )


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    load_addon()
    from blender_goh_gem_exporter.goh_core import read_mesh

    for sample in SAMPLES:
        source_mdl = sample["source"]
        if not source_mdl.exists():
            raise RuntimeError(f"Missing humanskin sample: {source_mdl}")
        clear_scene()
        result = bpy.ops.import_scene.goh_model(
            filepath=str(source_mdl),
            axis_mode="NONE",
            scale_factor=20.0,
            flip_v=True,
            import_materials=True,
            load_textures=False,
            import_volumes=False,
            import_shapes=False,
            import_lod0_only=True,
            defer_basis_flip=True,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Import failed for {sample['name']}: {result}")

        skin = bpy.data.objects.get("skin")
        if skin is None or skin.type != "MESH":
            raise RuntimeError(f"{sample['name']} import did not create a merged skin mesh.")
        if len(skin.data.vertices) < sample["min_vertices"]:
            raise RuntimeError(
                f"{sample['name']} LOD0 import is incomplete: only {len(skin.data.vertices)} vertices."
            )
        if skin.data.polygons and not all(polygon.use_smooth for polygon in skin.data.polygons):
            raise RuntimeError(f"{sample['name']} import did not keep the merged skin mesh smooth shaded.")
        if not bool(skin.data.get("goh_imported_custom_normals")):
            raise RuntimeError(f"{sample['name']} import did not preserve GOH vertex normals.")
        assert_humanskin_points_are_soedit_aligned(sample["name"], skin)
        for group_name in sample["required_groups"]:
            if skin.vertex_groups.get(group_name) is None:
                raise RuntimeError(f"{sample['name']} import is missing vertex group {group_name!r}.")
        if group_weighted_vertices(skin, "body") <= 0:
            raise RuntimeError(f"{sample['name']} body vertex group has no weighted vertices.")

        out_mdl = OUT_DIR / f"{sample['name']}_probe.mdl"
        export_result = bpy.ops.export_scene.goh_model(
            filepath=str(out_mdl),
            selection_only=False,
            include_hidden=False,
            axis_mode="NONE",
            scale_factor=20.0,
            flip_v=True,
            export_animations=False,
        )
        if "FINISHED" not in export_result:
            raise RuntimeError(f"Export failed for {sample['name']}: {export_result}")

        exported_mesh = read_mesh(out_mdl.parent / "skin.ply")
        if "skin" in exported_mesh.skinned_bones:
            raise RuntimeError(f"{sample['name']} export polluted the skin bone map with the owner node name.")
        for bone_name in sample["required_groups"]:
            if bone_name not in exported_mesh.skinned_bones:
                raise RuntimeError(f"{sample['name']} export is missing skin bone {bone_name!r}.")
        if len(exported_mesh.skinned_bones) < 24:
            raise RuntimeError(
                f"{sample['name']} export did not preserve the full skin bone table: {exported_mesh.skinned_bones}"
            )
        weighted_vertices = sum(1 for vertex in exported_mesh.vertices if vertex.weights or any(vertex.bone_indices))
        if weighted_vertices != len(exported_mesh.vertices):
            raise RuntimeError(
                f"{sample['name']} export lost weights: {weighted_vertices}/{len(exported_mesh.vertices)} vertices weighted."
            )

        print(
            "humanskin regression passed: "
            f"sample={sample['name']} imported_vertices={len(skin.data.vertices)} "
            f"exported_vertices={len(exported_mesh.vertices)} skin_bones={len(exported_mesh.skinned_bones)}"
        )


if __name__ == "__main__":
    main()
