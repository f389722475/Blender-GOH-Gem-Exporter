from __future__ import annotations

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
from blender_goh_gem_exporter.goh_core import read_animation  # noqa: E402


T26E4_DIR_CANDIDATES = (
    Path(
        r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\resource\!!!codex learning\entity\-vehicle\usa\tank_heavy\t26e4"
    ),
    Path(r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\resource\entity\-vehicle\usa\tank_heavy\t26e4"),
)
T26E4_DIR = next((path for path in T26E4_DIR_CANDIDATES if (path / "t26e4.mdl").exists()), T26E4_DIR_CANDIDATES[0])
T26E4_MODEL = T26E4_DIR / "t26e4.mdl"
T26E4_FIRE = T26E4_DIR / "fire.anm"


def _stored_rest_local_matrix(obj: bpy.types.Object | None) -> Matrix | None:
    if obj is None:
        return None
    values = obj.get("goh_rest_matrix_local")
    if values is None:
        return None
    floats = [float(value) for value in values]
    if len(floats) != 16:
        return None
    return Matrix((floats[0:4], floats[4:8], floats[8:12], floats[12:16]))


def _loc_rot_matrix(matrix: Matrix) -> Matrix:
    loc, rot, _scale = matrix.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def _display_delta_pitch_component(obj: bpy.types.Object) -> float:
    rest_matrix = _stored_rest_local_matrix(obj)
    if rest_matrix is None:
        raise RuntimeError(f"{obj.name} is missing stored GOH rest matrix.")
    delta = _loc_rot_matrix(rest_matrix).inverted_safe() @ _loc_rot_matrix(obj.matrix_local)
    return float(delta.to_3x3()[0][2])


def _raw_body_pitch_probe() -> tuple[int, float]:
    animation = read_animation(T26E4_FIRE)
    best_frame = 0
    best_pitch = 0.0
    for index, frame in enumerate(animation.frames, start=1):
        state = frame.get("body")
        if state is None:
            continue
        pitch = float(state.matrix[0][2])
        if abs(pitch) > abs(best_pitch):
            best_frame = index
            best_pitch = pitch
    if best_frame <= 0 or abs(best_pitch) <= 1e-4:
        raise RuntimeError("Official T26E4 fire.anm has no usable body pitch probe.")
    return best_frame, best_pitch


def _find_bone_object(name: str) -> bpy.types.Object:
    lowered = name.lower()
    obj = next(
        (
            item
            for item in bpy.data.objects
            if str(item.get("goh_bone_name") or item.name).strip().lower() == lowered
        ),
        None,
    )
    if obj is None:
        raise RuntimeError(f"T26E4 import did not create {name!r}.")
    return obj


def _assert_default_basis_display_space() -> bpy.types.Object:
    basis = _find_bone_object("basis")
    rest_matrix = _stored_rest_local_matrix(basis)
    if rest_matrix is None:
        raise RuntimeError("Default T26E4 import did not store original GOH basis metadata.")
    if rest_matrix.to_3x3().determinant() >= -1e-5:
        raise RuntimeError("Default T26E4 import lost the original mirrored GOH basis metadata.")
    display_det = float(basis.matrix_world.to_3x3().determinant())
    if display_det <= 1e-5 or not basis.get("goh_deferred_basis_flip"):
        raise RuntimeError(
            f"Default T26E4 import still displays mirrored basis space in Blender: determinant {display_det:g}."
        )
    return basis


def main() -> None:
    if not T26E4_MODEL.exists() or not T26E4_FIRE.exists():
        print(f"SKIP T26E4 import display-space regression: sample files not found under {T26E4_DIR}")
        return

    raw_frame, raw_pitch = _raw_body_pitch_probe()

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
            raise RuntimeError(f"T26E4 model import failed: {result}")

        basis = _assert_default_basis_display_space()
        tracked_positions = {
            name: _find_bone_object(name).matrix_world.translation.copy()
            for name in ("body", "turret", "gun")
        }

        result = bpy.ops.import_scene.goh_anm(
            filepath=str(T26E4_FIRE),
            basis_name="basis",
            frame_start=1,
            axis_mode="AUTO",
            scale_factor=20.0,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"T26E4 fire.anm import failed: {result}")

        bpy.context.scene.frame_set(1, subframe=0.0)
        bpy.context.view_layer.update()
        for name, baseline in tracked_positions.items():
            obj = _find_bone_object(name)
            distance = (obj.matrix_world.translation - baseline).length
            if distance > 0.08:
                raise RuntimeError(
                    f"T26E4 fire.anm frame 1 moved {name} away from imported rest pose by {distance:.4f}."
                )

        bpy.context.scene.frame_set(raw_frame, subframe=0.0)
        bpy.context.view_layer.update()
        display_pitch = _display_delta_pitch_component(_find_bone_object("body"))
        if raw_pitch * display_pitch >= 0.0 or abs(display_pitch) <= 1e-4:
            raise RuntimeError(
                "T26E4 fire.anm body pitch stayed in raw GOH mirrored space after import: "
                f"frame {raw_frame}, raw={raw_pitch:.6f}, blender={display_pitch:.6f}."
            )
        if float(basis.matrix_world.to_3x3().determinant()) <= 1e-5:
            raise RuntimeError("T26E4 fire.anm changed the default basis display space back to mirrored.")

        print(
            "OK T26E4 import display-space regression: "
            f"frame={raw_frame}, raw_pitch={raw_pitch:.6f}, blender_pitch={display_pitch:.6f}"
        )
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
