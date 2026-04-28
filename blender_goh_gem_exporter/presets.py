from __future__ import annotations

from dataclasses import dataclass


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
    "goh_lod_off": ("off", "lodlastoff"),
    "goh_no_cast_shadows": ("nocastshadows",),
    "goh_decal_target": ("decaltarget",),
    "goh_no_group_mesh": ("nogroupmesh",),
    "goh_no_get_shadows": ("nogetshadows",),
    "goh_ground": ("ground",),
    "goh_rotate_2d": ("rotate",),
    "goh_speed2": ("speed2",),
    "goh_terminator": ("terminator",),
}

GOH_CUSTOM_BOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "goh_force_mesh_animation": ("goh_force_commonmesh",),
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
            "Auto / Match Imported Model",
            "Auto",
            "Orientation",
            "Matrix34",
            "Validation Scope",
            "Validate GOH Scene",
            "Auto-Fill GOH Materials",
            "Import GOH Model",
            "Assign LOD Files",
            "Volume From Bounds",
            "Create Recoil Action",
            "Assign Physics Link",
            "Bake Linked Recoil",
            "Bake Directional Set",
            "Bake Impact Response",
            "Create Armor Ripple",
            "Load Role Defaults",
            "Clear Physics Links",
            "LOD Levels",
            "Write OFF",
            "Helper Volume",
            "Recoil Axis",
            "Direction Set",
            "Clip Prefix",
            "Impact Clip",
            "Ripple Amplitude",
            "Ripple Radius",
            "Ripple Waves",
            "Physics Power",
            "Duration Scale",
            "Import Materials",
            "Load Diffuse Textures",
            "LOD0 Only",
            "Link Role",
            "Link Weight",
            "Create NLA Clips",
            "Clear Baked Actions",
            "Body Spring",
            "Antenna Whip",
            "Accessory Jitter",
            "Follower",
            "Suspension Bounce",
            "Track Rumble",
            "Use Stored Links",
            "Four Fire Directions",
            "Six Local Axes",
            "Local +X",
            "Local -X",
            "Local +Y",
            "Local -Y",
            "Local +Z",
            "Local -Z",
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
