from __future__ import annotations

from pathlib import Path
import shutil
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PARENT = ROOT
if str(ADDON_PARENT) not in sys.path:
    sys.path.insert(0, str(ADDON_PARENT))

import blender_goh_gem_exporter as addon  # noqa: E402
from blender_goh_gem_exporter.goh_core import read_animation  # noqa: E402


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
        basis_settings.wheel_radius = 0.52
        basis_settings.steer_max = 31.0
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
        if basis_helper.get("Model") != "entity/-vehicle/tank_medium/runtime_test_vehicle":
            raise RuntimeError("Basis helper did not store the expected Model metadata.")

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
        material["goh_lightmap"] = "body_mask"
        material["goh_lightmap_options"] = "MipMap 1"
        material["goh_parallax_scale"] = 1.25
        material["goh_full_specular"] = True
        cube.data.materials.clear()
        cube.data.materials.append(material)
        cube["goh_lod_files"] = "body.ply;body_lod1.ply"
        cube["goh_lod_off"] = True

        tool_settings = scene.goh_tool_settings
        tool_settings.texture_scope = "SELECTED"
        texture_result = bpy.ops.scene.goh_report_textures()
        if "FINISHED" not in texture_result:
            raise RuntimeError(f"Texture report failed: {texture_result}")
        texture_report = bpy.data.texts.get("GOH_Texture_Report.txt")
        if texture_report is None or "BodyMaterial: body_mask" not in texture_report.as_string():
            raise RuntimeError("Texture report did not capture the expected GOH texture reference.")

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

        result = bpy.ops.export_scene.goh_model(
            filepath=str(output_file),
            selection_only=True,
            include_hidden=False,
            axis_mode="NONE",
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Export failed: {result}")

        expected = [
            output_dir / "runtime_test.mdl",
            output_dir / "body.ply",
            output_dir / "body.vol",
            output_dir / "body.anm",
            output_dir / "body_2.anm",
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
        anm_bytes = (output_dir / "body.anm").read_bytes()
        if anm_bytes[:4] != b"EANM":
            raise RuntimeError("body.anm does not look like a GOH animation file.")
        if int.from_bytes(anm_bytes[4:8], "little") != 0x00060000:
            raise RuntimeError("body.anm was expected to default to FRM2 / 0x00060000.")
        parsed = read_animation(output_dir / "body.anm")
        if not any(frame for frame in parsed.mesh_frames):
            raise RuntimeError("body.anm did not contain any mesh animation chunks.")

        cube.animation_data_clear()
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

        print("blender runtime test passed")
        for path in expected:
            print(path.name)
        for path in material_files:
            print(path.name)
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
