from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for module_name in list(sys.modules):
    if module_name == "blender_goh_gem_exporter" or module_name.startswith("blender_goh_gem_exporter."):
        del sys.modules[module_name]

import blender_goh_gem_exporter as addon  # noqa: E402


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


def _delta_euler_degrees(obj: bpy.types.Object) -> tuple[float, float, float]:
    rest_matrix = _stored_rest_local_matrix(obj)
    if rest_matrix is None:
        raise RuntimeError(f"{obj.name} is missing stored GOH rest matrix.")
    delta = _loc_rot_matrix(rest_matrix).inverted_safe() @ _loc_rot_matrix(obj.matrix_local)
    euler = delta.to_euler("XYZ")
    return tuple(math.degrees(value) for value in (euler.x, euler.y, euler.z))


def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--mdl")
    parser.add_argument("--anm", required=True)
    parser.add_argument("--object", default="body")
    parser.add_argument("--frame", type=int, default=12)
    parser.add_argument("--expect-pitch", choices=("negative", "positive", "any"), default="negative")
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    mdl = Path(args.mdl) if args.mdl else None
    anm = Path(args.anm)
    if mdl is not None and not mdl.exists():
        raise RuntimeError(f"MDL not found: {mdl}")
    if not anm.exists():
        raise RuntimeError(f"ANM not found: {anm}")

    addon.register()
    try:
        if mdl is not None:
            bpy.ops.object.select_all(action="SELECT")
            bpy.ops.object.delete()
            result = bpy.ops.import_scene.goh_model(
                filepath=str(mdl),
                axis_mode="NONE",
                scale_factor=20.0,
                flip_v=True,
                import_materials=False,
                load_textures=False,
                import_volumes=True,
                import_shapes=True,
                import_lod0_only=True,
            )
            if "FINISHED" not in result:
                raise RuntimeError(f"Model import failed for {mdl}: {result}")
        for obj in bpy.data.objects:
            obj.animation_data_clear()
        result = bpy.ops.import_scene.goh_anm(
            filepath=str(anm),
            basis_name="basis",
            frame_start=1,
            axis_mode="AUTO",
            scale_factor=20.0,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Animation import failed for {anm}: {result}")
        bpy.context.scene.frame_set(args.frame)
        obj = bpy.data.objects.get(args.object)
        if obj is None:
            raise RuntimeError(f"Object not found after import: {args.object}")
        pitch_y = _delta_euler_degrees(obj)[1]
        mdl_name = mdl.name if mdl is not None else Path(bpy.data.filepath).name
        print(f"ANM_PITCH {mdl_name} {anm.name} frame={args.frame} object={args.object} pitch_y={pitch_y:.6f}")
        if args.expect_pitch == "negative" and pitch_y >= -0.1:
            raise RuntimeError(f"Expected negative Y pitch, got {pitch_y:.6f}")
        if args.expect_pitch == "positive" and pitch_y <= 0.1:
            raise RuntimeError(f"Expected positive Y pitch, got {pitch_y:.6f}")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
