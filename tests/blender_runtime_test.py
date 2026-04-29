from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
ADDON_PARENT = ROOT
if str(ADDON_PARENT) not in sys.path:
    sys.path.insert(0, str(ADDON_PARENT))
for module_name in list(sys.modules):
    if module_name == "blender_goh_gem_exporter" or module_name.startswith("blender_goh_gem_exporter."):
        del sys.modules[module_name]

import blender_goh_gem_exporter as addon  # noqa: E402
from blender_goh_gem_exporter import blender_exporter as exporter_module  # noqa: E402
from blender_goh_gem_exporter.goh_core import read_animation  # noqa: E402


def assert_auto_quad_cage(
    obj: bpy.types.Object,
    *,
    max_faces: int | None = None,
    exact_faces: int | None = None,
    allowed_face_sides: set[int] | None = None,
) -> None:
    if not obj.get("goh_auto_quad_cage"):
        raise RuntimeError(f"{obj.name} is not marked as an auto collision cage helper.")
    face_count = len(obj.data.polygons)
    if exact_faces is not None and face_count != exact_faces:
        raise RuntimeError(f"{obj.name} has {face_count} faces, expected {exact_faces}.")
    if max_faces is not None and face_count > max_faces:
        raise RuntimeError(f"{obj.name} exceeded the configured face budget.")
    allowed_face_sides = allowed_face_sides or {3, 4}
    if any(len(polygon.vertices) not in allowed_face_sides for polygon in obj.data.polygons):
        raise RuntimeError(f"{obj.name} contains a face outside the allowed topology: {sorted(allowed_face_sides)}.")
    validation = str(obj.get("goh_auto_quad_validation") or "")
    if "ERROR:" in validation:
        raise RuntimeError(f"{obj.name} stored a failed collision cage validation report: {validation}")


def main() -> None:
    addon.register()
    try:
        scene = bpy.context.scene
        output_dir = ROOT / "runtime_test_output"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "runtime_test.mdl"

        bpy.ops.object.select_all(action="DESELECT")

        cube = bpy.data.objects.get("Cube")
        if cube is None:
            raise RuntimeError("Default Cube not found.")
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube

        basis_settings = scene.goh_basis_settings
        basis_settings.enabled = True
        basis_settings.vehicle_name = "runtime_test_vehicle"
        basis_settings.entity_type = "GAME_ENTITY"
        basis_settings.entity_path = "TANK_MEDIUM"
        basis_settings.wheel_radius = -0.52
        basis_settings.steer_max = -31.0
        basis_settings.animation_enabled = True
        basis_settings.start_enabled = True
        basis_settings.start_range = "1-10"
        basis_settings.stop_enabled = True
        basis_settings.stop_range = "11-20"
        copy_result = bpy.ops.scene.goh_copy_basis_legacy()
        if "FINISHED" not in copy_result:
            raise RuntimeError(f"Copy Basis legacy text failed: {copy_result}")
        sync_result = bpy.ops.object.goh_sync_basis_helper()
        if "FINISHED" not in sync_result:
            raise RuntimeError(f"Sync Basis helper failed: {sync_result}")
        basis_helper = bpy.data.objects.get("Basis")
        if basis_helper is None or not basis_helper.get("goh_basis_helper"):
            raise RuntimeError("Basis helper was not created.")
        if "Type=Game_Entity" not in str(basis_helper.get("goh_legacy_props") or ""):
            raise RuntimeError("Basis helper did not store the expected legacy Type line.")
        if "Wheelradius=-0.52" not in str(basis_helper.get("goh_legacy_props") or ""):
            raise RuntimeError("Basis helper clamped or omitted a negative Wheelradius value.")
        if "SteerMax=-31" not in str(basis_helper.get("goh_legacy_props") or ""):
            raise RuntimeError("Basis helper clamped or omitted a negative SteerMax value.")
        if basis_helper.get("Model") != "entity/-vehicle/tank_medium/runtime_test_vehicle":
            raise RuntimeError("Basis helper did not store the expected Model metadata.")
        if abs(float(basis_helper.get("Wheelradius")) + 0.52) > 1e-6:
            raise RuntimeError("Basis helper metadata did not preserve arbitrary Wheelradius values.")
        if abs(float(basis_helper.get("SteerMax")) + 31.0) > 1e-6:
            raise RuntimeError("Basis helper metadata did not preserve arbitrary SteerMax values.")
        basis_helper["goh_legacy_props"] = str(basis_helper.get("goh_legacy_props") or "") + "\nAnimationAuto=auto_idle, auto_idle, 21-25, 60"

        preset_settings = scene.goh_preset_settings
        preset_settings.template_family = "TANK"
        preset_settings.role = "visual"
        preset_settings.part = "body"
        preset_settings.rename_objects = True
        preset_settings.write_export_names = True
        preset_settings.auto_number = True
        preset_settings.helper_collections = True
        preset_settings.clear_conflicts = True
        preset_settings.mesh_animation_mode = "FORCE"
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Visual preset failed: {result}")
        if cube.name != "Body":
            raise RuntimeError(f"Visual preset did not rename Cube to Body: {cube.name}")
        if cube.get("goh_bone_name") != "body":
            raise RuntimeError("Visual preset did not write goh_bone_name.")
        if not cube.get("goh_force_mesh_animation"):
            raise RuntimeError("Visual preset did not set goh_force_mesh_animation.")

        scene.frame_start = 1
        scene.frame_end = 10
        scene.frame_set(1)
        cube.location = (0.0, 0.0, 0.0)
        cube.keyframe_insert(data_path="location", frame=1)
        cube.location = (2.0, 0.0, 0.0)
        cube.keyframe_insert(data_path="location", frame=10)
        if cube.animation_data and cube.animation_data.action:
            cube.animation_data.action.name = "move_body"
        cube["goh_sequence_name"] = "move_body"
        cube["goh_sequence_file"] = "move_body"

        if cube.data.shape_keys is None:
            cube.shape_key_add(name="Basis")
        flex_key = cube.shape_key_add(name="Flex")
        flex_key.value = 0.0
        flex_key.keyframe_insert(data_path="value", frame=1)
        flex_key.value = 1.0
        flex_key.keyframe_insert(data_path="value", frame=10)
        if cube.data.shape_keys and cube.data.shape_keys.animation_data and cube.data.shape_keys.animation_data.action:
            cube.data.shape_keys.animation_data.action.name = "move_body"

        material = bpy.data.materials.new(name="BodyMaterial")
        material.use_nodes = True
        for image_name in ("runtime_body_c", "runtime_body_n_n", "runtime_body_n_s"):
            image = bpy.data.images.new(name=image_name, width=1, height=1)
            image_node = material.node_tree.nodes.new(type="ShaderNodeTexImage")
            image_node.image = image
        material["goh_lightmap"] = "body_mask"
        material["goh_lightmap_options"] = "MipMap 1"
        material["goh_parallax_scale"] = 1.25
        material["goh_full_specular"] = True
        cube.data.materials.clear()
        cube.data.materials.append(material)

        tool_settings = scene.goh_tool_settings
        tool_settings.texture_scope = "SELECTED"
        tool_settings.material_overwrite = False
        autofill_result = bpy.ops.scene.goh_autofill_materials()
        if "FINISHED" not in autofill_result:
            raise RuntimeError(f"Material auto-fill failed: {autofill_result}")
        if material.get("goh_diffuse") != "runtime_body_c":
            raise RuntimeError("Material auto-fill did not infer goh_diffuse.")
        if material.get("goh_bump") != "runtime_body_n_n" or material.get("goh_specular") != "runtime_body_n_s":
            raise RuntimeError("Material auto-fill did not infer bump/specular textures.")

        tool_settings.lod_levels = 1
        tool_settings.lod_mark_off = True
        lod_result = bpy.ops.object.goh_assign_lod_files()
        if "FINISHED" not in lod_result:
            raise RuntimeError(f"LOD assignment failed: {lod_result}")
        if cube.get("goh_lod_files") != "body.ply;body_lod1.ply" or not cube.get("goh_lod_off"):
            raise RuntimeError("LOD assignment did not write the expected GOH LOD properties.")

        texture_result = bpy.ops.scene.goh_report_textures()
        if "FINISHED" not in texture_result:
            raise RuntimeError(f"Texture report failed: {texture_result}")
        texture_report = bpy.data.texts.get("GOH_Texture_Report.txt")
        if texture_report is None or "BodyMaterial: body_mask" not in texture_report.as_string():
            raise RuntimeError("Texture report did not capture the expected GOH texture reference.")

        bpy.ops.object.select_all(action="DESELECT")
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        tool_settings.helper_volume_kind = "BOX"
        bounds_result = bpy.ops.object.goh_create_volume_from_bounds()
        if "FINISHED" not in bounds_result:
            raise RuntimeError(f"Volume From Bounds failed: {bounds_result}")
        bounds_helper = bpy.context.active_object
        if bounds_helper is None or bounds_helper.get("goh_volume_kind") != "box" or bounds_helper.get("goh_volume_bone") != "body":
            raise RuntimeError("Volume From Bounds did not create the expected GOH helper.")
        bpy.data.objects.remove(bounds_helper, do_unlink=True)

        bpy.ops.object.select_all(action="DESELECT")
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        tool_settings.auto_convex_target_faces = 100
        tool_settings.auto_convex_output_topology = "MIXED"
        tool_settings.auto_convex_optimize_iterations = 1
        tool_settings.auto_convex_margin = 0.0
        auto_convex_result = bpy.ops.object.goh_create_auto_convex_volume()
        if "FINISHED" not in auto_convex_result:
            raise RuntimeError(f"Auto Convex Volume failed: {auto_convex_result}")
        auto_convex_helper = bpy.context.active_object
        if (
            auto_convex_helper is None
            or auto_convex_helper.get("goh_volume_kind") != "polyhedron"
            or auto_convex_helper.get("goh_volume_bone") != "body"
        ):
            raise RuntimeError("Auto Convex Volume did not create the expected GOH helper.")
        assert_auto_quad_cage(auto_convex_helper, max_faces=tool_settings.auto_convex_target_faces, exact_faces=96)
        if auto_convex_helper.get("goh_auto_convex_max_outside", 1.0) > 1e-4:
            raise RuntimeError("Auto Convex Volume did not enclose the source mesh.")
        bpy.data.objects.remove(auto_convex_helper, do_unlink=True)

        bpy.ops.object.select_all(action="DESELECT")
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        tool_settings.auto_convex_target_faces = 512
        tool_settings.auto_convex_output_topology = "TRIANGULATED"
        tool_settings.auto_convex_optimize_iterations = 2
        tool_settings.auto_convex_margin = 0.0
        tri_convex_result = bpy.ops.object.goh_create_auto_convex_volume()
        if "FINISHED" not in tri_convex_result:
            raise RuntimeError(f"Auto Convex Volume triangulated probe failed: {tri_convex_result}")
        tri_convex_helper = bpy.context.active_object
        if tri_convex_helper is None or tri_convex_helper.get("goh_auto_convex_output_topology") != "TRIANGULATED":
            raise RuntimeError("Auto Convex Volume did not preserve triangulated topology metadata.")
        assert_auto_quad_cage(
            tri_convex_helper,
            max_faces=tool_settings.auto_convex_target_faces,
            allowed_face_sides={3},
        )
        bpy.data.objects.remove(tri_convex_helper, do_unlink=True)

        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0, location=(-3.0, 0.0, 0.0))
        convex_probe = bpy.context.active_object
        convex_probe.name = "ConvexProbe"
        convex_probe["goh_bone_name"] = "convex_probe"
        bpy.ops.object.select_all(action="DESELECT")
        convex_probe.select_set(True)
        bpy.context.view_layer.objects.active = convex_probe
        tool_settings.auto_convex_template = "SPHERE"
        tool_settings.auto_convex_fit_mode = "RAY"
        tool_settings.auto_convex_output_topology = "MIXED"
        tool_settings.auto_convex_optimize_iterations = 1
        tool_settings.auto_convex_target_faces = 96
        tool_settings.auto_convex_max_hulls = 1
        tool_settings.auto_convex_margin = 0.002
        sphere_convex_result = bpy.ops.object.goh_create_auto_convex_volume()
        if "FINISHED" not in sphere_convex_result:
            raise RuntimeError(f"Auto Convex Volume sphere probe failed: {sphere_convex_result}")
        sphere_convex_helpers = [
            obj for obj in bpy.context.selected_objects
            if obj.get("goh_auto_convex_source") == "ConvexProbe"
        ]
        if len(sphere_convex_helpers) != 1:
            raise RuntimeError("Auto Convex Volume sphere probe did not create one quad cage.")
        for sphere_convex_helper in sphere_convex_helpers:
            assert_auto_quad_cage(sphere_convex_helper, exact_faces=96)
            if "quad_sphere" not in str(sphere_convex_helper.get("goh_auto_convex_mode") or ""):
                raise RuntimeError("Auto Convex Volume sphere probe did not use the quad-sphere path.")
            if sphere_convex_helper.get("goh_auto_convex_max_outside", 1.0) > 1e-4:
                raise RuntimeError("Auto Convex Volume sphere probe did not enclose the source mesh.")
            bpy.data.objects.remove(sphere_convex_helper, do_unlink=True)
        bpy.data.objects.remove(convex_probe, do_unlink=True)

        hull_mesh = bpy.data.meshes.new("LoftHullProbeMesh")
        hull_vertices = [
            (-2.0, -0.8, -0.25),
            (-2.0, 0.8, -0.25),
            (-2.0, 0.55, 0.45),
            (-2.0, -0.55, 0.45),
            (2.0, -1.15, -0.35),
            (2.0, 1.15, -0.35),
            (2.0, 0.72, 0.35),
            (2.0, -0.72, 0.35),
        ]
        hull_faces = [
            (0, 1, 2, 3),
            (4, 7, 6, 5),
            (0, 4, 5, 1),
            (1, 5, 6, 2),
            (2, 6, 7, 3),
            (3, 7, 4, 0),
        ]
        hull_mesh.from_pydata(hull_vertices, [], hull_faces)
        hull_mesh.update(calc_edges=True)
        hull_probe = bpy.data.objects.new("LoftHullProbe", hull_mesh)
        bpy.context.collection.objects.link(hull_probe)
        hull_probe["goh_bone_name"] = "body"
        bpy.ops.object.select_all(action="DESELECT")
        hull_probe.select_set(True)
        bpy.context.view_layer.objects.active = hull_probe
        tool_settings.auto_convex_template = "AUTO"
        tool_settings.auto_convex_fit_mode = "OBB"
        tool_settings.auto_convex_output_topology = "MIXED"
        tool_settings.auto_convex_optimize_iterations = 1
        tool_settings.auto_convex_target_faces = 96
        tool_settings.auto_convex_max_hulls = 1
        tool_settings.auto_convex_margin = 0.002
        loft_result = bpy.ops.object.goh_create_auto_convex_volume()
        if "FINISHED" not in loft_result:
            raise RuntimeError(f"Auto Quad Cage Volume loft probe failed: {loft_result}")
        loft_helper = bpy.context.active_object
        if loft_helper is None or loft_helper.get("goh_auto_convex_source") != "LoftHullProbe":
            raise RuntimeError("Auto Quad Cage Volume loft probe did not create the expected helper.")
        assert_auto_quad_cage(loft_helper, exact_faces=96)
        if "quad_loft" not in str(loft_helper.get("goh_auto_convex_mode") or ""):
            raise RuntimeError("Auto Quad Cage Volume loft probe did not use the loft path.")
        bpy.data.objects.remove(loft_helper, do_unlink=True)
        bpy.data.objects.remove(hull_probe, do_unlink=True)

        bpy.ops.mesh.primitive_cube_add(size=0.5, location=(-5.0, -1.0, 0.0))
        loose_a = bpy.context.active_object
        bpy.ops.mesh.primitive_cube_add(size=0.5, location=(-5.0, 1.0, 0.0))
        loose_b = bpy.context.active_object
        bpy.ops.object.select_all(action="DESELECT")
        loose_a.select_set(True)
        loose_b.select_set(True)
        bpy.context.view_layer.objects.active = loose_a
        bpy.ops.object.join()
        loose_source = bpy.context.active_object
        loose_source.name = "LooseConvexProbe"
        loose_source["goh_bone_name"] = "loose_probe"
        bpy.ops.object.select_all(action="DESELECT")
        loose_source.select_set(True)
        bpy.context.view_layer.objects.active = loose_source
        tool_settings.auto_convex_template = "ROUNDED_BOX"
        tool_settings.auto_convex_fit_mode = "OBB"
        tool_settings.auto_convex_output_topology = "MIXED"
        tool_settings.auto_convex_optimize_iterations = 1
        tool_settings.auto_convex_target_faces = 200
        tool_settings.auto_convex_max_hulls = 8
        tool_settings.auto_convex_split_loose_parts = True
        tool_settings.auto_convex_min_part_vertices = 4
        loose_convex_result = bpy.ops.object.goh_create_auto_convex_volume()
        if "FINISHED" not in loose_convex_result:
            raise RuntimeError(f"Auto Convex Volume loose-part probe failed: {loose_convex_result}")
        loose_helpers = [
            obj for obj in bpy.context.selected_objects
            if obj.get("goh_auto_convex_source") == "LooseConvexProbe"
        ]
        if len(loose_helpers) != 2:
            raise RuntimeError("Auto Convex Volume loose-part probe did not create one hull per loose island.")
        loose_names = {helper.get("goh_volume_name") for helper in loose_helpers}
        if len(loose_names) != 2:
            raise RuntimeError("Auto Convex Volume loose-part probe did not create unique volume names.")
        for loose_helper in loose_helpers:
            assert_auto_quad_cage(loose_helper, max_faces=tool_settings.auto_convex_target_faces, exact_faces=150)
            bpy.data.objects.remove(loose_helper, do_unlink=True)
        bpy.data.objects.remove(loose_source, do_unlink=True)

        bpy.ops.object.select_all(action="DESELECT")
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        scene.cursor.location = cube.matrix_world @ cube.data.vertices[0].co
        tool_settings.physics_impact_clip_name = "armor_ripple"
        tool_settings.physics_ripple_amplitude = 0.015
        tool_settings.physics_ripple_radius = 1.0
        tool_settings.physics_ripple_waves = 2
        tool_settings.physics_create_nla_clips = True
        ripple_result = bpy.ops.object.goh_create_armor_ripple()
        if "FINISHED" not in ripple_result:
            raise RuntimeError(f"Armor ripple generation failed: {ripple_result}")
        if cube.data.shape_keys is None or not any(key.name.startswith("GOH_Ripple_armor_ripple_") for key in cube.data.shape_keys.key_blocks):
            raise RuntimeError("Armor ripple did not create expected shape keys.")
        if not cube.get("goh_force_mesh_animation"):
            raise RuntimeError("Armor ripple did not force mesh animation sampling.")

        scene.frame_set(1)
        bpy.ops.mesh.primitive_cube_add(location=(3.0, 0.0, 0.0))
        volume = bpy.context.active_object
        bpy.ops.mesh.primitive_cube_add(location=(4.5, 0.0, 0.0))
        box_volume = bpy.context.active_object
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.8, location=(5.5, 0.0, 0.0))
        sphere_volume = bpy.context.active_object
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.6, depth=2.4, location=(6.0, 0.0, 0.0))
        cylinder_volume = bpy.context.active_object
        bpy.ops.mesh.primitive_cube_add(location=(6.0, 0.0, 0.0))
        obstacle = bpy.context.active_object

        bpy.ops.mesh.primitive_cube_add(location=(-6.0, 0.0, 0.0))
        area = bpy.context.active_object

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 3.0, 0.0))
        marker = bpy.context.active_object
        bpy.ops.mesh.primitive_cube_add(location=(0.0, -3.0, 0.0))
        legacy_mesh = bpy.context.active_object
        legacy_mesh["goh_legacy_props"] = "Poly\nID=turret\nIKMin=-45\nIKMax=45\nIKSpeed=0.02\nTransform=Orientation\n"

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(2.0, 3.0, 0.0))
        legacy_handle = bpy.context.active_object

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(3.0, 3.0, 0.0))
        recoil_dummy = bpy.context.active_object
        bpy.ops.object.select_all(action="DESELECT")
        recoil_dummy.select_set(True)
        bpy.context.view_layer.objects.active = recoil_dummy
        tool_settings.recoil_axis = "NEG_Y"
        tool_settings.recoil_distance = 0.2
        tool_settings.recoil_frames = 8
        recoil_result = bpy.ops.object.goh_create_recoil_action()
        if "FINISHED" not in recoil_result:
            raise RuntimeError(f"Recoil action generation failed: {recoil_result}")
        if recoil_dummy.animation_data is None or recoil_dummy.animation_data.action is None:
            raise RuntimeError("Recoil action generation did not create an action.")
        if recoil_dummy.get("goh_sequence_name") != "recoil":
            raise RuntimeError("Recoil action generation did not write GOH sequence metadata.")
        bpy.data.objects.remove(recoil_dummy, do_unlink=True)

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(4.0, 3.0, 0.0))
        recoil_source = bpy.context.active_object
        recoil_source.name = "Gun"
        recoil_source["goh_bone_name"] = "gun"
        recoil_source["goh_sequence_name"] = "fire"
        recoil_source["goh_sequence_file"] = "fire"
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(4.0, 2.4, 0.0))
        recoil_body = bpy.context.active_object
        recoil_body.name = "BodySpring"
        recoil_body["goh_bone_name"] = "body"
        antenna_mesh = bpy.data.meshes.new("AntennaMesh")
        antenna_mesh.from_pydata(
            [
                (-0.04, -0.04, 0.0),
                (0.04, -0.04, 0.0),
                (0.04, 0.04, 0.0),
                (-0.04, 0.04, 0.0),
                (-0.115, -0.035, 0.55),
                (-0.045, -0.035, 0.55),
                (-0.045, 0.035, 0.55),
                (-0.115, 0.035, 0.55),
                (-0.325, -0.025, 2.0),
                (-0.275, -0.025, 2.0),
                (-0.275, 0.025, 2.0),
                (-0.325, 0.025, 2.0),
            ],
            [],
            [
                (0, 1, 5, 4),
                (1, 2, 6, 5),
                (2, 3, 7, 6),
                (3, 0, 4, 7),
                (4, 5, 9, 8),
                (5, 6, 10, 9),
                (6, 7, 11, 10),
                (7, 4, 8, 11),
            ],
        )
        antenna_mesh.update()
        recoil_antenna = bpy.data.objects.new("Antenna", antenna_mesh)
        bpy.context.collection.objects.link(recoil_antenna)
        recoil_antenna.location = (4.0, 3.6, 0.0)
        recoil_antenna["goh_bone_name"] = "antenna"

        barrel_mesh = bpy.data.meshes.new("BarrelAxisProbeMesh")
        barrel_mesh.from_pydata(
            [
                (-1.2, -0.04, -0.04),
                (1.2, -0.04, -0.04),
                (1.2, 0.04, -0.04),
                (-1.2, 0.04, -0.04),
                (-1.2, -0.04, 0.04),
                (1.2, -0.04, 0.04),
                (1.2, 0.04, 0.04),
                (-1.2, 0.04, 0.04),
            ],
            [],
            [
                (0, 1, 2, 3),
                (4, 7, 6, 5),
                (0, 4, 5, 1),
                (1, 5, 6, 2),
                (2, 6, 7, 3),
                (3, 7, 4, 0),
            ],
        )
        barrel_mesh.update()
        barrel_probe = bpy.data.objects.new("BarrelAxisProbe", barrel_mesh)
        bpy.context.collection.objects.link(barrel_probe)
        inferred_drive_axis = exporter_module._physics_antenna_drive_axis_world(barrel_probe, Vector((0.0, 1.0, 0.0)))
        if abs(inferred_drive_axis.x) <= 0.90:
            raise RuntimeError("Antenna Whip did not infer the barrel/source mesh principal axis for front-back sway.")
        bpy.data.objects.remove(barrel_probe, do_unlink=True)

        bpy.ops.object.select_all(action="DESELECT")
        recoil_source.select_set(True)
        recoil_body.select_set(True)
        bpy.context.view_layer.objects.active = recoil_source
        tool_settings.physics_link_role = "BODY_SPRING"
        tool_settings.physics_link_weight = 1.0
        tool_settings.physics_link_delay = 1
        link_result = bpy.ops.object.goh_assign_physics_link()
        if "FINISHED" not in link_result:
            raise RuntimeError(f"Physics link assignment failed: {link_result}")
        if recoil_body.get("goh_physics_source") != "gun" or recoil_body.get("goh_physics_role") != "BODY_SPRING":
            raise RuntimeError("Physics link assignment did not store body spring metadata.")
        if abs(float(recoil_body.get("goh_physics_weight", 0.0)) - exporter_module._physics_role_defaults("BODY_SPRING")[0]) > 1e-6:
            raise RuntimeError("Physics link assignment did not auto-store body spring role defaults.")
        if float(recoil_body.get("goh_physics_frequency", 0.0)) <= 0.0:
            raise RuntimeError("Physics link assignment did not store role-specific frequency.")
        if recoil_body.get("goh_physics_solver_space") != tool_settings.physics_solver_space:
            raise RuntimeError("Physics link assignment did not store the inertial solver-space setting.")

        bpy.ops.object.select_all(action="DESELECT")
        recoil_source.select_set(True)
        recoil_antenna.select_set(True)
        bpy.context.view_layer.objects.active = recoil_source
        tool_settings.physics_link_role = "ANTENNA_WHIP"
        tool_settings.physics_link_weight = 0.8
        tool_settings.physics_link_delay = 2
        tool_settings.physics_link_jitter = 0.25
        tool_settings.physics_antenna_root_anchor = 0.22
        tool_settings.physics_antenna_segments = 12
        link_result = bpy.ops.object.goh_assign_physics_link()
        if "FINISHED" not in link_result:
            raise RuntimeError(f"Physics antenna link assignment failed: {link_result}")
        if recoil_antenna.get("goh_physics_role") != "ANTENNA_WHIP":
            raise RuntimeError("Physics link assignment did not store antenna role metadata.")
        if abs(float(recoil_antenna.get("goh_physics_rotation", 0.0)) - exporter_module._physics_role_defaults("ANTENNA_WHIP")[3]) > 1e-6:
            raise RuntimeError("Physics link assignment did not auto-store antenna rotation defaults.")
        if abs(float(recoil_antenna.get("goh_antenna_root_anchor", 0.0)) - 0.22) > 1e-6:
            raise RuntimeError("Physics link assignment did not store antenna root anchoring metadata.")
        if int(recoil_antenna.get("goh_antenna_segments", 0)) != 12:
            raise RuntimeError("Physics link assignment did not store antenna bend segment metadata.")

        bpy.ops.object.select_all(action="DESELECT")
        recoil_source.select_set(True)
        bpy.context.view_layer.objects.active = recoil_source
        tool_settings.recoil_frames = 10
        tool_settings.recoil_distance = 0.25
        tool_settings.recoil_axis = "NEG_Y"
        tool_settings.physics_power = 1.25
        tool_settings.physics_duration_scale = 1.2
        tool_settings.physics_include_scene_links = True
        clip_frames = exporter_module._physics_max_clip_frames(tool_settings, (recoil_body, recoil_antenna), tool_settings.recoil_frames)
        if clip_frames <= tool_settings.recoil_frames:
            raise RuntimeError("Physics duration scale did not extend linked recoil clip length.")
        antenna_clip_frames = exporter_module._physics_object_clip_frames(recoil_antenna, tool_settings, tool_settings.recoil_frames)
        antenna_expected_frames = exporter_module._physics_link_response_frames(
            tool_settings,
            "ANTENNA_WHIP",
            tool_settings.recoil_frames,
        ) + int(recoil_antenna.get("goh_physics_delay", 0))
        if antenna_clip_frames != antenna_expected_frames or antenna_clip_frames <= tool_settings.recoil_frames:
            raise RuntimeError("Antenna Whip response should use its long smooth spring tail.")
        stale_link_action = bpy.data.actions.new("stale_recoil_body")
        stale_link_action["goh_sequence_name"] = "recoil"
        stale_link_action["goh_sequence_file"] = "recoil"
        recoil_body.animation_data_create()
        recoil_body.animation_data.action = stale_link_action
        linked_recoil_result = bpy.ops.object.goh_bake_linked_recoil()
        if "FINISHED" not in linked_recoil_result:
            raise RuntimeError(f"Linked recoil bake failed: {linked_recoil_result}")

        def physics_action_segments(obj, sequence_name: str | None = None):
            animation_data = getattr(obj, "animation_data", None)
            action = getattr(animation_data, "action", None) if animation_data else None
            if action is None:
                return []
            segments = exporter_module._physics_load_action_segments(action)
            if sequence_name is None:
                return segments
            return [segment for segment in segments if segment["name"] == sequence_name]

        for baked in (recoil_source, recoil_body, recoil_antenna):
            animation_data = getattr(baked, "animation_data", None)
            if animation_data is None or animation_data.action is None:
                raise RuntimeError(f"Linked recoil bake did not keep an active timeline action on {baked.name}.")
            fire_segments = physics_action_segments(baked, "fire")
            if not fire_segments:
                raise RuntimeError(f"Linked recoil bake did not record a fire clip range on {baked.name}.")
            if any(segment.get("file_stem") != "fire" for segment in fire_segments):
                raise RuntimeError("Linked recoil bake did not preserve/inherit the requested fire sequence metadata.")
            if "fire:" not in str(baked.get("goh_sequence_ranges") or ""):
                raise RuntimeError("Linked recoil bake did not mirror the fire clip range to object custom properties.")
            if any(track.name.startswith("GOH Physics") for track in animation_data.nla_tracks):
                raise RuntimeError("Linked recoil bake should keep timeline keyframes instead of generated NLA strips.")
        scene.frame_set(1)
        if (
            abs(recoil_body.location.x - 4.0) > 1e-6
            or abs(recoil_body.location.y - 2.4) > 1e-6
            or abs(recoil_body.location.z) > 1e-6
        ):
            raise RuntimeError("Linked recoil should keep delayed linked parts at rest on the first frame.")
        source_recoil_axis = exporter_module._physics_axis_world(recoil_source, tool_settings.recoil_axis)
        body_rest_world = Vector((4.0, 2.4, 0.0))
        same_direction_body_motion = 0.0
        for probe_frame in range(1, 1 + tool_settings.recoil_frames + 1):
            scene.frame_set(probe_frame)
            same_direction_body_motion = max(
                same_direction_body_motion,
                (recoil_body.matrix_world.to_translation() - body_rest_world).dot(source_recoil_axis),
            )
        if same_direction_body_motion <= 0.001:
            raise RuntimeError("Body Spring should move in the same direction as the recoil-force proxy.")
        linked_body_action = recoil_body.animation_data.action
        linked_body_keyframes = [
            keyframe
            for fcurve in exporter_module._action_fcurves(linked_body_action)
            for keyframe in fcurve.keyframe_points
        ]
        if not linked_body_keyframes or any(keyframe.interpolation != "LINEAR" for keyframe in linked_body_keyframes):
            raise RuntimeError("Linked recoil should preserve sampled physics keys with linear interpolation.")
        if not recoil_antenna.get("goh_force_mesh_animation"):
            raise RuntimeError("Antenna Whip mesh bake should force mesh animation export.")
        antenna_shape_keys = recoil_antenna.data.shape_keys
        if antenna_shape_keys is None or antenna_shape_keys.animation_data is None or antenna_shape_keys.animation_data.action is None:
            raise RuntimeError("Antenna Whip mesh bake did not create a shape-key action.")
        antenna_segments = exporter_module._physics_load_action_segments(antenna_shape_keys.animation_data.action)
        if not any(segment["name"] == "fire" for segment in antenna_segments):
            raise RuntimeError("Antenna Whip mesh bake did not record the fire clip range on shape keys.")
        antenna_keyframes = [
            keyframe
            for fcurve in exporter_module._action_fcurves(antenna_shape_keys.animation_data.action)
            for keyframe in fcurve.keyframe_points
        ]
        if not antenna_keyframes or any(keyframe.interpolation != "LINEAR" for keyframe in antenna_keyframes):
            raise RuntimeError("Antenna Whip shape-key animation should use linear interpolation to avoid stepped playback.")
        antenna_keys = [
            key
            for key in antenna_shape_keys.key_blocks
            if key.name.startswith("GOH_AntennaWhip_fire_")
        ]
        if not antenna_keys:
            raise RuntimeError("Antenna Whip mesh bake did not create per-frame anchored shape keys.")
        base_positions = [vertex.co.copy() for vertex in recoil_antenna.data.vertices]
        anchor_data = exporter_module._physics_antenna_anchor_axis(recoil_antenna.data)
        if anchor_data is None:
            raise RuntimeError("Antenna Whip mesh bake did not detect a usable antenna axis.")
        antenna_axis, min_anchor, max_anchor = anchor_data
        antenna_length = max_anchor - min_anchor
        if abs(antenna_axis.x) <= 0.05:
            raise RuntimeError("Antenna Whip mesh bake did not detect the slanted antenna principal axis.")
        base_projections = [base.dot(antenna_axis) for base in base_positions]
        root_anchor_value = float(recoil_antenna.get("goh_antenna_root_anchor", 0.22))
        anchor_limit = min_anchor + antenna_length * max(0.0, root_anchor_value)
        axis_levels = sorted({round(projection, 4) for projection in base_projections})
        if len(axis_levels) < 8:
            raise RuntimeError("Antenna Whip mesh bake did not add enough bend segments for visible curvature.")
        tip_threshold = max_anchor - antenna_length * 0.005
        max_root_motion = 0.0
        max_tip_motion = 0.0
        for key in antenna_keys:
            for index, base in enumerate(base_positions):
                delta = (key.data[index].co - base).length
                if base_projections[index] <= anchor_limit + 1e-6:
                    max_root_motion = max(max_root_motion, delta)
                if base_projections[index] >= tip_threshold:
                    max_tip_motion = max(max_tip_motion, delta)
        if max_root_motion > 1e-7:
            raise RuntimeError("Antenna Whip mesh bake moved vertices inside the anchored root zone.")
        if max_tip_motion <= 1e-3:
            raise RuntimeError("Antenna Whip mesh bake did not bend the free antenna tip.")
        frame_to_antenna_key = {}
        for key in antenna_keys:
            try:
                frame_to_antenna_key[int(key.name.rsplit("_", 1)[-1])] = key
            except ValueError:
                continue
        if not frame_to_antenna_key:
            raise RuntimeError("Antenna Whip mesh bake did not name per-frame keys with frame numbers.")
        first_antenna_frame = min(frame_to_antenna_key)
        last_antenna_frame = max(frame_to_antenna_key)
        if last_antenna_frame < first_antenna_frame + max(1, int(round(antenna_expected_frames * 0.85))):
            raise RuntimeError("Antenna Whip mesh bake did not preserve enough smooth spring tail frames.")
        early_cutoff_frame = first_antenna_frame + max(3, int(round(tool_settings.recoil_frames * 0.65)))
        early_tip_motion = 0.0
        for frame, key in frame_to_antenna_key.items():
            if frame > early_cutoff_frame:
                continue
            early_tip_motion = max(
                early_tip_motion,
                max(
                    (key.data[index].co - base).length
                    for index, base in enumerate(base_positions)
                    if base_projections[index] >= tip_threshold
                ),
            )
        if early_tip_motion <= max(0.001, max_tip_motion * 0.18):
            raise RuntimeError("Antenna Whip mesh bake delayed most of the visible bend until after the recoil source clip.")
        curved_key = max(
            antenna_keys,
            key=lambda key: max(
                (key.data[index].co - base).length
                for index, base in enumerate(base_positions)
                if base_projections[index] >= tip_threshold
            ),
        )
        tip_indices = [index for index, projection in enumerate(base_projections) if projection >= tip_threshold]
        tip_delta = Vector((0.0, 0.0, 0.0))
        for index in tip_indices:
            tip_delta += curved_key.data[index].co - base_positions[index]
        tip_delta /= float(max(1, len(tip_indices)))
        tip_delta_spread = max(
            ((curved_key.data[index].co - base_positions[index]) - tip_delta).length
            for index in tip_indices
        )
        if tip_delta_spread <= 1e-5:
            raise RuntimeError("Antenna Whip mesh bake did not rotate the tip section with the elastic rod tangent.")
        free_length = max_anchor - anchor_limit
        tip_direction = tip_delta.normalized()
        tip_sway_samples = []
        tip_sway_by_frame = []
        for key in antenna_keys:
            sample_delta = Vector((0.0, 0.0, 0.0))
            for index in tip_indices:
                sample_delta += key.data[index].co - base_positions[index]
            sample_delta /= float(max(1, len(tip_indices)))
            tip_sway = sample_delta.dot(tip_direction)
            tip_sway_samples.append(tip_sway)
            try:
                tip_sway_by_frame.append((int(key.name.rsplit("_", 1)[-1]), tip_sway))
            except ValueError:
                pass
        significant_sway = [value for value in tip_sway_samples if abs(value) >= max_tip_motion * 0.05]
        sign_changes = 0
        previous_sign = 0
        for value in significant_sway:
            sign = 1 if value > 0.0 else -1
            if previous_sign and sign != previous_sign:
                sign_changes += 1
            previous_sign = sign
        if sign_changes < 1 or not any(value < -max_tip_motion * 0.08 for value in tip_sway_samples):
            raise RuntimeError("Antenna Whip mesh bake did not create a visible left-right rebound after the first bend.")
        late_start_frame = first_antenna_frame + max(
            int(round(tool_settings.recoil_frames * 1.20)),
            int(round((last_antenna_frame - first_antenna_frame) * 0.50)),
        )
        late_significant_sway = [
            value
            for frame, value in sorted(tip_sway_by_frame)
            if frame >= late_start_frame and abs(value) >= max_tip_motion * 0.018
        ]
        late_sign_changes = 0
        previous_sign = 0
        for value in late_significant_sway:
            sign = 1 if value > 0.0 else -1
            if previous_sign and sign != previous_sign:
                late_sign_changes += 1
            previous_sign = sign
        if late_sign_changes < 1:
            raise RuntimeError("Antenna Whip late spring tail became a stiff fade instead of continuing to rebound.")
        opposite_bend_levels = 0
        checked_bend_levels = 0
        for level in axis_levels:
            if level <= anchor_limit + free_length * 0.10 or level >= max_anchor - free_length * 0.10:
                continue
            indices = [index for index, projection in enumerate(base_projections) if abs(projection - level) <= 1e-4]
            if not indices:
                continue
            ring_delta = Vector((0.0, 0.0, 0.0))
            for index in indices:
                ring_delta += curved_key.data[index].co - base_positions[index]
            ring_delta /= float(len(indices))
            if ring_delta.length <= tip_delta.length * 0.08:
                continue
            checked_bend_levels += 1
            if ring_delta.dot(tip_direction) < -tip_delta.length * 0.02:
                opposite_bend_levels += 1
        if checked_bend_levels and opposite_bend_levels:
            raise RuntimeError("Antenna Whip mesh bake produced a snake-like S-curve instead of a single elastic whip arc.")
        max_curve_error = 0.0
        for level in axis_levels:
            if level <= anchor_limit + free_length * 0.12 or level >= max_anchor - free_length * 0.12:
                continue
            indices = [index for index, projection in enumerate(base_projections) if abs(projection - level) <= 1e-4]
            if not indices:
                continue
            ring_delta = Vector((0.0, 0.0, 0.0))
            for index in indices:
                ring_delta += curved_key.data[index].co - base_positions[index]
            ring_delta /= float(len(indices))
            u = max(0.0, min(1.0, (level - anchor_limit) / free_length))
            max_curve_error = max(max_curve_error, (ring_delta - tip_delta * u).length)
        if max_curve_error <= max(0.002, tip_delta.length * 0.03):
            raise RuntimeError("Antenna Whip mesh bake still follows a straight-line tip interpolation instead of a curved beam shape.")
        final_tip_motion = max(
            (antenna_keys[-1].data[index].co - base).length
            for index, base in enumerate(base_positions)
            if base_projections[index] >= tip_threshold
        )
        if final_tip_motion > 1e-5:
            raise RuntimeError("Antenna Whip mesh bake did not spring back to rest at the end.")
        scene.frame_set(6)
        if (
            abs(recoil_antenna.location.x - 4.0) > 1e-6
            or abs(recoil_antenna.location.y - 3.6) > 1e-6
            or abs(recoil_antenna.location.z) > 1e-6
        ):
            raise RuntimeError("Antenna Whip mesh bake should keep the object transform anchored.")
        first_level_count = len(axis_levels)
        first_fixed_level_count = sum(1 for level in axis_levels if level <= anchor_limit + 1e-6)
        recoil_antenna["goh_antenna_root_anchor"] = 0.35
        recoil_antenna["goh_antenna_segments"] = 24
        bpy.ops.object.select_all(action="DESELECT")
        recoil_source.select_set(True)
        bpy.context.view_layer.objects.active = recoil_source
        scene.frame_set(1)
        rebake_result = bpy.ops.object.goh_bake_linked_recoil()
        if "FINISHED" not in rebake_result:
            raise RuntimeError(f"Antenna Whip rebake failed: {rebake_result}")
        repeat_positions = [vertex.co.copy() for vertex in recoil_antenna.data.vertices]
        repeat_anchor_data = exporter_module._physics_antenna_anchor_axis(recoil_antenna.data)
        if repeat_anchor_data is None:
            raise RuntimeError("Antenna Whip rebake lost the antenna principal axis.")
        repeat_axis, repeat_min_anchor, repeat_max_anchor = repeat_anchor_data
        repeat_length = repeat_max_anchor - repeat_min_anchor
        repeat_projections = [base.dot(repeat_axis) for base in repeat_positions]
        repeat_axis_levels = sorted({round(projection, 4) for projection in repeat_projections})
        if int(recoil_antenna.get("goh_antenna_effective_segments", 0)) < 20:
            raise RuntimeError("Antenna Bend Segments did not report enough effective bend segments after rebake.")
        if len(repeat_axis_levels) < 8:
            raise RuntimeError("Antenna Bend Segments did not keep enough bend levels after rebake.")
        repeat_anchor_limit = repeat_min_anchor + repeat_length * max(0.0, float(recoil_antenna.get("goh_antenna_root_anchor", 0.35)))
        repeat_fixed_level_count = sum(1 for level in repeat_axis_levels if level <= repeat_anchor_limit + 1e-6)
        if repeat_fixed_level_count <= first_fixed_level_count:
            raise RuntimeError("Antenna Root Anchor did not expand the anchored segment on rebake.")
        repeat_shape_keys = recoil_antenna.data.shape_keys
        if repeat_shape_keys is None:
            raise RuntimeError("Antenna Whip rebake removed shape keys unexpectedly.")
        repeat_antenna_keys = [
            key
            for key in repeat_shape_keys.key_blocks
            if key.name.startswith("GOH_AntennaWhip_fire_")
        ]
        repeat_root_motion = 0.0
        for key in repeat_antenna_keys:
            for index, base in enumerate(repeat_positions):
                if repeat_projections[index] <= repeat_anchor_limit + 1e-6:
                    repeat_root_motion = max(repeat_root_motion, (key.data[index].co - base).length)
        if repeat_root_motion > 1e-7:
            raise RuntimeError("Antenna Root Anchor did not keep the expanded root segment fixed on rebake.")
        recoil_antenna["goh_antenna_root_anchor"] = -0.08
        bpy.ops.object.select_all(action="DESELECT")
        recoil_source.select_set(True)
        bpy.context.view_layer.objects.active = recoil_source
        scene.frame_set(1)
        lower_root_result = bpy.ops.object.goh_bake_linked_recoil()
        if "FINISHED" not in lower_root_result:
            raise RuntimeError(f"Antenna Whip lower-root rebake failed: {lower_root_result}")
        if abs(float(recoil_antenna.get("goh_antenna_root_anchor", 0.0)) + 0.08) > 1e-6:
            raise RuntimeError("Antenna Root Anchor did not preserve a negative virtual-root setting.")
        lower_positions = [vertex.co.copy() for vertex in recoil_antenna.data.vertices]
        lower_anchor_data = exporter_module._physics_antenna_anchor_axis(recoil_antenna.data)
        if lower_anchor_data is None:
            raise RuntimeError("Antenna Whip lower-root rebake lost the antenna principal axis.")
        lower_axis, lower_min_anchor, lower_max_anchor = lower_anchor_data
        lower_length = lower_max_anchor - lower_min_anchor
        lower_projections = [base.dot(lower_axis) for base in lower_positions]
        lower_shape_keys = recoil_antenna.data.shape_keys
        if lower_shape_keys is None:
            raise RuntimeError("Antenna Whip lower-root rebake removed shape keys unexpectedly.")
        lower_antenna_keys = [
            key
            for key in lower_shape_keys.key_blocks
            if key.name.startswith("GOH_AntennaWhip_fire_")
        ]
        lower_curved_key = max(
            lower_antenna_keys,
            key=lambda key: max((key.data[index].co - base).length for index, base in enumerate(lower_positions)),
        )
        lower_pinned_motion = max(
            (lower_curved_key.data[index].co - base).length
            for index, base in enumerate(lower_positions)
            if lower_projections[index] <= lower_min_anchor + 1e-6
        )
        if lower_pinned_motion > 1e-7:
            raise RuntimeError("Antenna Root Anchor negative virtual root moved the bottom pinned vertices.")
        lower_near_root_motion = max(
            (lower_curved_key.data[index].co - base).length
            for index, base in enumerate(lower_positions)
            if lower_min_anchor + lower_length * 0.03 < lower_projections[index] < lower_min_anchor + lower_length * 0.18
        )
        if lower_near_root_motion <= 1e-5:
            raise RuntimeError("Antenna Root Anchor negative virtual root did not let the bend start near the bottom.")
        antenna_probe_dir = output_dir / "antenna_probe"
        if antenna_probe_dir.exists():
            shutil.rmtree(antenna_probe_dir)
        antenna_probe_dir.mkdir(parents=True, exist_ok=True)
        bpy.ops.object.select_all(action="DESELECT")
        recoil_source.select_set(True)
        recoil_antenna.select_set(True)
        bpy.context.view_layer.objects.active = recoil_antenna
        antenna_probe_result = bpy.ops.export_scene.goh_model(
            filepath=str(antenna_probe_dir / "antenna_probe.mdl"),
            selection_only=True,
            include_hidden=True,
            axis_mode="NONE",
            scale_factor=20.0,
            flip_v=True,
            export_animations=True,
            anm_format="FRM2",
        )
        if "FINISHED" not in antenna_probe_result:
            raise RuntimeError(f"Antenna Whip export probe failed: {antenna_probe_result}")
        exported_antenna_anims = [read_animation(path) for path in antenna_probe_dir.glob("*.anm")]
        if not any("antenna" in frame for animation in exported_antenna_anims for frame in animation.mesh_frames):
            raise RuntimeError("Antenna Whip export probe did not write antenna mesh-animation frames.")

        tool_settings.physics_link_role = "BODY_SPRING"
        defaults_result = bpy.ops.object.goh_load_physics_defaults()
        if "FINISHED" not in defaults_result:
            raise RuntimeError(f"Physics defaults load failed: {defaults_result}")
        if tool_settings.physics_link_frequency <= 0.0 or tool_settings.physics_link_damping <= 0.0:
            raise RuntimeError("Physics defaults did not populate spring tuning fields.")
        role_profiles = {}
        for role_name in (
            "BODY_SPRING",
            "ANTENNA_WHIP",
            "ACCESSORY_JITTER",
            "FOLLOWER",
            "SUSPENSION_BOUNCE",
            "TRACK_RUMBLE",
        ):
            tool_settings.physics_link_role = role_name
            defaults_result = bpy.ops.object.goh_load_physics_defaults()
            if "FINISHED" not in defaults_result:
                raise RuntimeError(f"Physics defaults load failed for {role_name}: {defaults_result}")
            defaults = exporter_module._physics_role_defaults(role_name)
            if abs(tool_settings.physics_link_weight - defaults[0]) > 1e-6:
                raise RuntimeError(f"Physics defaults did not set role-specific weight for {role_name}.")
            role_profiles[role_name] = tuple(
                round(value, 4)
                for value in exporter_module._physics_role_motion(role_name, 0.28, defaults[1], defaults[2])
            )
            end_profile = exporter_module._physics_role_motion(role_name, 1.0, defaults[1], defaults[2])
            if any(abs(value) > 1e-5 for value in end_profile[:4]):
                raise RuntimeError(f"Physics role motion does not settle at the end for {role_name}.")
        if len(set(role_profiles.values())) != len(role_profiles):
            raise RuntimeError("Physics role motion profiles are not distinct enough.")
        if role_profiles["BODY_SPRING"][0] <= role_profiles["FOLLOWER"][0]:
            raise RuntimeError("Body Spring should have a stronger longitudinal recoil than Follower.")
        if abs(role_profiles["ANTENNA_WHIP"][3]) <= abs(role_profiles["FOLLOWER"][3]):
            raise RuntimeError("Antenna Whip should have a stronger rotation response than Follower.")

        def sign_changes(values: list[float], threshold: float) -> int:
            signs: list[int] = []
            for value in values:
                if abs(value) <= threshold:
                    continue
                sign = 1 if value > 0.0 else -1
                if not signs or signs[-1] != sign:
                    signs.append(sign)
            return max(0, len(signs) - 1)

        body_defaults = exporter_module._physics_role_defaults("BODY_SPRING")
        body_samples = [
            exporter_module._physics_role_motion("BODY_SPRING", index / 48.0, body_defaults[1], body_defaults[2])
            for index in range(1, 48)
        ]
        body_rotation = [sample[3] for sample in body_samples]
        body_side = [sample[1] for sample in body_samples]
        crank_swing = [
            exporter_module._physics_body_crank_swing(index / 48.0, body_defaults[1], body_defaults[2])
            for index in range(1, 48)
        ]
        crank_signs: list[int] = []
        for value in crank_swing:
            if abs(value) <= 0.025:
                continue
            sign = 1 if value > 0.0 else -1
            if not crank_signs or crank_signs[-1] != sign:
                crank_signs.append(sign)
        if sign_changes(body_rotation, 0.025) < 2:
            raise RuntimeError("Body Spring should produce multiple damped rotation reversals.")
        if sign_changes(body_side, 0.008) < 1:
            raise RuntimeError("Body Spring should include lateral pendulum follow-through.")
        if min(crank_swing[:14]) >= -0.08 or max(crank_swing[12:28]) <= 0.08 or min(crank_swing[26:42]) >= -0.03:
            raise RuntimeError("Body Spring crank swing should lift, dip, and rebound before settling.")
        if max(0, len(crank_signs) - 1) < 3:
            raise RuntimeError("Body Spring crank swing should include an extra small rebound cycle.")
        if max(abs(crank_swing[index + 1] - 2.0 * crank_swing[index] + crank_swing[index - 1]) for index in range(1, len(crank_swing) - 1)) > 0.28:
            raise RuntimeError("Body Spring crank swing curve is too sharp for smooth playback.")
        dominant_early_body_rotation = max(body_rotation[:18], key=lambda value: abs(value))
        if dominant_early_body_rotation >= 0.0:
            raise RuntimeError("Body Spring should start with a nose-up hull swing.")
        early_rotation = max(abs(value) for value in body_rotation[:18])
        late_rotation = max(abs(value) for value in body_rotation[30:])
        if late_rotation >= early_rotation:
            raise RuntimeError("Body Spring rotation should decay over time.")

        duration_profiles = {
            role_name: exporter_module._physics_role_duration_default(role_name)
            for role_name in role_profiles
        }
        if not (
            duration_profiles["ANTENNA_WHIP"]
            > duration_profiles["SUSPENSION_BOUNCE"]
            > duration_profiles["BODY_SPRING"]
            > duration_profiles["FOLLOWER"]
            > duration_profiles["ACCESSORY_JITTER"]
            > duration_profiles["TRACK_RUMBLE"]
        ):
            raise RuntimeError("Physics role duration defaults are not ordered from whip tail to short rumble.")

        bpy.ops.object.select_all(action="DESELECT")
        recoil_source.select_set(True)
        bpy.context.view_layer.objects.active = recoil_source
        scene.frame_set(100)
        tool_settings.physics_direction_set = "FOUR_FIRE"
        tool_settings.physics_clip_prefix = "fire"
        tool_settings.physics_create_nla_clips = True
        directional_result = bpy.ops.object.goh_bake_directional_recoil_set()
        if "FINISHED" not in directional_result:
            raise RuntimeError(f"Directional recoil bake failed: {directional_result}")
        if not physics_action_segments(recoil_source, "fire_front") or not physics_action_segments(recoil_body, "fire_front"):
            raise RuntimeError("Directional recoil bake did not record expected fire_front clip ranges.")
        if any(track.name.startswith("GOH Physics") for track in recoil_source.animation_data.nla_tracks):
            raise RuntimeError("Directional recoil bake should keep generated keys on the active timeline action.")

        bpy.ops.object.select_all(action="DESELECT")
        recoil_body.select_set(True)
        bpy.context.view_layer.objects.active = recoil_body
        scene.frame_set(200)
        tool_settings.physics_impact_clip_name = "hit_body"
        fire_segment_count_before = len(physics_action_segments(recoil_body, "fire"))
        impact_result = bpy.ops.object.goh_bake_impact_response()
        if "FINISHED" not in impact_result:
            raise RuntimeError(f"Impact response bake failed: {impact_result}")
        if not physics_action_segments(recoil_body, "hit_body"):
            raise RuntimeError("Impact response did not record a hit_body clip range.")
        if len(physics_action_segments(recoil_body, "fire")) != fire_segment_count_before:
            raise RuntimeError("Impact response bake should not replace earlier linked recoil clip ranges.")
        range_text = str(recoil_body.get("goh_sequence_ranges") or "")
        if "fire:" not in range_text or "hit_body:" not in range_text:
            raise RuntimeError("Impact response bake did not keep a readable multi-sequence range list.")
        if getattr(recoil_body.animation_data, "action", None) is None:
            raise RuntimeError("Impact response should keep visible keyframes on the active timeline action.")
        if any(segment.get("file_stem") != "hit_body" for segment in physics_action_segments(recoil_body, "hit_body")):
            raise RuntimeError("Impact response did not write sequence metadata.")
        recoil_body["goh_sequence_ranges"] = "manual_fire:1-3; manual_hit->manual_hit_file:4-6"
        parsed_ranges = exporter_module._physics_object_sequence_ranges(recoil_body, recoil_body.animation_data.action)
        if [segment["name"] for segment in parsed_ranges] != ["manual_fire", "manual_hit"]:
            raise RuntimeError("Manual goh_sequence_ranges text was not parsed as sequence ranges.")
        if parsed_ranges[1]["file_stem"] != "manual_hit_file":
            raise RuntimeError("Manual goh_sequence_ranges file-stem override was not parsed.")
        recoil_body["goh_sequence_ranges"] = range_text

        bpy.ops.object.select_all(action="DESELECT")
        for obj in (recoil_source, recoil_body, recoil_antenna):
            obj.select_set(True)
        bpy.context.view_layer.objects.active = recoil_source
        tool_settings.physics_clear_actions = True
        clear_result = bpy.ops.object.goh_clear_physics_links()
        if "FINISHED" not in clear_result:
            raise RuntimeError(f"Physics clear failed: {clear_result}")
        if "goh_physics_source" in recoil_body:
            raise RuntimeError("Physics clear did not remove stored link metadata.")
        if recoil_source.animation_data is not None and any(track.name.startswith("GOH Physics") for track in recoil_source.animation_data.nla_tracks):
            raise RuntimeError("Physics clear did not remove GOH physics NLA tracks.")
        if recoil_antenna.data.shape_keys and any(
            key.name.startswith("GOH_AntennaWhip_") for key in recoil_antenna.data.shape_keys.key_blocks
        ):
            raise RuntimeError("Physics clear did not remove Antenna Whip shape keys.")
        bpy.data.objects.remove(recoil_source, do_unlink=True)
        bpy.data.objects.remove(recoil_body, do_unlink=True)
        bpy.data.objects.remove(recoil_antenna, do_unlink=True)

        bpy.ops.object.select_all(action="DESELECT")
        volume.select_set(True)
        bpy.context.view_layer.objects.active = volume
        preset_settings.role = "volume"
        preset_settings.part = "body"
        preset_settings.target_name = "body"
        preset_settings.volume_kind = "POLYHEDRON"
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Volume preset failed: {result}")
        if volume.name != "Body_vol" or not volume.get("goh_is_volume"):
            raise RuntimeError("Volume preset did not assign volume helper state.")
        if volume.get("goh_volume_bone") != "body":
            raise RuntimeError("Volume preset did not write goh_volume_bone.")
        if not any(collection.name == "GOH_VOLUMES" for collection in volume.users_collection):
            raise RuntimeError("Volume preset did not link GOH_VOLUMES.")
        volume["goh_thickness"] = "45"
        volume["goh_thickness_front"] = "80 90"

        bpy.ops.object.select_all(action="DESELECT")
        box_volume.select_set(True)
        bpy.context.view_layer.objects.active = box_volume
        preset_settings.role = "volume"
        preset_settings.part = "engine"
        preset_settings.target_name = "body"
        preset_settings.volume_kind = "BOX"
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Primitive box preset failed: {result}")
        if box_volume.name != "Engine_vol" or box_volume.get("goh_volume_kind") != "box":
            raise RuntimeError("Box volume preset did not assign primitive metadata.")

        bpy.ops.object.select_all(action="DESELECT")
        sphere_volume.select_set(True)
        bpy.context.view_layer.objects.active = sphere_volume
        preset_settings.role = "volume"
        preset_settings.part = "detail"
        preset_settings.target_name = "body"
        preset_settings.volume_kind = "SPHERE"
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Primitive sphere preset failed: {result}")
        if sphere_volume.name != "Detail_vol" or sphere_volume.get("goh_volume_kind") != "sphere":
            raise RuntimeError("Sphere volume preset did not assign primitive metadata.")

        bpy.ops.object.select_all(action="DESELECT")
        preset_settings.template_family = "GENERIC"
        cylinder_volume.select_set(True)
        bpy.context.view_layer.objects.active = cylinder_volume
        preset_settings.role = "volume"
        preset_settings.part = "fuel"
        preset_settings.target_name = "body"
        preset_settings.volume_kind = "CYLINDER"
        preset_settings.volume_axis = "Z"
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Primitive cylinder preset failed: {result}")
        if cylinder_volume.name != "Fuel_vol" or cylinder_volume.get("goh_volume_kind") != "cylinder":
            raise RuntimeError("Cylinder volume preset did not assign primitive metadata.")
        if cylinder_volume.get("goh_volume_axis") != "z":
            raise RuntimeError("Cylinder volume preset did not assign the primitive axis.")

        bpy.ops.object.select_all(action="DESELECT")
        obstacle.select_set(True)
        bpy.context.view_layer.objects.active = obstacle
        preset_settings.role = "obstacle"
        preset_settings.part = "decor"
        preset_settings.target_name = ""
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Obstacle preset failed: {result}")
        if obstacle.name != "Decor_obstacle" or not obstacle.get("goh_is_obstacle"):
            raise RuntimeError("Obstacle preset did not assign helper state.")
        if obstacle.get("goh_shape_name") != "decor" or obstacle.get("goh_shape_2d") != "obb2":
            raise RuntimeError("Obstacle preset did not assign GOH obstacle metadata.")

        bpy.ops.object.select_all(action="DESELECT")
        area.select_set(True)
        bpy.context.view_layer.objects.active = area
        preset_settings.role = "area"
        preset_settings.part = "track"
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Area preset failed: {result}")
        if area.name != "Track_area" or not area.get("goh_is_area"):
            raise RuntimeError("Area preset did not assign helper state.")
        if area.get("goh_shape_name") != "track" or area.get("goh_shape_2d") != "polygon2":
            raise RuntimeError("Area preset did not assign GOH area metadata.")

        bpy.ops.object.select_all(action="DESELECT")
        marker.select_set(True)
        bpy.context.view_layer.objects.active = marker
        preset_settings.role = "attachment"
        preset_settings.part = "emit"
        preset_settings.target_name = "body"
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Attachment preset failed: {result}")
        if marker.name != "Emit1" or marker.get("goh_attach_bone") != "body":
            raise RuntimeError("Attachment preset did not assign goh_attach_bone.")

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(4.0, 3.0, 0.0))
        emit_auto_a = bpy.context.active_object
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(4.5, 3.0, 0.0))
        emit_auto_b = bpy.context.active_object
        bpy.ops.object.select_all(action="DESELECT")
        emit_auto_a.select_set(True)
        emit_auto_b.select_set(True)
        bpy.context.view_layer.objects.active = emit_auto_a
        preset_settings.template_family = "TANK"
        preset_settings.role = "attachment"
        preset_settings.part = "emit_lower_auto"
        preset_settings.target_name = ""
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Lowercase emit auto preset failed: {result}")
        if {emit_auto_a.name, emit_auto_b.name} != {"emit1", "emit2"}:
            raise RuntimeError("Lowercase emit auto preset did not generate emit1/emit2.")

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(5.0, 3.0, 0.0))
        wheel_auto_a = bpy.context.active_object
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(5.5, 3.0, 0.0))
        wheel_auto_b = bpy.context.active_object
        bpy.ops.object.select_all(action="DESELECT")
        wheel_auto_a.select_set(True)
        wheel_auto_b.select_set(True)
        bpy.context.view_layer.objects.active = wheel_auto_a
        preset_settings.template_family = "CANNON"
        preset_settings.role = "attachment"
        preset_settings.part = "wheel_l_mixed_auto"
        result = bpy.ops.object.goh_apply_preset()
        if "FINISHED" not in result:
            raise RuntimeError(f"Optional-first wheel auto preset failed: {result}")
        if {wheel_auto_a.name, wheel_auto_b.name} != {"wheelL", "wheelL1"}:
            raise RuntimeError("Optional-first wheel auto preset did not generate wheelL/wheelL1.")

        bpy.ops.object.select_all(action="DESELECT")
        legacy_handle.select_set(True)
        bpy.context.view_layer.objects.active = legacy_handle
        weapon_result = bpy.ops.object.goh_weapon_tool(action="HANDLE")
        if "FINISHED" not in weapon_result:
            raise RuntimeError(f"Weapon helper action failed: {weapon_result}")
        if legacy_handle.name != "handle" or legacy_handle.get("goh_bone_name") != "handle":
            raise RuntimeError("Weapon helper action did not assign the expected handle metadata.")

        bpy.ops.object.select_all(action="DESELECT")
        legacy_mesh.select_set(True)
        bpy.context.view_layer.objects.active = legacy_mesh
        tool_settings.transform_block = "ORIENTATION"
        transform_result = bpy.ops.object.goh_apply_transform_block()
        if "FINISHED" not in transform_result:
            raise RuntimeError(f"Apply Transform Block failed: {transform_result}")
        if legacy_mesh.get("goh_transform_block") != "orientation":
            raise RuntimeError("Transform block tool did not store the selected mode.")

        obstacle.select_set(True)
        area.select_set(True)
        volume.select_set(True)
        box_volume.select_set(True)
        sphere_volume.select_set(True)
        cylinder_volume.select_set(True)
        cube.select_set(True)
        legacy_mesh.select_set(True)
        legacy_handle.select_set(True)

        tool_settings.validation_scope = "SELECTED"
        validation_result = bpy.ops.scene.goh_validate_scene()
        if "FINISHED" not in validation_result:
            raise RuntimeError(f"GOH validation failed unexpectedly: {validation_result}")
        validation_report = bpy.data.texts.get("GOH_Validation_Report.txt")
        if validation_report is None or "GOH Validation Report" not in validation_report.as_string():
            raise RuntimeError("GOH validation did not create a report text block.")

        result = bpy.ops.export_scene.goh_model(
            filepath=str(output_file),
            selection_only=True,
            include_hidden=False,
            axis_mode="NONE",
            anm_format="FRM2",
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Export failed: {result}")

        expected = [
            output_dir / "runtime_test.mdl",
            output_dir / "body.ply",
            output_dir / "body.vol",
            output_dir / "body.anm",
            output_dir / "body_2.anm",
            output_dir / "auto_idle.anm",
            output_dir / "GOH_Export_Manifest.json",
        ]
        missing = [str(path) for path in expected if not path.exists()]
        if missing:
            raise RuntimeError(f"Missing exported files: {missing}")
        unexpected_volume_files = [path.name for path in (output_dir / "engine.vol", output_dir / "detail.vol", output_dir / "fuel.vol") if path.exists()]
        if unexpected_volume_files:
            raise RuntimeError(f"Primitive volumes should not create .vol files: {unexpected_volume_files}")
        material_files = list(output_dir.glob("*.mtl"))
        if not material_files:
            raise RuntimeError("No material file was exported.")
        mdl_text = (output_dir / "runtime_test.mdl").read_text(encoding="utf-8")
        if ";Basis Type=Game_Entity" not in mdl_text or ";Basis Model=entity/-vehicle/tank_medium/runtime_test_vehicle" not in mdl_text:
            raise RuntimeError("Basis metadata comments were not written into runtime_test.mdl.")
        if "{Orientation\n            1\t0\t0\n            0\t-1\t0\n            0\t0\t1" not in mdl_text and "{Orientation\n\t\t1\t0\t0\n\t\t0\t-1\t0\n\t\t0\t0\t1" not in mdl_text:
            raise RuntimeError("Basis bone did not write the expected GOH native orientation block.")
        if '{Sequence "start" {File "body.anm"}' not in mdl_text or '{Sequence "stop" {File "body_2.anm"}' not in mdl_text:
            raise RuntimeError("Legacy Basis animation sequences were not written into runtime_test.mdl.")
        if '{Sequence "auto_idle" {File "auto_idle.anm"}' not in mdl_text or "{Autostart}" not in mdl_text:
            raise RuntimeError("Legacy AnimationAuto sequence was not written with Autostart metadata.")
        if '{Volume "body"' not in mdl_text:
            raise RuntimeError("Volume block was not written into runtime_test.mdl.")
        if '{Volume "engine"' not in mdl_text or "{Box " not in mdl_text:
            raise RuntimeError("Primitive box volume was not written into runtime_test.mdl.")
        if '{Volume "detail"' not in mdl_text or "{Sphere " not in mdl_text:
            raise RuntimeError("Primitive sphere volume was not written into runtime_test.mdl.")
        if '{Volume "fuel"' not in mdl_text or "{Cylinder " not in mdl_text:
            raise RuntimeError("Primitive cylinder volume was not written into runtime_test.mdl.")
        if "{Thickness " not in mdl_text or "{Front " not in mdl_text:
            raise RuntimeError("Volume thickness data was not written into runtime_test.mdl.")
        if "{LODView" not in mdl_text or '{Obstacle "decor"' not in mdl_text or '{Area "track"' not in mdl_text:
            raise RuntimeError("LOD / obstacle / area blocks were not written into runtime_test.mdl.")
        if '{Bone "turret"' not in mdl_text or "{Limits -45 45}" not in mdl_text or "{Speed 0.02}" not in mdl_text:
            raise RuntimeError("Legacy Max text properties were not converted into GOH bone limits/speed.")
        if '{Bone "handle"' not in mdl_text:
            raise RuntimeError("Weapon helper tool output was not exported into runtime_test.mdl.")
        mtl_text = material_files[0].read_text(encoding="utf-8")
        if '{lightmap "body_mask" {MipMap 1}}' not in mtl_text or "{parallax_scale 1.25}" not in mtl_text:
            raise RuntimeError("Extended material parameters were not written into the .mtl file.")
        import_result = bpy.ops.import_scene.goh_model(
            filepath=str(output_file),
            axis_mode="NONE",
            scale_factor=20.0,
            flip_v=True,
            import_materials=True,
            load_textures=False,
            import_volumes=True,
            import_shapes=True,
            import_lod0_only=True,
            defer_basis_flip=True,
        )
        if "FINISHED" not in import_result:
            raise RuntimeError(f"Model import failed: {import_result}")
        imported_objects = [
            obj for obj in bpy.data.objects
            if str(obj.get("goh_source_mdl") or "") == str(output_file)
        ]
        if not imported_objects:
            raise RuntimeError("Model import did not create tagged imported objects.")
        imported_body = next((obj for obj in imported_objects if obj.get("goh_bone_name") == "body" and obj.type == "MESH"), None)
        imported_basis = next((obj for obj in imported_objects if obj.get("goh_bone_name") == "basis" and obj.type == "EMPTY"), None)
        if imported_body is None or len(imported_body.data.vertices) == 0:
            raise RuntimeError("Model import did not rebuild the body visual mesh.")
        if not imported_body.data.get("goh_imported_custom_normals"):
            raise RuntimeError("Model import did not apply EPLY custom split normals to the body mesh.")
        if imported_body.data.get("goh_imported_custom_normal_loops") != len(imported_body.data.loops):
            raise RuntimeError("Model import custom normal loop count does not match Blender mesh loops.")
        if imported_basis is None or not imported_basis.get("goh_deferred_basis_flip"):
            raise RuntimeError("Model import did not defer the mirrored GOH basis for Blender editing.")
        if imported_basis.matrix_world.to_3x3().determinant() < 0.0:
            raise RuntimeError("Deferred GOH basis import still displays a mirrored basis in Blender.")
        rest_values = imported_basis.get("goh_rest_matrix_local")
        rest_matrix = Matrix((rest_values[0:4], rest_values[4:8], rest_values[8:12], rest_values[12:16]))
        if rest_matrix.to_3x3().determinant() >= 0.0:
            raise RuntimeError("Deferred GOH basis import did not keep the mirrored basis for export.")
        if not imported_body.material_slots or imported_body.material_slots[0].material is None:
            raise RuntimeError("Model import did not attach a material to the body mesh.")
        imported_volumes = [obj for obj in imported_objects if obj.get("goh_is_volume")]
        if not any(obj.get("goh_volume_kind") == "box" for obj in imported_volumes):
            raise RuntimeError("Model import did not rebuild primitive box volumes.")
        if not any(obj.get("goh_volume_kind") == "sphere" for obj in imported_volumes):
            raise RuntimeError("Model import did not rebuild primitive sphere volumes.")
        if not any(obj.get("goh_volume_kind") == "cylinder" and obj.get("goh_volume_axis") == "z" for obj in imported_volumes):
            raise RuntimeError("Model import did not restore primitive cylinder axis metadata.")
        imported_obstacles = [obj for obj in imported_objects if obj.get("goh_is_obstacle")]
        imported_areas = [obj for obj in imported_objects if obj.get("goh_is_area")]
        if not any(obj.get("goh_shape_name") == "decor" and obj.get("goh_shape_2d") == "obb2" for obj in imported_obstacles):
            raise RuntimeError("Model import did not rebuild obstacle shape helpers.")
        if not any(obj.get("goh_shape_name") == "track" and obj.get("goh_shape_2d") == "polygon2" for obj in imported_areas):
            raise RuntimeError("Model import did not rebuild area shape helpers.")
        if imported_body.get("goh_import_axis_mode") != "NONE":
            raise RuntimeError("Model import did not store axis metadata for animation auto-matching.")
        if abs(float(imported_body.get("goh_import_scale_factor", 0.0)) - 20.0) > 1e-6:
            raise RuntimeError("Model import did not store scale metadata for animation auto-matching.")
        manifest = json.loads((output_dir / "GOH_Export_Manifest.json").read_text(encoding="utf-8"))
        manifest_files = {entry["path"] for entry in manifest.get("files", [])}
        if "runtime_test.mdl" not in manifest_files or "body.ply" not in manifest_files:
            raise RuntimeError("Export manifest did not record core exported files.")
        if manifest.get("counts", {}).get("obstacles", 0) < 1 or manifest.get("counts", {}).get("areas", 0) < 1:
            raise RuntimeError("Export manifest did not record obstacle / area counts.")
        bpy.ops.object.select_all(action="DESELECT")
        imported_body.select_set(True)
        bpy.context.view_layer.objects.active = imported_body
        model_anm_result = bpy.ops.import_scene.goh_anm(
            filepath=str(output_dir / "body.anm"),
            axis_mode="AUTO",
            frame_start=40,
        )
        if "FINISHED" not in model_anm_result:
            raise RuntimeError(f"Imported-model animation failed: {model_anm_result}")
        scene.frame_set(40)
        imported_start = imported_body.location.copy()
        scene.frame_set(49)
        imported_end = imported_body.location.copy()
        imported_delta = imported_end - imported_start
        if abs(imported_delta.x - 2.0) > 0.05 or abs(imported_delta.y) > 0.05 or abs(imported_delta.z) > 0.05:
            raise RuntimeError(f"Imported-model animation axis mismatch: delta={tuple(imported_delta)}")
        for imported in imported_objects:
            bpy.data.objects.remove(imported, do_unlink=True)
        anm_bytes = (output_dir / "body.anm").read_bytes()
        if anm_bytes[:4] != b"EANM":
            raise RuntimeError("body.anm does not look like a GOH animation file.")
        if int.from_bytes(anm_bytes[4:8], "little") != 0x00060000:
            raise RuntimeError("body.anm was expected to default to FRM2 / 0x00060000.")
        parsed = read_animation(output_dir / "body.anm")
        if "basis" in parsed.bone_names:
            raise RuntimeError("Object-mode ANM export should not override the static GOH basis transform.")
        if not any(frame for frame in parsed.mesh_frames):
            raise RuntimeError("body.anm did not contain any mesh animation chunks.")

        cube.animation_data_clear()
        bpy.ops.object.select_all(action="DESELECT")
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        result = bpy.ops.import_scene.goh_anm(
            filepath=str(output_dir / "body.anm"),
            axis_mode="NONE",
            frame_start=20,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Import failed: {result}")
        if cube.animation_data is None or cube.animation_data.action is None:
            raise RuntimeError("Import did not create an action on the target object.")
        if cube.data.shape_keys is None:
            raise RuntimeError("Import did not create shape keys for mesh animation.")
        imported_keys = [key.name for key in cube.data.shape_keys.key_blocks if key.name.startswith("GOH_body_body_")]
        if len(imported_keys) < 2:
            raise RuntimeError("Import did not rebuild mesh animation shape keys.")

        basis_probe_dir = output_dir / "basis_roundtrip"
        basis_probe_dir.mkdir(parents=True, exist_ok=True)
        basis_probe_mesh = bpy.data.meshes.new("basis_probe_mesh")
        basis_probe_mesh.from_pydata([(0.0, 0.0, 0.0), (0.25, 0.0, 0.0), (0.0, 0.25, 0.0)], [], [(0, 1, 2)])
        basis_probe_mesh.update()

        def matrix_prop(matrix: Matrix) -> list[float]:
            return [float(matrix[row][col]) for row in range(4) for col in range(4)]

        goh_basis_matrix = Matrix(
            (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, -1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        basis_probe_basis = bpy.data.objects.new("basis", None)
        basis_probe_basis.empty_display_type = "PLAIN_AXES"
        scene.collection.objects.link(basis_probe_basis)
        basis_probe_basis.matrix_world = goh_basis_matrix
        basis_probe_child = bpy.data.objects.new("BasisProbeBody", basis_probe_mesh)
        scene.collection.objects.link(basis_probe_child)
        basis_probe_child.parent = basis_probe_basis
        basis_probe_child.matrix_parent_inverse = Matrix.Identity(4)
        basis_probe_child.matrix_local = Matrix.Translation((1.0, 2.0, 3.0))
        basis_probe_child["goh_bone_name"] = "body"
        bpy.ops.object.select_all(action="DESELECT")
        basis_probe_basis.select_set(True)
        basis_probe_child.select_set(True)
        bpy.context.view_layer.objects.active = basis_probe_child
        basis_probe_file = basis_probe_dir / "basis_probe.mdl"
        basis_probe_result = bpy.ops.export_scene.goh_model(
            filepath=str(basis_probe_file),
            selection_only=True,
            include_hidden=True,
            axis_mode="NONE",
            scale_factor=20.0,
            export_animations=False,
        )
        if "FINISHED" not in basis_probe_result:
            raise RuntimeError(f"Basis helper round-trip export failed: {basis_probe_result}")
        basis_probe_text = basis_probe_file.read_text(encoding="utf-8")
        if "{Position 20\t40\t60}" not in basis_probe_text:
            raise RuntimeError("Basis helper round-trip export baked the GOH basis orientation into the child bone.")
        basis_probe_basis["goh_rest_matrix_local"] = matrix_prop(goh_basis_matrix)
        basis_probe_basis["goh_deferred_basis_flip"] = True
        basis_probe_basis.matrix_world = Matrix.Identity(4)
        basis_probe_child.matrix_local = Matrix.Translation((1.0, 2.0, 3.0))
        bpy.ops.object.select_all(action="DESELECT")
        basis_probe_basis.select_set(True)
        basis_probe_child.select_set(True)
        bpy.context.view_layer.objects.active = basis_probe_child
        deferred_basis_probe_file = basis_probe_dir / "basis_probe_deferred.mdl"
        deferred_basis_probe_result = bpy.ops.export_scene.goh_model(
            filepath=str(deferred_basis_probe_file),
            selection_only=True,
            include_hidden=True,
            axis_mode="NONE",
            scale_factor=20.0,
            export_animations=False,
        )
        if "FINISHED" not in deferred_basis_probe_result:
            raise RuntimeError(f"Deferred basis helper round-trip export failed: {deferred_basis_probe_result}")
        deferred_basis_probe_text = deferred_basis_probe_file.read_text(encoding="utf-8")
        if "{Position 20\t40\t60}" not in deferred_basis_probe_text:
            raise RuntimeError("Deferred basis export did not move the GOH basis flip back into the exported MDL.")
        deferred_animation_dir = basis_probe_dir / "deferred_animation"
        deferred_animation_dir.mkdir(parents=True, exist_ok=True)
        basis_probe_child["goh_rest_matrix_local"] = matrix_prop(Matrix.Translation((1.0, 2.0, 3.0)))
        scene.frame_set(1)
        basis_probe_child.location = Vector((1.0, 2.0, 3.0))
        basis_probe_child.rotation_euler = (0.0, 0.0, 0.0)
        basis_probe_child.keyframe_insert(data_path="location", frame=1)
        basis_probe_child.keyframe_insert(data_path="rotation_euler", frame=1)
        scene.frame_set(2)
        basis_probe_child.location = Vector((1.0, 1.5, 3.0))
        basis_probe_child.rotation_euler = (0.0, 0.2, 0.0)
        basis_probe_child.keyframe_insert(data_path="location", frame=2)
        basis_probe_child.keyframe_insert(data_path="rotation_euler", frame=2)
        if basis_probe_child.animation_data and basis_probe_child.animation_data.action:
            basis_probe_child.animation_data.action.name = "manual_deferred_basis_probe"
        bpy.ops.object.select_all(action="DESELECT")
        basis_probe_basis.select_set(True)
        basis_probe_child.select_set(True)
        bpy.context.view_layer.objects.active = basis_probe_child
        deferred_animation_result = bpy.ops.export_scene.goh_model(
            filepath=str(deferred_animation_dir / "deferred_animation_probe.mdl"),
            selection_only=True,
            include_hidden=True,
            axis_mode="NONE",
            scale_factor=20.0,
            export_animations=True,
        )
        if "FINISHED" not in deferred_animation_result:
            raise RuntimeError(f"Deferred basis animation export failed: {deferred_animation_result}")
        deferred_animation_path = None
        deferred_delta_y = None
        deferred_pitch_marker = None
        for animation_path in deferred_animation_dir.glob("*.anm"):
            candidate = read_animation(animation_path)
            if "body" not in candidate.bone_names or len(candidate.frames) < 2:
                continue
            delta = candidate.frames[-1]["body"].matrix[3][1] - candidate.frames[0]["body"].matrix[3][1]
            if abs(delta) > 1.0:
                deferred_animation_path = animation_path
                deferred_delta_y = delta
                deferred_pitch_marker = candidate.frames[-1]["body"].matrix[0][2]
                break
        if deferred_animation_path is None:
            raise RuntimeError("Deferred basis animation export did not produce a reusable ANM probe.")
        if deferred_delta_y is None:
            raise RuntimeError("Deferred basis animation export did not write the probe motion.")
        if deferred_delta_y <= 0.0:
            raise RuntimeError("Deferred basis animation was not converted into GOH export space.")
        if deferred_pitch_marker is None or deferred_pitch_marker >= -0.05:
            raise RuntimeError("Deferred basis animation did not invert the exported pitch delta for GOH playback.")
        basis_probe_child.animation_data_clear()
        basis_probe_child.location = Vector((1.0, 2.0, 3.0))
        basis_probe_child.rotation_euler = (0.0, 0.0, 0.0)
        bpy.ops.object.select_all(action="DESELECT")
        basis_probe_child.select_set(True)
        bpy.context.view_layer.objects.active = basis_probe_child
        deferred_import_result = bpy.ops.import_scene.goh_anm(
            filepath=str(deferred_animation_path),
            axis_mode="NONE",
            frame_start=70,
        )
        if "FINISHED" not in deferred_import_result:
            raise RuntimeError(f"Deferred basis animation re-import failed: {deferred_import_result}")
        scene.frame_set(70)
        bpy.context.view_layer.update()
        if abs(basis_probe_child.location.y - 2.0) > 0.05:
            raise RuntimeError("Deferred basis animation import changed the rest pose unexpectedly.")
        scene.frame_set(71)
        bpy.context.view_layer.update()
        if abs(basis_probe_child.location.y - 1.5) > 0.05:
            raise RuntimeError("Deferred basis animation import did not restore Blender-visible translation direction.")
        imported_pitch_marker = basis_probe_child.rotation_quaternion.to_matrix()[0][2]
        if imported_pitch_marker <= 0.05:
            raise RuntimeError("Deferred basis animation import did not restore Blender-visible pitch direction.")
        basis_probe_child.animation_data_clear()
        if "goh_deferred_basis_flip" in basis_probe_basis:
            del basis_probe_basis["goh_deferred_basis_flip"]
        basis_probe_basis.matrix_world = goh_basis_matrix
        basis_probe_child.matrix_local = Matrix.Translation((1.0, 2.0, 3.0))
        common_animation_dir = basis_probe_dir / "mirrored_basis_animation"
        common_animation_dir.mkdir(parents=True, exist_ok=True)
        basis_probe_child.animation_data_clear()
        basis_probe_child.rotation_mode = "XYZ"
        scene.frame_set(1)
        basis_probe_child.location = Vector((1.0, 2.0, 3.0))
        basis_probe_child.rotation_euler = (0.0, 0.0, 0.0)
        basis_probe_child.keyframe_insert(data_path="location", frame=1)
        basis_probe_child.keyframe_insert(data_path="rotation_euler", frame=1)
        scene.frame_set(2)
        basis_probe_child.location = Vector((1.0, 1.5, 3.0))
        basis_probe_child.rotation_euler = (0.0, -0.2, 0.0)
        basis_probe_child.keyframe_insert(data_path="location", frame=2)
        basis_probe_child.keyframe_insert(data_path="rotation_euler", frame=2)
        if basis_probe_child.animation_data and basis_probe_child.animation_data.action:
            basis_probe_child.animation_data.action.name = "manual_mirrored_basis_probe"
        bpy.ops.object.select_all(action="DESELECT")
        basis_probe_basis.select_set(True)
        basis_probe_child.select_set(True)
        bpy.context.view_layer.objects.active = basis_probe_child
        common_animation_result = bpy.ops.export_scene.goh_model(
            filepath=str(common_animation_dir / "mirrored_basis_animation_probe.mdl"),
            selection_only=True,
            include_hidden=True,
            axis_mode="NONE",
            scale_factor=20.0,
            export_animations=True,
        )
        if "FINISHED" not in common_animation_result:
            raise RuntimeError(f"Mirrored basis animation export failed: {common_animation_result}")
        common_animation = None
        common_delta_y = None
        common_pitch_marker = None
        for animation_path in common_animation_dir.glob("*.anm"):
            candidate = read_animation(animation_path)
            if "body" not in candidate.bone_names or len(candidate.frames) < 2:
                continue
            delta = candidate.frames[-1]["body"].matrix[3][1] - candidate.frames[0]["body"].matrix[3][1]
            if abs(delta) > 1.0:
                common_animation = candidate
                common_delta_y = delta
                common_pitch_marker = candidate.frames[-1]["body"].matrix[0][2]
                break
        if common_animation is None:
            raise RuntimeError("Mirrored basis animation export did not produce an ANM probe.")
        if common_delta_y is None or common_delta_y <= 0.0:
            raise RuntimeError("Mirrored basis animation did not convert Blender-visible translation for GOH playback.")
        if common_pitch_marker is None or common_pitch_marker <= 0.05:
            raise RuntimeError("Mirrored basis animation did not invert the exported pitch delta for GOH playback.")
        basis_probe_child.animation_data_clear()
        basis_probe_child.location = Vector((1.0, 2.0, 3.0))
        basis_probe_child.rotation_euler = (0.0, 0.0, 0.0)
        mirror_probe_dir = basis_probe_dir / "mirrored_physics"
        mirror_probe_dir.mkdir(parents=True, exist_ok=True)
        mirror_probe_mesh = bpy.data.meshes.new("mirror_physics_probe_mesh")
        mirror_probe_mesh.from_pydata([(0.0, 0.0, 0.0), (0.2, 0.0, 0.0), (0.0, 0.2, 0.0)], [], [(0, 1, 2)])
        mirror_probe_mesh.update()

        mirror_source = bpy.data.objects.new("MirrorPhysicsSource", mirror_probe_mesh)
        mirror_link = bpy.data.objects.new("MirrorPhysicsLink", mirror_probe_mesh)
        scene.collection.objects.link(mirror_source)
        scene.collection.objects.link(mirror_link)
        for obj, bone_name, role, rest_location in (
            (mirror_source, "mirror_source", "SOURCE", Vector((0.0, 0.0, 0.0))),
            (mirror_link, "mirror_link", "BODY_SPRING", Vector((1.0, 0.25, 0.0))),
        ):
            obj.parent = basis_probe_basis
            obj.matrix_parent_inverse = Matrix.Identity(4)
            obj.location = rest_location
            obj["goh_bone_name"] = bone_name
            obj["goh_physics_role"] = role
            obj["goh_rest_matrix_local"] = matrix_prop(Matrix.Translation(rest_location))
            scene.frame_set(1)
            obj.keyframe_insert(data_path="location", frame=1)
            obj.location = rest_location + Vector((0.0, 0.5, 0.0))
            obj.keyframe_insert(data_path="location", frame=2)
            obj.location = rest_location
            if obj.animation_data and obj.animation_data.action:
                if role == "SOURCE":
                    obj.animation_data.action.name = "goh_recoil_source_mirror_probe"
                else:
                    obj.animation_data.action.name = "goh_linked_recoil_mirror_probe"
        bpy.ops.object.select_all(action="DESELECT")
        basis_probe_basis.select_set(True)
        mirror_source.select_set(True)
        mirror_link.select_set(True)
        bpy.context.view_layer.objects.active = mirror_link
        mirror_probe_result = bpy.ops.export_scene.goh_model(
            filepath=str(mirror_probe_dir / "mirror_physics_probe.mdl"),
            selection_only=True,
            include_hidden=True,
            axis_mode="NONE",
            scale_factor=20.0,
            export_animations=True,
        )
        if "FINISHED" not in mirror_probe_result:
            raise RuntimeError(f"Mirrored physics export probe failed: {mirror_probe_result}")
        mirror_animation = None
        source_delta_y = 0.0
        link_delta_y = 0.0
        for animation_path in mirror_probe_dir.glob("*.anm"):
            candidate = read_animation(animation_path)
            if "mirror_source" in candidate.bone_names and "mirror_link" in candidate.bone_names:
                candidate_source_delta_y = (
                    candidate.frames[-1]["mirror_source"].matrix[3][1]
                    - candidate.frames[0]["mirror_source"].matrix[3][1]
                )
                candidate_link_delta_y = (
                    candidate.frames[-1]["mirror_link"].matrix[3][1]
                    - candidate.frames[0]["mirror_link"].matrix[3][1]
                )
                if abs(candidate_source_delta_y) > 1.0 and abs(candidate_link_delta_y) > 1.0:
                    mirror_animation = candidate
                    source_delta_y = candidate_source_delta_y
                    link_delta_y = candidate_link_delta_y
                    break
        if mirror_animation is None:
            raise RuntimeError("Mirrored physics export probe did not write the source/link animation.")
        if source_delta_y >= 0.0:
            raise RuntimeError("Mirrored physics export did not convert the source recoil into GOH mirrored space.")
        if link_delta_y <= 0.0 or abs(abs(link_delta_y) - abs(source_delta_y)) > 0.05:
            raise RuntimeError("Mirrored physics link role animation was not reflected at export time.")
        bpy.data.objects.remove(mirror_source, do_unlink=True)
        bpy.data.objects.remove(mirror_link, do_unlink=True)
        if mirror_probe_mesh.users == 0:
            bpy.data.meshes.remove(mirror_probe_mesh)
        bpy.data.objects.remove(basis_probe_child, do_unlink=True)
        bpy.data.objects.remove(basis_probe_basis, do_unlink=True)
        if basis_probe_mesh.users == 0:
            bpy.data.meshes.remove(basis_probe_mesh)

        print("blender runtime test passed")
        for path in expected:
            print(path.name)
        for path in material_files:
            print(path.name)
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
