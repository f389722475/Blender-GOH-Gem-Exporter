from __future__ import annotations

from pathlib import Path
import math
import struct
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "blender_goh_gem_exporter"
sys.path.insert(0, str(ADDON_DIR))

from goh_core import (  # noqa: E402
    AnimationFile,
    MeshAnimationState,
    AnimationState,
    BoneNode,
    ExportBundle,
    MaterialDef,
    MeshViewDef,
    MeshData,
    MeshSection,
    MeshVertex,
    ModelData,
    Shape2DEntry,
    SequenceDef,
    VolumeData,
    classify_triangle_sides,
    encode_mesh_vertex_stream,
    read_animation,
    write_animation,
    write_export_bundle,
)


def build_bundle() -> ExportBundle:
    material = MaterialDef(
        file_name="body.mtl",
        shader="bump",
        diffuse_texture="test_body_c",
        bump_texture="test_body_n_n",
        specular_texture="test_body_n_s",
        lightmap_texture="test_body_mask",
        height_texture="test_body_hm",
        parallax_scale=1.5,
        gloss_scale=1.0,
        blend="test",
        full_specular=True,
        texture_options={
            "diffuse": ("{MipMap 0}", "{AlphaChannel 1}"),
            "lightmap": ("{MipMap 1}",),
        },
    )

    vertices = [
        MeshVertex(position=(-1.0, -1.0, 0.0), normal=(0.0, 0.0, 1.0), uv=(0.0, 0.0)),
        MeshVertex(position=(1.0, -1.0, 0.0), normal=(0.0, 0.0, 1.0), uv=(1.0, 0.0)),
        MeshVertex(position=(1.0, 1.0, 0.0), normal=(0.0, 0.0, 1.0), uv=(1.0, 1.0)),
        MeshVertex(position=(-1.0, 1.0, 0.0), normal=(0.0, 0.0, 1.0), uv=(0.0, 1.0)),
    ]
    mesh = MeshData(
        file_name="body.ply",
        vertices=vertices,
        sections=[
            MeshSection(
                material_file="body.mtl",
                triangle_indices=[(0, 1, 2), (0, 2, 3)],
            )
        ],
    )
    mesh_blob, mesh_stride = encode_mesh_vertex_stream(mesh, {"body.mtl": material})

    animated_vertices = [
        MeshVertex(position=(-1.0, -1.0, 0.0), normal=(0.0, 0.0, 1.0), uv=(0.0, 0.0)),
        MeshVertex(position=(1.2, -1.0, 0.0), normal=(0.0, 0.0, 1.0), uv=(1.0, 0.0)),
        MeshVertex(position=(1.2, 1.0, 0.0), normal=(0.0, 0.0, 1.0), uv=(1.0, 1.0)),
        MeshVertex(position=(-1.0, 1.0, 0.0), normal=(0.0, 0.0, 1.0), uv=(0.0, 1.0)),
    ]
    animated_mesh = MeshData(
        file_name="body.ply",
        vertices=animated_vertices,
        sections=mesh.sections,
    )
    animated_blob, _animated_stride = encode_mesh_vertex_stream(animated_mesh, {"body.mtl": material})

    volume_vertices = [
        (-1.0, -1.0, -1.0),
        (1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 1.0),
        (-1.0, 1.0, 1.0),
    ]
    volume_triangles = [
        (0, 1, 2), (0, 2, 3),
        (4, 7, 6), (4, 6, 5),
        (0, 4, 5), (0, 5, 1),
        (1, 5, 6), (1, 6, 2),
        (2, 6, 7), (2, 7, 3),
        (3, 7, 4), (3, 4, 0),
    ]
    volume = VolumeData(
        file_name="body.vol",
        entry_name="body",
        vertices=volume_vertices,
        triangles=volume_triangles,
        side_codes=classify_triangle_sides(volume_vertices, volume_triangles),
        bone_name="body",
    )

    large_volume_vertices = [(float(index), math.sin(index * 0.01), math.cos(index * 0.01)) for index in range(65540)]
    large_volume_triangles = [(0, index, index + 1) for index in range(1, 65538)]
    large_volume = VolumeData(
        file_name="mega.vol",
        entry_name="mega",
        vertices=large_volume_vertices,
        triangles=large_volume_triangles,
        side_codes=[1] * len(large_volume_triangles),
        bone_name="body",
    )

    primitive_box = VolumeData(
        file_name=None,
        entry_name="engine",
        bone_name="body",
        volume_kind="box",
        box_size=(2.0, 3.0, 4.0),
        thickness={
            "common": (45.0,),
            "front": (80.0, 90.0),
        },
        matrix=(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (3.0, 0.0, 0.0),
        ),
    )

    primitive_cylinder = VolumeData(
        file_name=None,
        entry_name="fuel",
        bone_name="body",
        volume_kind="cylinder",
        cylinder_radius=1.25,
        cylinder_length=6.0,
        matrix=(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (8.0, 0.0, 0.0),
        ),
    )

    primitive_sphere = VolumeData(
        file_name=None,
        entry_name="crew",
        bone_name="body",
        volume_kind="sphere",
        sphere_radius=1.75,
        transform_block="position",
        matrix=(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (12.0, 0.0, 0.0),
        ),
    )

    model = ModelData(
        file_name="demo.mdl",
        basis=BoneNode(
            name="basis",
            matrix=(
                (1.0, 0.0, 0.0),
                (0.0, -1.0, 0.0),
                (0.0, 0.0, 1.0),
                (0.0, 0.0, 0.0),
            ),
            children=[
                BoneNode(
                    name="body",
                    transform_block="orientation",
                    limits=(-3.0, 85.0),
                    speed=0.008,
                    volume_view="body.ply",
                    mesh_views=[
                        MeshViewDef("body.ply"),
                        MeshViewDef("body_lod1.ply"),
                    ],
                    lod_off=True,
                    children=[
                        BoneNode(
                            name="gun_rot",
                            bone_type="revolute",
                            limits=(0.25,),
                            speed=0.2,
                            speed_uses_speed2=True,
                        )
                    ],
                ),
            ],
        ),
        metadata_comments=[
            "Basis Type=Game_Entity",
            "Basis Model=entity/-vehicle/tank_medium/demo_vehicle",
            "Basis Wheelradius=0.48",
            "Basis SteerMax=28",
        ],
        sequences=[
            SequenceDef(
                name="idle_open",
                file_name="idle_open.anm",
                speed=1.25,
                smooth=0.5,
                resume=True,
                autostart=True,
                store=True,
            )
        ],
        obstacles=[
            Shape2DEntry(
                entry_name="close",
                block_type="Obstacle",
                shape_type="Obb2",
                center=(0.0, 0.0),
                extent=(2.0, 4.0),
                axis=(1.0, 0.0),
                rotate=True,
                tags="close",
            )
        ],
        areas=[
            Shape2DEntry(
                entry_name="walk",
                block_type="Area",
                shape_type="Polygon2",
                vertices=[(-2.0, -2.0), (2.0, -2.0), (2.5, 2.0), (-1.5, 2.5)],
                rotate=False,
            )
        ],
        volumes=[volume, large_volume, primitive_box, primitive_cylinder, primitive_sphere],
        source_name="smoke_test",
    )

    return ExportBundle(
        model=model,
        meshes={"body.ply": mesh},
        materials={"body.mtl": material},
        animations={
            "idle_open.anm": AnimationFile(
                file_name="idle_open.anm",
                bone_names=["basis", "body"],
                frames=[
                    {
                        "basis": AnimationState(
                            matrix=(
                                (1.0, 0.0, 0.0),
                                (0.0, 1.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (0.0, 0.0, 0.0),
                            )
                        ),
                        "body": AnimationState(
                            matrix=(
                                (1.0, 0.0, 0.0),
                                (0.0, 1.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (0.0, 0.0, 0.0),
                            )
                        ),
                    },
                    {
                        "basis": AnimationState(
                            matrix=(
                                (1.0, 0.0, 0.0),
                                (0.0, 1.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (0.0, 0.0, 0.0),
                            )
                        ),
                        "body": AnimationState(
                            matrix=(
                                (1.0, 0.0, 0.0),
                                (0.0, 1.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (1.0, 0.0, 0.0),
                            )
                        ),
                    },
                ],
                mesh_frames=[
                    {
                        "body": MeshAnimationState(
                            first_vertex=0,
                            vertex_count=len(mesh.vertices),
                            vertex_stride=mesh_stride,
                            vertex_data=mesh_blob,
                            bbox=((-1.0, -1.0, 0.0), (1.0, 1.0, 0.0)),
                        )
                    },
                    {
                        "body": MeshAnimationState(
                            first_vertex=0,
                            vertex_count=len(animated_mesh.vertices),
                            vertex_stride=mesh_stride,
                            vertex_data=animated_blob,
                            bbox=((-1.0, -1.0, 0.0), (1.2, 1.0, 0.0)),
                        )
                    },
                ],
                format="auto",
            ),
            "legacy_idle.anm": AnimationFile(
                file_name="legacy_idle.anm",
                bone_names=["basis", "body"],
                frames=[
                    {
                        "basis": AnimationState(
                            matrix=(
                                (1.0, 0.0, 0.0),
                                (0.0, 1.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (0.0, 0.0, 0.0),
                            )
                        ),
                        "body": AnimationState(
                            matrix=(
                                (1.0, 0.0, 0.0),
                                (0.0, 1.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (0.0, 0.0, 0.0),
                            )
                        ),
                    },
                    {
                        "basis": AnimationState(
                            matrix=(
                                (1.0, 0.0, 0.0),
                                (0.0, 1.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (0.0, 0.0, 0.0),
                            )
                        ),
                        "body": AnimationState(
                            matrix=(
                                (1.0, 0.0, 0.0),
                                (0.0, 1.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (0.0, 1.0, 0.0),
                            )
                        ),
                    },
                ],
                format="legacy",
            )
        },
    )


def main() -> None:
    bundle = build_bundle()
    mesh_stride = bundle.animations["idle_open.anm"].mesh_frames[0]["body"].vertex_stride
    animated_blob = bundle.animations["idle_open.anm"].mesh_frames[1]["body"].vertex_data
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        write_export_bundle(output_dir, bundle)

        large_vertex_count = 70010
        large_stride = 12
        large_blob = b"".join(
            struct.pack("<3f", float(index), float(index % 17), float(index % 29))
            for index in range(large_vertex_count)
        )
        large_animation = AnimationFile(
            file_name="large_mesh.anm",
            bone_names=["basis"],
            frames=[
                {
                    "basis": AnimationState(
                        matrix=(
                            (1.0, 0.0, 0.0),
                            (0.0, 1.0, 0.0),
                            (0.0, 0.0, 1.0),
                            (0.0, 0.0, 0.0),
                        )
                    )
                }
            ],
            mesh_frames=[
                {
                    "basis": MeshAnimationState(
                        first_vertex=0,
                        vertex_count=large_vertex_count,
                        vertex_stride=large_stride,
                        vertex_data=large_blob,
                        bbox=((0.0, 0.0, 0.0), (float(large_vertex_count), 16.0, 28.0)),
                    )
                }
            ],
            format="frm2",
        )
        write_animation(output_dir / "large_mesh.anm", large_animation)

        mdl = output_dir / "demo.mdl"
        ply = output_dir / "body.ply"
        mtl = output_dir / "body.mtl"
        vol = output_dir / "body.vol"
        mega_vol = output_dir / "mega.vol"
        mega_vol_2 = output_dir / "mega_part2.vol"
        engine_vol = output_dir / "engine.vol"
        fuel_vol = output_dir / "fuel.vol"
        crew_vol = output_dir / "crew.vol"
        anm = output_dir / "idle_open.anm"
        legacy_anm = output_dir / "legacy_idle.anm"
        large_anm = output_dir / "large_mesh.anm"

        assert mdl.exists(), "Missing demo.mdl"
        assert ply.exists(), "Missing body.ply"
        assert mtl.exists(), "Missing body.mtl"
        assert vol.exists(), "Missing body.vol"
        assert mega_vol.exists(), "Missing mega.vol"
        assert mega_vol_2.exists(), "Missing mega_part2.vol"
        assert not engine_vol.exists(), "Primitive box volume should not create engine.vol"
        assert not fuel_vol.exists(), "Primitive cylinder volume should not create fuel.vol"
        assert not crew_vol.exists(), "Primitive sphere volume should not create crew.vol"
        assert anm.exists(), "Missing idle_open.anm"
        assert legacy_anm.exists(), "Missing legacy_idle.anm"
        assert large_anm.exists(), "Missing large_mesh.anm"
        assert ply.read_bytes()[:4] == b"EPLY"
        assert vol.read_bytes()[:4] == b"EVLM"
        ply_bytes = ply.read_bytes()
        mesh_flags = struct.unpack_from("<I", ply_bytes, 48)[0]
        anm_bytes = anm.read_bytes()
        legacy_bytes = legacy_anm.read_bytes()
        assert anm_bytes[:4] == b"EANM"
        assert legacy_bytes[:4] == b"EANM"
        assert int.from_bytes(anm_bytes[4:8], "little") == 0x00060000
        assert int.from_bytes(legacy_bytes[4:8], "little") == 0x00040000
        mdl_text = mdl.read_text(encoding="utf-8")
        assert "{Skeleton" in mdl_text
        basis_start = mdl_text.find('{Bone "basis"')
        assert basis_start != -1
        basis_end = mdl_text.find('{Bone "', basis_start + 1)
        basis_block = mdl_text[basis_start:basis_end] if basis_end != -1 else mdl_text[basis_start:]
        assert ";Basis Type=Game_Entity" in mdl_text
        assert ";Basis Model=entity/-vehicle/tank_medium/demo_vehicle" in mdl_text
        assert "{Orientation" in basis_block and "\t-1\t" in basis_block
        assert '{Sequence "idle_open" {File "idle_open.anm"} {Speed 1.25} {Smooth 0.5} {Resume} {Autostart} {Store}}' in mdl_text
        assert "{LODView" in mdl_text and '{VolumeView "body_lod1.ply"}' in mdl_text and "{OFF}" in mdl_text
        assert "{Limits -3 85}" in mdl_text
        assert "{Speed 0.008}" in mdl_text
        assert "{Speed2 0.2}" in mdl_text
        assert '{Bone "body"' in mdl_text and "{Orientation\n" in mdl_text
        assert '{Obstacle "close"' in mdl_text
        assert '{Area "walk"' in mdl_text
        assert '{Volume "mega"' in mdl_text
        assert '{Volume "mega_part2"' in mdl_text
        assert '{Volume "engine"' in mdl_text and "{Box 2 3 4}" in mdl_text
        assert "{Thickness 45" in mdl_text and "{Front 80 90}" in mdl_text
        assert '{Volume "fuel"' in mdl_text and "{Cylinder 1.25 6}" in mdl_text
        assert '{Volume "crew"' in mdl_text and "{Sphere 1.75}" in mdl_text
        assert "{Position 12\t0\t0}" in mdl_text
        mtl_text = mtl.read_text(encoding="utf-8")
        assert '{diffuse "test_body_c" {MipMap 0} {AlphaChannel 1}}' in mtl_text
        assert '{lightmap "test_body_mask" {MipMap 1}}' in mtl_text
        assert "{parallax_scale 1.5}" in mtl_text
        assert "{full_specular}" in mtl_text
        assert mesh_flags & 0x4000

        parsed = read_animation(anm)
        assert parsed.mesh_frames[0]["body"].vertex_count == 4
        assert parsed.mesh_frames[1]["body"].vertex_stride == mesh_stride
        assert parsed.mesh_frames[1]["body"].vertex_data == animated_blob
        parsed_large = read_animation(large_anm)
        assert parsed_large.mesh_frames[0]["basis"].vertex_count == large_vertex_count
        assert parsed_large.mesh_frames[0]["basis"].vertex_stride == large_stride
        assert parsed_large.mesh_frames[0]["basis"].vertex_data == large_blob
        print("smoke test passed")


if __name__ == "__main__":
    main()
