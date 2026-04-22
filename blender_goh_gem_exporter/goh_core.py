from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import math
import struct
from typing import BinaryIO, Iterable


class ExportError(RuntimeError):
    pass


MESH_FLAG_TWO_SIDED = 0x01
MESH_FLAG_LIGHT = 0x04
MESH_FLAG_SKINNED = 0x10
MESH_FLAG_BUMP = 0x100
MESH_FLAG_SPECULAR = 0x200
MESH_FLAG_MATERIAL = 0x400
MESH_FLAG_SUBSKIN = 0x800
MESH_FLAG_LIGHTMAP = 0x4000

D3DFVF_XYZ = 0x002
D3DFVF_NORMAL = 0x010
D3DFVF_TEX1 = 0x100
D3DFVF_LASTBETA_UBYTE4 = 0x1000

SIDE_BOTTOM = 1
SIDE_TOP = 2
SIDE_FRONT = 3
SIDE_REAR = 4
SIDE_LEFT = 5
SIDE_RIGHT = 6


@dataclass
class SequenceDef:
    name: str
    file_name: str | None = None
    speed: float = 1.0
    smooth: float = 0.0
    resume: bool = False
    autostart: bool = False
    store: bool = False


@dataclass
class MaterialDef:
    file_name: str
    shader: str = "simple"
    diffuse_texture: str | None = None
    bump_texture: str | None = None
    specular_texture: str | None = None
    lightmap_texture: str | None = None
    mask_texture: str | None = None
    height_texture: str | None = None
    diffuse1_texture: str | None = None
    simple_texture: str | None = None
    envmap_texture: str | None = None
    bump_volume_texture: str | None = None
    color_rgba: tuple[int, int, int, int] = (150, 150, 150, 25)
    blend: str = "none"
    two_sided: bool = False
    gloss_scale: float | None = None
    alpharef: float | None = None
    specular_intensity: float | None = None
    period: float | None = None
    envamount: float | None = None
    parallax_scale: float | None = None
    amount: float | None = None
    tile: bool = False
    glow: bool = False
    no_light: bool = False
    full_specular: bool = False
    emits_heat: bool = False
    translucency: bool = False
    alpha_to_coverage: bool = False
    no_outlines: bool = False
    fake_reflection: bool = False
    texture_options: dict[str, tuple[str, ...]] = field(default_factory=dict)
    extra_lines: list[str] = field(default_factory=list)

    @property
    def needs_bump(self) -> bool:
        return self.shader == "bump" or bool(self.bump_texture or self.specular_texture)


@dataclass
class MeshSection:
    material_file: str
    triangle_indices: list[tuple[int, int, int]] = field(default_factory=list)
    two_sided: bool = False
    specular_rgba: tuple[int, int, int, int] = (150, 150, 150, 25)
    subskin_bones: tuple[int, ...] = ()


@dataclass(frozen=True)
class MeshVertex:
    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    uv: tuple[float, float]
    tangent: tuple[float, float, float] = (1.0, 0.0, 0.0)
    tangent_sign: float = 1.0
    weights: tuple[float, ...] = ()
    bone_indices: tuple[int, int, int, int] = (0, 0, 0, 0)


@dataclass
class MeshData:
    file_name: str
    vertices: list[MeshVertex]
    sections: list[MeshSection]
    skinned_bones: list[str] = field(default_factory=list)
    vflags: int = 0x0007


@dataclass
class MeshViewDef:
    file_name: str
    flags: tuple[str, ...] = ()
    layer: int | str | None = None


@dataclass
class BoneNode:
    name: str
    matrix: tuple[tuple[float, float, float], ...] | None = None
    transform_block: str | None = None
    bone_type: str | None = None
    parameters: str | None = None
    limits: tuple[float, ...] = ()
    speed: float | None = None
    speed_uses_speed2: bool = False
    visibility: int | None = None
    terminator: bool = False
    color_rgba: tuple[int, int, int, int] | None = None
    volume_view: str | None = None
    volume_flags: tuple[str, ...] = ()
    layer: int | str | None = None
    mesh_views: list[MeshViewDef] = field(default_factory=list)
    lod_off: bool = False
    sequences: list[SequenceDef] = field(default_factory=list)
    children: list["BoneNode"] = field(default_factory=list)


@dataclass
class VolumeData:
    file_name: str | None
    entry_name: str
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    triangles: list[tuple[int, int, int]] = field(default_factory=list)
    side_codes: list[int] = field(default_factory=list)
    bone_name: str | None = None
    component: str | None = None
    tags: str | None = None
    density: float | None = None
    thickness: dict[str, tuple[float, ...]] = field(default_factory=dict)
    matrix: tuple[tuple[float, float, float], ...] | None = None
    transform_block: str | None = None
    volume_kind: str = "polyhedron"
    box_size: tuple[float, float, float] | None = None
    sphere_radius: float | None = None
    cylinder_radius: float | None = None
    cylinder_length: float | None = None


@dataclass
class Shape2DEntry:
    entry_name: str
    block_type: str
    shape_type: str = "Obb2"
    center: tuple[float, float] | None = None
    extent: tuple[float, float] | None = None
    axis: tuple[float, float] | None = None
    radius: float | None = None
    vertices: list[tuple[float, float]] = field(default_factory=list)
    rotate: bool = False
    tags: str | None = None


@dataclass
class ModelData:
    file_name: str
    basis: BoneNode
    sequences: list[SequenceDef] = field(default_factory=list)
    obstacles: list[Shape2DEntry] = field(default_factory=list)
    areas: list[Shape2DEntry] = field(default_factory=list)
    volumes: list[VolumeData] = field(default_factory=list)
    exporter_name: str = "Codex GOH Blender Exporter"
    source_name: str | None = None
    metadata_comments: list[str] = field(default_factory=list)


@dataclass
class AnimationState:
    matrix: tuple[tuple[float, float, float], ...]
    visible: int = 1


@dataclass
class MeshAnimationState:
    first_vertex: int
    vertex_count: int
    vertex_stride: int
    vertex_data: bytes
    bbox: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    reserved: tuple[float, float] = (0.0, 0.0)


@dataclass
class AnimationFile:
    file_name: str
    bone_names: list[str]
    frames: list[dict[str, AnimationState]]
    mesh_frames: list[dict[str, MeshAnimationState]] = field(default_factory=list)
    format: str = "auto"
    version: int | None = None


@dataclass
class ExportBundle:
    model: ModelData
    meshes: dict[str, MeshData]
    materials: dict[str, MaterialDef]
    animations: dict[str, AnimationFile] = field(default_factory=dict)


def write_export_bundle(output_dir: str | Path, bundle: ExportBundle) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    bundle.model.volumes = _expanded_volumes(bundle.model.volumes)

    written: dict[str, Path] = {}

    for material in bundle.materials.values():
        path = output_path / material.file_name
        write_material(path, material)
        written[str(path)] = path

    for mesh in bundle.meshes.values():
        path = output_path / mesh.file_name
        write_mesh(path, mesh, bundle.materials)
        written[str(path)] = path

    for volume in bundle.model.volumes:
        if volume.volume_kind != "polyhedron":
            continue
        if not volume.file_name:
            raise ExportError(f"Polyhedron volume {volume.entry_name} is missing a .vol file name.")
        path = output_path / volume.file_name
        write_volume(path, volume)
        written[str(path)] = path

    for animation in bundle.animations.values():
        path = output_path / animation.file_name
        write_animation(path, animation)
        written[str(path)] = path

    mdl_path = output_path / bundle.model.file_name
    write_model(mdl_path, bundle.model)
    written[str(mdl_path)] = mdl_path
    return written


def write_material(path: str | Path, material: MaterialDef) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    shader = material.shader if material.shader in {"simple", "bump", "envmap", "multiply"} else "simple"
    blend = (material.blend or "none").strip().lower()
    if blend == "alpha":
        blend = "blend"

    lines = [f"{{material {shader}"]
    if material.diffuse_texture:
        lines.append(_material_texture_line("diffuse", material.diffuse_texture, material.texture_options.get("diffuse", ())))
    if shader == "bump" and material.bump_texture:
        lines.append(_material_texture_line("bump", material.bump_texture, material.texture_options.get("bump", ())))
    if material.specular_texture:
        lines.append(_material_texture_line("specular", material.specular_texture, material.texture_options.get("specular", ())))
    if material.lightmap_texture:
        lines.append(_material_texture_line("lightmap", material.lightmap_texture, material.texture_options.get("lightmap", ())))
    if material.mask_texture:
        lines.append(_material_texture_line("mask", material.mask_texture, material.texture_options.get("mask", ())))
    if material.height_texture:
        lines.append(_material_texture_line("height", material.height_texture, material.texture_options.get("height", ())))
    if material.diffuse1_texture:
        lines.append(_material_texture_line("diffuse1", material.diffuse1_texture, material.texture_options.get("diffuse1", ())))
    if material.simple_texture:
        lines.append(_material_texture_line("simple", material.simple_texture, material.texture_options.get("simple", ())))
    if material.envmap_texture:
        lines.append(_material_texture_line("envmap", material.envmap_texture, material.texture_options.get("envmap", ())))
    if material.bump_volume_texture:
        lines.append(_material_texture_line("bumpVolume", material.bump_volume_texture, material.texture_options.get("bumpVolume", ())))

    r, g, b, a = [max(0, min(255, int(v))) for v in material.color_rgba]
    lines.append(f'\t{{color "{r} {g} {b} {a}"}}')
    lines.append(f"\t{{blend {blend}}}")
    for key, value in (
        ("gloss_scale", material.gloss_scale),
        ("alpharef", material.alpharef),
        ("specular_intensity", material.specular_intensity),
        ("period", material.period),
        ("envamount", material.envamount),
        ("parallax_scale", material.parallax_scale),
        ("amount", material.amount),
    ):
        if value is not None:
            lines.append(f"\t{{{key} {_fmt(value)}}}")
    for key, enabled in (
        ("tile", material.tile),
        ("glow", material.glow),
        ("nolight", material.no_light),
        ("full_specular", material.full_specular),
        ("emitsheat", material.emits_heat),
        ("translucency", material.translucency),
        ("alphatocoverage", material.alpha_to_coverage),
        ("no_outlines", material.no_outlines),
        ("FakeReflection", material.fake_reflection),
    ):
        if enabled:
            lines.append(f"\t{{{key}}}")
    for extra in material.extra_lines:
        text = extra.strip()
        if text:
            lines.append(f"\t{{{text}}}")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _material_texture_line(token: str, texture: str, options: tuple[str, ...]) -> str:
    line = f'\t{{{token} "{texture}"'
    for option in options:
        text = option.strip()
        if not text:
            continue
        line += f" {text}" if text.startswith("{") else f" {{{text}}}"
    line += "}"
    return line


def write_mesh(path: str | Path, mesh: MeshData, materials: dict[str, MaterialDef]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not mesh.vertices:
        raise ExportError(f"Mesh {mesh.file_name} has no vertices.")
    if not mesh.sections:
        raise ExportError(f"Mesh {mesh.file_name} has no material sections.")

    skinned = bool(mesh.skinned_bones)
    max_influences = _mesh_max_influences(mesh) if skinned else 0
    if skinned and max_influences < 1:
        max_influences = 1
    if skinned and max_influences > 5:
        raise ExportError(f"Mesh {mesh.file_name} uses more than 5 skin influences.")

    explicit_weights = max(0, max_influences - 1)
    uses_bump = any(materials[section.material_file].needs_bump for section in mesh.sections if section.material_file in materials)
    vsize = 12 + 12 + 8
    if skinned:
        vsize += (explicit_weights * 4) + 4
    if uses_bump:
        vsize += 16

    fvf = D3DFVF_XYZ | D3DFVF_NORMAL | D3DFVF_TEX1
    if skinned:
        fvf |= D3DFVF_LASTBETA_UBYTE4 | _d3dfvf_skin_token(max_influences)

    all_triangles: list[tuple[int, int, int]] = []
    encoded_sections: list[tuple[MeshSection, int, int, int]] = []
    for section in mesh.sections:
        if section.material_file not in materials:
            raise ExportError(f"Mesh {mesh.file_name} references missing material {section.material_file}.")
        section_flags = MESH_FLAG_LIGHT | MESH_FLAG_MATERIAL
        if materials[section.material_file].needs_bump:
            section_flags |= MESH_FLAG_BUMP | MESH_FLAG_SPECULAR
        if materials[section.material_file].lightmap_texture:
            section_flags |= MESH_FLAG_LIGHTMAP
        if section.two_sided or materials[section.material_file].two_sided:
            section_flags |= MESH_FLAG_TWO_SIDED
        if skinned:
            section_flags |= MESH_FLAG_SKINNED
            if section.subskin_bones:
                section_flags |= MESH_FLAG_SUBSKIN
        first_face = len(all_triangles)
        face_count = len(section.triangle_indices)
        all_triangles.extend(section.triangle_indices)
        encoded_sections.append((section, first_face, face_count, section_flags))

    if not all_triangles:
        raise ExportError(f"Mesh {mesh.file_name} has no triangles.")

    bbox_min, bbox_max = _bbox_from_vertices(mesh.vertices)
    index_type = "INDX" if len(mesh.vertices) <= 0xFFFF else "IND4"

    with path.open("wb") as fp:
        fp.write(b"EPLY")
        fp.write(b"BNDS")
        fp.write(struct.pack("<6f", *(bbox_min + bbox_max)))

        if skinned:
            fp.write(b"SKIN")
            fp.write(struct.pack("<I", len(mesh.skinned_bones)))
            for bone_name in mesh.skinned_bones:
                encoded = bone_name.encode("utf-8")
                if len(encoded) > 255:
                    raise ExportError(f"Bone name {bone_name!r} is too long for {mesh.file_name}.")
                fp.write(struct.pack("<B", len(encoded)))
                fp.write(encoded)

        for section, first_face, face_count, section_flags in encoded_sections:
            fp.write(b"MESH")
            fp.write(struct.pack("<4I", fvf, first_face, face_count, section_flags))
            if section_flags & MESH_FLAG_SPECULAR:
                fp.write(struct.pack("<I", rgba_to_uint(section.specular_rgba)))
            material_name = section.material_file.encode("utf-8")
            if len(material_name) > 255:
                raise ExportError(f"Material file name {section.material_file!r} is too long for {mesh.file_name}.")
            fp.write(struct.pack("<B", len(material_name)))
            fp.write(material_name)
            if section_flags & MESH_FLAG_SUBSKIN:
                fp.write(struct.pack("<B", len(section.subskin_bones)))
                fp.write(bytes(section.subskin_bones))

        fp.write(b"VERT")
        fp.write(struct.pack("<IHH", len(mesh.vertices), vsize, mesh.vflags))
        for vertex in mesh.vertices:
            fp.write(struct.pack("<3f", *vertex.position))
            if skinned:
                for weight in vertex.weights[:explicit_weights]:
                    fp.write(struct.pack("<f", weight))
                fp.write(bytes(vertex.bone_indices[:4]))
            fp.write(struct.pack("<3f", *vertex.normal))
            fp.write(struct.pack("<2f", *vertex.uv))
            if uses_bump:
                fp.write(struct.pack("<3f", *vertex.tangent))
                fp.write(struct.pack("<f", vertex.tangent_sign))

        fp.write(index_type.encode("ascii"))
        fp.write(struct.pack("<I", len(all_triangles) * 3))
        if index_type == "INDX":
            for triangle in all_triangles:
                fp.write(struct.pack("<3H", *triangle))
        else:
            for triangle in all_triangles:
                fp.write(struct.pack("<3I", *triangle))


def write_volume(path: str | Path, volume: VolumeData) -> None:
    if volume.volume_kind != "polyhedron":
        raise ExportError(f"write_volume() only supports polyhedron volumes, got {volume.volume_kind!r}.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(volume.vertices) > 0xFFFF:
        raise ExportError(f"Volume {volume.file_name or volume.entry_name} exceeds 65535 vertices.")
    if not volume.vertices or not volume.triangles:
        raise ExportError(f"Volume {volume.file_name or volume.entry_name} is empty.")

    side_codes = volume.side_codes or classify_triangle_sides(volume.vertices, volume.triangles)
    if len(side_codes) != len(volume.triangles):
        raise ExportError(f"Volume {volume.file_name or volume.entry_name} side count does not match triangle count.")

    with path.open("wb") as fp:
        fp.write(b"EVLM")
        fp.write(b"VERT")
        fp.write(struct.pack("<I", len(volume.vertices)))
        for vertex in volume.vertices:
            fp.write(struct.pack("<3f", *vertex))
        fp.write(b"INDX")
        fp.write(struct.pack("<I", len(volume.triangles) * 3))
        for triangle in volume.triangles:
            fp.write(struct.pack("<3H", *triangle))
        fp.write(b"SIDE")
        fp.write(struct.pack("<I", len(side_codes)))
        fp.write(bytes(side_codes))


def write_model(path: str | Path, model: ModelData) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        fp.write(f";Exported by: {model.exporter_name}\n")
        fp.write(f";Date:        {now.strftime('%a %b %d %H:%M:%S %Y')}\n")
        if model.source_name:
            fp.write(f";File:        {model.source_name}\n")
        for comment in model.metadata_comments:
            text = str(comment).strip()
            if text:
                fp.write(f";{text}\n")
        fp.write("{Skeleton\n")
        if model.sequences:
            _write_sequences(fp, 1, model.sequences)
        _write_bone(fp, 1, model.basis)
        fp.write("}\n")
        for obstacle in model.obstacles:
            _write_shape2d_entry(fp, 0, obstacle)
        for area in model.areas:
            _write_shape2d_entry(fp, 0, area)
        for volume in model.volumes:
            _write_volume_entry(fp, 0, volume)


def write_animation(path: str | Path, animation: AnimationFile) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not animation.frames:
        raise ExportError(f"Animation {animation.file_name} has no frames.")
    if not animation.bone_names:
        raise ExportError(f"Animation {animation.file_name} has no bones.")

    frame_count = len(animation.frames)
    bone_index_map = {bone_name: index for index, bone_name in enumerate(animation.bone_names)}
    mesh_frames = _normalized_mesh_frames(animation)
    anm_format = (animation.format or "auto").strip().lower()
    if anm_format not in {"auto", "legacy", "frm2"}:
        raise ExportError(f"Animation {animation.file_name} uses unknown format {animation.format!r}.")

    if anm_format == "auto":
        if len(animation.bone_names) <= 0xFF and frame_count <= 0xFFFF:
            anm_format = "frm2"
        else:
            anm_format = "legacy"

    with path.open("wb") as fp:
        fp.write(b"EANM")
        if anm_format == "legacy":
            fp.write(struct.pack("<I", 0x00040000))
        elif anm_format == "frm2":
            if len(animation.bone_names) > 0xFF:
                raise ExportError(f"Animation {animation.file_name} has more than 255 bones and cannot use FRM2.")
            if frame_count > 0xFFFF:
                raise ExportError(f"Animation {animation.file_name} has more than 65535 frames and cannot use FRM2.")
            fp.write(struct.pack("<I", 0x00060000))
        else:  # pragma: no cover - guarded above
            raise ExportError(f"Animation {animation.file_name} uses unsupported format {anm_format!r}.")
        fp.write(b"FRMS")
        fp.write(struct.pack("<I", frame_count))
        fp.write(b"BMAP")
        fp.write(struct.pack("<I", len(animation.bone_names)))
        for bone_name in animation.bone_names:
            encoded = bone_name.encode("utf-8")
            fp.write(struct.pack("<I", len(encoded)))
            fp.write(encoded)

        if anm_format == "frm2":
            _write_animation_frm2(fp, animation, bone_index_map, mesh_frames)
            return

        _write_animation_legacy(fp, animation, bone_index_map, mesh_frames)


def _write_animation_legacy(
    fp: BinaryIO,
    animation: AnimationFile,
    bone_index_map: dict[str, int],
    mesh_frames: list[dict[str, MeshAnimationState]],
) -> None:
    fp.write(b"FRMN")
    fp.write(struct.pack("<I", 0))
    first_frame = animation.frames[0]
    first_mesh_frame = mesh_frames[0]
    for bone_name in animation.bone_names:
        state = first_frame.get(bone_name)
        if state is None:
            raise ExportError(
                f"Animation {animation.file_name} first frame is missing state for bone {bone_name!r}."
            )
        fp.write(b"BONE")
        fp.write(struct.pack("<I", bone_index_map[bone_name]))
        fp.write(b"MATR")
        fp.write(struct.pack("<12f", *[value for row in state.matrix for value in row]))
        fp.write(b"VISI")
        fp.write(struct.pack("<I", 1 if state.visible else 0))
        mesh_state = first_mesh_frame.get(bone_name)
        if mesh_state is not None:
            for mesh_part, part_bbox in _split_mesh_animation_state(mesh_state, include_bbox=True):
                fp.write(b"MESH")
                _write_mesh_animation_chunk(fp, mesh_part, include_bbox=part_bbox)

    previous_frame = first_frame
    previous_mesh_frame = first_mesh_frame
    for frame_index in range(1, len(animation.frames)):
        current_frame = animation.frames[frame_index]
        current_mesh_frame = mesh_frames[frame_index]
        changed_bones: list[tuple[str, bool, bool, MeshAnimationState | None, bool]] = []
        for bone_name in animation.bone_names:
            previous_state = previous_frame.get(bone_name)
            current_state = current_frame.get(bone_name)
            if previous_state is None or current_state is None:
                raise ExportError(
                    f"Animation {animation.file_name} frame {frame_index} is missing state for bone {bone_name!r}."
                )
            previous_mesh = previous_mesh_frame.get(bone_name)
            current_mesh = current_mesh_frame.get(bone_name)
            matrix_changed = not _matrices_close(previous_state.matrix, current_state.matrix)
            visibility_changed = previous_state.visible != current_state.visible
            mesh_changed = not _mesh_animation_states_equal(previous_mesh, current_mesh)
            include_bbox = (
                current_mesh is not None
                and (
                    previous_mesh is None
                    or current_mesh.first_vertex != previous_mesh.first_vertex
                    or current_mesh.vertex_count != previous_mesh.vertex_count
                    or current_mesh.vertex_stride != previous_mesh.vertex_stride
                )
            )
            if matrix_changed or visibility_changed or mesh_changed:
                changed_bones.append((bone_name, matrix_changed, visibility_changed, current_mesh, include_bbox))

        if changed_bones:
            fp.write(b"FRMN")
            fp.write(struct.pack("<I", frame_index))
            for bone_name, matrix_changed, visibility_changed, mesh_state, include_bbox in changed_bones:
                state = current_frame[bone_name]
                fp.write(b"BONE")
                fp.write(struct.pack("<I", bone_index_map[bone_name]))
                if matrix_changed:
                    fp.write(b"MATR")
                    fp.write(struct.pack("<12f", *[value for row in state.matrix for value in row]))
                if visibility_changed:
                    fp.write(b"VISI")
                    fp.write(struct.pack("<I", 1 if state.visible else 0))
                if mesh_state is not None:
                    for mesh_part, part_bbox in _split_mesh_animation_state(mesh_state, include_bbox=include_bbox):
                        fp.write(b"MESH")
                        _write_mesh_animation_chunk(fp, mesh_part, include_bbox=part_bbox)

        previous_frame = current_frame
        previous_mesh_frame = current_mesh_frame


def _write_animation_frm2(
    fp: BinaryIO,
    animation: AnimationFile,
    bone_index_map: dict[str, int],
    mesh_frames: list[dict[str, MeshAnimationState]],
) -> None:
    previous_frame: dict[str, AnimationState] | None = None
    previous_mesh_frame: dict[str, MeshAnimationState] | None = None
    for frame_index, current_frame in enumerate(animation.frames):
        current_mesh_data = mesh_frames[frame_index]
        frame_chunks: list[
            tuple[
                int,
                int,
                tuple[float, float, float] | None,
                tuple[float, float, float] | None,
                MeshAnimationState | None,
                bool,
            ]
        ] = []
        for bone_name in animation.bone_names:
            state = current_frame.get(bone_name)
            if state is None:
                raise ExportError(
                    f"Animation {animation.file_name} frame {frame_index} is missing state for bone {bone_name!r}."
                )
            previous_state = previous_frame.get(bone_name) if previous_frame is not None else None
            previous_mesh = previous_mesh_frame.get(bone_name) if previous_mesh_frame is not None else None
            current_mesh = current_mesh_data.get(bone_name)
            if previous_state is None:
                position_changed = True
                rotation_changed = True
                visibility_changed = True
            else:
                position_changed = not _vectors_close(state.matrix[3], previous_state.matrix[3])
                rotation_changed = not _rotation_rows_close(state.matrix, previous_state.matrix)
                visibility_changed = state.visible != previous_state.visible
            mesh_changed = not _mesh_animation_states_equal(previous_mesh, current_mesh)
            include_bbox = (
                current_mesh is not None
                and (
                    previous_mesh is None
                    or current_mesh.first_vertex != previous_mesh.first_vertex
                    or current_mesh.vertex_count != previous_mesh.vertex_count
                    or current_mesh.vertex_stride != previous_mesh.vertex_stride
                )
            )

            chunk_flags = 0
            position = None
            rotation = None
            if position_changed:
                chunk_flags |= 0x0001
                position = tuple(float(value) for value in state.matrix[3])
            if rotation_changed:
                chunk_flags |= 0x0002
                rotation = _rotation_rows_to_quaternion_xyz(state.matrix)
            if visibility_changed:
                chunk_flags |= 0x0008 if state.visible else 0x0010
            if mesh_changed and current_mesh is not None:
                chunk_flags |= 0x0020

            if chunk_flags:
                if current_mesh is not None and (chunk_flags & 0x0020):
                    mesh_parts = _split_mesh_animation_state(current_mesh, include_bbox=include_bbox)
                    for part_index, (mesh_part, part_bbox) in enumerate(mesh_parts):
                        frame_chunks.append(
                            (
                                bone_index_map[bone_name],
                                chunk_flags if part_index == 0 else 0x0020,
                                position if part_index == 0 else None,
                                rotation if part_index == 0 else None,
                                mesh_part,
                                part_bbox,
                            )
                        )
                else:
                    frame_chunks.append((bone_index_map[bone_name], chunk_flags, position, rotation, current_mesh, include_bbox))

        if frame_chunks:
            for chunk_offset in range(0, len(frame_chunks), 0xFF):
                batch = frame_chunks[chunk_offset : chunk_offset + 0xFF]
                fp.write(b"FRM2")
                fp.write(struct.pack("<H", frame_index))
                fp.write(struct.pack("<B", len(batch)))
                for bone_index, chunk_flags, position, rotation, mesh_state, include_bbox in batch:
                    fp.write(struct.pack("<B", bone_index))
                    fp.write(struct.pack("<H", chunk_flags))
                    if position is not None:
                        fp.write(struct.pack("<3f", *position))
                    if rotation is not None:
                        fp.write(struct.pack("<3f", *rotation))
                    if chunk_flags & 0x0020:
                        assert mesh_state is not None
                        _write_mesh_animation_chunk(fp, mesh_state, include_bbox=include_bbox)
        previous_frame = current_frame
        previous_mesh_frame = current_mesh_data


def _write_mesh_animation_chunk(
    fp: BinaryIO,
    mesh_state: MeshAnimationState,
    *,
    include_bbox: bool,
) -> None:
    expected_size = mesh_state.vertex_count * mesh_state.vertex_stride
    if len(mesh_state.vertex_data) != expected_size:
        raise ExportError(
            f"Mesh animation chunk for first_vertex={mesh_state.first_vertex} does not match its stride/count."
        )
    if mesh_state.vertex_count > 0xFFFF:
        raise ExportError("Mesh animation chunk range still exceeds 65535 vertices after splitting.")
    if include_bbox and mesh_state.bbox is None:
        raise ExportError("Mesh animation chunk requested a bounding box but none was provided.")
    counter = 8 + len(mesh_state.vertex_data) + 8 + (24 if include_bbox else 0)
    fp.write(struct.pack("<I", counter))
    fp.write(struct.pack("<I", mesh_state.first_vertex))
    fp.write(struct.pack("<H", mesh_state.vertex_count))
    fp.write(struct.pack("<H", 1 if include_bbox else 0))
    fp.write(mesh_state.vertex_data)
    if include_bbox:
        bbox_min, bbox_max = mesh_state.bbox or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        fp.write(struct.pack("<6f", *(bbox_min + bbox_max)))
    fp.write(struct.pack("<2f", *mesh_state.reserved))


def encode_mesh_vertex_stream(mesh: MeshData, materials: dict[str, MaterialDef]) -> tuple[bytes, int]:
    skinned = bool(mesh.skinned_bones)
    max_influences = _mesh_max_influences(mesh) if skinned else 0
    if skinned and max_influences < 1:
        max_influences = 1
    if skinned and max_influences > 5:
        raise ExportError(f"Mesh {mesh.file_name} uses more than 5 skin influences.")
    explicit_weights = max(0, max_influences - 1)
    uses_bump = any(materials[section.material_file].needs_bump for section in mesh.sections if section.material_file in materials)
    vsize = 12 + 12 + 8
    if skinned:
        vsize += (explicit_weights * 4) + 4
    if uses_bump:
        vsize += 16
    encoded = bytearray()
    for vertex in mesh.vertices:
        encoded.extend(struct.pack("<3f", *vertex.position))
        if skinned:
            for weight in vertex.weights[:explicit_weights]:
                encoded.extend(struct.pack("<f", weight))
            encoded.extend(bytes(vertex.bone_indices[:4]))
        encoded.extend(struct.pack("<3f", *vertex.normal))
        encoded.extend(struct.pack("<2f", *vertex.uv))
        if uses_bump:
            encoded.extend(struct.pack("<3f", *vertex.tangent))
            encoded.extend(struct.pack("<f", vertex.tangent_sign))
    return bytes(encoded), vsize


def read_animation(path: str | Path) -> AnimationFile:
    path = Path(path)
    with path.open("rb") as fp:
        if _read_exact(fp, 4) != b"EANM":
            raise ExportError(f"{path} is not a GEM animation file.")
        version = struct.unpack("<I", _read_exact(fp, 4))[0]
        if version not in {0x00030000, 0x00040000, 0x00050000, 0x00060000, 0x00060001}:
            raise ExportError(f"{path} uses unsupported ANM version 0x{version:08x}.")
        if _read_exact(fp, 4) != b"FRMS":
            raise ExportError(f"{path} is missing the FRMS tag.")
        frame_count = struct.unpack("<I", _read_exact(fp, 4))[0]
        if _read_exact(fp, 4) != b"BMAP":
            raise ExportError(f"{path} is missing the BMAP tag.")
        bone_count = struct.unpack("<I", _read_exact(fp, 4))[0]
        bone_names: list[str] = []
        for _ in range(bone_count):
            name_len = struct.unpack("<I", _read_exact(fp, 4))[0]
            bone_names.append(_read_exact(fp, name_len).decode("utf-8", errors="replace"))

        raw_frames: list[dict[str, AnimationState]] = [{} for _ in range(frame_count)]
        raw_mesh_frames: list[dict[str, MeshAnimationState]] = [{} for _ in range(frame_count)]
        if version in {0x00060000, 0x00060001}:
            _read_animation_frm2(fp, bone_names, raw_frames, raw_mesh_frames)
        else:
            _read_animation_legacy(fp, bone_names, raw_frames, raw_mesh_frames)

    frames, mesh_frames = _finalize_animation_frames(raw_frames, raw_mesh_frames, bone_names)
    return AnimationFile(
        file_name=path.name,
        bone_names=bone_names,
        frames=frames,
        mesh_frames=mesh_frames,
        format="frm2" if version in {0x00060000, 0x00060001} else "legacy",
        version=version,
    )


def _read_animation_legacy(
    fp: BinaryIO,
    bone_names: list[str],
    frames: list[dict[str, AnimationState]],
    mesh_frames: list[dict[str, MeshAnimationState]],
) -> None:
    current_frame = 0
    current_bone_index: int | None = None
    last_states: dict[str, AnimationState] = {}
    while True:
        tag = fp.read(4)
        if not tag:
            return
        if len(tag) != 4:
            raise ExportError("Unexpected end of file while reading a legacy ANM tag.")
        if tag == b"FRMN":
            current_frame = struct.unpack("<I", _read_exact(fp, 4))[0]
            current_bone_index = None
        elif tag == b"BONE":
            current_bone_index = struct.unpack("<I", _read_exact(fp, 4))[0]
        elif tag == b"MATR":
            if current_bone_index is None:
                raise ExportError("Encountered MATR without a preceding BONE tag.")
            matrix_values = struct.unpack("<12f", _read_exact(fp, 48))
            matrix = tuple(tuple(matrix_values[row * 3 : (row + 1) * 3]) for row in range(4))
            bone_name = bone_names[current_bone_index]
            previous = frames[current_frame].get(bone_name) or last_states.get(bone_name)
            state = AnimationState(
                matrix=matrix,
                visible=previous.visible if previous is not None else 1,
            )
            frames[current_frame][bone_name] = state
            last_states[bone_name] = state
        elif tag == b"VISI":
            if current_bone_index is None:
                raise ExportError("Encountered VISI without a preceding BONE tag.")
            visible = struct.unpack("<I", _read_exact(fp, 4))[0]
            bone_name = bone_names[current_bone_index]
            previous = frames[current_frame].get(bone_name) or last_states.get(bone_name)
            state = AnimationState(
                matrix=previous.matrix if previous is not None else _identity_matrix34(),
                visible=1 if visible else 0,
            )
            frames[current_frame][bone_name] = state
            last_states[bone_name] = state
        elif tag == b"MESH":
            if current_bone_index is None:
                raise ExportError("Encountered MESH without a preceding BONE tag.")
            bone_name = bone_names[current_bone_index]
            incoming = _read_mesh_animation_chunk(fp)
            mesh_frames[current_frame][bone_name] = _merge_mesh_animation_state(
                mesh_frames[current_frame].get(bone_name),
                incoming,
            )
        else:
            raise ExportError(f"Encountered unsupported legacy ANM tag {tag!r}.")


def _read_animation_frm2(
    fp: BinaryIO,
    bone_names: list[str],
    frames: list[dict[str, AnimationState]],
    mesh_frames: list[dict[str, MeshAnimationState]],
) -> None:
    last_states: dict[str, AnimationState] = {}
    while True:
        tag = fp.read(4)
        if not tag:
            return
        if len(tag) != 4:
            raise ExportError("Unexpected end of file while reading an FRM2 tag.")
        if tag != b"FRM2":
            raise ExportError(f"Encountered unsupported FRM2 tag {tag!r}.")
        frame_index = struct.unpack("<H", _read_exact(fp, 2))[0]
        chunk_count = struct.unpack("<B", _read_exact(fp, 1))[0]
        for _ in range(chunk_count):
            bone_index = struct.unpack("<B", _read_exact(fp, 1))[0]
            chunk_flags = struct.unpack("<H", _read_exact(fp, 2))[0]
            bone_name = bone_names[bone_index]
            previous = last_states.get(bone_name)
            position = previous.matrix[3] if previous is not None else (0.0, 0.0, 0.0)
            rotation_matrix = previous.matrix[:3] if previous is not None else _identity_matrix34()[:3]
            if chunk_flags & 0x0001:
                position = struct.unpack("<3f", _read_exact(fp, 12))
            if chunk_flags & 0x0002:
                rotation_matrix = _rotation_rows_from_quaternion_xyz(struct.unpack("<3f", _read_exact(fp, 12)))
            visible = previous.visible if previous is not None else 1
            if chunk_flags & 0x0010:
                visible = 0
            elif chunk_flags & 0x0008:
                visible = 1
            matrix = (
                tuple(rotation_matrix[0]),
                tuple(rotation_matrix[1]),
                tuple(rotation_matrix[2]),
                tuple(position),
            )
            if chunk_flags & 0x0001 or chunk_flags & 0x0002 or chunk_flags & 0x0018:
                state = AnimationState(matrix=matrix, visible=visible)
                frames[frame_index][bone_name] = state
                last_states[bone_name] = state
            if chunk_flags & 0x0020:
                incoming = _read_mesh_animation_chunk(fp)
                mesh_frames[frame_index][bone_name] = _merge_mesh_animation_state(
                    mesh_frames[frame_index].get(bone_name),
                    incoming,
                )


def _read_mesh_animation_chunk(fp: BinaryIO) -> MeshAnimationState:
    counter = struct.unpack("<I", _read_exact(fp, 4))[0]
    first_vertex = struct.unpack("<I", _read_exact(fp, 4))[0]
    vertex_count = struct.unpack("<H", _read_exact(fp, 2))[0]
    has_bbox = struct.unpack("<H", _read_exact(fp, 2))[0]
    raw_size = counter - 16 - (24 if has_bbox else 0)
    if raw_size < 0:
        raise ExportError("Encountered an invalid mesh animation chunk size.")
    vertex_data = _read_exact(fp, raw_size)
    bbox = None
    if has_bbox:
        bbox_values = struct.unpack("<6f", _read_exact(fp, 24))
        bbox = (
            tuple(bbox_values[:3]),
            tuple(bbox_values[3:]),
        )
    reserved = struct.unpack("<2f", _read_exact(fp, 8))
    vertex_stride = 0 if vertex_count == 0 else raw_size // vertex_count
    if vertex_count > 0 and vertex_stride * vertex_count != raw_size:
        raise ExportError("Encountered a mesh animation chunk with a non-integer vertex stride.")
    return MeshAnimationState(
        first_vertex=first_vertex,
        vertex_count=vertex_count,
        vertex_stride=vertex_stride,
        vertex_data=vertex_data,
        bbox=bbox,
        reserved=reserved,
    )


def _finalize_animation_frames(
    raw_frames: list[dict[str, AnimationState]],
    raw_mesh_frames: list[dict[str, MeshAnimationState]],
    bone_names: list[str],
) -> tuple[list[dict[str, AnimationState]], list[dict[str, MeshAnimationState]]]:
    frames: list[dict[str, AnimationState]] = []
    mesh_frames: list[dict[str, MeshAnimationState]] = []
    previous_frame: dict[str, AnimationState] = {}
    previous_mesh_frame: dict[str, MeshAnimationState] = {}
    for frame_index, frame in enumerate(raw_frames):
        effective_frame: dict[str, AnimationState] = {}
        for bone_name in bone_names:
            state = frame.get(bone_name)
            if state is not None:
                effective_frame[bone_name] = AnimationState(
                    matrix=tuple(tuple(row) for row in state.matrix),
                    visible=1 if state.visible else 0,
                )
            elif bone_name in previous_frame:
                previous = previous_frame[bone_name]
                effective_frame[bone_name] = AnimationState(
                    matrix=tuple(tuple(row) for row in previous.matrix),
                    visible=previous.visible,
                )
            elif frame_index == 0:
                effective_frame[bone_name] = AnimationState(matrix=_identity_matrix34(), visible=1)
            else:
                raise ExportError(f"Animation frame {frame_index} is missing initial state for bone {bone_name!r}.")
        frames.append(effective_frame)
        previous_frame = effective_frame

        effective_mesh_frame: dict[str, MeshAnimationState] = {}
        for bone_name in bone_names:
            mesh_state = raw_mesh_frames[frame_index].get(bone_name)
            if mesh_state is not None:
                effective_mesh_frame[bone_name] = mesh_state
            elif bone_name in previous_mesh_frame:
                effective_mesh_frame[bone_name] = previous_mesh_frame[bone_name]
        mesh_frames.append(effective_mesh_frame)
        previous_mesh_frame = effective_mesh_frame
    return frames, mesh_frames


def _split_mesh_animation_state(
    mesh_state: MeshAnimationState,
    *,
    include_bbox: bool,
    max_vertices: int = 0xFFFF,
) -> list[tuple[MeshAnimationState, bool]]:
    if mesh_state.vertex_count <= max_vertices:
        return [(mesh_state, include_bbox)]
    if mesh_state.vertex_stride <= 0:
        raise ExportError("Mesh animation chunk uses an invalid vertex stride.")

    parts: list[tuple[MeshAnimationState, bool]] = []
    for start in range(0, mesh_state.vertex_count, max_vertices):
        count = min(max_vertices, mesh_state.vertex_count - start)
        byte_start = start * mesh_state.vertex_stride
        byte_end = byte_start + (count * mesh_state.vertex_stride)
        parts.append(
            (
                MeshAnimationState(
                    first_vertex=mesh_state.first_vertex + start,
                    vertex_count=count,
                    vertex_stride=mesh_state.vertex_stride,
                    vertex_data=mesh_state.vertex_data[byte_start:byte_end],
                    bbox=mesh_state.bbox if start == 0 and include_bbox else None,
                    reserved=mesh_state.reserved,
                ),
                include_bbox and start == 0,
            )
        )
    return parts


def _merge_mesh_animation_state(
    existing: MeshAnimationState | None,
    incoming: MeshAnimationState,
) -> MeshAnimationState:
    if existing is None:
        return incoming
    if existing.vertex_stride != incoming.vertex_stride:
        raise ExportError("Encountered mesh animation chunks with mixed vertex strides for the same bone/frame.")
    if existing.vertex_stride <= 0:
        return incoming

    first_vertex = min(existing.first_vertex, incoming.first_vertex)
    end_vertex = max(
        existing.first_vertex + existing.vertex_count,
        incoming.first_vertex + incoming.vertex_count,
    )
    vertex_count = end_vertex - first_vertex
    merged = bytearray(vertex_count * existing.vertex_stride)

    existing_offset = (existing.first_vertex - first_vertex) * existing.vertex_stride
    merged[existing_offset : existing_offset + len(existing.vertex_data)] = existing.vertex_data
    incoming_offset = (incoming.first_vertex - first_vertex) * incoming.vertex_stride
    merged[incoming_offset : incoming_offset + len(incoming.vertex_data)] = incoming.vertex_data

    bbox = existing.bbox
    if incoming.bbox is not None:
        if bbox is None:
            bbox = incoming.bbox
        else:
            bbox = (
                tuple(min(bbox[0][axis], incoming.bbox[0][axis]) for axis in range(3)),
                tuple(max(bbox[1][axis], incoming.bbox[1][axis]) for axis in range(3)),
            )

    return MeshAnimationState(
        first_vertex=first_vertex,
        vertex_count=vertex_count,
        vertex_stride=existing.vertex_stride,
        vertex_data=bytes(merged),
        bbox=bbox,
        reserved=incoming.reserved if incoming.reserved != (0.0, 0.0) else existing.reserved,
    )


def _expanded_volumes(volumes: list[VolumeData], max_vertices: int = 0xFFFF) -> list[VolumeData]:
    expanded: list[VolumeData] = []
    for volume in volumes:
        if volume.volume_kind != "polyhedron":
            expanded.append(volume)
            continue
        expanded.extend(_split_volume_data(volume, max_vertices=max_vertices))
    return expanded


def _split_volume_data(volume: VolumeData, *, max_vertices: int) -> list[VolumeData]:
    if volume.volume_kind != "polyhedron":
        return [volume]
    if len(volume.vertices) <= max_vertices:
        return [volume]

    side_codes = volume.side_codes or classify_triangle_sides(volume.vertices, volume.triangles)
    parts: list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[int]]] = []
    vertex_map: dict[int, int] = {}
    current_vertices: list[tuple[float, float, float]] = []
    current_triangles: list[tuple[int, int, int]] = []
    current_sides: list[int] = []

    def flush() -> None:
        nonlocal vertex_map, current_vertices, current_triangles, current_sides
        if not current_triangles:
            return
        parts.append((current_vertices, current_triangles, current_sides))
        vertex_map = {}
        current_vertices = []
        current_triangles = []
        current_sides = []

    for triangle, side_code in zip(volume.triangles, side_codes):
        unique_needed = {index for index in triangle if index not in vertex_map}
        if current_triangles and len(current_vertices) + len(unique_needed) > max_vertices:
            flush()
        remapped: list[int] = []
        for source_index in triangle:
            mapped = vertex_map.get(source_index)
            if mapped is None:
                mapped = len(current_vertices)
                vertex_map[source_index] = mapped
                current_vertices.append(volume.vertices[source_index])
            remapped.append(mapped)
        current_triangles.append((remapped[0], remapped[1], remapped[2]))
        current_sides.append(side_code)
    flush()

    stem = Path(volume.file_name).stem
    suffix = Path(volume.file_name).suffix or ".vol"
    expanded: list[VolumeData] = []
    for part_index, (vertices, triangles, sides) in enumerate(parts, start=1):
        entry_name = volume.entry_name if part_index == 1 else f"{volume.entry_name}_part{part_index}"
        file_name = volume.file_name if part_index == 1 else f"{stem}_part{part_index}{suffix}"
        expanded.append(
            VolumeData(
                file_name=file_name,
                entry_name=entry_name,
                vertices=vertices,
                triangles=triangles,
                side_codes=sides,
                bone_name=volume.bone_name,
                component=volume.component,
                tags=volume.tags,
                density=volume.density,
                thickness=dict(volume.thickness),
                matrix=volume.matrix,
                transform_block=volume.transform_block,
                volume_kind=volume.volume_kind,
                box_size=volume.box_size,
                sphere_radius=volume.sphere_radius,
                cylinder_radius=volume.cylinder_radius,
                cylinder_length=volume.cylinder_length,
            )
        )
    return expanded


def classify_triangle_sides(
    vertices: Iterable[tuple[float, float, float]],
    triangles: Iterable[tuple[int, int, int]],
) -> list[int]:
    vertex_list = list(vertices)
    side_codes: list[int] = []
    for triangle in triangles:
        a = vertex_list[triangle[0]]
        b = vertex_list[triangle[1]]
        c = vertex_list[triangle[2]]
        normal = _normalize(_cross(_sub(b, a), _sub(c, a)))
        nx, ny, nz = normal
        ax, ay, az = abs(nx), abs(ny), abs(nz)
        if ax >= ay and ax >= az:
            side_codes.append(SIDE_FRONT if nx >= 0.0 else SIDE_REAR)
        elif ay >= az:
            side_codes.append(SIDE_LEFT if ny >= 0.0 else SIDE_RIGHT)
        else:
            side_codes.append(SIDE_TOP if nz >= 0.0 else SIDE_BOTTOM)
    return side_codes


def rgba_to_uint(color: tuple[int, int, int, int]) -> int:
    r, g, b, a = [max(0, min(255, int(v))) for v in color]
    return r | (g << 8) | (b << 16) | (a << 24)


def sanitized_file_stem(text: str) -> str:
    result: list[str] = []
    for char in text.strip():
        if char.isascii() and (char.isalnum() or char in {"_", "-", ".", "+"}):
            result.append(char)
        elif char in {" ", "/", "\\", "|", ":"}:
            result.append("_")
        else:
            result.append(f"u{ord(char):04x}")
    sanitized = "".join(result).strip("._")
    return sanitized or "unnamed"


def _write_sequences(fp, indent: int, sequences: Iterable[SequenceDef]) -> None:
    _line(fp, indent, "{Animation")
    for sequence in sequences:
        parts = [f'{{Sequence "{sequence.name}"']
        if sequence.file_name:
            parts.append(f' {{File "{sequence.file_name}"}}')
        if abs(sequence.speed) > 1e-6 and abs(sequence.speed - 1.0) > 1e-6:
            parts.append(f" {{Speed {_fmt(sequence.speed)}}}")
        if abs(sequence.smooth) > 1e-6 and abs(sequence.smooth - 1.0) > 1e-6:
            parts.append(f" {{Smooth {_fmt(sequence.smooth)}}}")
        if sequence.resume:
            parts.append(" {Resume}")
        if sequence.autostart:
            parts.append(" {Autostart}")
        if sequence.store:
            parts.append(" {Store}")
        parts.append("}")
        _line(fp, indent + 1, "".join(parts))
    _line(fp, indent, "}")


def _write_bone(fp, indent: int, bone: BoneNode) -> None:
    header = "{Bone"
    if bone.bone_type:
        header += f" {bone.bone_type}"
    header += f' "{bone.name}"'
    _line(fp, indent, header)

    if bone.parameters:
        _line(fp, indent + 1, f'{{Parameters "{bone.parameters}"}}')
    if bone.sequences:
        _write_sequences(fp, indent + 1, bone.sequences)
    if bone.limits:
        if len(bone.limits) >= 2:
            _line(fp, indent + 1, f"{{Limits {_fmt(bone.limits[0])} {_fmt(bone.limits[1])}}}")
        else:
            _line(fp, indent + 1, f"{{Limits {_fmt(bone.limits[0])}}}")
    if bone.speed is not None and abs(bone.speed) > 1e-6 and abs(bone.speed - 1.0) > 1e-6:
        speed_tag = "Speed2" if bone.speed_uses_speed2 else "Speed"
        _line(fp, indent + 1, f"{{{speed_tag} {_fmt(bone.speed)}}}")
    if bone.terminator:
        _line(fp, indent + 1, "{Terminator}")
    if bone.color_rgba:
        _line(fp, indent + 1, f"{{Color 0x{rgba_to_uint(bone.color_rgba):x}}}")
    if bone.matrix:
        _write_transform(fp, indent + 1, bone.matrix, block_mode=bone.transform_block)
    if bone.visibility is not None:
        _line(fp, indent + 1, f"{{Visibility {int(bone.visibility)}}}")
    mesh_views = list(bone.mesh_views)
    if not mesh_views and bone.volume_view:
        mesh_views.append(
            MeshViewDef(
                file_name=bone.volume_view,
                flags=bone.volume_flags,
                layer=bone.layer,
            )
        )
    if len(mesh_views) > 1 or bone.lod_off:
        _line(fp, indent + 1, "{LODView")
        for mesh_view in mesh_views:
            _write_mesh_view(fp, indent + 2, mesh_view)
        if bone.lod_off:
            _line(fp, indent + 2, "{OFF}")
        _line(fp, indent + 1, "}")
    elif mesh_views:
        _write_mesh_view(fp, indent + 1, mesh_views[0])
    for child in bone.children:
        _write_bone(fp, indent + 1, child)
    _line(fp, indent, "}")


def _write_volume_entry(fp, indent: int, volume: VolumeData) -> None:
    _line(fp, indent, f'{{Volume "{volume.entry_name}"')
    volume_kind = (volume.volume_kind or "polyhedron").lower()
    if volume_kind == "polyhedron":
        if not volume.file_name:
            raise ExportError(f"Polyhedron volume {volume.entry_name} is missing a .vol file name.")
        _line(fp, indent + 1, f'{{Polyhedron "{volume.file_name}"}}')
    elif volume_kind == "box":
        if not volume.box_size:
            raise ExportError(f"Box volume {volume.entry_name} is missing box dimensions.")
        _line(fp, indent + 1, f"{{Box {_fmt(volume.box_size[0])} {_fmt(volume.box_size[1])} {_fmt(volume.box_size[2])}}}")
    elif volume_kind == "sphere":
        if volume.sphere_radius is None:
            raise ExportError(f"Sphere volume {volume.entry_name} is missing a radius.")
        _line(fp, indent + 1, f"{{Sphere {_fmt(volume.sphere_radius)}}}")
    elif volume_kind == "cylinder":
        if volume.cylinder_radius is None or volume.cylinder_length is None:
            raise ExportError(f"Cylinder volume {volume.entry_name} is missing radius or length.")
        _line(fp, indent + 1, f"{{Cylinder {_fmt(volume.cylinder_radius)} {_fmt(volume.cylinder_length)}}}")
    else:
        raise ExportError(f"Unsupported volume kind {volume.volume_kind!r} on {volume.entry_name!r}.")
    if volume.bone_name:
        _line(fp, indent + 1, f'{{Bone "{volume.bone_name}"}}')
    if volume.component:
        _line(fp, indent + 1, f'{{Component "{volume.component}"}}')
    if volume.tags:
        _line(fp, indent + 1, f'{{Tags "{volume.tags}"}}')
    if volume.density is not None:
        _line(fp, indent + 1, f'{{Density "{_fmt(volume.density)}"}}')
    if volume.thickness:
        _write_thickness(fp, indent + 1, volume.thickness)
    if volume.matrix:
        _write_transform(fp, indent + 1, volume.matrix, block_mode=volume.transform_block)
    _line(fp, indent, "}")


def _write_thickness(fp, indent: int, thickness: dict[str, tuple[float, ...]]) -> None:
    side_order = (
        ("front", "Front"),
        ("rear", "Rear"),
        ("right", "Right"),
        ("left", "Left"),
        ("top", "Top"),
        ("bottom", "Bottom"),
    )
    common = thickness.get("common")
    side_entries = [(label, thickness[key]) for key, label in side_order if key in thickness]

    def values_text(values: tuple[float, ...]) -> str:
        return " ".join(_fmt(value) for value in values[:2])

    if common:
        if side_entries:
            _line(fp, indent, f"{{Thickness {values_text(common)}")
            for label, values in side_entries:
                _line(fp, indent + 1, f"{{{label} {values_text(values)}}}")
            _line(fp, indent, "}")
            return
        _line(fp, indent, f"{{Thickness {values_text(common)}}}")
        return

    if side_entries:
        _line(fp, indent, "{Thickness")
        for label, values in side_entries:
            _line(fp, indent + 1, f"{{{label} {values_text(values)}}}")
        _line(fp, indent, "}")


def _write_shape2d_entry(fp, indent: int, entry: Shape2DEntry) -> None:
    _line(fp, indent, f'{{{entry.block_type} "{entry.entry_name}"')
    _line(fp, indent + 1, f"{{{entry.shape_type}")
    if entry.radius is not None:
        _line(fp, indent + 2, f"{{Radius {_fmt(entry.radius)}}}")
    for vertex in entry.vertices:
        _line(fp, indent + 2, f"{{Vertex {_fmt(vertex[0])} {_fmt(vertex[1])}}}")
    if entry.center is not None:
        _line(fp, indent + 2, f"{{Center {_fmt(entry.center[0])} {_fmt(entry.center[1])}}}")
    if entry.extent is not None:
        _line(fp, indent + 2, f"{{Extent {_fmt(entry.extent[0])} {_fmt(entry.extent[1])}}}")
    if entry.axis is not None:
        _line(fp, indent + 2, f"{{Axis {_fmt(entry.axis[0])} {_fmt(entry.axis[1])}}}")
    _line(fp, indent + 1, "}")
    if entry.rotate:
        _line(fp, indent + 1, "{Rotate}")
    if entry.tags:
        _line(fp, indent + 1, f'{{Tags "{entry.tags}"}}')
    _line(fp, indent, "}")


def _write_mesh_view(fp, indent: int, mesh_view: MeshViewDef) -> None:
    volume_line = f'{{VolumeView "{mesh_view.file_name}"'
    for flag in mesh_view.flags:
        volume_line += f" {{{flag}}}"
    if mesh_view.layer is not None:
        volume_line += f" {{Layer {mesh_view.layer}}}"
    volume_line += "}"
    _line(fp, indent, volume_line)


def _write_transform(
    fp,
    indent: int,
    matrix: tuple[tuple[float, float, float], ...],
    *,
    block_mode: str | None = None,
) -> None:
    mode = (block_mode or "auto").strip().lower()
    rotation_identity = _is_identity_rotation(matrix)
    position_zero = _is_zero_vector(matrix[3])
    if mode == "position" and not position_zero and rotation_identity:
        _line(fp, indent, f"{{Position {_fmt(matrix[3][0])}\t{_fmt(matrix[3][1])}\t{_fmt(matrix[3][2])}}}")
        return
    if mode == "orientation" and position_zero:
        _line(fp, indent, "{Orientation")
        for row in matrix[:3]:
            _line(fp, indent + 1, f"{_fmt(row[0])}\t{_fmt(row[1])}\t{_fmt(row[2])}")
        _line(fp, indent, "}")
        return
    if mode == "matrix34":
        _line(fp, indent, "{Matrix34")
        for row in matrix:
            _line(fp, indent + 1, f"{_fmt(row[0])}\t{_fmt(row[1])}\t{_fmt(row[2])}")
        _line(fp, indent, "}")
        return
    if rotation_identity and not position_zero:
        _line(fp, indent, f"{{Position {_fmt(matrix[3][0])}\t{_fmt(matrix[3][1])}\t{_fmt(matrix[3][2])}}}")
        return
    if position_zero and not rotation_identity:
        _line(fp, indent, "{Orientation")
        for row in matrix[:3]:
            _line(fp, indent + 1, f"{_fmt(row[0])}\t{_fmt(row[1])}\t{_fmt(row[2])}")
        _line(fp, indent, "}")
        return
    _line(fp, indent, "{Matrix34")
    for row in matrix:
        _line(fp, indent + 1, f"{_fmt(row[0])}\t{_fmt(row[1])}\t{_fmt(row[2])}")
    _line(fp, indent, "}")


def _line(fp, indent: int, text: str) -> None:
    fp.write(f"{' ' * (4 * indent)}{text}\n")


def _mesh_max_influences(mesh: MeshData) -> int:
    max_influences = 0
    for vertex in mesh.vertices:
        count = 0
        for index in vertex.bone_indices:
            if index > 0:
                count += 1
        max_influences = max(max_influences, count)
    return max_influences


def _d3dfvf_skin_token(influence_count: int) -> int:
    if influence_count < 1 or influence_count > 5:
        raise ExportError(f"Unsupported influence count: {influence_count}")
    return 0x4 + (influence_count * 2)


def _bbox_from_vertices(vertices: Iterable[MeshVertex]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    points = [vertex.position for vertex in vertices]
    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    min_z = min(point[2] for point in points)
    max_x = max(point[0] for point in points)
    max_y = max(point[1] for point in points)
    max_z = max(point[2] for point in points)
    return (min_x, min_y, min_z), (max_x, max_y, max_z)


def _fmt(value: float) -> str:
    if abs(value) < 1e-7:
        value = 0.0
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _is_identity_rotation(matrix: tuple[tuple[float, float, float], ...], eps: float = 1e-6) -> bool:
    identity = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    for row_index in range(3):
        for col_index in range(3):
            if abs(matrix[row_index][col_index] - identity[row_index][col_index]) > eps:
                return False
    return True


def _is_zero_vector(vector: tuple[float, float, float], eps: float = 1e-6) -> bool:
    return abs(vector[0]) <= eps and abs(vector[1]) <= eps and abs(vector[2]) <= eps


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        (a[1] * b[2]) - (a[2] * b[1]),
        (a[2] * b[0]) - (a[0] * b[2]),
        (a[0] * b[1]) - (a[1] * b[0]),
    )


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt((vector[0] ** 2) + (vector[1] ** 2) + (vector[2] ** 2))
    if length <= 1e-8:
        return (0.0, 0.0, 1.0)
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _read_exact(fp: BinaryIO, size: int) -> bytes:
    data = fp.read(size)
    if len(data) != size:
        raise ExportError("Unexpected end of file while reading binary data.")
    return data


def _identity_matrix34() -> tuple[tuple[float, float, float], ...]:
    return (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, 0.0),
    )


def _normalized_mesh_frames(animation: AnimationFile) -> list[dict[str, MeshAnimationState]]:
    if not animation.mesh_frames:
        return [{} for _ in animation.frames]
    if len(animation.mesh_frames) != len(animation.frames):
        raise ExportError(
            f"Animation {animation.file_name} mesh frame count does not match transform frame count."
        )
    return animation.mesh_frames


def _mesh_animation_states_equal(
    left: MeshAnimationState | None,
    right: MeshAnimationState | None,
) -> bool:
    if left is right:
        return True
    if left is None or right is None:
        return False
    return (
        left.first_vertex == right.first_vertex
        and left.vertex_count == right.vertex_count
        and left.vertex_stride == right.vertex_stride
        and left.vertex_data == right.vertex_data
        and left.bbox == right.bbox
        and abs(left.reserved[0] - right.reserved[0]) <= 1e-6
        and abs(left.reserved[1] - right.reserved[1]) <= 1e-6
    )


def _matrices_close(
    left: tuple[tuple[float, float, float], ...],
    right: tuple[tuple[float, float, float], ...],
    eps: float = 1e-6,
) -> bool:
    for row_index in range(4):
        for col_index in range(3):
            if abs(left[row_index][col_index] - right[row_index][col_index]) > eps:
                return False
    return True


def _vectors_close(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
    eps: float = 1e-6,
) -> bool:
    for index in range(3):
        if abs(left[index] - right[index]) > eps:
            return False
    return True


def _rotation_rows_close(
    left: tuple[tuple[float, float, float], ...],
    right: tuple[tuple[float, float, float], ...],
    eps: float = 1e-6,
) -> bool:
    for row_index in range(3):
        for col_index in range(3):
            if abs(left[row_index][col_index] - right[row_index][col_index]) > eps:
                return False
    return True


def _rotation_rows_to_quaternion_xyz(
    matrix: tuple[tuple[float, float, float], ...],
) -> tuple[float, float, float]:
    m00, m01, m02 = matrix[0]
    m10, m11, m12 = matrix[1]
    m20, m21, m22 = matrix[2]

    trace = m00 + m11 + m22
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (m21 - m12) / scale
        y = (m02 - m20) / scale
        z = (m10 - m01) / scale
    elif m00 > m11 and m00 > m22:
        scale = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        w = (m21 - m12) / scale
        x = 0.25 * scale
        y = (m01 + m10) / scale
        z = (m02 + m20) / scale
    elif m11 > m22:
        scale = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        w = (m02 - m20) / scale
        x = (m01 + m10) / scale
        y = 0.25 * scale
        z = (m12 + m21) / scale
    else:
        scale = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        w = (m10 - m01) / scale
        x = (m02 + m20) / scale
        y = (m12 + m21) / scale
        z = 0.25 * scale

    length = math.sqrt((x * x) + (y * y) + (z * z) + (w * w))
    if length <= 1e-8:
        return (0.0, 0.0, 0.0)
    x /= length
    y /= length
    z /= length
    w /= length

    # FRM2 stores quaternion xyz and reconstructs w as a negative root.
    # Negating the quaternion when w is positive preserves the rotation.
    if w > 0.0:
        x = -x
        y = -y
        z = -z

    return (float(x), float(y), float(z))


def _rotation_rows_from_quaternion_xyz(quaternion_xyz: tuple[float, float, float]) -> tuple[tuple[float, float, float], ...]:
    x, y, z = quaternion_xyz
    value = max(0.0, 1.0 - ((x * x) + (y * y) + (z * z)))
    w = -math.sqrt(value)
    r2 = (w * w) + (x * x) + (y * y) + (z * z)
    if r2 <= 1e-8:
        return _identity_matrix34()[:3]
    scale = 2.0 / r2
    xs = x * scale
    ys = y * scale
    zs = z * scale
    xx = x * xs
    xy = x * ys
    xz = x * zs
    xw = w * xs
    yy = y * ys
    yz = y * zs
    yw = w * ys
    zz = z * zs
    zw = w * zs
    return (
        (1.0 - (yy + zz), xy - zw, xz + yw),
        (xy + zw, 1.0 - (xx + zz), yz - xw),
        (xz - yw, yz + xw, 1.0 - (xx + yy)),
    )
