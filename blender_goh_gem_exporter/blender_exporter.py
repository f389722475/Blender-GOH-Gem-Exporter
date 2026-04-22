from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import math
import re
import struct
from typing import Iterable

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Matrix, Vector

from .goh_core import (
    AnimationFile,
    MeshAnimationState,
    AnimationState,
    BoneNode,
    ExportBundle,
    ExportError,
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
    sanitized_file_stem,
    write_export_bundle,
)


EPSILON = 1e-6
GOH_NATIVE_SCALE = 20.0
GOH_BASIS_HELPER_NAME = "Basis"

GOH_TRANSFORM_BLOCK_ITEMS = (
    ("AUTO", "Auto", "Write Position / Orientation / Matrix34 automatically based on the transform content"),
    ("ORIENTATION", "Orientation", "Prefer a pure {Orientation} block when the transform has no translation"),
    ("MATRIX34", "Matrix34", "Always write a {Matrix34} block"),
)


@dataclass
class AttachmentObject:
    obj: bpy.types.Object
    mesh_matrix: Matrix
    attach_bone: str


@dataclass(frozen=True)
class RawLoopVertex:
    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    uv: tuple[float, float]
    tangent: tuple[float, float, float]
    tangent_sign: float
    influences: tuple[tuple[str, float], ...]
    fallback_bone: str


@dataclass(frozen=True)
class AnimationClipSpec:
    name: str
    frame_start: int
    frame_end: int
    file_stem: str | None = None
    speed: float = 1.0
    smooth: float = 0.0
    resume: bool = False
    autostart: bool = False
    store: bool = False


@dataclass(frozen=True)
class MeshGroupKey:
    bone_name: str
    lod_level: int = 0


@dataclass
class MeshImportTarget:
    obj: bpy.types.Object
    export_to_source: list[int]
    mesh_bake_matrix: Matrix


@dataclass(frozen=True)
class GOHPartPreset:
    key: str
    label: str
    display_name: str
    export_name: str
    description: str


@dataclass(frozen=True)
class GOHRolePreset:
    key: str
    label: str
    description: str
    name_suffix: str = ""
    helper_flag: str | None = None
    collection_name: str | None = None
    default_shape_2d: str | None = None
    sets_attach_bone: bool = False


GOH_PART_PRESETS: tuple[GOHPartPreset, ...] = (
    GOHPartPreset("generic", "Generic Part", "Part", "part", "Generic visual part with no old 3ds Max baggage."),
    GOHPartPreset("body", "Body", "Body", "body", "Main hull or chassis section."),
    GOHPartPreset("turret", "Turret", "Turret", "turret", "Turret or rotating upper structure."),
    GOHPartPreset("gun", "Gun", "Gun", "gun", "Main cannon or articulated weapon mesh."),
    GOHPartPreset("gun_rot", "Gun_rot", "Gun_rot", "gun_rot", "Rotation pivot for a gun assembly."),
    GOHPartPreset("mgun", "Mgun", "Mgun", "mgun", "Machine-gun assembly."),
    GOHPartPreset("mgun_rot", "Mgun_rot", "Mgun_rot", "mgun_rot", "Machine-gun rotation or elevation pivot."),
    GOHPartPreset("engine", "Engine", "Engine", "engine", "Engine or transmission housing."),
    GOHPartPreset("wheel", "Wheel", "Wheel", "wheel", "Wheel, bogie, or roller section."),
    GOHPartPreset("track", "Track", "Track", "track", "Track mesh or track-related subpart."),
    GOHPartPreset("hatch", "Hatch", "Hatch", "hatch", "Door, hatch, or opening cover."),
    GOHPartPreset("headlight", "Headlight", "Headlight", "headlight", "Headlight or lamp assembly."),
    GOHPartPreset("ammo", "Ammo", "Ammo", "ammo", "Ammo rack, shell mesh, or ammunition box."),
    GOHPartPreset("fuel", "Fuel", "Fuel", "fuel", "Fuel tank or jerry-can part."),
    GOHPartPreset("decor", "Decor", "Decor", "decor", "Non-functional decorative visual mesh."),
    GOHPartPreset("armor", "Armor", "Armor", "armor", "Armor plate or shielded visual mesh."),
    GOHPartPreset("glass", "Glass", "Glass", "glass", "Window or glass mesh section."),
    GOHPartPreset("detail", "Detail", "Detail", "detail", "Small visual detail or miscellaneous mesh."),
    GOHPartPreset("mantlet", "Mantled", "Mantled", "mantled", "Mantlet or gun-shield housing."),
    GOHPartPreset("shield", "Shield", "Shield", "shield", "Generic shield section."),
    GOHPartPreset("shield_left", "Shield_Left", "Shield_Left", "shield_left", "Left shield collision or mesh section."),
    GOHPartPreset("shield_front", "Shield_Front", "Shield_Front", "shield_front", "Front shield collision or mesh section."),
    GOHPartPreset("shield_right", "Shield_Right", "Shield_Right", "shield_right", "Right shield collision or mesh section."),
    GOHPartPreset("wheel_l", "Wheell", "Wheell", "wheell", "Left-side wheel or wheel collision block."),
    GOHPartPreset("wheel_r", "Wheelr", "Wheelr", "wheelr", "Right-side wheel or wheel collision block."),
    GOHPartPreset("track_l", "TrackL", "TrackL", "trackl", "Left track mesh or collision block."),
    GOHPartPreset("track_r", "TrackR", "TrackR", "trackr", "Right track mesh or collision block."),
    GOHPartPreset("armor_l", "ArmorL", "ArmorL", "armorl", "Left armor collision block."),
    GOHPartPreset("armor_r", "ArmorR", "ArmorR", "armorr", "Right armor collision block."),
    GOHPartPreset("inventory", "Inventory", "Inventory", "inventory", "Inventory or stowage collision/helper block."),
    GOHPartPreset("ram", "Ram", "Ram", "ram", "Ramming collision/helper block."),
    GOHPartPreset("close", "Close", "Close", "close", "Obstacle helper for close / blocked zones."),
    GOHPartPreset("select", "Select", "Select", "select", "Selection or interaction helper zone."),
    GOHPartPreset("walk", "Walk", "Walk", "walk", "Area helper for walkable surfaces."),
    GOHPartPreset("trigger", "Trigger", "Trigger", "trigger", "Area helper used as a trigger zone."),
    GOHPartPreset("zone", "Zone", "Zone", "zone", "Generic named area zone."),
    GOHPartPreset("cover", "Cover", "Cover", "cover", "Obstacle or area helper for cover."),
    GOHPartPreset("block", "Block", "Block", "block", "Generic blocker helper."),
    GOHPartPreset("emit", "Emit1", "Emit1", "Emit1", "Crew / passenger emit marker."),
    GOHPartPreset("emit2", "Emit2", "Emit2", "Emit2", "Crew / passenger emit marker."),
    GOHPartPreset("emit3", "Emit3", "Emit3", "Emit3", "Crew / passenger emit marker."),
    GOHPartPreset("emit4", "Emit4", "Emit4", "Emit4", "Crew / passenger emit marker."),
    GOHPartPreset("emit_auto", "Emit* (Auto)", "Emit1", "Emit1", "Auto-numbered emit marker family used by the Max tool."),
    GOHPartPreset("seat", "Seat00", "Seat00", "Seat00", "Seat / placer helper with padded numbering."),
    GOHPartPreset("commander", "Commander", "Commander", "Commander", "Commander placement helper."),
    GOHPartPreset("driver", "Driver", "Driver", "Driver", "Driver placement helper."),
    GOHPartPreset("gunner", "Gunner", "Gunner", "Gunner", "Gunner placement helper."),
    GOHPartPreset("visor", "Visor", "Visor", "Visor", "Driver or sight helper without numbering."),
    GOHPartPreset("visor1", "Visor1", "Visor1", "Visor1", "Driver or turret-linked visor helper."),
    GOHPartPreset("visor2", "Visor2", "Visor2", "Visor2", "Secondary visor helper."),
    GOHPartPreset("pivot_front", "Pivot_Front", "Pivot_Front", "Pivot_Front", "Front pivot dummy."),
    GOHPartPreset("pivot_back", "Pivot_Back", "Pivot_Back", "Pivot_Back", "Rear pivot dummy."),
    GOHPartPreset("steerl", "SteerL", "SteerL", "SteerL", "Left steering dummy."),
    GOHPartPreset("steerr", "SteerR", "SteerR", "SteerR", "Right steering dummy."),
    GOHPartPreset("springl", "SpringL", "SpringL", "SpringL", "Left suspension spring dummy."),
    GOHPartPreset("springr", "SpringR", "SpringR", "SpringR", "Right suspension spring dummy."),
    GOHPartPreset("wheelsl", "WheelsL", "WheelsL", "WheelsL", "Left support-wheel dummy."),
    GOHPartPreset("wheelsr", "WheelsR", "WheelsR", "WheelsR", "Right support-wheel dummy."),
    GOHPartPreset("wheelsupport_l", "WheelSL", "WheelSL", "WheelSL", "Left small support wheel dummy."),
    GOHPartPreset("wheelsupport_r", "WheelSR", "WheelSR", "WheelSR", "Right small support wheel dummy."),
    GOHPartPreset("link1", "Link1", "Link1", "Link1", "Dummy link helper."),
    GOHPartPreset("link2", "Link2", "Link2", "Link2", "Second dummy link helper."),
    GOHPartPreset("support1", "Support1", "Support1", "Support1", "Support helper."),
    GOHPartPreset("support2", "Support2", "Support2", "Support2", "Support helper."),
    GOHPartPreset("support3", "Support3", "Support3", "Support3", "Support helper."),
    GOHPartPreset("handle", "Handle", "Handle", "Handle", "Handle helper used by some weapon templates."),
    GOHPartPreset("foresight1", "Foresight1", "Foresight1", "Foresight1", "Primary foresight / muzzle reference point."),
    GOHPartPreset("foresight3", "Foresight3", "Foresight3", "Foresight3", "Additional foresight marker."),
    GOHPartPreset("foresight4", "Foresight4", "Foresight4", "Foresight4", "MG or alternate foresight marker."),
    GOHPartPreset("foresight5", "Foresight5", "Foresight5", "Foresight5", "Additional foresight marker."),
    GOHPartPreset("foresight6", "Foresight6", "Foresight6", "Foresight6", "Additional foresight marker."),
    GOHPartPreset("fx_trace_l1", "fxTraceL1", "fxTraceL1", "fxTraceL1", "Left tracer effect marker."),
    GOHPartPreset("fx_trace_l2", "fxTraceL2", "fxTraceL2", "fxTraceL2", "Left tracer effect marker."),
    GOHPartPreset("fx_trace_r1", "fxTraceR1", "fxTraceR1", "fxTraceR1", "Right tracer effect marker."),
    GOHPartPreset("fx_trace_r2", "fxTraceR2", "fxTraceR2", "fxTraceR2", "Right tracer effect marker."),
    GOHPartPreset("fx_dust", "fxDust", "fxDust", "fxDust", "Dust effect marker."),
    GOHPartPreset("fx_light", "fxLight", "fxLight", "fxLight", "Light or flare effect marker."),
    GOHPartPreset("headlight_l", "HeadlightL", "HeadlightL", "HeadlightL", "Left headlight effect marker."),
    GOHPartPreset("headlight_r", "HeadlightR", "HeadlightR", "HeadlightR", "Right headlight effect marker."),
    GOHPartPreset("fx_fire1", "fxFire1", "fxFire1", "fxFire1", "Fire effect marker."),
    GOHPartPreset("fx_fire2", "fxFire2", "fxFire2", "fxFire2", "Fire effect marker."),
    GOHPartPreset("fx_fire3", "fxFire3", "fxFire3", "fxFire3", "Fire effect marker."),
    GOHPartPreset("fx_smoke1", "fxSmoke1", "fxSmoke1", "fxSmoke1", "Smoke effect marker."),
    GOHPartPreset("fx_smoke2", "fxSmoke2", "fxSmoke2", "fxSmoke2", "Smoke effect marker."),
    GOHPartPreset("fx_stop1", "fxStop1", "fxStop1", "fxStop1", "Stop or brake effect marker."),
    GOHPartPreset("fx_stop2", "fxStop2", "fxStop2", "fxStop2", "Stop or brake effect marker."),
    GOHPartPreset("fx_shell1", "fxShell1", "fxShell1", "fxShell1", "Shell-eject effect marker."),
    GOHPartPreset("fx_invers", "fx_Invers", "fx_Invers", "fx_Invers", "Inverse / mirrored effect marker."),
    GOHPartPreset("fx_steam", "fxSteam", "fxSteam", "fxSteam", "Steam or vapor effect marker."),
    GOHPartPreset("fxshell", "FxShell", "FxShell", "FxShell", "Weapon shell or point helper used by the old Max weapon tool."),
    GOHPartPreset("carriage", "Carriage", "Carriage", "carriage", "Carriage or sidecar visual part."),
    GOHPartPreset("carriage1", "Carriage1", "Carriage1", "carriage1", "Primary cannon carriage part."),
    GOHPartPreset("carriage2", "Carriage2", "Carriage2", "carriage2", "Secondary cannon carriage part."),
    GOHPartPreset("cartridge_belt", "Cartridge_Belt", "Cartridge_Belt", "cartridge_belt", "Ammo belt or cartridge feed visual part."),
    GOHPartPreset("steerrudder", "SteerRudder", "SteerRudder", "steerrudder", "Car steering rudder or steering helper."),
    GOHPartPreset("steerl1", "SteerL1", "SteerL1", "SteerL1", "Left cannon steering dummy."),
    GOHPartPreset("steerr1", "SteerR1", "SteerR1", "SteerR1", "Right cannon steering dummy."),
    GOHPartPreset("springl2", "SpringL2", "SpringL2", "SpringL2", "Left cannon suspension helper."),
    GOHPartPreset("springr2", "SpringR2", "SpringR2", "SpringR2", "Right cannon suspension helper."),
    GOHPartPreset("standl", "StandL", "StandL", "standl", "Left stabilizer or stand part."),
    GOHPartPreset("standr", "StandR", "StandR", "standr", "Right stabilizer or stand part."),
    GOHPartPreset("shankl", "ShankL", "ShankL", "shankl", "Left stand shank or linkage part."),
    GOHPartPreset("shankr", "ShankR", "ShankR", "shankr", "Right stand shank or linkage part."),
    GOHPartPreset("stan1", "Stan1", "Stan1", "stan1", "Cannon stand visual mesh that often behaves like CommonMesh."),
    GOHPartPreset("stan2", "Stan2", "Stan2", "stan2", "Cannon stand visual mesh that often behaves like CommonMesh."),
    GOHPartPreset("stan3", "Stan3", "Stan3", "stan3", "Cannon stand visual mesh that often behaves like CommonMesh."),
)

GOH_PART_PRESET_MAP = {preset.key: preset for preset in GOH_PART_PRESETS}

GOH_ROLE_PART_KEYS: dict[str, tuple[str, ...]] = {
    "visual": (
        "generic",
        "body",
        "turret",
        "gun",
        "gun_rot",
        "mgun",
        "mgun_rot",
        "engine",
        "wheel",
        "track",
        "hatch",
        "headlight",
        "ammo",
        "fuel",
        "decor",
        "armor",
        "glass",
        "detail",
        "mantlet",
        "shield",
        "shield_left",
        "shield_front",
        "shield_right",
    ),
    "attachment": (
        "generic",
        "emit",
        "emit2",
        "emit3",
        "emit4",
        "emit_auto",
        "seat",
        "commander",
        "driver",
        "gunner",
        "visor",
        "visor1",
        "visor2",
        "pivot_front",
        "pivot_back",
        "steerl",
        "steerr",
        "springl",
        "springr",
        "wheelsl",
        "wheelsr",
        "wheelsupport_l",
        "wheelsupport_r",
        "link1",
        "link2",
        "support1",
        "support2",
        "support3",
        "handle",
    ),
    "volume": (
        "body",
        "engine",
        "fuel",
        "turret",
        "gun",
        "wheel_l",
        "wheel_r",
        "track_l",
        "track_r",
        "shield",
        "shield_left",
        "shield_front",
        "shield_right",
        "mantlet",
        "inventory",
        "ram",
        "armor_l",
        "armor_r",
        "detail",
        "generic",
    ),
    "obstacle": (
        "generic",
        "close",
        "select",
        "cover",
        "block",
        "body",
        "track",
        "decor",
    ),
    "area": (
        "generic",
        "walk",
        "trigger",
        "zone",
        "select",
        "cover",
        "body",
        "track",
    ),
    "fx": (
        "foresight1",
        "foresight3",
        "foresight4",
        "foresight5",
        "foresight6",
        "fx_trace_l1",
        "fx_trace_l2",
        "fx_trace_r1",
        "fx_trace_r2",
        "fx_dust",
        "fx_light",
        "headlight_l",
        "headlight_r",
        "fx_fire1",
        "fx_fire2",
        "fx_fire3",
        "fx_smoke1",
        "fx_smoke2",
        "fx_stop1",
        "fx_stop2",
        "fx_shell1",
        "fxshell",
        "fx_invers",
        "fx_steam",
    ),
}

GOH_TEMPLATE_FAMILY_ITEMS = (
    ("GENERIC", "Generic", "Show the full general-purpose GOH preset library"),
    ("TANK", "Tank", "Filter parts to the common tank-style MultiScript naming set"),
    ("CAR", "Car", "Filter parts to the common car / truck / motorcycle naming set"),
    ("CANNON", "Cannon", "Filter parts to the towed-gun / cannon naming set"),
    ("WEAPON", "Weapon", "Filter parts to the old MultiScript weapon helper naming set"),
)

GOH_TEMPLATE_ROLE_PART_KEYS: dict[str, dict[str, tuple[str, ...]]] = {
    "GENERIC": GOH_ROLE_PART_KEYS,
    "TANK": {
        "visual": ("body", "engine", "turret", "gun_rot", "gun", "mgun", "mgun_rot", "ammo", "hatch", "detail", "mantlet"),
        "attachment": ("emit_auto", "emit", "emit2", "emit3", "emit4", "seat", "commander", "driver", "gunner", "visor", "visor1", "visor2"),
        "volume": ("body", "engine", "turret", "gun", "track_l", "track_r", "mantlet", "inventory", "ram", "armor_l", "armor_r", "detail"),
        "obstacle": ("close", "select", "cover", "body", "track"),
        "area": ("walk", "trigger", "zone", "select", "cover", "body", "track"),
        "fx": ("foresight1", "foresight3", "foresight4", "foresight5", "foresight6", "fx_trace_l1", "fx_trace_l2", "fx_trace_r1", "fx_trace_r2", "fx_dust", "fx_light", "headlight_l", "headlight_r", "fx_fire1", "fx_fire2", "fx_fire3", "fx_smoke1", "fx_smoke2", "fx_stop1", "fx_stop2"),
    },
    "CAR": {
        "visual": ("body", "engine", "armor", "hatch", "wheel", "glass", "fuel", "detail", "gun_rot", "gun", "mgun_rot", "mgun", "carriage", "steerrudder"),
        "attachment": ("emit_auto", "emit", "emit2", "emit3", "emit4", "seat", "commander", "driver", "gunner", "visor", "visor1", "visor2", "pivot_front", "pivot_back", "steerl", "steerr", "springl", "springr", "wheelsl", "wheelsr"),
        "volume": ("body", "engine", "armor", "wheel_l", "wheel_r", "glass", "fuel", "detail", "turret", "gun"),
        "obstacle": ("close", "select", "cover", "body"),
        "area": ("walk", "trigger", "zone", "select", "cover", "body"),
        "fx": ("fx_trace_l1", "fx_trace_l2", "fx_trace_r1", "fx_trace_r2", "fx_dust", "fx_light", "headlight_l", "headlight_r", "fx_fire1", "fx_fire2", "fx_smoke1", "fx_smoke2", "fx_stop1", "fx_stop2", "foresight1", "foresight3", "foresight4", "foresight5", "foresight6"),
    },
    "CANNON": {
        "visual": ("body", "turret", "shield_left", "shield_front", "shield_right", "shield", "gun_rot", "gun", "mgun_rot", "mgun", "carriage1", "carriage2", "cartridge_belt", "detail", "standl", "standr", "shankl", "shankr", "stan1", "stan2", "stan3"),
        "attachment": ("pivot_front", "pivot_back", "steerl1", "steerr1", "wheel_r", "springl2", "springr2", "link1", "link2", "support1", "support2", "support3", "seat", "commander", "driver", "gunner", "visor", "visor1", "visor2"),
        "volume": ("body", "engine", "fuel", "shield_left", "shield_front", "shield_right", "shield", "wheel_l", "wheel_r", "detail", "turret", "gun"),
        "obstacle": ("close", "select", "cover", "body"),
        "area": ("walk", "trigger", "zone", "body"),
        "fx": ("foresight1", "foresight3", "foresight4", "foresight5", "foresight6", "fx_trace_l1", "fx_trace_l2", "fx_trace_r1", "fx_trace_r2", "fx_dust", "fx_shell1", "fxshell", "fx_invers"),
    },
    "WEAPON": {
        "visual": ("generic", "body", "detail"),
        "attachment": ("handle",),
        "volume": ("body", "select", "generic"),
        "obstacle": ("select",),
        "area": ("trigger",),
        "fx": ("foresight3", "fxshell"),
    },
}

GOH_ROLE_PRESETS: tuple[GOHRolePreset, ...] = (
    GOHRolePreset("visual", "Visual Mesh", "Standard visible GOH mesh part."),
    GOHRolePreset(
        "attachment",
        "Dummy / Placer",
        "Named dummy, placer, or helper node that should explicitly attach to a GOH bone.",
        sets_attach_bone=True,
    ),
    GOHRolePreset(
        "volume",
        "Collision Volume",
        "3D collision volume helper. Links to GOH_VOLUMES and writes volume metadata.",
        name_suffix="_vol",
        helper_flag="goh_is_volume",
        collection_name="GOH_VOLUMES",
    ),
    GOHRolePreset(
        "obstacle",
        "Obstacle (2D)",
        "2D obstacle helper. Links to GOH_OBSTACLES and defaults to Obb2.",
        name_suffix="_obstacle",
        helper_flag="goh_is_obstacle",
        collection_name="GOH_OBSTACLES",
        default_shape_2d="obb2",
    ),
    GOHRolePreset(
        "area",
        "Area (2D)",
        "2D area helper. Links to GOH_AREAS and defaults to Polygon2.",
        name_suffix="_area",
        helper_flag="goh_is_area",
        collection_name="GOH_AREAS",
        default_shape_2d="polygon2",
    ),
    GOHRolePreset("fx", "Effect / Marker", "Named effect marker without collision/helper flags."),
)

GOH_ROLE_PRESET_MAP = {preset.key: preset for preset in GOH_ROLE_PRESETS}
GOH_ROLE_PRESET_ITEMS = [
    (preset.key, preset.label, preset.description)
    for preset in GOH_ROLE_PRESETS
]

GOH_HELPER_FLAGS = ("goh_is_volume", "goh_is_obstacle", "goh_is_area")
GOH_HELPER_COLLECTIONS = ("GOH_VOLUMES", "GOH_OBSTACLES", "GOH_AREAS")
GOH_TRANSLATION_CONTEXTS = ("*", "GOH_PRESET")
GOH_TRANSLATION_LOCALES = ("zh_CN", "zh_HANS", "zh_TW")
GOH_TRANSLATION_DOMAIN = f"{__package__ or __name__}.goh_en_labels"

GOH_LEGACY_TEXT_FALLBACKS: dict[str, tuple[str, ...]] = {
    "goh_attach_bone": ("bone", "attachbone", "parent"),
    "goh_bone_name": ("id",),
    "goh_bone_type": ("bonetype",),
    "goh_component": ("component",),
    "goh_shape_name": ("id", "name"),
    "goh_shape_2d": ("shape", "shape2d"),
    "goh_tags": ("tags",),
    "goh_transform_block": ("transform",),
    "goh_volume_bone": ("bone",),
    "goh_volume_name": ("id", "name"),
}

GOH_LEGACY_FLOAT_FALLBACKS: dict[str, tuple[str, ...]] = {
    "goh_density": ("density",),
    "goh_speed": ("ikspeed", "speed"),
}

GOH_LEGACY_INT_FALLBACKS: dict[str, tuple[str, ...]] = {
    "goh_layer": ("layer",),
    "goh_visibility": ("visibility",),
}

GOH_LEGACY_BOOL_FLAGS: dict[str, tuple[str, ...]] = {
    "goh_force_mesh_animation": ("commonmesh",),
    "goh_is_volume": ("volume",),
    "goh_lod_off": ("off",),
    "goh_rotate_2d": ("rotate",),
    "goh_speed2": ("speed2",),
    "goh_terminator": ("terminator",),
}


def _build_translation_overrides() -> dict[str, dict[tuple[str, str], str]]:
    msgids = {
        preset.label
        for preset in GOH_PART_PRESETS
    }
    msgids.update(preset.label for preset in GOH_ROLE_PRESETS)
    msgids.update(label for _key, label, _description in GOH_TEMPLATE_FAMILY_ITEMS)
    msgids.update(
        {
            "Poly",
            "CommonMesh",
            "Body_vol",
            "Select_vol",
            "Foresight3",
            "Handle",
            "FxShell",
            "Polyhedron (.vol)",
            "Primitive Box",
            "Primitive Sphere",
            "Primitive Cylinder",
            "X Axis",
            "Y Axis",
            "Z Axis",
            "Force",
            "Clear",
            "Leave",
            "Blender -> GOH (Legacy)",
            "None / GOH Native",
            "Auto",
            "Orientation",
            "Matrix34",
        }
    )
    translations: dict[str, dict[tuple[str, str], str]] = {}
    for locale in GOH_TRANSLATION_LOCALES:
        locale_map: dict[tuple[str, str], str] = {}
        for context in GOH_TRANSLATION_CONTEXTS:
            for msgid in msgids:
                locale_map[(context, msgid)] = msgid
        translations[locale] = locale_map
    return translations


GOH_TRANSLATION_OVERRIDES = _build_translation_overrides()


def _part_keys_for_role(role_key: str, family_key: str = "GENERIC") -> tuple[str, ...]:
    template_map = GOH_TEMPLATE_ROLE_PART_KEYS.get(family_key, GOH_TEMPLATE_ROLE_PART_KEYS["GENERIC"])
    return template_map.get(role_key, GOH_ROLE_PART_KEYS.get(role_key, GOH_ROLE_PART_KEYS["visual"]))


def _part_items_for_role(role_key: str, family_key: str = "GENERIC") -> list[tuple[str, str, str]]:
    items: list[tuple[str, str, str]] = []
    for key in _part_keys_for_role(role_key, family_key):
        preset = GOH_PART_PRESET_MAP[key]
        items.append((preset.key, preset.label, preset.description))
    return items


def _resolve_part_preset(role_key: str, part_key: str, family_key: str = "GENERIC") -> GOHPartPreset:
    allowed = _part_keys_for_role(role_key, family_key)
    if part_key in allowed:
        return GOH_PART_PRESET_MAP[part_key]
    return GOH_PART_PRESET_MAP[allowed[0]]


def _goh_part_items(settings, _context):
    role_key = getattr(settings, "role", "visual")
    family_key = getattr(settings, "template_family", "GENERIC")
    return _part_items_for_role(role_key, family_key)


def _goh_role_updated(settings, _context) -> None:
    allowed = _part_keys_for_role(getattr(settings, "role", "visual"), getattr(settings, "template_family", "GENERIC"))
    if getattr(settings, "part", "") not in allowed:
        settings.part = allowed[0]


def _goh_template_updated(settings, _context) -> None:
    _goh_role_updated(settings, _context)


GOH_BASIS_ENTITY_TYPE_ITEMS = (
    ("GAME_ENTITY", "Game_Entity", "Legacy MultiScript Game_Entity type"),
    ("ENTITY", "Entity", "Legacy MultiScript Entity type"),
    ("ARMORED_CAR", "ArmoredCar", "Legacy MultiScript ArmoredCar type"),
)

GOH_BASIS_PATH_ITEMS = (
    ("CAR", "vehicle/car", "entity/-vehicle/car/"),
    ("BTR", "vehicle/btr", "entity/-vehicle/btr/"),
    ("TANK_LIGHT", "vehicle/tank_light", "entity/-vehicle/tank_light/"),
    ("TANK_MEDIUM", "vehicle/tank_medium", "entity/-vehicle/tank_medium/"),
    ("TANK_HEAVY", "vehicle/tank_heavy", "entity/-vehicle/tank_heavy/"),
    ("MARINE", "vehicle/marine", "entity/-vehicle/marine/"),
    ("TRAIN", "vehicle/train", "entity/-vehicle/train/"),
    ("ENTITY", "entity", "entity/"),
    ("CUSTOM", "Custom", "Use a custom entity path"),
)


class GOHAddonPresetSettings(PropertyGroup):
    template_family: EnumProperty(
        name="Template Family",
        items=GOH_TEMPLATE_FAMILY_ITEMS,
        default="GENERIC",
        update=_goh_template_updated,
        translation_context="GOH_PRESET",
    )
    role: EnumProperty(
        name="Role",
        items=GOH_ROLE_PRESET_ITEMS,
        default="visual",
        update=_goh_role_updated,
        translation_context="GOH_PRESET",
    )
    part: EnumProperty(name="Part", items=_goh_part_items, translation_context="GOH_PRESET")
    target_name: StringProperty(
        name="Target Bone / ID",
        description="Optional attach or volume target override. Leave empty to derive it from the selected part preset",
        default="",
    )
    volume_kind: EnumProperty(
        name="Volume Kind",
        items=(
            ("POLYHEDRON", "Polyhedron (.vol)", "Export a triangulated .vol polyhedron collision mesh"),
            ("BOX", "Primitive Box", "Write an inline {Box ...} volume block into the .mdl"),
            ("SPHERE", "Primitive Sphere", "Write an inline {Sphere ...} volume block into the .mdl"),
            ("CYLINDER", "Primitive Cylinder", "Write an inline {Cylinder ...} volume block into the .mdl"),
        ),
        default="POLYHEDRON",
        translation_context="GOH_PRESET",
    )
    volume_axis: EnumProperty(
        name="Cylinder Axis",
        items=(
            ("X", "X Axis", "Treat the object's local X axis as the cylinder length axis"),
            ("Y", "Y Axis", "Treat the object's local Y axis as the cylinder length axis"),
            ("Z", "Z Axis", "Treat the object's local Z axis as the cylinder length axis"),
        ),
        default="Z",
        translation_context="GOH_PRESET",
    )
    rename_objects: BoolProperty(
        name="Rename Objects",
        description="Rename selected objects to the preset's display names",
        default=True,
    )
    write_export_names: BoolProperty(
        name="Write GOH Names",
        description="Write the preset's export names into GOH custom properties such as goh_bone_name / goh_volume_name",
        default=True,
    )
    auto_number: BoolProperty(
        name="Auto Number",
        description="When multiple objects are selected, append numeric suffixes so each generated name stays unique",
        default=True,
    )
    helper_collections: BoolProperty(
        name="Link Helper Collections",
        description="Link helper objects into GOH_VOLUMES / GOH_OBSTACLES / GOH_AREAS collections automatically",
        default=True,
    )
    clear_conflicts: BoolProperty(
        name="Clear Conflicts",
        description="Clear conflicting GOH helper flags and unlink from other GOH helper collections when applying a preset",
        default=True,
    )
    mesh_animation_mode: EnumProperty(
        name="Mesh Animation",
        items=(
            ("LEAVE", "Leave", "Keep goh_force_mesh_animation unchanged"),
            ("FORCE", "Force", "Set goh_force_mesh_animation = true on the selected objects"),
            ("CLEAR", "Clear", "Remove goh_force_mesh_animation from the selected objects"),
        ),
        default="LEAVE",
        translation_context="GOH_PRESET",
    )


class GOHBasisSettings(PropertyGroup):
    enabled: BoolProperty(name="Enable Basis Metadata", default=False)
    vehicle_name: StringProperty(
        name="Vehicle Name",
        description="Name used by the legacy MultiScript Basis helper and as the default exported model stem",
        default="",
    )
    entity_type: EnumProperty(
        name="Type",
        items=GOH_BASIS_ENTITY_TYPE_ITEMS,
        default="GAME_ENTITY",
        translation_context="GOH_PRESET",
    )
    entity_path: EnumProperty(
        name="Entity Path",
        items=GOH_BASIS_PATH_ITEMS,
        default="CAR",
        translation_context="GOH_PRESET",
    )
    entity_path_custom: StringProperty(
        name="Custom Path",
        description="Custom entity path prefix used when Entity Path is set to Custom",
        default="entity/",
    )
    wheel_radius: FloatProperty(name="Wheelradius", default=0.48, min=0.0, soft_max=100.0)
    steer_max: FloatProperty(name="SteerMax", default=28.0, min=0.0, soft_max=360.0)
    animation_enabled: BoolProperty(name="Legacy Animation Clips", default=False)
    start_enabled: BoolProperty(name="Start", default=False)
    start_range: StringProperty(name="Start Range", default="")
    stop_enabled: BoolProperty(name="Stop", default=False)
    stop_range: StringProperty(name="Stop Range", default="")
    fire_enabled: BoolProperty(name="Fire", default=False)
    fire_range: StringProperty(name="Fire Range", default="")


class GOHToolSettings(PropertyGroup):
    transform_block: EnumProperty(
        name="Transform Block",
        items=GOH_TRANSFORM_BLOCK_ITEMS,
        default="AUTO",
        translation_context="GOH_PRESET",
    )
    texture_scope: EnumProperty(
        name="Texture Scope",
        items=(
            ("SELECTED", "Selected", "Report textures used by the selected objects"),
            ("VISIBLE", "Visible", "Report textures used by all visible objects in the current view layer"),
            ("ALL", "All", "Report textures used by every material in the .blend file"),
        ),
        default="SELECTED",
        translation_context="GOH_PRESET",
    )


def _numbered_identifier(base: str, index: int, auto_number: bool) -> str:
    text = (base or "part").strip() or "part"
    if not auto_number or index <= 0:
        return text
    match = re.search(r"(\d+)$", text)
    if match:
        digits = match.group(1)
        start = int(digits)
        next_value = start + index
        replacement = str(next_value).zfill(len(digits))
        return f"{text[:-len(digits)]}{replacement}"
    return f"{text}{index + 1}"


def _numbered_display_name(base: str, suffix: str, index: int, auto_number: bool) -> str:
    return f"{_numbered_identifier(base, index, auto_number)}{suffix}"


def _remove_custom_prop(owner, key: str) -> None:
    if owner is not None and key in owner:
        del owner[key]


def _set_custom_bool_prop(owner, key: str, enabled: bool) -> None:
    if enabled:
        owner[key] = True
    else:
        _remove_custom_prop(owner, key)


def _set_custom_text_prop(owner, key: str, value: str | None) -> None:
    text = (value or "").strip()
    if text:
        owner[key] = text
    else:
        _remove_custom_prop(owner, key)


def _basis_entity_type_value(settings: GOHBasisSettings) -> str:
    return {
        "GAME_ENTITY": "Game_Entity",
        "ENTITY": "Entity",
        "ARMORED_CAR": "ArmoredCar",
    }.get(settings.entity_type, "Game_Entity")


def _basis_entity_path_value(settings: GOHBasisSettings) -> str:
    if settings.entity_path == "CUSTOM":
        text = (settings.entity_path_custom or "").strip()
        return text or "entity/"
    return dict((key, value) for key, _label, value in GOH_BASIS_PATH_ITEMS).get(settings.entity_path, "entity/-vehicle/car/")


def _basis_model_value(settings: GOHBasisSettings) -> str | None:
    vehicle_name = (settings.vehicle_name or "").strip()
    if not vehicle_name:
        return None
    return f"{_basis_entity_path_value(settings)}{vehicle_name}"


def _basis_legacy_lines(settings: GOHBasisSettings) -> list[str]:
    if not settings.enabled:
        return []
    lines = [
        f"Type={_basis_entity_type_value(settings)}",
    ]
    model_value = _basis_model_value(settings)
    if model_value:
        lines.append(f"Model={model_value}")
    lines.append(f"Wheelradius={settings.wheel_radius:g}")
    lines.append(f"SteerMax={settings.steer_max:g}")
    if settings.animation_enabled:
        for enabled, name, bone_name, frame_range, frame_rate in (
            (settings.start_enabled, "start", "body", settings.start_range, 60),
            (settings.stop_enabled, "stop", "body", settings.stop_range, 60),
            (settings.fire_enabled, "fire", "fire", settings.fire_range, 60),
        ):
            text = (frame_range or "").strip()
            if enabled and text:
                lines.append(f"Animation={name},{bone_name},{text},{frame_rate}")
    return lines


def _basis_legacy_text(settings: GOHBasisSettings) -> str:
    return "\n".join(_basis_legacy_lines(settings))


def _legacy_flag_set(text: str) -> set[str]:
    flags: set[str] = set()
    for line in text.replace("\r", "\n").split("\n"):
        token = line.strip()
        if not token or "=" in token:
            continue
        flags.add(token.lower())
    return flags


def _legacy_key_values(text: str) -> dict[str, list[str]]:
    data: dict[str, list[str]] = {}
    for line in text.replace("\r", "\n").split("\n"):
        token = line.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key:
            continue
        data.setdefault(key, []).append(value)
    return data


def _parse_frame_range(text: str) -> tuple[int, int] | None:
    match = re.match(r"^\s*(-?\d+)\s*-\s*(-?\d+)\s*$", text or "")
    if not match:
        return None
    start_frame = int(match.group(1))
    end_frame = int(match.group(2))
    return (start_frame, max(start_frame, end_frame))


def _ensure_scene_collection_link(scene: bpy.types.Scene, obj: bpy.types.Object) -> None:
    if scene.collection.objects.get(obj.name) is None:
        scene.collection.objects.link(obj)


def _preset_collection(scene: bpy.types.Scene, collection_name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.new(collection_name)
    if scene.collection.children.get(collection_name) is None:
        scene.collection.children.link(collection)
    return collection


def _clear_helper_state(
    scene: bpy.types.Scene,
    obj: bpy.types.Object,
    clear_collections: bool,
    keep_attach_bone: bool = False,
) -> None:
    for prop_name in GOH_HELPER_FLAGS:
        _remove_custom_prop(obj, prop_name)
    for prop_name in (
        "goh_volume_name",
        "goh_volume_bone",
        "goh_volume_kind",
        "goh_volume_axis",
        "goh_shape_name",
        "goh_shape_2d",
        "goh_rotate_2d",
    ):
        _remove_custom_prop(obj, prop_name)
    if not keep_attach_bone:
        _remove_custom_prop(obj, "goh_attach_bone")

    if not clear_collections:
        return

    removed_collection = False
    for collection in list(obj.users_collection):
        if collection.name not in GOH_HELPER_COLLECTIONS:
            continue
        collection.objects.unlink(obj)
        removed_collection = True
    if removed_collection and not obj.users_collection:
        _ensure_scene_collection_link(scene, obj)


def _link_to_helper_collection(scene: bpy.types.Scene, obj: bpy.types.Object, collection_name: str) -> None:
    collection = _preset_collection(scene, collection_name)
    if collection.objects.get(obj.name) is None:
        collection.objects.link(obj)


def _apply_goh_preset_to_object(
    scene: bpy.types.Scene,
    obj: bpy.types.Object,
    settings: GOHAddonPresetSettings,
    index: int,
) -> str:
    role_preset = GOH_ROLE_PRESET_MAP[settings.role]
    part_preset = _resolve_part_preset(settings.role, settings.part, settings.template_family)
    display_name = _numbered_display_name(part_preset.display_name, role_preset.name_suffix, index, settings.auto_number)
    export_name = _numbered_identifier(part_preset.export_name, index, settings.auto_number)
    target_override = settings.target_name.strip()
    target_name = target_override or export_name

    if settings.clear_conflicts:
        _clear_helper_state(scene, obj, settings.helper_collections, keep_attach_bone=role_preset.sets_attach_bone)

    if settings.rename_objects:
        obj.name = display_name

    if settings.mesh_animation_mode == "FORCE":
        _set_custom_bool_prop(obj, "goh_force_mesh_animation", True)
    elif settings.mesh_animation_mode == "CLEAR":
        _remove_custom_prop(obj, "goh_force_mesh_animation")

    if role_preset.key in {"visual", "attachment", "fx"}:
        if settings.write_export_names:
            _set_custom_text_prop(obj, "goh_bone_name", export_name)
        elif role_preset.key != "attachment":
            _remove_custom_prop(obj, "goh_bone_name")
    else:
        _remove_custom_prop(obj, "goh_bone_name")

    if role_preset.sets_attach_bone:
        _set_custom_text_prop(obj, "goh_attach_bone", target_name)

    if role_preset.helper_flag:
        _set_custom_bool_prop(obj, role_preset.helper_flag, True)
    if role_preset.collection_name and settings.helper_collections:
        _link_to_helper_collection(scene, obj, role_preset.collection_name)

    if role_preset.key == "volume":
        if settings.write_export_names:
            _set_custom_text_prop(obj, "goh_volume_name", export_name)
        _set_custom_text_prop(obj, "goh_volume_bone", target_name)
        _set_custom_text_prop(obj, "goh_volume_kind", settings.volume_kind.lower())
        if settings.volume_kind == "CYLINDER":
            _set_custom_text_prop(obj, "goh_volume_axis", settings.volume_axis.lower())
        else:
            _remove_custom_prop(obj, "goh_volume_axis")
    elif role_preset.key in {"obstacle", "area"}:
        if settings.write_export_names:
            _set_custom_text_prop(obj, "goh_shape_name", export_name)
        if role_preset.default_shape_2d:
            _set_custom_text_prop(obj, "goh_shape_2d", role_preset.default_shape_2d)
        _remove_custom_prop(obj, "goh_volume_kind")
        _remove_custom_prop(obj, "goh_volume_axis")
    else:
        _remove_custom_prop(obj, "goh_volume_kind")
        _remove_custom_prop(obj, "goh_volume_axis")

    return obj.name


class GOHBlenderExporter:
    def __init__(self, context: bpy.types.Context, operator: "EXPORT_SCENE_OT_goh_model") -> None:
        self.context = context
        self.operator = operator
        self.depsgraph = context.evaluated_depsgraph_get()
        self.axis_rotation = self._axis_rotation_matrix(operator.axis_mode)
        self.scale_factor = operator.scale_factor
        self.output_path = Path(operator.filepath)
        self.model_name = sanitized_file_stem(self.output_path.stem)
        self.basis_name = operator.basis_name.strip() or "basis"
        self.volume_collection_name = operator.volume_collection_name.strip() or "GOH_VOLUMES"
        self.obstacle_collection_name = operator.obstacle_collection_name.strip() or "GOH_OBSTACLES"
        self.area_collection_name = operator.area_collection_name.strip() or "GOH_AREAS"
        self.basis_settings: GOHBasisSettings | None = getattr(context.scene, "goh_basis_settings", None)
        self.basis_helper = self._find_basis_helper_object()
        self.warnings: list[str] = []
        self.material_cache: dict[tuple[str, int], MaterialDef] = {}
        self.file_name_counts: dict[str, int] = {}
        self.bone_file_names: dict[str, str] = {}
        self.volume_file_names: dict[str, str] = {}
        self.legacy_cache: dict[int, tuple[set[str], dict[str, list[str]]]] = {}
        self.armature_obj: bpy.types.Object | None = None
        self.armature_bone_order: list[str] = []
        self.mesh_groups: dict[MeshGroupKey, list[AttachmentObject]] = {}
        self.group_representatives: dict[MeshGroupKey, bpy.types.Object] = {}
        self.animation_attachments: dict[str, list[AttachmentObject]] = {}

    def export(self) -> tuple[ExportBundle, list[str]]:
        visual_objects, volume_objects, obstacle_objects, area_objects = self._collect_scope_objects()
        self.armature_obj = self._find_single_armature(visual_objects)
        if self.armature_obj:
            self.armature_bone_order = [bone.name for bone in self.armature_obj.data.bones]

        if self.armature_obj:
            bundle = self._build_armature_bundle(visual_objects, volume_objects, obstacle_objects, area_objects)
        else:
            bundle = self._build_object_bundle(visual_objects, volume_objects, obstacle_objects, area_objects)

        if self.operator.export_animations:
            self._attach_animations(bundle, visual_objects)

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        write_export_bundle(self.output_path.parent, bundle)
        return bundle, self.warnings

    def _collect_scope_objects(
        self,
    ) -> tuple[set[bpy.types.Object], list[bpy.types.Object], list[bpy.types.Object], list[bpy.types.Object]]:
        scope: set[bpy.types.Object] = set()
        if self.operator.selection_only:
            for obj in self.context.selected_objects:
                scope.update(self._iter_descendants(obj))
        else:
            scope = set(self.context.collection.all_objects)

        if not self.operator.include_hidden:
            scope = {obj for obj in scope if not self._is_hidden(obj)}

        obstacle_objects = [obj for obj in scope if self._is_obstacle_object(obj)]
        area_objects = [obj for obj in scope if self._is_area_object(obj)]
        volume_objects = [obj for obj in scope if self._is_volume_object(obj)]
        basis_helpers = {obj for obj in scope if self._is_basis_helper_object(obj)}
        non_visual = set(obstacle_objects) | set(area_objects) | set(volume_objects) | basis_helpers
        visual_objects = {obj for obj in scope if obj not in non_visual}
        return visual_objects, volume_objects, obstacle_objects, area_objects

    def _build_object_bundle(
        self,
        visual_objects: set[bpy.types.Object],
        volume_objects: list[bpy.types.Object],
        obstacle_objects: list[bpy.types.Object],
        area_objects: list[bpy.types.Object],
    ) -> ExportBundle:
        attachments: dict[str, list[AttachmentObject]] = {}
        roots = [
            obj for obj in visual_objects
            if obj.parent not in visual_objects or self._is_non_visual_helper(obj.parent)
        ]
        roots.sort(key=lambda item: item.name.lower())

        basis_node = BoneNode(
            name=self.basis_name,
            matrix=self._basis_matrix_rows(),
            parameters=self._basis_parameter_text(),
        )

        bone_name_map: dict[bpy.types.Object, str] = {}
        for root in roots:
            child_node = self._build_object_node(
                obj=root,
                parent_matrix=Matrix.Identity(4),
                visual_scope=visual_objects,
                attachments=attachments,
                bone_name_map=bone_name_map,
            )
            basis_node.children.append(child_node)

        meshes = self._build_mesh_map(attachments)
        self.animation_attachments = attachments
        volumes = self._build_volume_entries(volume_objects, bone_name_map, visual_objects)
        obstacles = self._build_shape_entries(obstacle_objects, "Obstacle")
        areas = self._build_shape_entries(area_objects, "Area")
        model = ModelData(
            file_name=f"{self.model_name}.mdl",
            basis=basis_node,
            obstacles=obstacles,
            areas=areas,
            volumes=volumes,
            source_name=bpy.data.filepath or "untitled.blend",
            metadata_comments=self._basis_metadata_comments(),
        )
        return ExportBundle(model=model, meshes=meshes, materials={mat.file_name: mat for mat in self.material_cache.values()})

    def _build_armature_bundle(
        self,
        visual_objects: set[bpy.types.Object],
        volume_objects: list[bpy.types.Object],
        obstacle_objects: list[bpy.types.Object],
        area_objects: list[bpy.types.Object],
    ) -> ExportBundle:
        assert self.armature_obj is not None
        attachments: dict[str, list[AttachmentObject]] = {}
        bone_name_map: dict[bpy.types.Object, str] = {}

        arm_loc, arm_rot, arm_scale = self.armature_obj.matrix_world.decompose()
        if not self._scale_is_identity(arm_scale):
            self.warnings.append(
                f'Armature "{self.armature_obj.name}" has object scale. Apply scale for the safest GOH export.'
            )

        basis_node = BoneNode(
            name=self.basis_name,
            matrix=self._basis_matrix_rows(arm_loc, arm_rot.to_matrix()),
            parameters=self._basis_parameter_text(),
        )

        attached_bones: set[str] = set()
        attachment_props: dict[str, bpy.types.Object] = {}
        for obj in sorted(visual_objects, key=lambda item: item.name.lower()):
            if obj == self.armature_obj or obj.type != "MESH":
                continue
            attach_bone = self._resolve_attach_bone(obj)
            if attach_bone != self.basis_name and attach_bone not in self.armature_obj.data.bones:
                raise ExportError(f'Mesh "{obj.name}" is attached to unknown bone "{attach_bone}".')
            reference_matrix = self._reference_matrix_for_bone(attach_bone)
            mesh_matrix = reference_matrix.inverted() @ obj.matrix_world
            attachments.setdefault(attach_bone, []).append(
                AttachmentObject(obj=obj, mesh_matrix=mesh_matrix, attach_bone=attach_bone)
            )
            attached_bones.add(attach_bone)
            attachment_props.setdefault(attach_bone, obj)

        if self.basis_name in attached_bones:
            basis_default = self._file_name_for_bone(self.basis_name, ".ply")
            basis_flags = self._bone_volume_flags(attachment_props.get(self.basis_name))
            basis_layer = self._custom_scalar(attachment_props.get(self.basis_name), "goh_layer")
            basis_node.volume_view = basis_default
            basis_node.volume_flags = basis_flags
            basis_node.layer = basis_layer
            basis_node.mesh_views = self._mesh_views_for_owner(attachment_props.get(self.basis_name), basis_default, basis_flags, basis_layer)
            basis_node.lod_off = self._custom_bool(attachment_props.get(self.basis_name), "goh_lod_off")

        for root_bone in [bone for bone in self.armature_obj.data.bones if bone.parent is None]:
            basis_node.children.append(self._build_armature_node(root_bone, attached_bones, attachment_props))

        meshes = self._build_mesh_map(attachments)
        self.animation_attachments = attachments
        volumes = self._build_volume_entries(volume_objects, bone_name_map, visual_objects)
        obstacles = self._build_shape_entries(obstacle_objects, "Obstacle")
        areas = self._build_shape_entries(area_objects, "Area")
        model = ModelData(
            file_name=f"{self.model_name}.mdl",
            basis=basis_node,
            obstacles=obstacles,
            areas=areas,
            volumes=volumes,
            source_name=bpy.data.filepath or "untitled.blend",
            metadata_comments=self._basis_metadata_comments(),
        )
        return ExportBundle(model=model, meshes=meshes, materials={mat.file_name: mat for mat in self.material_cache.values()})

    def _attach_animations(self, bundle: ExportBundle, visual_objects: set[bpy.types.Object]) -> None:
        clip_specs = self._collect_animation_specs(visual_objects)
        if not clip_specs:
            return

        bone_names = self._animation_bone_names(bundle.model.basis)
        if not bone_names:
            return

        scene = self.context.scene
        current_frame = scene.frame_current
        current_subframe = scene.frame_subframe
        animation_map: dict[str, AnimationFile] = {}
        sequences: list[SequenceDef] = []
        try:
            for clip in clip_specs:
                file_name = self._unique_file_name(clip.file_stem or clip.name, ".anm")
                frames = self._sample_animation_frames(visual_objects, bone_names, clip)
                mesh_frames = self._sample_mesh_animation_frames(clip, bundle.meshes, bundle.materials)
                if not frames:
                    continue
                animation_map[file_name] = AnimationFile(
                    file_name=file_name,
                    bone_names=bone_names,
                    frames=frames,
                    mesh_frames=mesh_frames,
                    format=self.operator.anm_format.lower(),
                )
                sequences.append(
                    SequenceDef(
                        name=clip.name,
                        file_name=file_name,
                        speed=clip.speed,
                        smooth=clip.smooth,
                        resume=clip.resume,
                        autostart=clip.autostart,
                        store=clip.store,
                    )
                )
        finally:
            scene.frame_set(current_frame, subframe=current_subframe)
            self.context.view_layer.update()

        if animation_map:
            bundle.animations.update(animation_map)
            bundle.model.sequences.extend(sequences)

    def _collect_animation_specs(self, visual_objects: set[bpy.types.Object]) -> list[AnimationClipSpec]:
        legacy_specs = self._legacy_animation_specs()
        owners = self._animation_clip_owners(visual_objects)
        if not owners:
            return legacy_specs

        nla_specs: dict[tuple[str, int, int], AnimationClipSpec] = {}
        for owner in owners:
            animation_data = getattr(owner, "animation_data", None)
            if animation_data is None or not getattr(animation_data, "use_nla", False):
                continue
            for track in animation_data.nla_tracks:
                if track.mute:
                    continue
                for strip in track.strips:
                    if strip.mute:
                        continue
                    action = getattr(strip, "action", None)
                    if action is None:
                        continue
                    clip = self._clip_spec_from_strip(strip, action, owner)
                    key = (
                        sanitized_file_stem(clip.file_stem or clip.name).lower(),
                        clip.frame_start,
                        clip.frame_end,
                    )
                    if key in nla_specs:
                        nla_specs[key] = self._merge_clip_specs(nla_specs[key], clip)
                    else:
                        nla_specs[key] = clip

        for clip in legacy_specs:
            key = (
                sanitized_file_stem(clip.file_stem or clip.name).lower(),
                clip.frame_start,
                clip.frame_end,
            )
            if key in nla_specs:
                nla_specs[key] = self._merge_clip_specs(nla_specs[key], clip)
            else:
                nla_specs[key] = clip

        if nla_specs:
            return sorted(nla_specs.values(), key=lambda clip: (clip.frame_start, clip.frame_end, clip.name.lower()))

        action_sources: list[tuple[bpy.types.Object, bpy.types.Action]] = []
        start_frame: int | None = None
        end_frame: int | None = None
        names: list[str] = []
        for owner in owners:
            animation_data = getattr(owner, "animation_data", None)
            action = getattr(animation_data, "action", None) if animation_data else None
            if action is None:
                continue
            clip_start, clip_end = self._action_frame_range(action)
            start_frame = clip_start if start_frame is None else min(start_frame, clip_start)
            end_frame = clip_end if end_frame is None else max(end_frame, clip_end)
            action_sources.append((owner, action))
            if action.name not in names:
                names.append(action.name)

        if not action_sources or start_frame is None or end_frame is None:
            return legacy_specs

        sources = [action for _owner, action in action_sources]
        sources.extend(owner for owner, _action in action_sources)
        sources.append(self.context.scene)
        default_name = names[0] if len(names) == 1 else self.model_name
        clips = [self._clip_spec(default_name, start_frame, end_frame, sources)]
        clips.extend(legacy_specs)
        merged: dict[tuple[str, int, int], AnimationClipSpec] = {}
        for clip in clips:
            key = (
                sanitized_file_stem(clip.file_stem or clip.name).lower(),
                clip.frame_start,
                clip.frame_end,
            )
            if key in merged:
                merged[key] = self._merge_clip_specs(merged[key], clip)
            else:
                merged[key] = clip
        return sorted(merged.values(), key=lambda clip: (clip.frame_start, clip.frame_end, clip.name.lower()))

    def _animation_clip_owners(self, visual_objects: set[bpy.types.Object]) -> list[bpy.types.Object]:
        if self.armature_obj is not None:
            ignored = [
                obj.name
                for obj in sorted(visual_objects, key=lambda item: item.name.lower())
                if obj != self.armature_obj and self._has_animation_data(obj)
            ]
            for name in ignored[:10]:
                self.warnings.append(
                    f'Animated object "{name}" is ignored in armature mode. Export bone motion from the armature action/NLA tracks instead.'
                )
            return [self.armature_obj]
        owners: list[object] = []
        seen: set[int] = set()
        for obj in sorted(visual_objects, key=lambda item: item.name.lower()):
            for candidate in (obj, getattr(obj.data, "shape_keys", None)):
                if candidate is None:
                    continue
                pointer = candidate.as_pointer() if hasattr(candidate, "as_pointer") else id(candidate)
                if pointer in seen:
                    continue
                seen.add(pointer)
                owners.append(candidate)
        return owners  # type: ignore[return-value]

    def _has_animation_data(self, obj: bpy.types.Object) -> bool:
        for owner in (obj, getattr(obj.data, "shape_keys", None)):
            animation_data = getattr(owner, "animation_data", None)
            if animation_data is None:
                continue
            if animation_data.action is not None:
                return True
            if getattr(animation_data, "use_nla", False):
                for track in animation_data.nla_tracks:
                    if track.mute:
                        continue
                    for strip in track.strips:
                        if not strip.mute and getattr(strip, "action", None) is not None:
                            return True
        return False

    def _legacy_animation_specs(self) -> list[AnimationClipSpec]:
        sources: list[tuple[str, list[str]]] = []
        if self.basis_settings and self.basis_settings.enabled:
            lines = _basis_legacy_lines(self.basis_settings)
            if lines:
                sources.append(("Basis settings", lines))
        if self.basis_helper is not None:
            _flags, values = self._legacy_entries(self.basis_helper)
            helper_lines = values.get("animation", []) + values.get("animationresume", [])
            if helper_lines:
                sources.append((self.basis_helper.name, helper_lines))

        clips: list[AnimationClipSpec] = []
        for source_name, lines in sources:
            clips.extend(self._legacy_animation_specs_from_lines(lines, source_name))
        return clips

    def _legacy_animation_specs_from_lines(self, raw_lines: Iterable[str], source_name: str) -> list[AnimationClipSpec]:
        clips: list[AnimationClipSpec] = []
        scene_fps = float(getattr(self.context.scene.render, "fps", 24) or 24)
        for raw_line in raw_lines:
            text = (raw_line or "").strip()
            if not text:
                continue
            lower_text = text.lower()
            if lower_text.startswith("animationresume="):
                key = "animationresume"
            elif lower_text.startswith("animation="):
                key = "animation"
            else:
                continue
            payload = text.split("=", 1)[1].strip() if "=" in text else text
            parts = [part.strip() for part in payload.split(",") if part.strip()]
            if len(parts) < 3:
                self.warnings.append(f'Legacy {key} line on "{source_name}" is incomplete and was skipped: {text}')
                continue
            name = parts[0]
            file_stem = parts[1] if len(parts) >= 2 else None
            frame_token = next((part for part in parts[2:] if _parse_frame_range(part) is not None), None)
            frame_range = _parse_frame_range(frame_token or "")
            if frame_range is None:
                self.warnings.append(f'Legacy {key} line on "{source_name}" is missing a valid frame range and was skipped: {text}')
                continue
            rate_token = next((part for part in reversed(parts) if re.fullmatch(r"-?\d+(?:\.\d+)?", part)), None)
            speed = 1.0
            if rate_token is not None:
                try:
                    rate_value = float(rate_token)
                    if abs(rate_value) > EPSILON:
                        speed = scene_fps / rate_value
                except ValueError:
                    speed = 1.0
            clips.append(
                AnimationClipSpec(
                    name=name,
                    frame_start=frame_range[0],
                    frame_end=frame_range[1],
                    file_stem=file_stem,
                    speed=speed,
                    resume=key == "animationresume",
                )
            )
        return clips

    def _clip_spec_from_strip(
        self,
        strip: bpy.types.NlaStrip,
        action: bpy.types.Action,
        owner,
    ) -> AnimationClipSpec:
        start_frame, end_frame = self._strip_frame_range(strip)
        sources = [strip, action, owner, self.context.scene]
        default_name = strip.name or action.name or getattr(owner, "name", self.model_name)
        return self._clip_spec(default_name, start_frame, end_frame, sources)

    def _clip_spec(
        self,
        default_name: str,
        start_frame: int,
        end_frame: int,
        sources: list[object],
    ) -> AnimationClipSpec:
        name = self._first_custom_text(sources, "goh_sequence_name") or default_name or self.model_name
        file_stem = self._first_custom_text(sources, "goh_sequence_file")
        speed = self._first_custom_float(sources, "goh_sequence_speed")
        smooth = self._first_custom_float(sources, "goh_sequence_smooth")
        return AnimationClipSpec(
            name=name,
            frame_start=start_frame,
            frame_end=max(start_frame, end_frame),
            file_stem=file_stem,
            speed=1.0 if speed is None else speed,
            smooth=0.0 if smooth is None else smooth,
            resume=self._any_custom_bool(sources, "goh_sequence_resume"),
            autostart=self._any_custom_bool(sources, "goh_sequence_autostart"),
            store=self._any_custom_bool(sources, "goh_sequence_store"),
        )

    def _merge_clip_specs(self, left: AnimationClipSpec, right: AnimationClipSpec) -> AnimationClipSpec:
        return AnimationClipSpec(
            name=left.name,
            frame_start=min(left.frame_start, right.frame_start),
            frame_end=max(left.frame_end, right.frame_end),
            file_stem=left.file_stem or right.file_stem,
            speed=left.speed if abs(left.speed - 1.0) > 1e-6 else right.speed,
            smooth=left.smooth if abs(left.smooth) > 1e-6 else right.smooth,
            resume=left.resume or right.resume,
            autostart=left.autostart or right.autostart,
            store=left.store or right.store,
        )

    def _strip_frame_range(self, strip: bpy.types.NlaStrip) -> tuple[int, int]:
        start_frame = int(math.ceil(float(strip.frame_start) - EPSILON))
        end_frame = int(math.floor(float(strip.frame_end) - EPSILON))
        if end_frame < start_frame:
            end_frame = start_frame
        return start_frame, end_frame

    def _action_frame_range(self, action: bpy.types.Action) -> tuple[int, int]:
        start, end = action.frame_range
        start_frame = int(math.floor(float(start) + EPSILON))
        end_frame = int(math.ceil(float(end) - EPSILON))
        if end_frame < start_frame:
            end_frame = start_frame
        return start_frame, end_frame

    def _animation_bone_names(self, basis: BoneNode) -> list[str]:
        names: list[str] = []

        def walk(node: BoneNode) -> None:
            names.append(node.name)
            for child in node.children:
                walk(child)

        walk(basis)
        return names

    def _sample_animation_frames(
        self,
        visual_objects: set[bpy.types.Object],
        bone_names: list[str],
        clip: AnimationClipSpec,
    ) -> list[dict[str, AnimationState]]:
        frame_states: list[dict[str, AnimationState]] = []
        object_map = self._animation_object_map(visual_objects) if self.armature_obj is None else None
        for frame in range(clip.frame_start, clip.frame_end + 1):
            self.context.scene.frame_set(frame, subframe=0.0)
            self.context.view_layer.update()
            if self.armature_obj is not None:
                frame_states.append(self._sample_armature_frame_state(bone_names))
            else:
                assert object_map is not None
                frame_states.append(self._sample_object_frame_state(bone_names, object_map, visual_objects))
        return frame_states

    def _sample_mesh_animation_frames(
        self,
        clip: AnimationClipSpec,
        mesh_map: dict[str, MeshData],
        materials: dict[str, MaterialDef],
    ) -> list[dict[str, MeshAnimationState]]:
        candidates: dict[str, tuple[list[AttachmentObject], MeshData, bytes, int]] = {}
        for bone_name, attachments in self.animation_attachments.items():
            mesh_file = self._file_name_for_bone(bone_name, ".ply")
            base_mesh = mesh_map.get(mesh_file)
            if base_mesh is None:
                continue
            if base_mesh.skinned_bones:
                continue
            if not self._attachments_support_mesh_animation(attachments):
                continue
            base_blob, base_stride = encode_mesh_vertex_stream(base_mesh, materials)
            candidates[bone_name] = (attachments, base_mesh, base_blob, base_stride)

        if not candidates:
            return [{} for _ in range(clip.frame_end - clip.frame_start + 1)]

        mesh_frames: list[dict[str, MeshAnimationState]] = []
        for frame in range(clip.frame_start, clip.frame_end + 1):
            self.context.scene.frame_set(frame, subframe=0.0)
            self.context.view_layer.update()
            frame_states: dict[str, MeshAnimationState] = {}
            for bone_name, (attachments, base_mesh, _base_blob, base_stride) in candidates.items():
                animated_mesh = self._build_mesh_data(base_mesh.file_name, attachments, use_evaluated_mesh=True)
                if animated_mesh is None:
                    continue
                blob, stride = encode_mesh_vertex_stream(animated_mesh, materials)
                if stride != base_stride or len(animated_mesh.vertices) != len(base_mesh.vertices):
                    raise ExportError(
                        f'Mesh animation on "{bone_name}" changes vertex layout. GOH mesh animation requires a stable vertex count and stride.'
                    )
                frame_states[bone_name] = MeshAnimationState(
                    first_vertex=0,
                    vertex_count=len(animated_mesh.vertices),
                    vertex_stride=stride,
                    vertex_data=blob,
                    bbox=self._bbox_from_mesh_vertices(animated_mesh.vertices),
                    reserved=(0.0, 0.0),
                )
            mesh_frames.append(frame_states)
        return mesh_frames

    def _animation_object_map(self, visual_objects: set[bpy.types.Object]) -> dict[str, bpy.types.Object]:
        object_map: dict[str, bpy.types.Object] = {}
        for obj in visual_objects:
            bone_name = self._bone_name_for_object(obj)
            if bone_name == self.basis_name:
                continue
            if bone_name in object_map and object_map[bone_name] != obj:
                raise ExportError(f'Duplicate GOH bone name "{bone_name}" detected in object animation export.')
            object_map[bone_name] = obj
        return object_map

    def _sample_armature_frame_state(self, bone_names: list[str]) -> dict[str, AnimationState]:
        assert self.armature_obj is not None
        frame_state: dict[str, AnimationState] = {}
        arm_loc, arm_rot, _arm_scale = self.armature_obj.matrix_world.decompose()
        frame_state[self.basis_name] = AnimationState(
            matrix=self._matrix_rows(arm_loc, arm_rot.to_matrix()),
            visible=1,
        )
        for bone_name in bone_names:
            if bone_name == self.basis_name:
                continue
            pose_bone = self.armature_obj.pose.bones.get(bone_name)
            if pose_bone is None:
                raise ExportError(f'Animation export could not find pose bone "{bone_name}".')
            if pose_bone.parent:
                local_matrix = pose_bone.parent.matrix.inverted_safe() @ pose_bone.matrix
            else:
                local_matrix = pose_bone.matrix.copy()
            loc, rot, _scale = local_matrix.decompose()
            frame_state[bone_name] = AnimationState(
                matrix=self._matrix_rows(loc, rot.to_matrix()),
                visible=1,
            )
        return frame_state

    def _sample_object_frame_state(
        self,
        bone_names: list[str],
        object_map: dict[str, bpy.types.Object],
        visual_objects: set[bpy.types.Object],
    ) -> dict[str, AnimationState]:
        frame_state: dict[str, AnimationState] = {
            self.basis_name: AnimationState(
                matrix=self._matrix_rows(Vector((0.0, 0.0, 0.0)), Matrix.Identity(3)),
                visible=1,
            )
        }
        for bone_name in bone_names:
            if bone_name == self.basis_name:
                continue
            obj = object_map.get(bone_name)
            if obj is None:
                raise ExportError(f'Animation export could not find object for GOH bone "{bone_name}".')
            parent_matrix = Matrix.Identity(4)
            if obj.parent in visual_objects and not self._is_volume_object(obj.parent):
                parent_matrix = obj.parent.matrix_world
            local_matrix = parent_matrix.inverted_safe() @ obj.matrix_world
            loc, rot, _scale = local_matrix.decompose()
            frame_state[bone_name] = AnimationState(
                matrix=self._matrix_rows(loc, rot.to_matrix()),
                visible=1 if self._is_object_visible(obj) else 0,
            )
        return frame_state

    def _is_object_visible(self, obj: bpy.types.Object) -> bool:
        try:
            return bool(obj.visible_get(view_layer=self.context.view_layer))
        except TypeError:
            return bool(obj.visible_get())

    def _first_custom_text(self, sources: Iterable[object], key: str) -> str | None:
        for source in sources:
            text = self._custom_text(source, key)
            if text:
                return text
        return None

    def _first_custom_float(self, sources: Iterable[object], key: str) -> float | None:
        for source in sources:
            value = self._custom_float(source, key)
            if value is not None:
                return value
        return None

    def _any_custom_bool(self, sources: Iterable[object], key: str) -> bool:
        return any(self._custom_bool(source, key) for source in sources)

    def _build_object_node(
        self,
        obj: bpy.types.Object,
        parent_matrix: Matrix,
        visual_scope: set[bpy.types.Object],
        attachments: dict[str, list[AttachmentObject]],
        bone_name_map: dict[bpy.types.Object, str],
    ) -> BoneNode:
        local_matrix = parent_matrix.inverted() @ obj.matrix_world
        node_matrix = self._node_matrix_for_object(obj, local_matrix, visual_scope)
        mesh_matrix = node_matrix.inverted() @ local_matrix

        loc, rot, scale = local_matrix.decompose()
        node_loc, node_rot, _node_scale = node_matrix.decompose()
        if not self._scale_is_identity(scale):
            self.warnings.append(
                f'Object "{obj.name}" has unapplied scale. The exporter bakes it into mesh data, but child transforms are safer with applied scale.'
            )

        bone_name = self._bone_name_for_object(obj)
        bone_name_map[obj] = bone_name
        node = BoneNode(
            name=bone_name,
            matrix=self._matrix_rows(node_loc, node_rot.to_matrix()),
            transform_block=self._transform_block_mode(obj),
            bone_type=self._custom_text(obj, "goh_bone_type"),
            parameters=self._legacy_parameter_text_for_owner(obj),
            limits=self._custom_float_list(obj, "goh_limits")[:2],
            speed=self._custom_float(obj, "goh_speed"),
            speed_uses_speed2=self._custom_bool(obj, "goh_speed2"),
            visibility=self._custom_int(obj, "goh_visibility"),
            terminator=self._custom_bool(obj, "goh_terminator"),
            color_rgba=self._custom_rgba(obj, "goh_color_rgba"),
            volume_view=self._file_name_for_bone(bone_name, ".ply") if obj.type == "MESH" else None,
            volume_flags=self._bone_volume_flags(obj),
            layer=self._custom_scalar(obj, "goh_layer"),
            mesh_views=self._mesh_views_for_owner(
                obj,
                self._file_name_for_bone(bone_name, ".ply") if obj.type == "MESH" else None,
                self._bone_volume_flags(obj),
                self._custom_scalar(obj, "goh_layer"),
            ),
            lod_off=self._custom_bool(obj, "goh_lod_off"),
        )

        if obj.type == "MESH":
            attachments.setdefault(bone_name, []).append(
                AttachmentObject(obj=obj, mesh_matrix=mesh_matrix, attach_bone=bone_name)
            )

        child_objects = [
            child for child in obj.children
            if child in visual_scope and not self._is_volume_object(child)
        ]
        child_objects.sort(key=lambda item: item.name.lower())
        for child in child_objects:
            node.children.append(
                self._build_object_node(
                    obj=child,
                    parent_matrix=obj.matrix_world,
                    visual_scope=visual_scope,
                    attachments=attachments,
                    bone_name_map=bone_name_map,
                )
            )
        return node

    def _node_matrix_for_object(
        self,
        obj: bpy.types.Object,
        local_matrix: Matrix,
        visual_scope: set[bpy.types.Object],
    ) -> Matrix:
        if self._should_bake_root_visual_rotation(obj, visual_scope):
            loc, _rot, _scale = local_matrix.decompose()
            return Matrix.Translation(loc)
        return self._loc_rot_matrix(local_matrix)

    def _should_bake_root_visual_rotation(
        self,
        obj: bpy.types.Object,
        visual_scope: set[bpy.types.Object],
    ) -> bool:
        if self.operator.axis_mode != "NONE":
            return False
        if obj.type != "MESH":
            return False
        if obj.parent in visual_scope and not self._is_non_visual_helper(obj.parent):
            return False
        if self._has_animation_data(obj):
            return False
        for child in obj.children:
            if child in visual_scope and not self._is_non_visual_helper(child):
                return False
        return True

    def _build_armature_node(
        self,
        bone: bpy.types.Bone,
        attached_bones: set[str],
        attachment_props: dict[str, bpy.types.Object],
    ) -> BoneNode:
        if bone.parent:
            local_matrix = bone.parent.matrix_local.inverted() @ bone.matrix_local
        else:
            local_matrix = bone.matrix_local.copy()

        loc, rot, scale = local_matrix.decompose()
        if not self._scale_is_identity(scale):
            self.warnings.append(f'Bone "{bone.name}" has non-identity rest scale.')

        return BoneNode(
            name=bone.name,
            matrix=self._matrix_rows(loc, rot.to_matrix()),
            transform_block=self._transform_block_mode(attachment_props.get(bone.name) or bone),
            bone_type=self._custom_text(bone, "goh_bone_type"),
            parameters=self._legacy_parameter_text_for_owner(attachment_props.get(bone.name) or bone),
            limits=self._custom_float_list(bone, "goh_limits")[:2],
            speed=self._custom_float(bone, "goh_speed"),
            speed_uses_speed2=self._custom_bool(bone, "goh_speed2"),
            visibility=self._custom_int(bone, "goh_visibility"),
            terminator=self._custom_bool(bone, "goh_terminator"),
            color_rgba=self._custom_rgba(bone, "goh_color_rgba"),
            volume_view=self._file_name_for_bone(bone.name, ".ply") if bone.name in attached_bones else None,
            volume_flags=self._bone_volume_flags(attachment_props.get(bone.name)),
            layer=self._custom_scalar(attachment_props.get(bone.name), "goh_layer") or self._custom_scalar(bone, "goh_layer"),
            mesh_views=self._mesh_views_for_owner(
                attachment_props.get(bone.name) or bone,
                self._file_name_for_bone(bone.name, ".ply") if bone.name in attached_bones else None,
                self._bone_volume_flags(attachment_props.get(bone.name)),
                self._custom_scalar(attachment_props.get(bone.name), "goh_layer") or self._custom_scalar(bone, "goh_layer"),
            ),
            lod_off=self._custom_bool(attachment_props.get(bone.name), "goh_lod_off") or self._custom_bool(bone, "goh_lod_off"),
            children=[self._build_armature_node(child, attached_bones, attachment_props) for child in bone.children],
        )

    def _build_mesh_map(self, attachments: dict[str, list[AttachmentObject]]) -> dict[str, MeshData]:
        mesh_map: dict[str, MeshData] = {}
        for bone_name, grouped_attachments in attachments.items():
            file_name = self._file_name_for_bone(bone_name, ".ply")
            mesh_data = self._build_mesh_data(file_name, grouped_attachments)
            if mesh_data is not None:
                mesh_map[file_name] = mesh_data
        return mesh_map

    def _build_mesh_data(
        self,
        file_name: str,
        attachments: list[AttachmentObject],
        use_evaluated_mesh: bool = False,
    ) -> MeshData | None:
        raw_sections: OrderedDict[str, list[tuple[RawLoopVertex, RawLoopVertex, RawLoopVertex]]] = OrderedDict()
        used_bones: set[str] = set()
        any_weighted_vertices = False

        for attachment in attachments:
            section_data, weighted = self._collect_raw_triangles(attachment, use_evaluated_mesh=use_evaluated_mesh)
            any_weighted_vertices = any_weighted_vertices or weighted
            for material_file, triangles in section_data.items():
                raw_sections.setdefault(material_file, []).extend(triangles)
                for triangle in triangles:
                    for raw_vertex in triangle:
                        for bone_name, _weight in raw_vertex.influences:
                            used_bones.add(bone_name)

        if not raw_sections:
            return None

        skinned = any_weighted_vertices
        if skinned:
            for attachment in attachments:
                used_bones.add(attachment.attach_bone)
            ordered_skin_bones = self._ordered_skin_bones(used_bones)
            bone_index_map = {name: index + 1 for index, name in enumerate(ordered_skin_bones)}
            max_influences = 1
            for section_triangles in raw_sections.values():
                for triangle in section_triangles:
                    for raw_vertex in triangle:
                        max_influences = max(max_influences, max(1, len(raw_vertex.influences)))
            max_influences = min(max_influences, 4)
        else:
            ordered_skin_bones = []
            bone_index_map = {}
            max_influences = 0

        vertex_lookup: dict[tuple, int] = {}
        vertices: list[MeshVertex] = []
        mesh_sections: list[MeshSection] = []

        for material_file, triangles in raw_sections.items():
            material = self.material_cache_by_file(material_file)
            section = MeshSection(material_file=material_file, two_sided=material.two_sided, specular_rgba=material.color_rgba)
            for triangle in triangles:
                tri_indices: list[int] = []
                for raw_vertex in triangle:
                    final_vertex = self._finalize_vertex(
                        raw_vertex=raw_vertex,
                        skinned=skinned,
                        bone_index_map=bone_index_map,
                        max_influences=max_influences,
                    )
                    key = self._mesh_vertex_key(final_vertex)
                    index = vertex_lookup.get(key)
                    if index is None:
                        index = len(vertices)
                        vertex_lookup[key] = index
                        vertices.append(final_vertex)
                    tri_indices.append(index)
                section.triangle_indices.append((tri_indices[0], tri_indices[1], tri_indices[2]))

            if skinned:
                used_indices = {
                    bone_index - 1
                    for triangle in section.triangle_indices
                    for vertex_index in triangle
                    for bone_index in vertices[vertex_index].bone_indices
                    if bone_index > 0
                }
                section.subskin_bones = tuple(sorted(used_indices))
            mesh_sections.append(section)

        return MeshData(
            file_name=file_name,
            vertices=vertices,
            sections=mesh_sections,
            skinned_bones=ordered_skin_bones,
        )

    def _collect_raw_triangles(
        self,
        attachment: AttachmentObject,
        *,
        use_evaluated_mesh: bool = False,
    ) -> tuple[OrderedDict[str, list[tuple[RawLoopVertex, RawLoopVertex, RawLoopVertex]]], bool]:
        obj = attachment.obj
        evaluated_obj = obj.evaluated_get(self.depsgraph) if use_evaluated_mesh else None
        if evaluated_obj is not None:
            mesh = evaluated_obj.to_mesh(preserve_all_data_layers=True, depsgraph=self.depsgraph)
        else:
            mesh = obj.data.copy()
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()

        mesh.calc_loop_triangles()

        uv_layer = mesh.uv_layers.active
        material_files = [self._material_for_slot(obj, index) for index in range(max(1, len(obj.material_slots)))]
        uses_bump = any(material.needs_bump for material in material_files)

        tangent_ready = False
        if uses_bump and uv_layer is not None:
            try:
                mesh.calc_tangents(uvmap=uv_layer.name)
                tangent_ready = True
            except RuntimeError:
                self.warnings.append(f'Mesh "{obj.name}" could not calculate tangents. Writing fallback tangents.')

        raw_sections: OrderedDict[str, list[tuple[RawLoopVertex, RawLoopVertex, RawLoopVertex]]] = OrderedDict()
        weighted_vertices = False

        try:
            for triangle in mesh.loop_triangles:
                material = material_files[triangle.material_index] if triangle.material_index < len(material_files) else material_files[0]
                raw_sections.setdefault(material.file_name, [])
                raw_triangle: list[RawLoopVertex] = []
                for loop_index in triangle.loops:
                    loop = mesh.loops[loop_index]
                    vertex = mesh.vertices[loop.vertex_index]
                    local_position = attachment.mesh_matrix @ vertex.co
                    local_normal = self._transform_normal(attachment.mesh_matrix, loop.normal)

                    if uv_layer is not None:
                        uv = uv_layer.data[loop_index].uv.copy()
                    else:
                        uv = Vector((0.0, 0.0))

                    if tangent_ready:
                        tangent = self._transform_tangent(attachment.mesh_matrix, loop.tangent)
                        tangent_sign = float(loop.bitangent_sign)
                        if attachment.mesh_matrix.to_3x3().determinant() < 0.0:
                            tangent_sign *= -1.0
                    else:
                        tangent = Vector((1.0, 0.0, 0.0))
                        tangent_sign = 1.0

                    influences = self._vertex_influences(obj, vertex, attachment.attach_bone)
                    weighted_vertices = weighted_vertices or bool(influences)

                    raw_triangle.append(
                        RawLoopVertex(
                            position=self._convert_point(local_position),
                            normal=self._convert_direction(local_normal),
                            uv=self._convert_uv(uv),
                            tangent=self._convert_direction(tangent),
                            tangent_sign=tangent_sign,
                            influences=influences,
                            fallback_bone=attachment.attach_bone,
                        )
                    )
                raw_sections[material.file_name].append((raw_triangle[0], raw_triangle[1], raw_triangle[2]))
        finally:
            if tangent_ready:
                mesh.free_tangents()
            if evaluated_obj is not None:
                evaluated_obj.to_mesh_clear()
            else:
                bpy.data.meshes.remove(mesh)

        return raw_sections, weighted_vertices

    def _attachments_support_mesh_animation(self, attachments: list[AttachmentObject]) -> bool:
        supports_animation = False
        for attachment in attachments:
            obj = attachment.obj
            if self._custom_bool(obj, "goh_force_mesh_animation"):
                supports_animation = True
            shape_keys = getattr(obj.data, "shape_keys", None)
            animation_data = getattr(shape_keys, "animation_data", None) if shape_keys else None
            if shape_keys and len(shape_keys.key_blocks) > 1 and animation_data is not None:
                supports_animation = True
            if any(modifier.type == "ARMATURE" and modifier.show_viewport for modifier in obj.modifiers):
                self.warnings.append(
                    f'Mesh animation sampling skips armature deformation on "{obj.name}". Use shape keys or non-armature mesh deformation for GOH mesh animation.'
                )
                return False
        return supports_animation

    def _bbox_from_mesh_vertices(
        self,
        vertices: list[MeshVertex],
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        min_x = min(vertex.position[0] for vertex in vertices)
        min_y = min(vertex.position[1] for vertex in vertices)
        min_z = min(vertex.position[2] for vertex in vertices)
        max_x = max(vertex.position[0] for vertex in vertices)
        max_y = max(vertex.position[1] for vertex in vertices)
        max_z = max(vertex.position[2] for vertex in vertices)
        return (min_x, min_y, min_z), (max_x, max_y, max_z)

    def _build_volume_entries(
        self,
        volume_objects: list[bpy.types.Object],
        bone_name_map: dict[bpy.types.Object, str],
        visual_scope: set[bpy.types.Object],
    ) -> list[VolumeData]:
        volumes: list[VolumeData] = []
        for obj in sorted(volume_objects, key=lambda item: item.name.lower()):
            volume_name = self._volume_entry_name(obj)
            bone_name, reference_matrix = self._resolve_volume_bone(obj, bone_name_map, visual_scope)
            local_matrix = reference_matrix.inverted() @ obj.matrix_world
            volume_kind = self._volume_kind(obj)
            common_kwargs = dict(
                entry_name=volume_name,
                bone_name=bone_name,
                component=self._custom_text(obj, "goh_component"),
                tags=self._custom_text(obj, "goh_tags"),
                density=self._custom_float(obj, "goh_density"),
                thickness=self._volume_thickness(obj),
                transform_block=self._transform_block_mode(obj),
            )

            if volume_kind == "polyhedron":
                file_name = self._unique_file_name(volume_name, ".vol")
                vertices, triangles = self._collect_volume_geometry(obj, local_matrix)
                side_codes = classify_triangle_sides(vertices, triangles)
                volumes.append(
                    VolumeData(
                        file_name=file_name,
                        vertices=vertices,
                        triangles=triangles,
                        side_codes=side_codes,
                        **common_kwargs,
                    )
                )
                continue

            center_local, size_local = self._local_bbox_center_size(obj)
            center = local_matrix @ center_local
            _loc, rotation, scale = local_matrix.decompose()
            scaled_size = Vector((
                abs(size_local.x * scale.x),
                abs(size_local.y * scale.y),
                abs(size_local.z * scale.z),
            ))

            if volume_kind == "box":
                primitive_matrix = Matrix.Translation(center) @ rotation.to_matrix().to_4x4()
                volumes.append(
                    VolumeData(
                        file_name=None,
                        volume_kind="box",
                        box_size=self._convert_lengths(scaled_size),
                        matrix=self._matrix_rows_from_matrix(primitive_matrix),
                        **common_kwargs,
                    )
                )
                continue

            if volume_kind == "sphere":
                radius = max(float(scaled_size.x), float(scaled_size.y), float(scaled_size.z)) * 0.5
                if min(float(scaled_size.x), float(scaled_size.y), float(scaled_size.z)) <= EPSILON:
                    raise ExportError(f'Sphere volume "{obj.name}" has zero size.')
                if max(float(scaled_size.x), float(scaled_size.y), float(scaled_size.z)) - min(float(scaled_size.x), float(scaled_size.y), float(scaled_size.z)) > 1e-3:
                    self.warnings.append(
                        f'Sphere volume "{obj.name}" uses a non-uniform bounding box. The exporter keeps the largest radius and writes a true GEM sphere.'
                    )
                primitive_matrix = Matrix.Translation(center)
                volumes.append(
                    VolumeData(
                        file_name=None,
                        volume_kind="sphere",
                        sphere_radius=self._convert_length(radius),
                        matrix=self._matrix_rows_from_matrix(primitive_matrix),
                        **common_kwargs,
                    )
                )
                continue

            if volume_kind == "cylinder":
                volume_axis = self._volume_axis(obj)
                radius, length, align_matrix = self._primitive_cylinder_dimensions(obj, scaled_size, volume_axis)
                primitive_matrix = Matrix.Translation(center) @ rotation.to_matrix().to_4x4() @ align_matrix
                volumes.append(
                    VolumeData(
                        file_name=None,
                        volume_kind="cylinder",
                        cylinder_radius=self._convert_length(radius),
                        cylinder_length=self._convert_length(length),
                        matrix=self._matrix_rows_from_matrix(primitive_matrix),
                        **common_kwargs,
                    )
                )
                continue

            raise ExportError(f'Unsupported GOH volume kind "{volume_kind}" on "{obj.name}".')
        return volumes

    def _build_shape_entries(
        self,
        shape_objects: list[bpy.types.Object],
        block_type: str,
    ) -> list[Shape2DEntry]:
        entries: list[Shape2DEntry] = []
        for obj in sorted(shape_objects, key=lambda item: item.name.lower()):
            shape_type = (self._custom_text(obj, "goh_shape_2d") or "Obb2").strip().lower()
            points = self._shape_points_2d(obj)
            if not points:
                continue
            entry = Shape2DEntry(
                entry_name=self._custom_text(obj, "goh_shape_name") or obj.name,
                block_type=block_type,
                shape_type="Obb2",
                rotate=self._custom_bool(obj, "goh_rotate_2d") or shape_type == "obb2",
                tags=self._custom_text(obj, "goh_tags"),
            )
            if shape_type == "circle2":
                center = self._points_center_2d(points)
                radius = max(math.hypot(point[0] - center[0], point[1] - center[1]) for point in points)
                entry.shape_type = "Circle2"
                entry.center = center
                entry.radius = radius
            elif shape_type == "polygon2":
                hull = self._convex_hull_2d(points)
                entry.shape_type = "Polygon2"
                entry.vertices = hull
            else:
                center, extent, axis = self._obb2_from_points(points, obj)
                entry.shape_type = "Obb2"
                entry.center = center
                entry.extent = extent
                entry.axis = axis
            entries.append(entry)
        return entries

    def _collect_volume_geometry(
        self,
        obj: bpy.types.Object,
        mesh_matrix: Matrix,
    ) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
        mesh = obj.data.copy()
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
        mesh.calc_loop_triangles()

        vertex_lookup: dict[tuple[float, float, float], int] = {}
        vertices: list[tuple[float, float, float]] = []
        triangles: list[tuple[int, int, int]] = []
        try:
            for triangle in mesh.loop_triangles:
                tri_indices: list[int] = []
                for loop_index in triangle.loops:
                    vertex = mesh.vertices[mesh.loops[loop_index].vertex_index]
                    point = self._convert_point(mesh_matrix @ vertex.co)
                    key = tuple(round(value, 6) for value in point)
                    index = vertex_lookup.get(key)
                    if index is None:
                        index = len(vertices)
                        vertex_lookup[key] = index
                        vertices.append(point)
                    tri_indices.append(index)
                triangles.append((tri_indices[0], tri_indices[1], tri_indices[2]))
        finally:
            bpy.data.meshes.remove(mesh)
        return vertices, triangles

    def _local_bbox_center_size(self, obj: bpy.types.Object) -> tuple[Vector, Vector]:
        bbox = [Vector(corner) for corner in obj.bound_box]
        if not bbox:
            raise ExportError(f'Volume helper "{obj.name}" has no bounding box.')
        min_corner = Vector((
            min(point.x for point in bbox),
            min(point.y for point in bbox),
            min(point.z for point in bbox),
        ))
        max_corner = Vector((
            max(point.x for point in bbox),
            max(point.y for point in bbox),
            max(point.z for point in bbox),
        ))
        center = (min_corner + max_corner) * 0.5
        size = max_corner - min_corner
        if size.length <= EPSILON:
            raise ExportError(f'Volume helper "{obj.name}" has an empty bounding box.')
        return center, size

    def _primitive_cylinder_dimensions(
        self,
        obj: bpy.types.Object,
        scaled_size: Vector,
        axis: str,
    ) -> tuple[float, float, Matrix]:
        axis_key = axis.lower()
        if axis_key == "x":
            radius = max(scaled_size.y, scaled_size.z) * 0.5
            cross_a = scaled_size.y
            cross_b = scaled_size.z
            length = scaled_size.x
            align = Matrix.Rotation(math.pi / 2.0, 4, "Y")
        elif axis_key == "y":
            radius = max(scaled_size.x, scaled_size.z) * 0.5
            cross_a = scaled_size.x
            cross_b = scaled_size.z
            length = scaled_size.y
            align = Matrix.Rotation(-math.pi / 2.0, 4, "X")
        else:
            radius = max(scaled_size.x, scaled_size.y) * 0.5
            cross_a = scaled_size.x
            cross_b = scaled_size.y
            length = scaled_size.z
            align = Matrix.Identity(4)

        if radius <= EPSILON or length <= EPSILON:
            raise ExportError(f'Cylinder volume "{obj.name}" has zero radius or length.')
        if abs(cross_a - cross_b) > 1e-4:
            self.warnings.append(
                f'Cylinder volume "{obj.name}" uses a non-circular cross-section. The exporter keeps the larger radius and writes a true GEM cylinder.'
            )
        return radius, length, align

    def _shape_points_2d(self, obj: bpy.types.Object) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        if obj.type == "MESH" and obj.data:
            for vertex in obj.data.vertices:
                point = self._convert_point(obj.matrix_world @ vertex.co)
                points.append((point[0], point[1]))
        if not points:
            for corner in obj.bound_box:
                point = self._convert_point(obj.matrix_world @ Vector(corner))
                points.append((point[0], point[1]))
        unique: list[tuple[float, float]] = []
        seen: set[tuple[float, float]] = set()
        for point in points:
            rounded = (round(point[0], 6), round(point[1], 6))
            if rounded not in seen:
                seen.add(rounded)
                unique.append(point)
        return unique

    def _points_center_2d(self, points: list[tuple[float, float]]) -> tuple[float, float]:
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )

    def _obb2_from_points(
        self,
        points: list[tuple[float, float]],
        obj: bpy.types.Object,
    ) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
        center = self._points_center_2d(points)
        axis_vector = self._convert_direction(obj.matrix_world.to_3x3().col[0])
        axis_2d = Vector((axis_vector[0], axis_vector[1]))
        if axis_2d.length <= EPSILON:
            axis_2d = Vector((1.0, 0.0))
        else:
            axis_2d.normalize()
        perp = Vector((-axis_2d.y, axis_2d.x))
        max_x = 0.0
        max_y = 0.0
        center_vec = Vector(center)
        for point in points:
            delta = Vector(point) - center_vec
            max_x = max(max_x, abs(delta.dot(axis_2d)))
            max_y = max(max_y, abs(delta.dot(perp)))
        return center, (max_x, max_y), (float(axis_2d.x), float(axis_2d.y))

    def _convex_hull_2d(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        sorted_points = sorted({(round(x, 6), round(y, 6)) for x, y in points})
        if len(sorted_points) <= 2:
            return [(float(x), float(y)) for x, y in sorted_points]

        def cross(o, a, b) -> float:
            return ((a[0] - o[0]) * (b[1] - o[1])) - ((a[1] - o[1]) * (b[0] - o[0]))

        lower: list[tuple[float, float]] = []
        for point in sorted_points:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
                lower.pop()
            lower.append(point)

        upper: list[tuple[float, float]] = []
        for point in reversed(sorted_points):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
                upper.pop()
            upper.append(point)

        hull = lower[:-1] + upper[:-1]
        return [(float(x), float(y)) for x, y in hull]

    def _finalize_vertex(
        self,
        raw_vertex: RawLoopVertex,
        skinned: bool,
        bone_index_map: dict[str, int],
        max_influences: int,
    ) -> MeshVertex:
        if not skinned:
            return MeshVertex(
                position=raw_vertex.position,
                normal=raw_vertex.normal,
                uv=raw_vertex.uv,
                tangent=raw_vertex.tangent,
                tangent_sign=raw_vertex.tangent_sign,
            )

        influences = list(raw_vertex.influences)
        if not influences:
            fallback_name = raw_vertex.fallback_bone or self.basis_name
            influences = [(fallback_name, 1.0)]

        influences.sort(key=lambda item: item[1], reverse=True)
        influences = influences[:max_influences]
        total = sum(weight for _name, weight in influences) or 1.0
        normalized = [(name, weight / total) for name, weight in influences]
        while len(normalized) < max_influences:
            normalized.append((normalized[0][0], 0.0))

        bone_indices = [0, 0, 0, 0]
        for index, (name, _weight) in enumerate(normalized[:4]):
            if name not in bone_index_map:
                raise ExportError(f'Unknown skin bone "{name}" used by mesh vertex.')
            bone_indices[index] = bone_index_map[name]

        explicit_weights = max(0, max_influences - 1)
        weight_values = [weight for _name, weight in normalized[:explicit_weights]]
        return MeshVertex(
            position=raw_vertex.position,
            normal=raw_vertex.normal,
            uv=raw_vertex.uv,
            tangent=raw_vertex.tangent,
            tangent_sign=raw_vertex.tangent_sign,
            weights=tuple(weight_values),
            bone_indices=tuple(bone_indices),
        )

    def _ordered_skin_bones(self, used_bones: Iterable[str]) -> list[str]:
        ordered: list[str] = []
        used_set = set(used_bones)
        if self.basis_name in used_set:
            ordered.append(self.basis_name)
        for bone_name in self.armature_bone_order:
            if bone_name in used_set and bone_name not in ordered:
                ordered.append(bone_name)
        for bone_name in sorted(used_set):
            if bone_name not in ordered:
                ordered.append(bone_name)
        return ordered

    def material_cache_by_file(self, file_name: str) -> MaterialDef:
        for material in self.material_cache.values():
            if material.file_name == file_name:
                return material
        raise ExportError(f"Missing material cache entry for {file_name}.")

    def _material_for_slot(self, obj: bpy.types.Object, slot_index: int) -> MaterialDef:
        if slot_index < len(obj.material_slots):
            material = obj.material_slots[slot_index].material
        else:
            material = None
        key = ("material", material.as_pointer()) if material else ("fallback", hash((obj.name, slot_index)))
        if key in self.material_cache:
            return self.material_cache[key]

        fallback_name = f"{obj.name}_{slot_index + 1}"
        file_name = self._unique_file_name(material.name if material else fallback_name, ".mtl")
        material_def = self._build_material_definition(material, file_name)
        self.material_cache[key] = material_def
        return material_def

    def _build_material_definition(self, material: bpy.types.Material | None, file_name: str) -> MaterialDef:
        diffuse = self._custom_text(material, "goh_diffuse") if material else None
        bump = self._custom_text(material, "goh_bump") if material else None
        specular = self._custom_text(material, "goh_specular") if material else None
        lightmap = self._custom_text(material, "goh_lightmap") if material else None
        mask = self._custom_text(material, "goh_mask") if material else None
        height = self._custom_text(material, "goh_height") if material else None
        diffuse1 = self._custom_text(material, "goh_diffuse1") if material else None
        simple = self._custom_text(material, "goh_simple") if material else None
        envmap_texture = self._custom_text(material, "goh_envmap_texture") if material else None
        bump_volume = self._custom_text(material, "goh_bump_volume") if material else None
        shader = self._custom_text(material, "goh_material_kind") if material else None
        blend = self._custom_text(material, "goh_blend") if material else None
        color = self._custom_rgba(material, "goh_color_rgba") if material else None
        two_sided = self._custom_bool(material, "goh_two_sided") if material else False
        extra_lines = self._custom_lines(material, "goh_material_lines") if material else []

        if material and material.node_tree:
            principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
            diffuse = diffuse or self._image_from_socket(principled.inputs.get("Base Color") if principled else None)
            bump = bump or self._normal_image(material, principled)
            specular = specular or self._specular_image(material, principled)
            height = height or self._find_named_image(material, ("height", "_hm"))
            lightmap = lightmap or self._find_named_image(material, ("lightmap", "_lm", "_mask"))
            mask = mask or self._find_named_image(material, ("mask", "_msk"))

        shader = (shader or ("bump" if bump or specular else "simple")).lower()
        blend = (blend or ("blend" if material and material.blend_method != "OPAQUE" else "none")).lower()
        color = color or (150, 150, 150, 25)
        if material and hasattr(material, "use_backface_culling") and not material.use_backface_culling:
            two_sided = True

        texture_options = {
            "diffuse": tuple(self._material_texture_options(material, "goh_diffuse_options")) if material else (),
            "bump": tuple(self._material_texture_options(material, "goh_bump_options")) if material else (),
            "specular": tuple(self._material_texture_options(material, "goh_specular_options")) if material else (),
            "lightmap": tuple(self._material_texture_options(material, "goh_lightmap_options")) if material else (),
            "mask": tuple(self._material_texture_options(material, "goh_mask_options")) if material else (),
            "height": tuple(self._material_texture_options(material, "goh_height_options")) if material else (),
            "diffuse1": tuple(self._material_texture_options(material, "goh_diffuse1_options")) if material else (),
            "simple": tuple(self._material_texture_options(material, "goh_simple_options")) if material else (),
            "envmap": tuple(self._material_texture_options(material, "goh_envmap_texture_options")) if material else (),
            "bumpVolume": tuple(self._material_texture_options(material, "goh_bump_volume_options")) if material else (),
        }
        texture_options = {key: value for key, value in texture_options.items() if value}

        return MaterialDef(
            file_name=file_name,
            shader=shader,
            diffuse_texture=diffuse,
            bump_texture=bump,
            specular_texture=specular,
            lightmap_texture=lightmap,
            mask_texture=mask,
            height_texture=height,
            diffuse1_texture=diffuse1,
            simple_texture=simple,
            envmap_texture=envmap_texture,
            bump_volume_texture=bump_volume,
            color_rgba=color,
            blend=blend,
            two_sided=two_sided,
            gloss_scale=self._custom_float(material, "goh_gloss_scale") if material else None,
            alpharef=self._custom_float(material, "goh_alpharef") if material else None,
            specular_intensity=self._custom_float(material, "goh_specular_intensity") if material else None,
            period=self._custom_float(material, "goh_period") if material else None,
            envamount=self._custom_float(material, "goh_envamount") if material else None,
            parallax_scale=self._custom_float(material, "goh_parallax_scale") if material else None,
            amount=self._custom_float(material, "goh_amount") if material else None,
            tile=self._custom_bool(material, "goh_tile") if material else False,
            glow=self._custom_bool(material, "goh_glow") if material else False,
            no_light=self._custom_bool(material, "goh_nolight") if material else False,
            full_specular=self._custom_bool(material, "goh_full_specular") if material else False,
            emits_heat=self._custom_bool(material, "goh_emitsheat") if material else False,
            translucency=self._custom_bool(material, "goh_translucency") if material else False,
            alpha_to_coverage=self._custom_bool(material, "goh_alphatocoverage") if material else False,
            no_outlines=self._custom_bool(material, "goh_no_outlines") if material else False,
            fake_reflection=self._custom_bool(material, "goh_fake_reflection") if material else False,
            texture_options=texture_options,
            extra_lines=extra_lines,
        )

    def _material_texture_options(self, owner, key: str) -> list[str]:
        options = self._custom_lines(owner, key)
        normalized: list[str] = []
        for option in options:
            text = option.strip()
            if not text:
                continue
            normalized.append(text if text.startswith("{") else f"{{{text}}}")
        return normalized

    def _normal_image(self, material: bpy.types.Material, principled: bpy.types.Node | None) -> str | None:
        if principled and "Normal" in principled.inputs:
            socket = principled.inputs["Normal"]
            if socket.is_linked:
                node = socket.links[0].from_node
                if node.type == "NORMAL_MAP":
                    return self._image_from_socket(node.inputs.get("Color"))
        return self._find_named_image(material, ("normal", "_n_n", "bump"))

    def _specular_image(self, material: bpy.types.Material, principled: bpy.types.Node | None) -> str | None:
        if principled:
            for input_name in ("Specular IOR Level", "Specular", "Roughness"):
                socket = principled.inputs.get(input_name)
                image = self._image_from_socket(socket)
                if image:
                    return image
        return self._find_named_image(material, ("spec", "_n_s", "gloss"))

    def _find_named_image(self, material: bpy.types.Material, needles: tuple[str, ...]) -> str | None:
        if not material or not material.node_tree:
            return None
        for node in material.node_tree.nodes:
            if node.type != "TEX_IMAGE" or not node.image:
                continue
            name = node.image.name.lower()
            path = (node.image.filepath_from_user() or node.image.filepath or "").lower()
            if any(needle in name or needle in path for needle in needles):
                return Path(node.image.filepath_from_user() or node.image.filepath or node.image.name).stem
        return None

    def _image_from_socket(self, socket: bpy.types.NodeSocket | None) -> str | None:
        if socket is None or not socket.is_linked:
            return None
        visited: set[int] = set()
        pending = [socket.links[0].from_node]
        while pending:
            node = pending.pop()
            if id(node) in visited:
                continue
            visited.add(id(node))
            if node.type == "TEX_IMAGE" and node.image:
                return Path(node.image.filepath_from_user() or node.image.filepath or node.image.name).stem
            for input_socket in getattr(node, "inputs", []):
                if input_socket.is_linked:
                    pending.extend(link.from_node for link in input_socket.links)
        return None

    def _resolve_attach_bone(self, obj: bpy.types.Object) -> str:
        custom_bone = self._custom_text(obj, "goh_attach_bone")
        if custom_bone:
            return custom_bone
        if obj.parent == self.armature_obj and obj.parent_type == "BONE" and obj.parent_bone:
            return obj.parent_bone
        return self.basis_name

    def _resolve_volume_bone(
        self,
        obj: bpy.types.Object,
        bone_name_map: dict[bpy.types.Object, str],
        visual_scope: set[bpy.types.Object],
    ) -> tuple[str, Matrix]:
        custom_bone = self._custom_text(obj, "goh_volume_bone")
        if custom_bone:
            return custom_bone, self._reference_matrix_for_bone(custom_bone)

        if self.armature_obj and obj.parent == self.armature_obj and obj.parent_type == "BONE" and obj.parent_bone:
            return obj.parent_bone, self._reference_matrix_for_bone(obj.parent_bone)

        if obj.parent in bone_name_map:
            bone_name = bone_name_map[obj.parent]
            reference_matrix = obj.parent.matrix_world
            return bone_name, reference_matrix

        derived = self._derive_volume_bone_from_name(obj.name)
        if derived:
            return derived, self._reference_matrix_for_bone(derived)

        return self.basis_name, self._reference_matrix_for_bone(self.basis_name)

    def _reference_matrix_for_bone(self, bone_name: str) -> Matrix:
        if self.armature_obj is None or bone_name == self.basis_name:
            if self.armature_obj:
                return self.armature_obj.matrix_world.copy()
            return Matrix.Identity(4)
        bone = self.armature_obj.data.bones.get(bone_name)
        if bone is None:
            raise ExportError(f'Unknown reference bone "{bone_name}".')
        return self.armature_obj.matrix_world @ bone.matrix_local

    def _vertex_influences(
        self,
        obj: bpy.types.Object,
        vertex: bpy.types.MeshVertex,
        fallback_bone: str,
    ) -> tuple[tuple[str, float], ...]:
        if self.armature_obj is None:
            return ()

        influences: list[tuple[str, float]] = []
        for group_element in vertex.groups:
            if group_element.weight <= EPSILON:
                continue
            if group_element.group >= len(obj.vertex_groups):
                continue
            group_name = obj.vertex_groups[group_element.group].name
            if group_name == self.basis_name or group_name in self.armature_bone_order:
                influences.append((group_name, float(group_element.weight)))

        influences.sort(key=lambda item: item[1], reverse=True)
        if len(influences) > 4:
            self.warnings.append(f'Mesh "{obj.name}" has vertices with more than 4 bone weights. Extra weights were truncated.')
            influences = influences[:4]
        total = sum(weight for _bone_name, weight in influences) or 1.0
        normalized = tuple((bone_name, weight / total) for bone_name, weight in influences)
        return normalized

    def _mesh_vertex_key(self, vertex: MeshVertex) -> tuple:
        values = [
            *vertex.position,
            *vertex.normal,
            *vertex.uv,
            *vertex.tangent,
            vertex.tangent_sign,
            *vertex.weights,
            *vertex.bone_indices,
        ]
        return tuple(round(value, 6) if isinstance(value, float) else value for value in values)

    def _legacy_entries(self, owner) -> tuple[set[str], dict[str, list[str]]]:
        if owner is None:
            return set(), {}
        owner_id = owner.as_pointer() if hasattr(owner, "as_pointer") else id(owner)
        cached = self.legacy_cache.get(owner_id)
        if cached is not None:
            return cached

        flags: set[str] = set()
        values: dict[str, list[str]] = {}

        def add_value(raw_key: str, raw_value) -> None:
            key = str(raw_key).strip().lower()
            if not key or key.startswith("_") or key.startswith("goh_"):
                return
            if isinstance(raw_value, bool):
                if raw_value:
                    flags.add(key)
                return
            if raw_value is None:
                return
            if isinstance(raw_value, (int, float)):
                values.setdefault(key, []).append(str(raw_value))
                return
            text = str(raw_value).strip()
            if not text:
                flags.add(key)
                return
            values.setdefault(key, []).append(text)

        if hasattr(owner, "keys"):
            for raw_key in owner.keys():
                if raw_key == "goh_legacy_props":
                    continue
                try:
                    add_value(raw_key, owner.get(raw_key))
                except Exception:
                    continue
        raw_text = ""
        if hasattr(owner, "get"):
            try:
                raw_text = str(owner.get("goh_legacy_props") or "")
            except Exception:
                raw_text = ""
        if raw_text.strip():
            flags.update(_legacy_flag_set(raw_text))
            parsed = _legacy_key_values(raw_text)
            for key, bucket in parsed.items():
                values.setdefault(key, []).extend(bucket)

        result = (flags, values)
        self.legacy_cache[owner_id] = result
        return result

    def _legacy_has_flag(self, owner, *flag_names: str) -> bool:
        flags, values = self._legacy_entries(owner)
        for flag_name in flag_names:
            key = flag_name.strip().lower()
            if key in flags:
                return True
            if key in values and any(not entry or entry.lower() not in {"0", "false", "off"} for entry in values[key]):
                return True
        return False

    def _legacy_values(self, owner, *keys: str) -> list[str]:
        _flags, values = self._legacy_entries(owner)
        entries: list[str] = []
        for key in keys:
            entries.extend(values.get(key.strip().lower(), ()))
        return entries

    def _legacy_first_text(self, owner, *keys: str) -> str | None:
        for value in self._legacy_values(owner, *keys):
            text = str(value).strip()
            if text:
                return text
        return None

    def _legacy_first_float(self, owner, *keys: str) -> float | None:
        for value in self._legacy_values(owner, *keys):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _find_basis_helper_object(self) -> bpy.types.Object | None:
        for obj in sorted(self.context.scene.objects, key=lambda item: item.name.lower()):
            if obj.get("goh_basis_helper"):
                return obj
        for obj in sorted(self.context.scene.objects, key=lambda item: item.name.lower()):
            if obj.type == "EMPTY" and obj.name.lower() == GOH_BASIS_HELPER_NAME.lower():
                return obj
        return None

    def _is_basis_helper_object(self, obj: bpy.types.Object | None) -> bool:
        if obj is None:
            return False
        if obj.get("goh_basis_helper"):
            return True
        return obj.type == "EMPTY" and obj.name.lower() == GOH_BASIS_HELPER_NAME.lower()

    def _basis_parameter_text(self) -> str | None:
        parts: list[str] = []
        if self.basis_helper is not None:
            helper_type = self._legacy_first_text(self.basis_helper, "type")
            helper_model = self._legacy_first_text(self.basis_helper, "model")
            helper_radius = self._legacy_first_text(self.basis_helper, "wheelradius")
            helper_steer = self._legacy_first_text(self.basis_helper, "steermax")
            for key, value in (
                ("Type", helper_type),
                ("Model", helper_model),
                ("Wheelradius", helper_radius),
                ("SteerMax", helper_steer),
            ):
                if value:
                    parts.append(f"{key}={value};")
        if self.basis_settings and self.basis_settings.enabled:
            model_value = _basis_model_value(self.basis_settings)
            parts = [
                f"Type={_basis_entity_type_value(self.basis_settings)};",
            ]
            if model_value:
                parts.append(f"Model={model_value};")
            parts.append(f"Wheelradius={self.basis_settings.wheel_radius:g};")
            parts.append(f"SteerMax={self.basis_settings.steer_max:g};")
        text = "".join(parts).strip()
        return text or None

    def _basis_metadata_comments(self) -> list[str]:
        comments: list[str] = []
        if self.basis_settings and self.basis_settings.enabled:
            entity_type = _basis_entity_type_value(self.basis_settings)
            model_value = _basis_model_value(self.basis_settings)
            comments.append(f"Basis Type={entity_type}")
            if model_value:
                comments.append(f"Basis Model={model_value}")
            comments.append(f"Basis Wheelradius={self.basis_settings.wheel_radius:g}")
            comments.append(f"Basis SteerMax={self.basis_settings.steer_max:g}")
            return comments
        if self.basis_helper is None:
            return comments
        key_labels = {
            "type": "Type",
            "model": "Model",
            "wheelradius": "Wheelradius",
            "steermax": "SteerMax",
        }
        for key in ("type", "model", "wheelradius", "steermax"):
            value = self._legacy_first_text(self.basis_helper, key)
            if value:
                comments.append(f"Basis {key_labels[key]}={value}")
        return comments

    def _legacy_parameter_text_for_owner(self, owner) -> str | None:
        explicit = self._custom_text(owner, "goh_parameters")
        if explicit:
            return explicit
        parts: list[str] = []
        for key_name, legacy_key in (
            ("ID", "id"),
            ("Radius", "radius"),
            ("Support", "support"),
            ("Wheelradius", "wheelradius"),
            ("SteerMax", "steermax"),
            ("Type", "type"),
            ("Model", "model"),
        ):
            value = self._legacy_first_text(owner, legacy_key)
            if value:
                parts.append(f"{key_name}={value};")
        text = "".join(parts).strip()
        return text or None

    def _transform_block_mode(self, owner) -> str | None:
        value = self._custom_text(owner, "goh_transform_block") or self._legacy_first_text(owner, "transform")
        if not value:
            return None
        normalized = value.strip().lower()
        if normalized in {"orientation", "ori"}:
            return "orientation"
        if normalized in {"matrix34", "matrix"}:
            return "matrix34"
        if normalized == "position":
            return "position"
        if normalized == "auto":
            return "auto"
        return None

    def _bone_name_for_object(self, obj: bpy.types.Object) -> str:
        return self._custom_text(obj, "goh_bone_name") or self._legacy_first_text(obj, "id") or obj.name

    def _volume_entry_name(self, obj: bpy.types.Object) -> str:
        custom_name = self._custom_text(obj, "goh_volume_name")
        if custom_name:
            return custom_name
        legacy_name = self._legacy_first_text(obj, "id")
        if legacy_name:
            return legacy_name
        lower_name = obj.name.lower()
        if lower_name.endswith("_vol"):
            return obj.name[:-4]
        return obj.name

    def _derive_volume_bone_from_name(self, name: str) -> str | None:
        lower_name = name.lower()
        if lower_name.endswith("_vol") and len(name) > 4:
            return name[:-4]
        return None

    def _bone_volume_flags(self, owner) -> tuple[str, ...]:
        flags: list[str] = []
        flag_map = (
            ("goh_no_cast_shadows", "NoCastShadows"),
            ("goh_decal_target", "DecalTarget"),
            ("goh_no_group_mesh", "NoGroupMesh"),
            ("goh_no_get_shadows", "NoGetShadows"),
            ("goh_ground", "Ground"),
        )
        for prop_name, flag_name in flag_map:
            if self._custom_bool(owner, prop_name):
                flags.append(flag_name)
        return tuple(flags)

    def _mesh_views_for_owner(
        self,
        owner,
        default_file: str | None,
        flags: tuple[str, ...],
        layer,
    ) -> list[MeshViewDef]:
        files_value = self._custom_text(owner, "goh_lod_files")
        if not files_value:
            return [MeshViewDef(file_name=default_file, flags=flags, layer=layer)] if default_file else []
        parts = [
            entry.strip()
            for chunk in files_value.replace("\n", ";").split(";")
            for entry in chunk.split(",")
            if entry.strip()
        ]
        return [MeshViewDef(file_name=part, flags=flags, layer=layer) for part in parts]

    def _is_non_visual_helper(self, obj: bpy.types.Object | None) -> bool:
        return self._is_volume_object(obj) or self._is_obstacle_object(obj) or self._is_area_object(obj) or self._is_basis_helper_object(obj)

    def _is_obstacle_object(self, obj: bpy.types.Object | None) -> bool:
        if obj is None or obj.type != "MESH":
            return False
        if self._custom_bool(obj, "goh_is_obstacle"):
            return True
        return any(collection.name == self.obstacle_collection_name for collection in obj.users_collection)

    def _is_area_object(self, obj: bpy.types.Object | None) -> bool:
        if obj is None or obj.type != "MESH":
            return False
        if self._custom_bool(obj, "goh_is_area"):
            return True
        return any(collection.name == self.area_collection_name for collection in obj.users_collection)

    def _file_name_for_bone(self, bone_name: str, extension: str) -> str:
        key = f"{bone_name}|{extension.lower()}"
        if key not in self.bone_file_names:
            self.bone_file_names[key] = self._unique_file_name(bone_name, extension)
        return self.bone_file_names[key]

    def _unique_file_name(self, stem: str, extension: str) -> str:
        safe_stem = sanitized_file_stem(stem)
        key = f"{safe_stem}{extension.lower()}"
        count = self.file_name_counts.get(key, 0)
        self.file_name_counts[key] = count + 1
        if count == 0:
            return f"{safe_stem}{extension}"
        return f"{safe_stem}_{count + 1}{extension}"

    def _iter_descendants(self, obj: bpy.types.Object) -> Iterable[bpy.types.Object]:
        yield obj
        for child in obj.children:
            yield from self._iter_descendants(child)

    def _find_single_armature(self, visual_objects: set[bpy.types.Object]) -> bpy.types.Object | None:
        armatures = [obj for obj in visual_objects if obj.type == "ARMATURE"]
        if not armatures:
            return None
        if len(armatures) > 1:
            raise ExportError("The current GOH exporter only supports one armature per export.")
        return armatures[0]

    def _axis_rotation_matrix(self, axis_mode: str) -> Matrix:
        if axis_mode == "BLENDER_TO_GOH":
            return Matrix.Rotation(-math.pi / 2.0, 4, "Z")
        return Matrix.Identity(4)

    def _basis_rotation_matrix(self) -> Matrix:
        return Matrix(
            (
                (1.0, 0.0, 0.0),
                (0.0, -1.0, 0.0),
                (0.0, 0.0, 1.0),
            )
        )

    def _basis_matrix_rows(
        self,
        location: Vector | None = None,
        rotation_matrix: Matrix | None = None,
    ) -> tuple[tuple[float, float, float], ...]:
        basis_rotation = self._basis_rotation_matrix()
        if rotation_matrix is not None:
            basis_rotation = basis_rotation @ rotation_matrix.to_3x3()
        return self._matrix_rows(location or Vector((0.0, 0.0, 0.0)), basis_rotation)

    def _loc_rot_matrix(self, matrix: Matrix) -> Matrix:
        loc, rot, _scale = matrix.decompose()
        return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()

    def _matrix_rows_from_matrix(self, matrix: Matrix) -> tuple[tuple[float, float, float], ...]:
        location, rotation, _scale = matrix.decompose()
        return self._matrix_rows(location, rotation.to_matrix())

    def _matrix_rows(self, location: Vector, rotation_matrix: Matrix) -> tuple[tuple[float, float, float], ...]:
        axis3 = self.axis_rotation.to_3x3()
        converted_rotation = axis3 @ rotation_matrix.to_3x3() @ axis3.inverted()
        converted_location = axis3 @ location
        converted_location *= self.scale_factor
        return (
            (float(converted_rotation[0][0]), float(converted_rotation[0][1]), float(converted_rotation[0][2])),
            (float(converted_rotation[1][0]), float(converted_rotation[1][1]), float(converted_rotation[1][2])),
            (float(converted_rotation[2][0]), float(converted_rotation[2][1]), float(converted_rotation[2][2])),
            (float(converted_location[0]), float(converted_location[1]), float(converted_location[2])),
        )

    def _convert_point(self, point: Vector) -> tuple[float, float, float]:
        converted = self.axis_rotation.to_3x3() @ Vector(point)
        converted *= self.scale_factor
        return (float(converted[0]), float(converted[1]), float(converted[2]))

    def _convert_length(self, value: float) -> float:
        return float(abs(value) * self.scale_factor)

    def _convert_lengths(self, value: Vector) -> tuple[float, float, float]:
        return (
            self._convert_length(value.x),
            self._convert_length(value.y),
            self._convert_length(value.z),
        )

    def _convert_direction(self, direction: Vector) -> tuple[float, float, float]:
        converted = self.axis_rotation.to_3x3() @ Vector(direction)
        if converted.length > EPSILON:
            converted.normalize()
        return (float(converted[0]), float(converted[1]), float(converted[2]))

    def _convert_uv(self, uv: Vector) -> tuple[float, float]:
        return (float(uv.x), float(1.0 - uv.y) if self.operator.flip_v else float(uv.y))

    def _transform_normal(self, matrix: Matrix, normal: Vector) -> Vector:
        normal_matrix = matrix.to_3x3().inverted().transposed()
        transformed = normal_matrix @ Vector(normal)
        if transformed.length > EPSILON:
            transformed.normalize()
        return transformed

    def _transform_tangent(self, matrix: Matrix, tangent: Vector) -> Vector:
        tangent_matrix = matrix.to_3x3()
        transformed = tangent_matrix @ Vector(tangent)
        if transformed.length > EPSILON:
            transformed.normalize()
        return transformed

    def _scale_is_identity(self, scale: Vector) -> bool:
        return (
            abs(scale.x - 1.0) <= 1e-4
            and abs(scale.y - 1.0) <= 1e-4
            and abs(scale.z - 1.0) <= 1e-4
        )

    def _is_hidden(self, obj: bpy.types.Object) -> bool:
        return obj.hide_get() or obj.hide_viewport

    def _is_volume_object(self, obj: bpy.types.Object | None) -> bool:
        if obj is None or obj.type != "MESH":
            return False
        if bool(obj.get("goh_is_volume")) or self._legacy_has_flag(obj, "volume"):
            return True
        if obj.name.lower().endswith("_vol"):
            return True
        return any(collection.name == self.volume_collection_name for collection in obj.users_collection)

    def _custom_scalar(self, owner, key: str):
        if owner is None:
            return None
        value = owner.get(key)
        if value is not None:
            return value
        for legacy_key in GOH_LEGACY_INT_FALLBACKS.get(key, ()):
            legacy_value = self._legacy_first_float(owner, legacy_key)
            if legacy_value is not None:
                return int(legacy_value)
        return None

    def _custom_text(self, owner, key: str) -> str | None:
        if owner is None:
            return None
        value = owner.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
        if key == "goh_bone_type":
            for flag_name in ("revolute", "prizmatic", "socket"):
                if self._legacy_has_flag(owner, flag_name):
                    return flag_name
        for legacy_key in GOH_LEGACY_TEXT_FALLBACKS.get(key, ()):
            text = self._legacy_first_text(owner, legacy_key)
            if text:
                return text
        return None

    def _custom_float_list(self, owner, key: str) -> tuple[float, ...]:
        text = self._custom_text(owner, key)
        if not text:
            if key == "goh_limits":
                min_value = self._legacy_first_float(owner, "ikmin")
                max_value = self._legacy_first_float(owner, "ikmax")
                values = tuple(
                    value
                    for value in (min_value, max_value)
                    if value is not None
                )
                return values
            return ()
        values: list[float] = []
        for token in re.split(r"[\s,;]+", text):
            if not token:
                continue
            try:
                values.append(float(token))
            except ValueError:
                continue
        return tuple(values)

    def _custom_bool(self, owner, key: str) -> bool:
        if owner is None:
            return False
        value = bool(owner.get(key))
        if value:
            return True
        flag_names = GOH_LEGACY_BOOL_FLAGS.get(key)
        if flag_names and self._legacy_has_flag(owner, *flag_names):
            return True
        return False

    def _custom_int(self, owner, key: str) -> int | None:
        if owner is None:
            return None
        value = owner.get(key)
        if value is None:
            for legacy_key in GOH_LEGACY_INT_FALLBACKS.get(key, ()):
                legacy_value = self._legacy_first_float(owner, legacy_key)
                if legacy_value is not None:
                    return int(legacy_value)
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _custom_float(self, owner, key: str) -> float | None:
        if owner is None:
            return None
        value = owner.get(key)
        if value is None:
            for legacy_key in GOH_LEGACY_FLOAT_FALLBACKS.get(key, ()):
                legacy_value = self._legacy_first_float(owner, legacy_key)
                if legacy_value is not None:
                    return legacy_value
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _custom_lines(self, owner, key: str) -> list[str]:
        if owner is None:
            return []
        value = owner.get(key)
        if value is None:
            return []
        if isinstance(value, str):
            parts = [line.strip() for line in value.replace("\r", "\n").split("\n")]
            return [part for part in parts if part]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _custom_rgba(self, owner, key: str) -> tuple[int, int, int, int] | None:
        if owner is None:
            return None
        value = owner.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            parts = [part.strip() for part in value.replace(";", ",").split(",")]
            if len(parts) == 4:
                try:
                    return tuple(int(part) for part in parts)  # type: ignore[return-value]
                except ValueError:
                    return None
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                return tuple(int(part) for part in value)  # type: ignore[return-value]
            except (TypeError, ValueError):
                return None
        return None

    def _volume_kind(self, owner) -> str:
        value = (self._custom_text(owner, "goh_volume_kind") or "polyhedron").strip().lower()
        if value in {"polyhedron", "mesh", "vol"}:
            return "polyhedron"
        if value in {"box", "cube"}:
            return "box"
        if value in {"sphere", "ball"}:
            return "sphere"
        if value in {"cylinder", "cyl"}:
            return "cylinder"
        return value

    def _volume_axis(self, owner) -> str:
        value = (self._custom_text(owner, "goh_volume_axis") or "z").strip().lower()
        if value not in {"x", "y", "z"}:
            return "z"
        return value

    def _volume_thickness(self, owner) -> dict[str, tuple[float, ...]]:
        mapping = {
            "common": "goh_thickness",
            "front": "goh_thickness_front",
            "rear": "goh_thickness_rear",
            "right": "goh_thickness_right",
            "left": "goh_thickness_left",
            "top": "goh_thickness_top",
            "bottom": "goh_thickness_bottom",
        }
        thickness: dict[str, tuple[float, ...]] = {}
        for entry_key, prop_name in mapping.items():
            values = self._custom_float_list(owner, prop_name)
            if not values:
                continue
            thickness[entry_key] = tuple(self._convert_length(value) for value in values[:2])
        return thickness


class GOHAnimationImporter:
    def __init__(self, context: bpy.types.Context, operator: "IMPORT_SCENE_OT_goh_anm") -> None:
        self.context = context
        self.operator = operator
        self.axis_rotation = self._axis_rotation_matrix(operator.axis_mode)
        self.scale_factor = operator.scale_factor
        self.warnings: list[str] = []

    def import_animation(self) -> list[str]:
        animation = read_animation(self.operator.filepath)
        armature = self._target_armature()
        if armature is not None:
            self._apply_to_armature(animation, armature)
        else:
            self._apply_to_objects(animation)
        self._apply_mesh_animation(animation)
        return self.warnings

    def _apply_mesh_animation(self, animation: AnimationFile) -> None:
        if not animation.mesh_frames:
            return

        mesh_names = sorted({name for frame in animation.mesh_frames for name in frame})
        if not mesh_names:
            return

        targets: dict[str, MeshImportTarget] = {}
        for mesh_name in mesh_names:
            states = [frame_state.get(mesh_name) for frame_state in animation.mesh_frames]
            active_states = [state for state in states if state is not None]
            if not active_states:
                continue
            required_vertices = max(state.first_vertex + state.vertex_count for state in active_states)
            target = self._resolve_mesh_import_target(mesh_name, required_vertices)
            if target is None:
                continue
            targets[mesh_name] = target

        for mesh_name, target in targets.items():
            self._import_mesh_shape_keys(animation, mesh_name, target)

    def _resolve_mesh_import_target(self, mesh_name: str, required_vertices: int) -> MeshImportTarget | None:
        candidates = self._mesh_candidate_objects(mesh_name)
        valid_targets: list[MeshImportTarget] = []
        mismatched: list[str] = []
        for obj in candidates:
            export_to_source = self._build_export_vertex_map(obj)
            if len(export_to_source) < required_vertices:
                mismatched.append(f'{obj.name} ({len(export_to_source)})')
                continue
            valid_targets.append(
                MeshImportTarget(
                    obj=obj,
                    export_to_source=export_to_source,
                    mesh_bake_matrix=self._mesh_bake_matrix_for_object(obj, mesh_name),
                )
            )

        if len(valid_targets) == 1:
            return valid_targets[0]
        if len(valid_targets) > 1:
            joined = ", ".join(target.obj.name for target in valid_targets)
            self.warnings.append(
                f'Mesh animation chunk "{mesh_name}" matched multiple Blender meshes ({joined}). Select one target mesh before importing to disambiguate.'
            )
            return None
        if mismatched:
            joined = ", ".join(mismatched)
            self.warnings.append(
                f'Mesh animation chunk "{mesh_name}" did not find a compatible mesh topology. Candidate export vertex counts: {joined}.'
            )
        else:
            self.warnings.append(f'Mesh animation chunk "{mesh_name}" did not match any Blender mesh object.')
        return None

    def _mesh_candidate_objects(self, mesh_name: str) -> list[bpy.types.Object]:
        selected_meshes = [obj for obj in self.context.selected_objects if obj.type == "MESH"]
        search_pool = selected_meshes or [obj for obj in self.context.view_layer.objects if obj.type == "MESH"]
        candidates: list[bpy.types.Object] = []
        seen: set[int] = set()
        for obj in search_pool:
            names = {
                obj.name,
                str(obj.get("goh_bone_name")).strip() if obj.get("goh_bone_name") is not None else "",
                str(obj.get("goh_attach_bone")).strip() if obj.get("goh_attach_bone") is not None else "",
                obj.parent_bone.strip() if obj.parent_type == "BONE" and obj.parent_bone else "",
            }
            if mesh_name not in names:
                continue
            pointer = obj.as_pointer()
            if pointer in seen:
                continue
            seen.add(pointer)
            candidates.append(obj)
        return candidates

    def _build_export_vertex_map(self, obj: bpy.types.Object) -> list[int]:
        mesh = obj.data.copy()
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
        mesh.calc_loop_triangles()

        uv_layer = mesh.uv_layers.active
        tangent_ready = False
        if uv_layer is not None:
            try:
                mesh.calc_tangents(uvmap=uv_layer.name)
                tangent_ready = True
            except RuntimeError:
                tangent_ready = False

        vertex_lookup: dict[tuple, int] = {}
        export_to_source: list[int] = []
        try:
            for triangle in mesh.loop_triangles:
                for loop_index in triangle.loops:
                    loop = mesh.loops[loop_index]
                    vertex = mesh.vertices[loop.vertex_index]
                    uv = uv_layer.data[loop_index].uv.copy() if uv_layer is not None else Vector((0.0, 0.0))
                    if tangent_ready:
                        tangent = loop.tangent.copy()
                        tangent_sign = float(loop.bitangent_sign)
                    else:
                        tangent = Vector((1.0, 0.0, 0.0))
                        tangent_sign = 1.0
                    key = (
                        round(float(vertex.co.x), 6),
                        round(float(vertex.co.y), 6),
                        round(float(vertex.co.z), 6),
                        round(float(loop.normal.x), 6),
                        round(float(loop.normal.y), 6),
                        round(float(loop.normal.z), 6),
                        round(float(uv.x), 6),
                        round(float(uv.y), 6),
                        round(float(tangent.x), 6),
                        round(float(tangent.y), 6),
                        round(float(tangent.z), 6),
                        round(tangent_sign, 6),
                    )
                    if key in vertex_lookup:
                        continue
                    vertex_lookup[key] = len(export_to_source)
                    export_to_source.append(loop.vertex_index)
        finally:
            if tangent_ready:
                mesh.free_tangents()
            bpy.data.meshes.remove(mesh)
        return export_to_source

    def _mesh_bake_matrix_for_object(self, obj: bpy.types.Object, mesh_name: str) -> Matrix:
        basis_name = self.operator.basis_name.strip() or "basis"
        if obj.parent and obj.parent.type == "ARMATURE":
            attach_bone = str(obj.get("goh_attach_bone")).strip() if obj.get("goh_attach_bone") is not None else ""
            if obj.parent_type == "BONE" and obj.parent_bone:
                attach_bone = obj.parent_bone
            if not attach_bone:
                attach_bone = basis_name
            if attach_bone == mesh_name:
                if attach_bone == basis_name:
                    reference = obj.parent.matrix_world.copy()
                else:
                    bone = obj.parent.data.bones.get(attach_bone)
                    if bone is None:
                        return Matrix.Identity(4)
                    reference = obj.parent.matrix_world @ bone.matrix_local
                return reference.inverted_safe() @ obj.matrix_world

        parent_world = Matrix.Identity(4)
        if obj.parent and obj.parent.type != "ARMATURE":
            parent_world = obj.parent.matrix_world
        local_matrix = parent_world.inverted_safe() @ obj.matrix_world
        loc, rot, _scale = local_matrix.decompose()
        node_matrix = Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
        return node_matrix.inverted_safe() @ local_matrix

    def _import_mesh_shape_keys(self, animation: AnimationFile, mesh_name: str, target: MeshImportTarget) -> None:
        obj = target.obj
        frame_start = self.operator.frame_start
        prefix = f"GOH_{Path(animation.file_name).stem}_{mesh_name}_"

        if obj.data.shape_keys is None:
            obj.shape_key_add(name="Basis", from_mix=False)

        imported_keys: list[tuple[int, bpy.types.ShapeKey]] = []
        for offset, frame_state in enumerate(animation.mesh_frames):
            mesh_state = frame_state.get(mesh_name)
            if mesh_state is None:
                continue
            frame = frame_start + offset
            key_name = f"{prefix}{frame:04d}"
            shape_key = obj.data.shape_keys.key_blocks.get(key_name)
            if shape_key is None:
                shape_key = obj.shape_key_add(name=key_name, from_mix=False)
            self._populate_shape_key(shape_key, target, mesh_state)
            imported_keys.append((frame, shape_key))

        if not imported_keys:
            return

        shape_keys = obj.data.shape_keys
        assert shape_keys is not None
        action = bpy.data.actions.new(name=f"{Path(animation.file_name).stem}_{obj.name}_mesh")
        shape_keys.animation_data_create().action = action
        for _frame, shape_key in imported_keys:
            shape_key.value = 0.0

        for current_frame, current_key in imported_keys:
            for frame, shape_key in imported_keys:
                shape_key.value = 1.0 if shape_key == current_key else 0.0
                shape_key.keyframe_insert(data_path="value", frame=frame)

        legacy_fcurves = getattr(action, "fcurves", None)
        if legacy_fcurves is not None:
            for fcurve in legacy_fcurves:
                for keyframe in fcurve.keyframe_points:
                    keyframe.interpolation = "CONSTANT"

    def _populate_shape_key(
        self,
        shape_key: bpy.types.ShapeKey,
        target: MeshImportTarget,
        mesh_state: MeshAnimationState,
    ) -> None:
        positions_by_source: dict[int, Vector] = {}
        counts_by_source: dict[int, int] = {}
        inverse_bake = target.mesh_bake_matrix.inverted_safe()
        for local_index in range(mesh_state.vertex_count):
            export_index = mesh_state.first_vertex + local_index
            if export_index >= len(target.export_to_source):
                continue
            source_index = target.export_to_source[export_index]
            point = self._decode_mesh_vertex_point(mesh_state, local_index)
            point = inverse_bake @ point
            positions_by_source[source_index] = positions_by_source.get(source_index, Vector((0.0, 0.0, 0.0))) + point
            counts_by_source[source_index] = counts_by_source.get(source_index, 0) + 1

        for source_index, point in positions_by_source.items():
            count = counts_by_source[source_index]
            averaged = point / float(max(1, count))
            shape_key.data[source_index].co = averaged

    def _decode_mesh_vertex_point(self, mesh_state: MeshAnimationState, local_index: int) -> Vector:
        offset = local_index * mesh_state.vertex_stride
        x, y, z = struct.unpack_from("<3f", mesh_state.vertex_data, offset)
        point = self.axis_rotation.to_3x3().inverted() @ Vector((x, y, z))
        if abs(self.scale_factor) > EPSILON:
            point /= self.scale_factor
        return Vector((point.x, point.y, point.z))

    def _target_armature(self) -> bpy.types.Object | None:
        selected = [obj for obj in self.context.selected_objects if obj.type == "ARMATURE"]
        if selected:
            return selected[0]
        armatures = [obj for obj in self.context.view_layer.objects if obj.type == "ARMATURE"]
        return armatures[0] if len(armatures) == 1 else None

    def _apply_to_armature(self, animation: AnimationFile, armature: bpy.types.Object) -> None:
        action = bpy.data.actions.new(name=f"{Path(animation.file_name).stem}_anm")
        armature.animation_data_create().action = action
        basis_name = self.operator.basis_name.strip() or "basis"
        frame_start = self.operator.frame_start
        for offset, frame_state in enumerate(animation.frames):
            frame = frame_start + offset
            basis_state = frame_state.get(basis_name)
            if basis_state is not None:
                location, rotation = self._decode_matrix_rows(basis_state.matrix)
                armature.rotation_mode = "QUATERNION"
                armature.location = location
                armature.rotation_quaternion = rotation
                armature.keyframe_insert("location", frame=frame)
                armature.keyframe_insert("rotation_quaternion", frame=frame)

            for bone_name, state in frame_state.items():
                if bone_name == basis_name:
                    continue
                pose_bone = armature.pose.bones.get(bone_name)
                if pose_bone is None:
                    continue
                location, rotation = self._decode_matrix_rows(state.matrix)
                pose_bone.rotation_mode = "QUATERNION"
                pose_bone.location = location
                pose_bone.rotation_quaternion = rotation
                pose_bone.keyframe_insert("location", frame=frame)
                pose_bone.keyframe_insert("rotation_quaternion", frame=frame)

    def _apply_to_objects(self, animation: AnimationFile) -> None:
        object_map: dict[str, bpy.types.Object] = {}
        for obj in self.context.view_layer.objects:
            if obj.type not in {"MESH", "EMPTY"}:
                continue
            object_map[obj.name] = obj
            custom_name = obj.get("goh_bone_name")
            if custom_name:
                object_map[str(custom_name)] = obj

        frame_start = self.operator.frame_start
        for offset, frame_state in enumerate(animation.frames):
            frame = frame_start + offset
            for bone_name, state in frame_state.items():
                obj = object_map.get(bone_name)
                if obj is None:
                    continue
                location, rotation = self._decode_matrix_rows(state.matrix)
                obj.rotation_mode = "QUATERNION"
                obj.location = location
                obj.rotation_quaternion = rotation
                obj.hide_viewport = not bool(state.visible)
                obj.hide_render = not bool(state.visible)
                obj.keyframe_insert("location", frame=frame)
                obj.keyframe_insert("rotation_quaternion", frame=frame)
                obj.keyframe_insert("hide_viewport", frame=frame)
                obj.keyframe_insert("hide_render", frame=frame)

    def _decode_matrix_rows(
        self,
        matrix_rows: tuple[tuple[float, float, float], ...],
    ) -> tuple[Vector, tuple[float, float, float, float]]:
        axis3 = self.axis_rotation.to_3x3()
        rotation = Matrix((matrix_rows[0], matrix_rows[1], matrix_rows[2]))
        converted_rotation = axis3.inverted() @ rotation @ axis3
        location = axis3.inverted() @ Vector(matrix_rows[3])
        if abs(self.scale_factor) > EPSILON:
            location /= self.scale_factor
        quaternion = converted_rotation.to_quaternion()
        return Vector((location.x, location.y, location.z)), (
            float(quaternion.w),
            float(quaternion.x),
            float(quaternion.y),
            float(quaternion.z),
        )

    def _axis_rotation_matrix(self, axis_mode: str) -> Matrix:
        if axis_mode == "GOH_TO_BLENDER":
            return Matrix.Rotation(-math.pi / 2.0, 4, "Z")
        return Matrix.Identity(4)


class EXPORT_SCENE_OT_goh_model(Operator, ExportHelper):
    bl_idname = "export_scene.goh_model"
    bl_label = "Export GOH Model"
    bl_options = {"PRESET"}

    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={"HIDDEN"})
    selection_only: BoolProperty(name="Selection Only", default=True)
    include_hidden: BoolProperty(name="Include Hidden", default=False)
    basis_name: StringProperty(name="Basis Bone", default="basis")
    volume_collection_name: StringProperty(name="Volume Collection", default="GOH_VOLUMES")
    obstacle_collection_name: StringProperty(name="Obstacle Collection", default="GOH_OBSTACLES")
    area_collection_name: StringProperty(name="Area Collection", default="GOH_AREAS")
    axis_mode: EnumProperty(
        name="Axis Conversion",
        items=(
            ("BLENDER_TO_GOH", "Blender -> GOH (Legacy)", "Apply the older addon axis rotation used by early Blender-only scenes"),
            ("NONE", "None / GOH Native", "Write Blender transforms directly. This matches 3ds Max / SOEdit style GOH round-trips"),
        ),
        default="NONE",
    )
    scale_factor: FloatProperty(name="Scale Factor", default=GOH_NATIVE_SCALE, min=0.001, soft_max=1000.0)
    flip_v: BoolProperty(name="Flip V", default=True)
    export_animations: BoolProperty(name="Export Animations", default=True)
    anm_format: EnumProperty(
        name="ANM Format",
        items=(
            ("AUTO", "Auto", "Prefer FRM2 (0x00060000) and fall back to legacy FRMN when needed"),
            ("FRM2", "FRM2", "Write compact FRM2 animation chunks with version 0x00060000"),
            ("LEGACY", "Legacy", "Write the older FRMN/BONE/MATR/VISI format with version 0x00040000"),
        ),
        default="AUTO",
    )

    def draw(self, _context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "selection_only")
        layout.prop(self, "include_hidden")
        layout.prop(self, "basis_name")
        layout.prop(self, "volume_collection_name")
        layout.prop(self, "obstacle_collection_name")
        layout.prop(self, "area_collection_name")
        layout.prop(self, "axis_mode")
        layout.prop(self, "scale_factor")
        layout.prop(self, "flip_v")
        layout.prop(self, "export_animations")
        if self.export_animations:
            layout.prop(self, "anm_format")

    def execute(self, context: bpy.types.Context):
        exporter = GOHBlenderExporter(context, self)
        try:
            _bundle, warnings = exporter.export()
        except ExportError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:  # pragma: no cover - Blender runtime guard
            self.report({"ERROR"}, f"Unexpected GOH export error: {exc}")
            raise

        for warning in warnings[:10]:
            self.report({"WARNING"}, warning)
        self.report({"INFO"}, f"GOH export finished: {self.filepath}")
        return {"FINISHED"}

    def invoke(self, context: bpy.types.Context, event):
        if not self.filepath:
            blend_path = Path(bpy.data.filepath) if bpy.data.filepath else None
            basis_settings = getattr(context.scene, "goh_basis_settings", None)
            basis_name = ""
            if basis_settings and basis_settings.enabled:
                basis_name = sanitized_file_stem((basis_settings.vehicle_name or "").strip())
            default_name = basis_name or sanitized_file_stem(blend_path.stem if blend_path else "goh_model")
            self.filepath = str(Path.home() / f"{default_name}.mdl")
        return super().invoke(context, event)


class IMPORT_SCENE_OT_goh_anm(Operator, ImportHelper):
    bl_idname = "import_scene.goh_anm"
    bl_label = "Import GOH Animation"
    bl_options = {"PRESET"}

    filename_ext = ".anm"
    filter_glob: StringProperty(default="*.anm", options={"HIDDEN"})
    basis_name: StringProperty(name="Basis Bone", default="basis")
    frame_start: IntProperty(name="Start Frame", default=1, min=0)
    axis_mode: EnumProperty(
        name="Axis Conversion",
        items=(
            ("GOH_TO_BLENDER", "GOH -> Blender", "Convert GOH X-forward transforms back into Blender space"),
            ("NONE", "None", "Use ANM transforms exactly as stored"),
        ),
        default="GOH_TO_BLENDER",
    )
    scale_factor: FloatProperty(name="Scale Factor", default=GOH_NATIVE_SCALE, min=0.001, soft_max=1000.0)

    def draw(self, _context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "basis_name")
        layout.prop(self, "frame_start")
        layout.prop(self, "axis_mode")
        layout.prop(self, "scale_factor")

    def execute(self, context: bpy.types.Context):
        importer = GOHAnimationImporter(context, self)
        try:
            warnings = importer.import_animation()
        except ExportError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:  # pragma: no cover - Blender runtime guard
            self.report({"ERROR"}, f"Unexpected GOH import error: {exc}")
            raise

        for warning in warnings[:10]:
            self.report({"WARNING"}, warning)
        self.report({"INFO"}, f"GOH animation imported: {self.filepath}")
        return {"FINISHED"}


class OBJECT_OT_goh_apply_preset(Operator):
    bl_idname = "object.goh_apply_preset"
    bl_label = "Apply GOH Preset"
    bl_description = "Apply a structured GOH preset to the selected objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.selected_objects)

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_preset_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH preset settings are not available.")
            return {"CANCELLED"}

        role_preset = GOH_ROLE_PRESET_MAP[settings.role]
        selected_objects = sorted(context.selected_objects, key=lambda obj: obj.name.lower())
        applied_names: list[str] = []
        skipped = 0

        for index, obj in enumerate(selected_objects):
            if role_preset.key in {"volume", "obstacle", "area"} and obj.type != "MESH":
                skipped += 1
                continue
            applied_names.append(_apply_goh_preset_to_object(context.scene, obj, settings, index))

        if not applied_names:
            self.report({"WARNING"}, "No compatible objects were selected for this GOH preset.")
            return {"CANCELLED"}

        summary = ", ".join(applied_names[:3])
        if len(applied_names) > 3:
            summary = f"{summary}, ..."
        if skipped:
            self.report({"WARNING"}, f"Applied preset to {len(applied_names)} object(s); skipped {skipped}.")
        else:
            self.report({"INFO"}, f"Applied GOH preset to {len(applied_names)} object(s): {summary}")
        return {"FINISHED"}


class SCENE_OT_goh_copy_basis_legacy(Operator):
    bl_idname = "scene.goh_copy_basis_legacy"
    bl_label = "Copy Basis Legacy Text"
    bl_description = "Copy the legacy MultiScript Basis text to the clipboard"

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_basis_settings", None)
        if settings is None or not settings.enabled:
            self.report({"WARNING"}, "Enable Basis metadata first.")
            return {"CANCELLED"}
        text = _basis_legacy_text(settings)
        if not text:
            self.report({"WARNING"}, "Basis metadata is empty.")
            return {"CANCELLED"}
        context.window_manager.clipboard = text
        self.report({"INFO"}, "Copied Basis legacy text to the clipboard.")
        return {"FINISHED"}


class OBJECT_OT_goh_sync_basis_helper(Operator):
    bl_idname = "object.goh_sync_basis_helper"
    bl_label = "Create / Update Basis Helper"
    bl_description = "Create or update a hidden Basis helper Empty that stores legacy MultiScript metadata"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_basis_settings", None)
        if settings is None or not settings.enabled:
            self.report({"WARNING"}, "Enable Basis metadata first.")
            return {"CANCELLED"}

        helper = bpy.data.objects.get(GOH_BASIS_HELPER_NAME)
        if helper is None:
            helper = bpy.data.objects.new(GOH_BASIS_HELPER_NAME, None)
            helper.empty_display_type = "PLAIN_AXES"
            helper.empty_display_size = 0.5
            context.scene.collection.objects.link(helper)

        helper.name = GOH_BASIS_HELPER_NAME
        helper.location = (0.0, 0.0, 0.0)
        helper.rotation_euler = (0.0, 0.0, 0.0)
        helper.scale = (1.0, 1.0, 1.0)
        helper["goh_basis_helper"] = True
        helper["goh_legacy_props"] = _basis_legacy_text(settings)
        helper["Type"] = _basis_entity_type_value(settings)
        model_value = _basis_model_value(settings)
        if model_value:
            helper["Model"] = model_value
        elif "Model" in helper:
            del helper["Model"]
        helper["Wheelradius"] = settings.wheel_radius
        helper["SteerMax"] = settings.steer_max
        self.report({"INFO"}, "Basis helper synced.")
        return {"FINISHED"}


class OBJECT_OT_goh_apply_transform_block(Operator):
    bl_idname = "object.goh_apply_transform_block"
    bl_label = "Apply Transform Block"
    bl_description = "Write the selected transform block preference onto the selected objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.selected_objects)

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}
        count = 0
        for obj in context.selected_objects:
            if settings.transform_block == "AUTO":
                _remove_custom_prop(obj, "goh_transform_block")
            else:
                obj["goh_transform_block"] = settings.transform_block.lower()
            count += 1
        self.report({"INFO"}, f"Updated transform block mode on {count} object(s).")
        return {"FINISHED"}


class OBJECT_OT_goh_weapon_tool(Operator):
    bl_idname = "object.goh_weapon_tool"
    bl_label = "Apply GOH Weapon Tool"
    bl_description = "Apply a legacy-style GOH weapon helper action to the selected objects"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        name="Action",
        items=(
            ("COMMONMESH", "CommonMesh", "Mark the selected objects as legacy CommonMesh and force mesh animation sampling"),
            ("POLY", "Poly", "Mark the selected objects as legacy Poly visual parts"),
            ("BODY_VOL", "Body_vol", "Mark the selected mesh as a Body_vol collision helper"),
            ("SELECT_VOL", "Select_vol", "Mark the selected mesh as a Select_vol collision helper"),
            ("FORESIGHT3", "Foresight3", "Mark the selected object as a Foresight3 point helper"),
            ("HANDLE", "Handle", "Mark the selected object as a handle point helper"),
            ("FXSHELL", "FxShell", "Mark the selected object as an FxShell point helper"),
        ),
        default="COMMONMESH",
        translation_context="GOH_PRESET",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.selected_objects)

    def execute(self, context: bpy.types.Context):
        selected = sorted(context.selected_objects, key=lambda obj: obj.name.lower())
        count = 0
        for obj in selected:
            if self.action in {"BODY_VOL", "SELECT_VOL"} and obj.type != "MESH":
                continue
            if self.action == "COMMONMESH":
                _set_custom_bool_prop(obj, "goh_force_mesh_animation", True)
                obj["CommonMesh"] = True
                _remove_custom_prop(obj, "Poly")
            elif self.action == "POLY":
                _clear_helper_state(context.scene, obj, clear_collections=True)
                _remove_custom_prop(obj, "goh_force_mesh_animation")
                obj["Poly"] = True
                _remove_custom_prop(obj, "CommonMesh")
                _remove_custom_prop(obj, "Volume")
            elif self.action == "BODY_VOL":
                _clear_helper_state(context.scene, obj, clear_collections=True)
                obj.name = "Body_vol"
                _set_custom_bool_prop(obj, "goh_is_volume", True)
                _set_custom_text_prop(obj, "goh_volume_name", "body")
                _set_custom_text_prop(obj, "goh_volume_bone", "body")
                _set_custom_text_prop(obj, "goh_volume_kind", "polyhedron")
                _link_to_helper_collection(context.scene, obj, "GOH_VOLUMES")
                obj["Volume"] = True
                _remove_custom_prop(obj, "Poly")
                _remove_custom_prop(obj, "CommonMesh")
            elif self.action == "SELECT_VOL":
                _clear_helper_state(context.scene, obj, clear_collections=True)
                obj.name = "Select_vol"
                _set_custom_bool_prop(obj, "goh_is_volume", True)
                _set_custom_text_prop(obj, "goh_volume_name", "Select")
                _set_custom_text_prop(obj, "goh_volume_bone", "body")
                _set_custom_text_prop(obj, "goh_volume_kind", "polyhedron")
                _link_to_helper_collection(context.scene, obj, "GOH_VOLUMES")
                obj["Volume"] = True
                _remove_custom_prop(obj, "Poly")
                _remove_custom_prop(obj, "CommonMesh")
            elif self.action == "FORESIGHT3":
                obj.name = "Foresight3"
                _set_custom_text_prop(obj, "goh_bone_name", "Foresight3")
                obj["Voxels"] = 0
            elif self.action == "HANDLE":
                obj.name = "handle"
                _set_custom_text_prop(obj, "goh_bone_name", "handle")
                obj["Voxels"] = 0
            elif self.action == "FXSHELL":
                obj.name = "FxShell"
                _set_custom_text_prop(obj, "goh_bone_name", "FxShell")
                obj["Voxels"] = 0
            count += 1
        if count == 0:
            self.report({"WARNING"}, "No compatible objects were selected for that weapon tool action.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Applied {self.action} to {count} object(s).")
        return {"FINISHED"}


class SCENE_OT_goh_report_textures(Operator):
    bl_idname = "scene.goh_report_textures"
    bl_label = "Report Texture Names"
    bl_description = "Create a Blender text report and clipboard dump of texture names used by the current GOH scene"

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}

        materials: list[bpy.types.Material] = []
        if settings.texture_scope == "ALL":
            materials = [material for material in bpy.data.materials if material is not None]
        else:
            if settings.texture_scope == "SELECTED":
                source_objects = list(context.selected_objects)
            else:
                source_objects = [
                    obj for obj in context.view_layer.objects
                    if obj.type == "MESH" and obj.visible_get(view_layer=context.view_layer)
                ]
            seen: set[int] = set()
            for obj in source_objects:
                for slot in obj.material_slots:
                    material = slot.material
                    if material is None:
                        continue
                    pointer = material.as_pointer()
                    if pointer in seen:
                        continue
                    seen.add(pointer)
                    materials.append(material)

        texture_lines: list[str] = []
        seen_textures: set[str] = set()
        texture_keys = (
            "goh_diffuse",
            "goh_bump",
            "goh_specular",
            "goh_lightmap",
            "goh_mask",
            "goh_height",
            "goh_diffuse1",
            "goh_simple",
            "goh_envmap_texture",
            "goh_bump_volume",
        )
        for material in sorted(materials, key=lambda item: item.name.lower()):
            entries: list[str] = []
            for key in texture_keys:
                value = material.get(key)
                if value:
                    entries.append(str(value).strip())
            if material.node_tree:
                for node in material.node_tree.nodes:
                    if node.type != "TEX_IMAGE" or not node.image:
                        continue
                    path = node.image.filepath_from_user() or node.image.filepath or node.image.name
                    entries.append(Path(path).name)
            unique_entries = [entry for entry in entries if entry and entry not in seen_textures]
            for entry in unique_entries:
                seen_textures.add(entry)
                texture_lines.append(f"{material.name}: {entry}")

        report_text = "\n".join(texture_lines) if texture_lines else "No textures found."
        text_name = "GOH_Texture_Report.txt"
        text_block = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
        text_block.clear()
        text_block.write(report_text)
        context.window_manager.clipboard = report_text
        self.report({"INFO"}, f"Reported {len(texture_lines)} texture reference(s).")
        return {"FINISHED"}


class VIEW3D_PT_goh_basis(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GOH"
    bl_label = "GOH Basis"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.goh_basis_settings
        layout.prop(settings, "enabled")
        if not settings.enabled:
            layout.label(text="Enable Basis metadata to mirror the old MultiScript helper.")
            return
        layout.prop(settings, "vehicle_name")
        layout.prop(settings, "entity_type")
        layout.prop(settings, "entity_path")
        if settings.entity_path == "CUSTOM":
            layout.prop(settings, "entity_path_custom")
        layout.prop(settings, "wheel_radius")
        layout.prop(settings, "steer_max")
        layout.prop(settings, "animation_enabled")
        if settings.animation_enabled:
            layout.prop(settings, "start_enabled")
            if settings.start_enabled:
                layout.prop(settings, "start_range")
            layout.prop(settings, "stop_enabled")
            if settings.stop_enabled:
                layout.prop(settings, "stop_range")
            layout.prop(settings, "fire_enabled")
            if settings.fire_enabled:
                layout.prop(settings, "fire_range")

        preview = layout.box()
        preview.label(text=f"Type: {_basis_entity_type_value(settings)}")
        model_value = _basis_model_value(settings)
        if model_value:
            preview.label(text=f"Model: {model_value}")
        legacy_lines = _basis_legacy_lines(settings)
        if legacy_lines:
            preview.label(text="Legacy Preview:")
            for line in legacy_lines[:6]:
                preview.label(text=line)

        row = layout.row(align=True)
        row.operator(SCENE_OT_goh_copy_basis_legacy.bl_idname, text="Copy Legacy Text")
        row.operator(OBJECT_OT_goh_sync_basis_helper.bl_idname, text="Sync Basis Helper")


class VIEW3D_PT_goh_tools(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GOH"
    bl_label = "GOH Tools"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.goh_tool_settings

        transform_box = layout.box()
        transform_box.label(text="Transform Block")
        transform_box.prop(settings, "transform_block")
        transform_box.operator(OBJECT_OT_goh_apply_transform_block.bl_idname, text="Apply Transform Mode")

        weapon_box = layout.box()
        weapon_box.label(text="Weapon Helpers")
        row = weapon_box.row(align=True)
        row.operator(OBJECT_OT_goh_weapon_tool.bl_idname, text="CommonMesh", translate=False).action = "COMMONMESH"
        row.operator(OBJECT_OT_goh_weapon_tool.bl_idname, text="Poly", translate=False).action = "POLY"
        row = weapon_box.row(align=True)
        row.operator(OBJECT_OT_goh_weapon_tool.bl_idname, text="Body_vol", translate=False).action = "BODY_VOL"
        row.operator(OBJECT_OT_goh_weapon_tool.bl_idname, text="Select_vol", translate=False).action = "SELECT_VOL"
        row = weapon_box.row(align=True)
        row.operator(OBJECT_OT_goh_weapon_tool.bl_idname, text="Foresight3", translate=False).action = "FORESIGHT3"
        row.operator(OBJECT_OT_goh_weapon_tool.bl_idname, text="Handle", translate=False).action = "HANDLE"
        row.operator(OBJECT_OT_goh_weapon_tool.bl_idname, text="FxShell", translate=False).action = "FXSHELL"

        texture_box = layout.box()
        texture_box.label(text="Texture Tool")
        texture_box.prop(settings, "texture_scope")
        texture_box.operator(SCENE_OT_goh_report_textures.bl_idname, text="Report Texture Names")


class VIEW3D_PT_goh_presets(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GOH"
    bl_label = "GOH Presets"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.goh_preset_settings
        role_preset = GOH_ROLE_PRESET_MAP[settings.role]
        part_preset = _resolve_part_preset(settings.role, settings.part, settings.template_family)

        layout.label(text="Structured presets for GOH parts and helpers.")
        layout.prop(settings, "template_family")
        layout.prop(settings, "role")
        layout.prop(settings, "part")

        preview_box = layout.box()
        preview_box.label(text=f"Preview: {part_preset.display_name}{role_preset.name_suffix}")
        preview_box.label(text=f"Export ID: {part_preset.export_name}")
        if role_preset.helper_flag:
            preview_box.label(text=f"Helper Flag: {role_preset.helper_flag}")
        if role_preset.collection_name:
            preview_box.label(text=f"Collection: {role_preset.collection_name}")
        if role_preset.key == "volume":
            preview_box.label(text=f"Volume Kind: {settings.volume_kind.title()}")
            if settings.volume_kind == "CYLINDER":
                preview_box.label(text=f"Cylinder Axis: {settings.volume_axis}")

        if role_preset.sets_attach_bone or role_preset.key == "volume":
            layout.prop(settings, "target_name")
        if role_preset.key == "volume":
            layout.prop(settings, "volume_kind")
            if settings.volume_kind == "CYLINDER":
                layout.prop(settings, "volume_axis")

        layout.prop(settings, "rename_objects")
        layout.prop(settings, "write_export_names")
        layout.prop(settings, "auto_number")
        layout.prop(settings, "helper_collections")
        layout.prop(settings, "clear_conflicts")
        layout.prop(settings, "mesh_animation_mode")
        layout.operator(OBJECT_OT_goh_apply_preset.bl_idname, text="Apply Preset to Selection")


class VIEW3D_PT_goh_export_help(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GOH"
    bl_label = "GOH Export"

    def draw(self, _context: bpy.types.Context) -> None:
        layout = self.layout
        layout.operator(EXPORT_SCENE_OT_goh_model.bl_idname, text="Export GOH Model")
        layout.operator(IMPORT_SCENE_OT_goh_anm.bl_idname, text="Import GOH Animation")
        layout.label(text="网格对象 Mesh objects 会导出为 GOH bones。", translate=False)
        layout.label(text='辅助体 Helpers 可用 "_vol"、GOH_VOLUMES、GOH_OBSTACLES、GOH_AREAS 识别。', translate=False)
        layout.label(text="预设 GOH Presets 用结构化字段替代旧版 Max 文本模板。", translate=False)
        layout.label(text="骨架 Armature + 顶点组 Vertex Groups 可导出 skinned PLY。", translate=False)
        layout.label(text="动作 Action / NLA strips 可导出 ANM 与 shape-key mesh chunks。", translate=False)
        layout.label(text=f"SOEdit / Max round-trip 推荐使用 Axis=None、Scale={int(GOH_NATIVE_SCALE)}、Flip V=On。", translate=False)


def menu_func_export(self, _context):
    self.layout.operator(EXPORT_SCENE_OT_goh_model.bl_idname, text="GOH Model (.mdl)")


def menu_func_import(self, _context):
    self.layout.operator(IMPORT_SCENE_OT_goh_anm.bl_idname, text="GOH Animation (.anm)")


CLASSES = (
    GOHAddonPresetSettings,
    GOHBasisSettings,
    GOHToolSettings,
    EXPORT_SCENE_OT_goh_model,
    IMPORT_SCENE_OT_goh_anm,
    OBJECT_OT_goh_apply_preset,
    SCENE_OT_goh_copy_basis_legacy,
    OBJECT_OT_goh_sync_basis_helper,
    OBJECT_OT_goh_apply_transform_block,
    OBJECT_OT_goh_weapon_tool,
    SCENE_OT_goh_report_textures,
    VIEW3D_PT_goh_basis,
    VIEW3D_PT_goh_tools,
    VIEW3D_PT_goh_presets,
    VIEW3D_PT_goh_export_help,
)


def register() -> None:
    try:
        bpy.app.translations.unregister(GOH_TRANSLATION_DOMAIN)
    except (ValueError, KeyError):
        pass
    bpy.app.translations.register(GOH_TRANSLATION_DOMAIN, GOH_TRANSLATION_OVERRIDES)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.goh_preset_settings = PointerProperty(type=GOHAddonPresetSettings)
    bpy.types.Scene.goh_basis_settings = PointerProperty(type=GOHBasisSettings)
    bpy.types.Scene.goh_tool_settings = PointerProperty(type=GOHToolSettings)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister() -> None:
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    del bpy.types.Scene.goh_preset_settings
    del bpy.types.Scene.goh_basis_settings
    del bpy.types.Scene.goh_tool_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    try:
        bpy.app.translations.unregister(GOH_TRANSLATION_DOMAIN)
    except (ValueError, KeyError):
        pass
