from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..goh_core import BoneNode, MeshData, MeshSection, MeshVertex, MeshViewDef


HUMANSKIN_SKIN_BONE_NAME = "skin"


@dataclass(frozen=True)
class HumanSkinImportPlan:
    bone_name: str
    mesh_views: tuple[MeshViewDef, ...]
    merged_file_name: str


def is_humanskin_skin_node(bone: BoneNode) -> bool:
    if bone.name.strip().lower() != HUMANSKIN_SKIN_BONE_NAME:
        return False
    groups = lod_view_groups(bone)
    return bool(groups) and sum(len(group) for group in groups) > 1


def lod_view_groups(bone: BoneNode) -> tuple[tuple[MeshViewDef, ...], ...]:
    groups = tuple(tuple(group) for group in getattr(bone, "lod_view_groups", ()) if group)
    if groups:
        return groups
    return tuple((view,) for view in bone.mesh_views)


def mesh_views_for_import(bone: BoneNode, *, lod0_only: bool) -> tuple[MeshViewDef, ...]:
    if not is_humanskin_skin_node(bone):
        views = tuple(bone.mesh_views)
        return views[:1] if lod0_only else views

    groups = lod_view_groups(bone)
    if lod0_only:
        return tuple(group[0] for group in groups if group)
    return tuple(view for group in groups for view in group)


def import_plan_for_bone(bone: BoneNode, *, lod0_only: bool) -> HumanSkinImportPlan | None:
    if not is_humanskin_skin_node(bone):
        return None
    views = mesh_views_for_import(bone, lod0_only=lod0_only)
    if len(views) <= 1:
        return None
    return HumanSkinImportPlan(
        bone_name=bone.name,
        mesh_views=views,
        merged_file_name=f"{bone.name}.ply",
    )


def has_humanskin_skeleton(bone: BoneNode) -> bool:
    if is_humanskin_skin_node(bone):
        return True
    return any(has_humanskin_skeleton(child) for child in bone.children)


def combine_skinned_meshes(file_name: str, meshes: Iterable[MeshData]) -> MeshData:
    mesh_list = [mesh for mesh in meshes if mesh.vertices and mesh.sections]
    if not mesh_list:
        return MeshData(file_name=file_name, vertices=[], sections=[])

    skin_bones: list[str] = []
    for mesh in mesh_list:
        for bone_name in mesh.skinned_bones:
            if bone_name not in skin_bones:
                skin_bones.append(bone_name)

    combined_vertices: list[MeshVertex] = []
    combined_sections: list[MeshSection] = []
    vertex_offset = 0

    for mesh in mesh_list:
        bone_index_remap = _bone_index_remap(mesh.skinned_bones, skin_bones)
        section_index_remap = _section_bone_index_remap(mesh.skinned_bones, skin_bones)
        for vertex in mesh.vertices:
            combined_vertices.append(
                MeshVertex(
                    position=vertex.position,
                    normal=vertex.normal,
                    uv=vertex.uv,
                    tangent=vertex.tangent,
                    tangent_sign=vertex.tangent_sign,
                    weights=vertex.weights,
                    bone_indices=tuple(bone_index_remap.get(index, 0) for index in vertex.bone_indices),
                )
            )
        for section in mesh.sections:
            combined_sections.append(
                MeshSection(
                    material_file=Path(section.material_file).name,
                    triangle_indices=[
                        (a + vertex_offset, b + vertex_offset, c + vertex_offset)
                        for a, b, c in section.triangle_indices
                    ],
                    two_sided=section.two_sided,
                    specular_rgba=section.specular_rgba,
                    subskin_bones=tuple(
                        section_index_remap[index]
                        for index in section.subskin_bones
                        if index in section_index_remap
                    ),
                )
            )
        vertex_offset += len(mesh.vertices)

    return MeshData(
        file_name=file_name,
        vertices=combined_vertices,
        sections=combined_sections,
        skinned_bones=skin_bones,
        vflags=mesh_list[0].vflags,
    )


def _bone_index_remap(source_bones: list[str], target_bones: list[str]) -> dict[int, int]:
    remap = {0: 0}
    for source_index, bone_name in enumerate(source_bones, start=1):
        try:
            remap[source_index] = target_bones.index(bone_name) + 1
        except ValueError:
            remap[source_index] = 0
    return remap


def _section_bone_index_remap(source_bones: list[str], target_bones: list[str]) -> dict[int, int]:
    remap: dict[int, int] = {}
    for source_index, bone_name in enumerate(source_bones):
        try:
            remap[source_index] = target_bones.index(bone_name)
        except ValueError:
            continue
    return remap
