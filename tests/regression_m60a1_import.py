from __future__ import annotations

import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
ADDON_PARENT = ROOT
if str(ADDON_PARENT) not in sys.path:
    sys.path.insert(0, str(ADDON_PARENT))
for module_name in list(sys.modules):
    if module_name == "blender_goh_gem_exporter" or module_name.startswith("blender_goh_gem_exporter."):
        del sys.modules[module_name]

import blender_goh_gem_exporter as addon  # noqa: E402


M60A1_DIR = Path(
    r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\mods\WTREBUILD\resource\entity\wt_lethe\vehicle\csa\tank\m60a1"
)
M60A1_MODEL = M60A1_DIR / "m60a1.mdl"
ANIMATIONS = ("fire.anm", "fire_left.anm", "fire_right.anm", "fire_back.anm", "open_driver.anm")


def _principled(material: bpy.types.Material):
    if not material.use_nodes or material.node_tree is None:
        return None
    return next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)


def _input_value(node, names: tuple[str, ...], default=None):
    if node is None:
        return default
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None and hasattr(socket, "default_value"):
            return socket.default_value
    return default


def _has_link(node, names: tuple[str, ...]) -> bool:
    if node is None:
        return False
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None and socket.is_linked:
            return True
    return False


def _determinant(obj: bpy.types.Object) -> float:
    return float(obj.matrix_local.to_3x3().determinant())


def _stored_rest_local_matrix(obj: bpy.types.Object | None) -> Matrix | None:
    if obj is None:
        return None
    values = obj.get("goh_rest_matrix_local")
    if values is None:
        return None
    floats = [float(value) for value in values]
    if len(floats) != 16:
        return None
    return Matrix(
        (
            floats[0:4],
            floats[4:8],
            floats[8:12],
            floats[12:16],
        )
    )


def _loc_rot_matrix(matrix: Matrix) -> Matrix:
    loc, rot, _scale = matrix.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def _object_animation_delta_euler(obj: bpy.types.Object) -> tuple[float, float, float]:
    rest_matrix = _stored_rest_local_matrix(obj)
    if rest_matrix is None:
        raise RuntimeError(f"{obj.name} is missing stored GOH rest matrix.")
    delta = _loc_rot_matrix(rest_matrix).inverted_safe() @ _loc_rot_matrix(obj.matrix_local)
    euler = delta.to_euler("XYZ")
    return tuple(math.degrees(value) for value in (euler.x, euler.y, euler.z))


def _assert_fire_body_pitch_matches_game_direction() -> None:
    body = bpy.data.objects.get("body")
    if body is None:
        raise RuntimeError("m60a1 import did not create body object.")
    bpy.context.scene.frame_set(12)
    _pitch_x, pitch_y, _pitch_z = _object_animation_delta_euler(body)
    if pitch_y >= -0.1:
        raise RuntimeError(
            f"fire.anm frame 12 body pitch is {pitch_y:.3f} degrees; expected negative pitch for SOEdit/game direction."
        )


def _assert_materials_look_goh_like() -> None:
    materials = [mat for mat in bpy.data.materials if mat.get("goh_import_mtl")]
    if not materials:
        raise RuntimeError("m60a1 import did not create GOH materials.")

    bump_materials = [mat for mat in materials if mat.get("goh_material_kind") == "bump"]
    if len(bump_materials) < 4:
        raise RuntimeError(f"Expected several bump materials, got {len(bump_materials)}.")

    bad: list[str] = []
    for mat in bump_materials:
        principled = _principled(mat)
        if principled is None:
            bad.append(f"{mat.name}: no Principled BSDF")
            continue
        metallic = float(_input_value(principled, ("Metallic",), 0.0))
        roughness = float(_input_value(principled, ("Roughness",), 0.0))
        specular = float(_input_value(principled, ("Specular IOR Level", "Specular"), 0.0))
        if metallic > 0.05:
            bad.append(f"{mat.name}: metallic {metallic:.3f}")
        if roughness < 0.72:
            bad.append(f"{mat.name}: roughness {roughness:.3f}")
        if specular > 0.75 and not _has_link(principled, ("Specular IOR Level", "Specular")):
            bad.append(f"{mat.name}: specular {specular:.3f}")
        if not _has_link(principled, ("Base Color",)):
            bad.append(f"{mat.name}: base color not texture-linked")
        if mat.get("goh_bump") and not _has_link(principled, ("Normal",)):
            bad.append(f"{mat.name}: normal map not linked")
        if mat.get("goh_specular") and mat.get("goh_specular_role") != "specular":
            bad.append(f"{mat.name}: missing imported specular role metadata")
        if mat.get("goh_specular") and not _has_link(principled, ("Specular IOR Level", "Specular")):
            bad.append(f"{mat.name}: specular texture not linked")
    if bad:
        raise RuntimeError("GOH material regression failed: " + "; ".join(bad[:12]))


def _assert_animation_does_not_break_mirrored_basis() -> None:
    basis = bpy.data.objects.get("basis") or bpy.data.objects.get("Basis")
    if basis is None:
        raise RuntimeError("m60a1 import did not create basis object.")
    rest_values = basis.get("goh_rest_matrix_local")
    if rest_values is None:
        raise RuntimeError("basis object is missing stored GOH rest matrix.")
    rest_det = _determinant(basis)
    if rest_det >= -1e-5:
        raise RuntimeError(f"basis rest determinant is not mirrored before animation: {rest_det:g}")

    baseline_positions = {}
    for name in ("body", "turret", "gun_rot", "gun"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            baseline_positions[name] = obj.matrix_world.translation.copy()

    for anm_name in ANIMATIONS:
        anm_path = M60A1_DIR / anm_name
        if not anm_path.exists():
            continue
        result = bpy.ops.import_scene.goh_anm(
            filepath=str(anm_path),
            basis_name="basis",
            frame_start=1,
            axis_mode="AUTO",
            scale_factor=20.0,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Animation import failed for {anm_name}: {result}")
        if anm_name == "fire.anm":
            _assert_fire_body_pitch_matches_game_direction()
        bpy.context.scene.frame_set(1)
        for name, baseline in baseline_positions.items():
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            distance = (obj.matrix_world.translation - baseline).length
            if distance > 0.08:
                raise RuntimeError(
                    f"{anm_name} frame 1 moved {name} away from its imported rest pose by {distance:.4f}; "
                    "this usually means root handedness was flipped during ANM import."
                )
        for frame in (1, 10, 50, 100):
            bpy.context.scene.frame_set(frame)
            det = _determinant(basis)
            if det >= -1e-5:
                raise RuntimeError(f"{anm_name} frame {frame} changed mirrored basis determinant to {det:g}.")


def _assert_imported_geometry() -> None:
    imported = [obj for obj in bpy.data.objects if str(obj.get("goh_source_mdl") or "") == str(M60A1_MODEL)]
    if len(imported) < 40:
        raise RuntimeError(f"m60a1 import produced too few tagged objects: {len(imported)}")
    meshes = [obj for obj in imported if obj.type == "MESH" and obj.get("goh_import_ply")]
    if len(meshes) < 20:
        raise RuntimeError(f"m60a1 import produced too few visual meshes: {len(meshes)}")
    missing_normals = [
        obj.name
        for obj in meshes
        if len(obj.data.loops) and not obj.data.get("goh_imported_custom_normals")
    ]
    if missing_normals:
        raise RuntimeError("Meshes skipped custom normals: " + ", ".join(missing_normals[:8]))


def main() -> None:
    if not M60A1_MODEL.exists():
        print(f"SKIP m60a1 regression: {M60A1_MODEL} not found")
        return
    addon.register()
    try:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()
        result = bpy.ops.import_scene.goh_model(
            filepath=str(M60A1_MODEL),
            axis_mode="NONE",
            scale_factor=20.0,
            flip_v=True,
            import_materials=True,
            load_textures=True,
            import_volumes=True,
            import_shapes=True,
            import_lod0_only=True,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"m60a1 import failed: {result}")
        _assert_imported_geometry()
        _assert_materials_look_goh_like()
        _assert_animation_does_not_break_mirrored_basis()
        print("OK m60a1 import/material/animation regression")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
