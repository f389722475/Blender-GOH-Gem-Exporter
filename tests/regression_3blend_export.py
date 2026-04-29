from __future__ import annotations

from pathlib import Path
import shutil
import struct
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


BLEND_PATH = ROOT / "tests" / "3.blend"
OUTPUT_ROOT = ROOT / "runtime_test_output" / "regression_3blend_export"


def _load_probe_file() -> None:
    current = Path(bpy.data.filepath) if bpy.data.filepath else None
    if current is None or current.resolve() != BLEND_PATH.resolve():
        if not BLEND_PATH.exists():
            raise RuntimeError(f"Missing regression probe file: {BLEND_PATH}")
        bpy.ops.wm.open_mainfile(filepath=str(BLEND_PATH))


def _export_probe(output_dir: Path, *, anm_format: str) -> list[Path]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = bpy.ops.export_scene.goh_model(
        filepath=str(output_dir / "t26e4_probe.mdl"),
        selection_only=False,
        include_hidden=True,
        axis_mode="NONE",
        scale_factor=20.0,
        flip_v=True,
        export_animations=True,
        anm_format=anm_format,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"3.blend export failed in {anm_format}: {result}")
    animation_paths = sorted(output_dir.glob("*.anm"))
    if not animation_paths:
        raise RuntimeError(f"3.blend export wrote no ANM files in {anm_format}.")
    return animation_paths


def _animation_with_bones(paths: list[Path], *bone_names: str):
    for path in paths:
        animation = read_animation(path)
        if all(name in animation.bone_names for name in bone_names):
            return path, animation
    raise RuntimeError(f"No exported ANM contains required bones: {', '.join(bone_names)}")


def _body_local_pitch_at_frame(frame: int) -> float:
    body = next(
        (
            obj for obj in bpy.data.objects
            if obj.type == "MESH" and str(obj.get("goh_bone_name") or "").strip().lower() == "body"
        ),
        None,
    )
    if body is None:
        raise RuntimeError("3.blend probe has no body mesh with goh_bone_name=body.")
    bpy.context.scene.frame_set(frame, subframe=0.0)
    bpy.context.view_layer.update()
    parent_matrix = body.parent.matrix_world if body.parent is not None else Matrix.Identity(4)
    local_matrix = parent_matrix.inverted_safe() @ body.matrix_world
    _loc, rot, _scale = local_matrix.decompose()
    return float(rot.to_matrix()[0][2])


def _rotation_variation(animation, bone_name: str) -> float:
    base = animation.frames[0][bone_name].matrix
    maximum = 0.0
    for frame in animation.frames[1:]:
        matrix = frame[bone_name].matrix
        for row in range(3):
            for col in range(3):
                maximum = max(maximum, abs(matrix[row][col] - base[row][col]))
    return maximum


def _mesh_bbox_max_abs(animation, bone_name: str) -> float:
    maximum = 0.0
    for frame in animation.mesh_frames:
        mesh_state = frame.get(bone_name)
        if mesh_state is None:
            continue
        if mesh_state.bbox is not None:
            for corner in mesh_state.bbox:
                for value in corner:
                    maximum = max(maximum, abs(float(value)))
            continue
        for vertex_index in range(mesh_state.vertex_count):
            offset = vertex_index * mesh_state.vertex_stride
            if offset + 12 > len(mesh_state.vertex_data):
                break
            x, y, z = struct.unpack_from("<3f", mesh_state.vertex_data, offset)
            maximum = max(maximum, abs(float(x)), abs(float(y)), abs(float(z)))
    return maximum


def main() -> None:
    _load_probe_file()
    addon.register()
    try:
        auto_paths = _export_probe(OUTPUT_ROOT / "auto", anm_format="AUTO")
        auto_path, auto_animation = _animation_with_bones(auto_paths, "body", "antenna")
        if any(frame for animation_path in auto_paths for frame in read_animation(animation_path).mesh_frames):
            raise RuntimeError("AUTO export wrote MESH animation chunks, which prevents SOEdit from opening fire.anm.")
        if len(auto_animation.frames) <= 12:
            raise RuntimeError(f"{auto_path.name} does not contain enough frames for the frame-12 handedness probe.")

        blender_pitch = _body_local_pitch_at_frame(12)
        exported_pitch = float(auto_animation.frames[11]["body"].matrix[0][2])
        if blender_pitch < -0.01 and exported_pitch <= 0.01:
            raise RuntimeError(
                f"Mirrored-basis ANM export kept Blender pitch sign: Blender {blender_pitch:.5f}, ANM {exported_pitch:.5f}."
            )
        if blender_pitch > 0.01 and exported_pitch >= -0.01:
            raise RuntimeError(
                f"Mirrored-basis ANM export kept Blender pitch sign: Blender {blender_pitch:.5f}, ANM {exported_pitch:.5f}."
            )
        antenna_rotation = _rotation_variation(auto_animation, "antenna")
        if antenna_rotation <= 0.001:
            raise RuntimeError("AUTO export did not convert antenna shape-key whip into a SOEdit-safe bone fallback.")

        frm2_paths = _export_probe(OUTPUT_ROOT / "frm2", anm_format="FRM2")
        _frm2_path, frm2_animation = _animation_with_bones(frm2_paths, "antenna")
        if not any("antenna" in frame for frame in frm2_animation.mesh_frames):
            raise RuntimeError("Explicit FRM2 export did not write antenna mesh-animation chunks.")
        bbox_limit = _mesh_bbox_max_abs(frm2_animation, "antenna")
        if bbox_limit > 30.0:
            raise RuntimeError(f"Explicit FRM2 antenna mesh animation is stretched: bbox limit {bbox_limit:.3f}.")

        print(
            "regression 3.blend export passed: "
            f"auto={auto_path.name}, blender_pitch={blender_pitch:.5f}, anm_pitch={exported_pitch:.5f}, "
            f"antenna_rotation={antenna_rotation:.5f}, frm2_bbox={bbox_limit:.3f}"
        )
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
