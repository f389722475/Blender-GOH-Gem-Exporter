from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
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
from mathutils.bvhtree import BVHTree

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
    read_material,
    read_mesh,
    read_model,
    read_volume,
    sanitized_file_stem,
    write_export_bundle,
)
from .core.names import (
    NUMBERING_RULE_PAD2,
    NUMBERING_RULE_PLAIN,
    numbered_display_name as _numbered_display_name,
    numbered_identifier as _numbered_identifier,
    strip_blender_duplicate_suffix as _strip_blender_duplicate_suffix,
)
from .formats.legacy_props import (
    legacy_flag_set as _legacy_flag_set,
    legacy_key_values as _legacy_key_values,
    parse_frame_range as _parse_frame_range,
)
from .presets import (
    GOH_CUSTOM_BOOL_ALIASES,
    GOH_HELPER_COLLECTIONS,
    GOH_HELPER_FLAGS,
    GOH_LEGACY_BOOL_FLAGS,
    GOH_LEGACY_FLOAT_FALLBACKS,
    GOH_LEGACY_INT_FALLBACKS,
    GOH_LEGACY_TEXT_FALLBACKS,
    GOH_ROLE_PRESET_ITEMS,
    GOH_ROLE_PRESET_MAP,
    GOH_TEMPLATE_FAMILY_ITEMS,
    GOH_TRANSLATION_DOMAIN,
    GOH_TRANSLATION_OVERRIDES,
    _goh_part_items,
    _goh_role_updated,
    _goh_template_updated,
    _resolve_part_preset,
)


EPSILON = 1e-6
GOH_NATIVE_SCALE = 20.0
GOH_BASIS_HELPER_NAME = "Basis"
GOH_ADDON_VERSION = "1.5.1"

GOH_TRANSFORM_BLOCK_ITEMS = (
    ("AUTO", "Auto", "Write Position / Orientation / Matrix34 automatically based on the transform content"),
    ("ORIENTATION", "Orientation", "Prefer a pure {Orientation} block when the transform has no translation"),
    ("MATRIX34", "Matrix34", "Always write a {Matrix34} block"),
)

GOH_TEXTURE_PROP_KEYS = (
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

GOH_VOLUME_KIND_VALUES = {"polyhedron", "box", "sphere", "cylinder"}
GOH_PHYSICS_PROP_KEYS = (
    "goh_physics_source",
    "goh_physics_role",
    "goh_physics_weight",
    "goh_physics_delay",
    "goh_physics_frequency",
    "goh_physics_damping",
    "goh_physics_jitter",
    "goh_physics_rotation",
    "goh_physics_solver_space",
    "goh_physics_mass",
    "goh_physics_inertia",
    "goh_physics_com_offset",
    "goh_physics_linear_axes",
    "goh_physics_angular_axes",
    "goh_physics_max_offset",
    "goh_physics_max_angle",
    "goh_physics_substeps",
    "goh_physics_force_limit",
    "goh_physics_end_fade",
    "goh_antenna_root_anchor",
    "goh_antenna_segments",
)
GOH_PHYSICS_ACTION_PREFIXES = (
    "goh_recoil_",
    "goh_recoil_source_",
    "goh_linked_recoil_",
    "goh_directional_recoil_",
    "goh_impact_",
    "goh_antenna_whip_",
)
GOH_PHYSICS_NLA_PREFIX = "GOH Physics"
GOH_PHYSICS_SEGMENTS_PROP = "goh_physics_segments"
GOH_SEQUENCE_RANGES_PROP = "goh_sequence_ranges"
GOH_ANTENNA_SHAPE_KEY_PREFIX = "GOH_AntennaWhip_"


@dataclass
class AttachmentObject:
    obj: bpy.types.Object
    mesh_matrix: Matrix
    attach_bone: str


@dataclass
class AutoQuadCageResult:
    vertices: list[Vector]
    faces: list[tuple[int, ...]]
    mode: str
    source_face_count: int
    final_face_count: int
    report: list[tuple[str, str, float | int | str]]
    score: float = 0.0
    iterations: int = 1
    max_outside: float = 0.0


@dataclass
class AutoConvexSourceGroup:
    source: bpy.types.Object
    label: str
    points: list[Vector]
    triangles: list[tuple[int, int, int]]
    vertex_count: int


@dataclass
class AutoConvexBuildTask:
    source: bpy.types.Object
    label: str
    points: list[Vector]
    triangles: list[tuple[int, int, int]]
    vertex_count: int


@dataclass(frozen=True)
class AutoQuadCageCandidate:
    target_faces: int
    template: str
    fit_mode: str
    offset: float
    smooth_iterations: int
    planarize_quads: bool
    planarize_strength: float
    output_topology: str


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
    numbering_rule: EnumProperty(
        name="Numbering Rule",
        description="Number format used by presets whose label contains Auto",
        items=(
            (NUMBERING_RULE_PLAIN, "x1, x2", "Use plain numeric suffixes such as emit1, emit2, emit10"),
            (NUMBERING_RULE_PAD2, "x01, x02", "Use two-digit suffixes such as emit01, emit02, emit10"),
        ),
        default=NUMBERING_RULE_PLAIN,
        translation_context="GOH_PRESET",
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
    wheel_radius: FloatProperty(
        name="Wheelradius",
        description="Legacy Basis Wheelradius value. Accepts any numeric value for source-faithful templates.",
        default=0.48,
    )
    steer_max: FloatProperty(
        name="SteerMax",
        description="Legacy Basis SteerMax value. Accepts any numeric value for source-faithful templates.",
        default=28.0,
    )
    animation_enabled: BoolProperty(name="Legacy Animation Clips", default=False)
    start_enabled: BoolProperty(name="Start", default=False)
    start_range: StringProperty(name="Start Range", default="")
    stop_enabled: BoolProperty(name="Stop", default=False)
    stop_range: StringProperty(name="Stop Range", default="")
    fire_enabled: BoolProperty(name="Fire", default=False)
    fire_range: StringProperty(name="Fire Range", default="")


class GOHToolSettings(PropertyGroup):
    validation_scope: EnumProperty(
        name="Validation Scope",
        items=(
            ("SELECTED", "Selected", "Validate selected objects and their materials"),
            ("VISIBLE", "Visible", "Validate visible objects in the current view layer"),
            ("ALL", "All", "Validate every object in the scene"),
        ),
        default="VISIBLE",
        translation_context="GOH_PRESET",
    )
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
    material_overwrite: BoolProperty(
        name="Overwrite Existing",
        description="Allow the material auto-fill tool to replace existing GOH texture custom properties",
        default=False,
    )
    lod_levels: IntProperty(
        name="LOD Levels",
        description="Number of additional LOD file entries to write after the base .ply file",
        default=2,
        min=0,
        max=8,
    )
    lod_mark_off: BoolProperty(
        name="Write OFF",
        description="Also set goh_lod_off on selected mesh objects",
        default=False,
    )
    helper_volume_kind: EnumProperty(
        name="Helper Volume",
        items=(
            ("POLYHEDRON", "Polyhedron (.vol)", "Create a regular .vol collision helper from the selected mesh bounds"),
            ("BOX", "Primitive Box", "Create an inline Box collision helper from the selected mesh bounds"),
            ("SPHERE", "Primitive Sphere", "Create an inline Sphere collision helper from the selected mesh bounds"),
            ("CYLINDER", "Primitive Cylinder", "Create an inline Cylinder collision helper from the selected mesh bounds"),
        ),
        default="BOX",
        translation_context="GOH_PRESET",
    )
    auto_convex_template: EnumProperty(
        name="Cage Template",
        items=(
            ("BOX", "Box Cage", "Subdivided cube cage for hard-surface body, turret, and track blocks"),
            ("ROUNDED_BOX", "Rounded Box", "Rounded box cage for smoother vehicle volumes"),
            ("SPHERE", "Quad Sphere", "Cube-sphere cage for round turrets, mantlets, and domes"),
            ("LOFT", "Loft Cage", "Lengthwise profile cage for hulls and turrets with sloped or tapered silhouettes"),
            ("BARREL", "Barrel Cage", "Stable tube cage for long gun barrels and cannons"),
            ("AUTO", "Auto", "Choose a cage template from the source proportions"),
        ),
        default="AUTO",
        translation_context="GOH_PRESET",
    )
    auto_convex_fit_mode: EnumProperty(
        name="Fit Mode",
        items=(
            ("OBB", "OBB Only", "Generate an oriented bounding cage and apply offset"),
            ("RAY", "Ray Projection", "Project cage vertices radially toward the source surface, then keep an outward offset"),
        ),
        default="OBB",
        translation_context="GOH_PRESET",
    )
    auto_convex_output_topology: EnumProperty(
        name="Output Topology",
        items=(
            ("MIXED", "Tri / Quad Legal", "Keep generated triangles and quads; ngons are not allowed"),
            ("QUAD", "Prefer Quads", "Keep quad cage topology when available"),
            ("TRIANGULATED", "All Triangles", "Triangulate generated faces before validation/export review"),
        ),
        default="MIXED",
        translation_context="GOH_PRESET",
    )
    auto_convex_target_faces: IntProperty(
        name="Face Budget",
        description="Per-collision-helper face budget. Triangles and quads are legal; ngons are rejected. Hard maximum is 5000 faces per helper",
        default=150,
        min=12,
        max=5000,
    )
    auto_convex_optimize_iterations: IntProperty(
        name="Optimize Iterations",
        description="Deterministic reward-guided candidate search iterations per source group",
        default=12,
        min=1,
        max=500,
        soft_max=100,
    )
    auto_convex_max_hulls: IntProperty(
        name="Max Cages",
        description="Maximum number of auto collision cage helpers to create from the selected source set",
        default=32,
        min=1,
        max=128,
    )
    auto_convex_margin: FloatProperty(
        name="Offset",
        description="Extra Blender-unit padding applied to keep the cage outside the source surface",
        default=0.02,
        min=0.0,
        soft_max=0.25,
        precision=4,
    )
    auto_convex_source_scope: EnumProperty(
        name="Cage Source",
        items=(
            ("SELECTED", "Selected", "Generate from selected mesh objects only"),
            ("HIERARCHY", "Selected + Children", "Generate from selected mesh objects and mesh descendants"),
        ),
        default="HIERARCHY",
        translation_context="GOH_PRESET",
    )
    auto_convex_clear_existing: BoolProperty(
        name="Clear Previous",
        description="Remove previously generated auto collision cage helpers for the same source objects before creating new ones",
        default=True,
    )
    auto_convex_split_loose_parts: BoolProperty(
        name="Split Loose Parts",
        description="Generate separate cages for disconnected mesh islands; useful for hand-picked objects, but can over-spend cage budget on full vehicles",
        default=False,
    )
    auto_convex_min_part_vertices: IntProperty(
        name="Min Part Vertices",
        description="Ignore very small loose islands below this unique-vertex count unless they are the only source island",
        default=20,
        min=1,
        max=256,
    )
    auto_convex_use_evaluated: BoolProperty(
        name="Use Modifiers",
        description="Generate the collider from evaluated mesh data after visible modifiers",
        default=True,
    )
    auto_convex_smooth_display: BoolProperty(
        name="Smooth Display",
        description="Use smooth normals on the generated helper for easier viewport inspection without changing the quad topology",
        default=True,
    )
    auto_convex_smooth_iterations: IntProperty(
        name="Smooth Iterations",
        description="Taubin smoothing passes after cage fitting",
        default=3,
        min=0,
        max=16,
    )
    auto_convex_planarize_quads: BoolProperty(
        name="Planarize Quads",
        description="Relax fitted cage vertices toward local quad planes before validation",
        default=True,
    )
    auto_convex_planarize_strength: FloatProperty(
        name="Planarize Strength",
        description="How strongly quad vertices are moved toward their face planes",
        default=0.35,
        min=0.0,
        max=1.0,
        precision=3,
    )
    recoil_axis: EnumProperty(
        name="Recoil Axis",
        items=(
            ("X", "Local +X", "Move along local positive X"),
            ("NEG_X", "Local -X", "Move along local negative X"),
            ("Y", "Local +Y", "Move along local positive Y"),
            ("NEG_Y", "Local -Y", "Move along local negative Y"),
            ("Z", "Local +Z", "Move along local positive Z"),
            ("NEG_Z", "Local -Z", "Move along local negative Z"),
        ),
        default="NEG_Y",
        translation_context="GOH_PRESET",
    )
    recoil_distance: FloatProperty(
        name="Distance",
        description="Blender-unit recoil distance before GOH export scaling",
        default=0.18,
        min=0.0,
        soft_max=5.0,
    )
    recoil_frames: IntProperty(
        name="Frames",
        description="Total baked recoil action length in frames",
        default=12,
        min=3,
        max=240,
    )
    recoil_set_sequence: BoolProperty(
        name="Write Sequence",
        description="Write goh_sequence_name and goh_sequence_file for the generated recoil action",
        default=True,
    )
    physics_direction_set: EnumProperty(
        name="Direction Set",
        items=(
            ("FOUR_FIRE", "Four Fire Directions", "Bake fire_front, fire_back, fire_left, and fire_right recoil clips"),
            ("EIGHT_FIRE", "Eight Fire Directions", "Bake eight horizontal fire-direction recoil clips"),
        ),
        default="FOUR_FIRE",
        translation_context="GOH_PRESET",
    )
    physics_clip_prefix: StringProperty(
        name="Clip Prefix",
        description="Prefix used when creating directional recoil clips",
        default="fire",
    )
    physics_impact_clip_name: StringProperty(
        name="Impact Clip",
        description="Sequence/file name used by the impact-response bake",
        default="hit",
    )
    physics_ripple_amplitude: FloatProperty(
        name="Ripple Amplitude",
        description="Maximum mesh shape-key ripple displacement in Blender units",
        default=0.025,
        min=0.0,
        soft_max=0.5,
    )
    physics_ripple_radius: FloatProperty(
        name="Ripple Radius",
        description="Approximate radius around the 3D cursor affected by armor ripple shape keys",
        default=1.25,
        min=0.01,
        soft_max=10.0,
    )
    physics_ripple_waves: IntProperty(
        name="Ripple Waves",
        description="Number of radial wave bands in the generated armor ripple",
        default=2,
        min=1,
        max=12,
    )
    physics_power: FloatProperty(
        name="Physics Power",
        description="Global multiplier for linked physics, impact shake, and ripple intensity",
        default=1.0,
        min=0.0,
        soft_max=4.0,
    )
    physics_body_sway_strength: FloatProperty(
        name="Body Sway Strength",
        description="Extra multiplier for Body Spring hull kick and rocking during linked or directional recoil bakes",
        default=1.0,
        min=0.0,
        soft_max=4.0,
    )
    physics_antenna_sway_strength: FloatProperty(
        name="Antenna Sway Strength",
        description="Extra multiplier for Antenna Whip tip bend during linked or directional recoil bakes",
        default=1.0,
        min=0.0,
        soft_max=4.0,
    )
    physics_antenna_mount: EnumProperty(
        name="Antenna Mount",
        description="Choose whether directional antenna whip follows the body fire direction or the fixed turret/gun X axis",
        items=(
            ("TURRET", "Antenna on Turret", "Bake antenna whip with the turret/gun X/-X recoil axis"),
            ("BODY", "Antenna on Body", "Bake antenna whip with the body directional recoil response"),
        ),
        default="TURRET",
        translation_context="GOH_PRESET",
    )
    physics_duration_scale: FloatProperty(
        name="Duration Scale",
        description="Global multiplier for role-specific linked physics duration",
        default=1.0,
        min=0.2,
        soft_max=3.0,
    )
    physics_create_nla_clips: BoolProperty(
        name="Record Clip Ranges",
        description="Record generated frame ranges for multi-segment ANM export on the same active Action",
        default=True,
    )
    physics_link_role: EnumProperty(
        name="Link Role",
        items=(
            ("BODY_SPRING", "Body Spring", "Heavy vehicle hull recoil with a hard initial shove, low-frequency rebound, and visible rocking"),
            ("ANTENNA_WHIP", "Antenna Whip", "Delayed flexible whip motion with large rotation and small translation"),
            ("ACCESSORY_JITTER", "Accessory Jitter", "Loose external equipment with high-frequency rattling and asymmetric shake"),
            ("FOLLOWER", "Follower", "Generic linked part with a mild, readable damped follow-through"),
            ("SUSPENSION_BOUNCE", "Suspension Bounce", "Vehicle movement bounce with vertical travel, pitch, and soft recovery"),
            ("TRACK_RUMBLE", "Track Rumble", "Track, wheel, and bogie movement rumble with fast low-amplitude vibration"),
        ),
        default="BODY_SPRING",
        translation_context="GOH_PRESET",
    )
    physics_link_weight: FloatProperty(
        name="Link Weight",
        description="How strongly linked parts react to the source recoil",
        default=1.0,
        min=0.0,
        soft_max=5.0,
    )
    physics_link_delay: IntProperty(
        name="Delay",
        description="Delay in frames before linked parts react",
        default=2,
        min=0,
        max=120,
    )
    physics_link_frequency: FloatProperty(
        name="Frequency",
        description="Spring oscillation frequency for linked response",
        default=0.0,
        min=0.0,
        soft_max=12.0,
    )
    physics_link_damping: FloatProperty(
        name="Damping",
        description="Response damping for linked spring motion",
        default=0.0,
        min=0.0,
        soft_max=4.0,
    )
    physics_link_jitter: FloatProperty(
        name="Jitter",
        description="Deterministic secondary jitter amount added to linked parts",
        default=0.0,
        min=0.0,
        soft_max=1.0,
    )
    physics_link_rotation: FloatProperty(
        name="Rotation",
        description="Maximum linked part rotation in degrees",
        default=0.0,
        min=0.0,
        soft_max=45.0,
    )
    physics_solver_space: EnumProperty(
        name="Solver Space",
        description="Coordinate frame used by the inertial bake solver",
        items=(
            ("PARENT_LOCAL", "Parent Local", "Resolve forces in the driven object's parent space"),
            ("SOURCE_LOCAL", "Source Local", "Resolve forces in the active recoil source space"),
            ("OBJECT_LOCAL", "Object Local", "Resolve forces in the driven object's own space"),
            ("WORLD", "World", "Resolve forces in world axes"),
        ),
        default="PARENT_LOCAL",
    )
    physics_substeps: IntProperty(
        name="Substeps",
        description="Semi-implicit solver substeps per frame for stable inertial bakes",
        default=4,
        min=1,
        max=32,
    )
    physics_force_limit: FloatProperty(
        name="Force Limit",
        description="Optional acceleration clamp before inertial integration; zero disables the clamp",
        default=0.0,
        min=0.0,
        soft_max=250.0,
    )
    physics_end_fade: FloatProperty(
        name="End Fade",
        description="Final portion of the baked clip forced back to rest",
        default=0.16,
        min=0.0,
        max=0.50,
    )
    physics_antenna_root_anchor: FloatProperty(
        name="Antenna Root Anchor",
        description="Fraction of the antenna height kept rigid from the bottom during Antenna Whip mesh bakes; negative values move the virtual bend root below the mesh",
        default=0.06,
        min=-0.35,
        max=0.95,
        soft_min=-0.12,
        soft_max=0.30,
    )
    physics_antenna_segments: IntProperty(
        name="Antenna Bend Segments",
        description="Minimum lengthwise segments added before Antenna Whip shape-key baking; set to 0 to keep the mesh topology unchanged",
        default=12,
        min=0,
        max=64,
    )
    physics_include_scene_links: BoolProperty(
        name="Use Stored Links",
        description="Bake all scene objects whose goh_physics_source points at the active source, even if they are not selected",
        default=True,
    )
    fire_trigger_radius: FloatProperty(
        name="Trigger Radius",
        description="Radius of the generated recoil_gun_* pie-slice trigger volumes",
        default=0.45,
        min=0.01,
        soft_max=5.0,
    )
    fire_trigger_thickness: FloatProperty(
        name="Trigger Thickness",
        description="Vertical thickness of each generated fire trigger volume",
        default=0.05,
        min=0.001,
        soft_max=1.0,
    )
    fire_trigger_point_distance: FloatProperty(
        name="gun_recoil Distance",
        description="Distance from the turret pivot to a newly-created gun_recoil point along turret local +X",
        default=0.40,
        min=0.0,
        soft_max=5.0,
    )
    fire_trigger_arc_segments: IntProperty(
        name="Arc Segments",
        description="Outer-arc subdivisions per generated pie-slice trigger volume",
        default=8,
        min=1,
        max=32,
    )
    fire_trigger_replace_existing: BoolProperty(
        name="Replace Existing",
        description="Replace existing recoil_gun_*_vol trigger volumes while preserving an existing gun_recoil point",
        default=True,
    )
    physics_clear_actions: BoolProperty(
        name="Clear Baked Actions",
        description="Also detach GOH physics active actions and GOH physics NLA tracks when clearing links",
        default=False,
    )


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


def _write_text_block(name: str, content: str) -> bpy.types.Text:
    text_block = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    text_block.clear()
    text_block.write(content)
    return text_block


def _objects_for_tool_scope(context: bpy.types.Context, scope: str) -> list[bpy.types.Object]:
    if scope == "SELECTED":
        return list(context.selected_objects)
    if scope == "VISIBLE":
        return [
            obj for obj in context.view_layer.objects
            if obj.visible_get(view_layer=context.view_layer)
        ]
    return list(context.scene.objects)


def _materials_for_tool_scope(context: bpy.types.Context, scope: str) -> list[bpy.types.Material]:
    if scope == "ALL":
        return [material for material in bpy.data.materials if material is not None]

    materials: list[bpy.types.Material] = []
    seen: set[int] = set()
    for obj in _objects_for_tool_scope(context, scope):
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                continue
            pointer = material.as_pointer()
            if pointer in seen:
                continue
            seen.add(pointer)
            materials.append(material)
    return materials


def _image_texture_stem(image: bpy.types.Image) -> str:
    path = image.filepath_from_user() or image.filepath or image.name
    return Path(path).stem.strip() or image.name.strip()


def _image_source_path(image: bpy.types.Image) -> Path | None:
    if image.packed_file is not None:
        return None
    raw_path = image.filepath_from_user() or image.filepath
    if not raw_path:
        return None
    try:
        return Path(bpy.path.abspath(raw_path))
    except Exception:
        return Path(raw_path)


def _texture_role_from_name(stem: str) -> str | None:
    lower = stem.lower()
    checks: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("goh_bump", ("_n_n", "_normal", "normal", "bump")),
        ("goh_specular", ("_n_s", "_spec", "_s", "spec", "gloss", "rough")),
        ("goh_height", ("_hm", "_height", "height", "displace")),
        ("goh_lightmap", ("_lightmap", "lightmap", "_lm", "_mask")),
        ("goh_mask", ("_msk", "mask")),
        ("goh_envmap_texture", ("envmap", "environment", "reflection")),
        ("goh_diffuse1", ("_d1", "_diffuse1", "diffuse1")),
        ("goh_diffuse", ("_c", "_d", "_diff", "diffuse", "albedo", "basecolor", "base_color", "color")),
    )
    for role, needles in checks:
        if any(needle in lower for needle in needles):
            return role
    return None


def _infer_material_texture_props(material: bpy.types.Material) -> dict[str, str]:
    inferred: dict[str, str] = {}
    if material.node_tree:
        for node in material.node_tree.nodes:
            if node.type != "TEX_IMAGE" or not node.image:
                continue
            stem = _image_texture_stem(node.image)
            role = _texture_role_from_name(stem)
            if role and role not in inferred:
                inferred[role] = stem

    # Common one-texture Blender materials often use the material name itself.
    if "goh_diffuse" not in inferred:
        role = _texture_role_from_name(material.name)
        if role == "goh_diffuse":
            inferred["goh_diffuse"] = sanitized_file_stem(material.name)
    return inferred


def _material_has_goh_texture(material: bpy.types.Material) -> bool:
    return any(bool(material.get(key)) for key in GOH_TEXTURE_PROP_KEYS)


def _is_tool_volume_object(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH":
        return False
    if bool(obj.get("goh_is_volume")) or bool(obj.get("Volume")):
        return True
    if obj.name.lower().endswith("_vol"):
        return True
    return any(collection.name == "GOH_VOLUMES" for collection in obj.users_collection)


def _is_tool_obstacle_object(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH":
        return False
    return bool(obj.get("goh_is_obstacle")) or any(collection.name == "GOH_OBSTACLES" for collection in obj.users_collection)


def _is_tool_area_object(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH":
        return False
    return bool(obj.get("goh_is_area")) or any(collection.name == "GOH_AREAS" for collection in obj.users_collection)


def _is_tool_helper_object(obj: bpy.types.Object) -> bool:
    return _is_tool_volume_object(obj) or _is_tool_obstacle_object(obj) or _is_tool_area_object(obj) or bool(obj.get("goh_basis_helper"))


def _tool_export_name(obj: bpy.types.Object) -> str:
    for key in ("goh_bone_name", "goh_volume_name", "goh_shape_name", "ID"):
        value = obj.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return obj.name


def _local_axis_vector(axis_key: str) -> Vector:
    mapping = {
        "X": Vector((1.0, 0.0, 0.0)),
        "NEG_X": Vector((-1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "NEG_Y": Vector((0.0, -1.0, 0.0)),
        "X_Y": Vector((1.0, 1.0, 0.0)).normalized(),
        "NEG_X_Y": Vector((-1.0, 1.0, 0.0)).normalized(),
        "NEG_X_NEG_Y": Vector((-1.0, -1.0, 0.0)).normalized(),
        "X_NEG_Y": Vector((1.0, -1.0, 0.0)).normalized(),
        "Z": Vector((0.0, 0.0, 1.0)),
        "NEG_Z": Vector((0.0, 0.0, -1.0)),
    }
    return mapping.get(axis_key, Vector((0.0, -1.0, 0.0))).copy()


from .tools.physics_bake import export_to as _export_physics_bake_symbols
_export_physics_bake_symbols(globals())
del _export_physics_bake_symbols


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


GOH_PRESET_NAME_PROPS = (
    "goh_bone_name",
    "goh_attach_bone",
    "goh_volume_name",
    "goh_volume_bone",
    "goh_shape_name",
)


def _preset_name_key(name: str) -> str:
    return _strip_blender_duplicate_suffix(name)


def _preset_part_is_auto(part_preset) -> bool:
    return "auto" in part_preset.key.lower() or "(auto)" in part_preset.label.lower()


def _preset_reserved_names(selected_objects: Iterable[bpy.types.Object]) -> dict[str, set[str]]:
    selected = set(selected_objects)
    object_names: set[str] = set()
    goh_names: set[str] = set()
    for obj in bpy.data.objects:
        if obj in selected:
            continue
        object_names.add(_preset_name_key(obj.name))
        for prop_name in GOH_PRESET_NAME_PROPS:
            value = obj.get(prop_name)
            if isinstance(value, str) and value.strip():
                goh_names.add(_preset_name_key(value))
    return {"object": object_names, "goh": goh_names}


def _preset_generated_names(role_preset, part_preset, settings: GOHAddonPresetSettings, index: int) -> tuple[str, str]:
    numbering_rule = settings.numbering_rule if settings.auto_number else NUMBERING_RULE_PLAIN
    display_name = _numbered_display_name(
        part_preset.display_name,
        role_preset.name_suffix,
        index,
        settings.auto_number,
        part_preset.numbering,
        numbering_rule,
    )
    export_name = _numbered_identifier(
        part_preset.export_name,
        index,
        settings.auto_number,
        part_preset.numbering,
        numbering_rule,
    )
    return display_name, export_name


def _reserve_preset_names(used_names: dict[str, set[str]], display_name: str, export_name: str) -> None:
    used_names["object"].add(_preset_name_key(display_name))
    used_names["goh"].add(_preset_name_key(export_name))


def _allocate_preset_names(
    role_preset,
    part_preset,
    settings: GOHAddonPresetSettings,
    index: int,
    used_names: dict[str, set[str]],
) -> tuple[str, str]:
    if not settings.auto_number or not _preset_part_is_auto(part_preset):
        display_name, export_name = _preset_generated_names(role_preset, part_preset, settings, index)
        _reserve_preset_names(used_names, display_name, export_name)
        return display_name, export_name

    candidate_index = 0
    while candidate_index < 10000:
        display_name, export_name = _preset_generated_names(role_preset, part_preset, settings, candidate_index)
        display_conflicts = settings.rename_objects and _preset_name_key(display_name) in used_names["object"]
        export_conflicts = settings.write_export_names and _preset_name_key(export_name) in used_names["goh"]
        if not display_conflicts and not export_conflicts:
            _reserve_preset_names(used_names, display_name, export_name)
            return display_name, export_name
        candidate_index += 1

    display_name, export_name = _preset_generated_names(role_preset, part_preset, settings, index)
    _reserve_preset_names(used_names, display_name, export_name)
    return display_name, export_name


def _apply_goh_preset_to_object(
    scene: bpy.types.Scene,
    obj: bpy.types.Object,
    settings: GOHAddonPresetSettings,
    index: int,
    display_name: str | None = None,
    export_name: str | None = None,
) -> str:
    role_preset = GOH_ROLE_PRESET_MAP[settings.role]
    part_preset = _resolve_part_preset(settings.role, settings.part, settings.template_family)
    if display_name is None or export_name is None:
        display_name, export_name = _preset_generated_names(role_preset, part_preset, settings, index)
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


from .export.model_exporter import GOHBlenderExporter
from .importers.animation_importer import GOHAnimationImporter
from .importers.model_importer import GOHModelImporter


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
    material_blend: EnumProperty(
        name="Material Blend",
        items=(
            ("none", "blend none", "Write {blend none} for exported material files"),
            ("test", "blend test", "Write {blend test} for exported material files"),
            ("blend", "blend blend", "Write {blend blend} for exported material files"),
        ),
        default="none",
    )
    export_animations: BoolProperty(name="Export Animations", default=True)
    anm_format: EnumProperty(
        name="ANM Format",
        items=(
            ("AUTO", "Auto", "Write SOEdit-friendly transform FRM2 clips and fall back to legacy FRMN when needed"),
            ("FRM2", "FRM2", "Write FRM2 0x00060000 clips and include mesh animation chunks when present"),
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
        layout.prop(self, "material_blend")
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


class IMPORT_SCENE_OT_goh_model(Operator, ImportHelper):
    bl_idname = "import_scene.goh_model"
    bl_label = "Import GOH Model"
    bl_options = {"PRESET"}

    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={"HIDDEN"})
    axis_mode: EnumProperty(
        name="Axis Conversion",
        items=(
            ("NONE", "None / GOH Native", "Import GOH coordinates directly. Best for SOEdit-style round trips"),
            ("GOH_TO_BLENDER", "GOH -> Blender", "Rotate GOH X-forward coordinates into a Blender-friendly orientation"),
        ),
        default="NONE",
    )
    scale_factor: FloatProperty(name="Scale Factor", default=GOH_NATIVE_SCALE, min=0.001, soft_max=1000.0)
    flip_v: BoolProperty(name="Flip V", default=True)
    import_materials: BoolProperty(name="Import Materials", default=True)
    load_textures: BoolProperty(name="Load Diffuse Textures", default=True)
    import_volumes: BoolProperty(name="Import Volumes", default=True)
    import_shapes: BoolProperty(name="Import Obstacles / Areas", default=True)
    import_lod0_only: BoolProperty(name="LOD0 Only", default=True)
    defer_basis_flip: BoolProperty(
        name="Defer Basis Flip",
        description="Display mirrored GOH basis imports like they appear in-game, while preserving the original basis for export",
        default=True,
    )

    def draw(self, _context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "axis_mode")
        layout.prop(self, "scale_factor")
        layout.prop(self, "flip_v")
        layout.prop(self, "import_materials")
        layout.prop(self, "load_textures")
        layout.prop(self, "import_volumes")
        layout.prop(self, "import_shapes")
        layout.prop(self, "import_lod0_only")
        layout.prop(self, "defer_basis_flip")

    def execute(self, context: bpy.types.Context):
        importer = GOHModelImporter(context, self)
        try:
            count, warnings = importer.import_model()
        except ExportError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:  # pragma: no cover - Blender runtime guard
            self.report({"ERROR"}, f"Unexpected GOH model import error: {exc}")
            raise

        for warning in warnings[:10]:
            self.report({"WARNING"}, warning)
        self.report({"INFO"}, f"GOH model imported: {self.filepath} ({count} object(s))")
        return {"FINISHED"}


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
            ("AUTO", "Auto / Match Imported Model", "Use the axis and scale metadata stored by Import GOH Model when available"),
            ("GOH_TO_BLENDER", "GOH -> Blender", "Convert GOH X-forward transforms back into Blender space"),
            ("NONE", "None", "Use ANM transforms exactly as stored"),
        ),
        default="AUTO",
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
        part_preset = _resolve_part_preset(settings.role, settings.part, settings.template_family)
        selected_objects = sorted(context.selected_objects, key=lambda obj: obj.name.lower())
        used_names = _preset_reserved_names(selected_objects)
        applied_names: list[str] = []
        skipped = 0

        for index, obj in enumerate(selected_objects):
            if role_preset.key in {"volume", "obstacle", "area"} and obj.type != "MESH":
                skipped += 1
                continue
            display_name, export_name = _allocate_preset_names(role_preset, part_preset, settings, index, used_names)
            applied_names.append(
                _apply_goh_preset_to_object(
                    context.scene,
                    obj,
                    settings,
                    index,
                    display_name=display_name,
                    export_name=export_name,
                )
            )

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
                _set_custom_bool_prop(obj, "goh_force_commonmesh", True)
                obj["CommonMesh"] = True
                _remove_custom_prop(obj, "Poly")
            elif self.action == "POLY":
                _clear_helper_state(context.scene, obj, clear_collections=True)
                _remove_custom_prop(obj, "goh_force_mesh_animation")
                _remove_custom_prop(obj, "goh_force_commonmesh")
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
                _remove_custom_prop(obj, "goh_force_commonmesh")
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
                _remove_custom_prop(obj, "goh_force_commonmesh")
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

        texture_lines: list[str] = []
        seen_textures: set[str] = set()
        for material in sorted(_materials_for_tool_scope(context, settings.texture_scope), key=lambda item: item.name.lower()):
            entries: list[str] = []
            for key in GOH_TEXTURE_PROP_KEYS:
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
        _write_text_block("GOH_Texture_Report.txt", report_text)
        context.window_manager.clipboard = report_text
        self.report({"INFO"}, f"Reported {len(texture_lines)} texture reference(s).")
        return {"FINISHED"}


class SCENE_OT_goh_autofill_materials(Operator):
    bl_idname = "scene.goh_autofill_materials"
    bl_label = "Auto-Fill GOH Materials"
    bl_description = "Infer GOH material texture properties from Blender image texture node names"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}

        changed = 0
        materials = _materials_for_tool_scope(context, settings.texture_scope)
        for material in materials:
            inferred = _infer_material_texture_props(material)
            wrote_any = False
            for key, value in inferred.items():
                if not settings.material_overwrite and material.get(key):
                    continue
                material[key] = value
                wrote_any = True
            if wrote_any:
                if inferred.get("goh_bump") or inferred.get("goh_specular"):
                    material["goh_material_kind"] = "bump"
                elif not material.get("goh_material_kind"):
                    material["goh_material_kind"] = "simple"
                changed += 1

        self.report({"INFO"}, f"Auto-filled GOH texture fields on {changed} material(s).")
        return {"FINISHED"}


class SCENE_OT_goh_validate_scene(Operator):
    bl_idname = "scene.goh_validate_scene"
    bl_label = "Validate GOH Scene"
    bl_description = "Scan the current GOH scene for common export mistakes and create a text report"

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        scope = settings.validation_scope if settings else "VISIBLE"
        objects = _objects_for_tool_scope(context, scope)
        materials = _materials_for_tool_scope(context, "ALL" if scope == "ALL" else scope)
        errors: list[str] = []
        warnings: list[str] = []
        info: list[str] = []

        basis_settings = getattr(context.scene, "goh_basis_settings", None)
        has_basis = bool(basis_settings and basis_settings.enabled) or any(
            obj.name.lower() == GOH_BASIS_HELPER_NAME.lower() or obj.get("goh_basis_helper")
            for obj in context.scene.objects
        )
        if not has_basis:
            warnings.append("Basis metadata is not enabled and no Basis helper was found.")

        export_names: dict[str, list[str]] = {}
        for obj in objects:
            if _is_tool_helper_object(obj):
                continue
            if obj.type not in {"MESH", "EMPTY", "ARMATURE"}:
                continue
            export_names.setdefault(_tool_export_name(obj).lower(), []).append(obj.name)
            if obj.type == "MESH":
                if not obj.material_slots:
                    warnings.append(f'Mesh "{obj.name}" has no material slot.')
                if obj.material_slots and not obj.data.uv_layers:
                    warnings.append(f'Mesh "{obj.name}" has materials but no UV map.')
                if not obj.data.polygons:
                    warnings.append(f'Mesh "{obj.name}" has no faces.')
                else:
                    zero_area_count = sum(1 for polygon in obj.data.polygons if polygon.area <= EPSILON)
                    if zero_area_count:
                        warnings.append(f'Mesh "{obj.name}" has {zero_area_count} zero-area face(s).')
                if any(abs(value - 1.0) > 1e-4 for value in obj.scale):
                    warnings.append(f'Mesh "{obj.name}" has unapplied object scale.')
                lod_value = str(obj.get("goh_lod_files") or "").strip()
                if lod_value:
                    bad_lods = [
                        entry.strip()
                        for entry in re.split(r"[,;\n]+", lod_value)
                        if entry.strip() and not entry.strip().lower().endswith(".ply")
                    ]
                    if bad_lods:
                        warnings.append(f'Mesh "{obj.name}" has non-.ply LOD entries: {", ".join(bad_lods)}')

        for export_name, object_names in sorted(export_names.items()):
            if export_name and len(object_names) > 1:
                warnings.append(f'Duplicate GOH export name "{export_name}" on objects: {", ".join(object_names)}')

        for obj in objects:
            if not _is_tool_volume_object(obj):
                continue
            volume_kind = str(obj.get("goh_volume_kind") or "polyhedron").strip().lower()
            if volume_kind not in GOH_VOLUME_KIND_VALUES:
                errors.append(f'Volume "{obj.name}" has unsupported goh_volume_kind "{volume_kind}".')
            if not str(obj.get("goh_volume_bone") or "").strip() and not obj.name.lower().endswith("_vol"):
                warnings.append(f'Volume "{obj.name}" has no goh_volume_bone and cannot derive one from _vol naming.')
            if volume_kind == "cylinder":
                axis = str(obj.get("goh_volume_axis") or "").strip().lower()
                if axis not in {"x", "y", "z"}:
                    warnings.append(f'Cylinder volume "{obj.name}" has no valid goh_volume_axis; default export axis is Z.')
            if volume_kind == "polyhedron" and obj.type == "MESH" and len(obj.data.vertices) > 65535:
                info.append(f'Volume "{obj.name}" exceeds 65535 vertices and will be split into multiple .vol files.')
            if volume_kind == "polyhedron" and obj.type == "MESH" and bool(obj.get("goh_auto_quad_cage")):
                max_faces = int(obj.get("goh_auto_convex_target_faces") or 5000)
                vertices, faces = _quad_cage_from_mesh_object(obj)
                quad_report = _validate_quad_cage(vertices, faces, max_faces)
                for severity, key, value in quad_report:
                    if severity == "ERROR":
                        errors.append(f'Auto collision cage "{obj.name}" failed {key}: {value}.')
                    elif severity == "WARN":
                        warnings.append(f'Auto collision cage "{obj.name}" warning {key}: {value}.')

        for obj in objects:
            if not (_is_tool_obstacle_object(obj) or _is_tool_area_object(obj)):
                continue
            shape_type = str(obj.get("goh_shape_2d") or "obb2").strip().lower()
            if shape_type not in {"obb2", "circle2", "polygon2"}:
                errors.append(f'Shape helper "{obj.name}" has unsupported goh_shape_2d "{shape_type}".')
            if obj.type == "MESH" and shape_type == "polygon2" and len(obj.data.vertices) < 3:
                warnings.append(f'Polygon2 helper "{obj.name}" has fewer than three vertices.')
            if not str(obj.get("goh_shape_name") or "").strip():
                warnings.append(f'Shape helper "{obj.name}" has no goh_shape_name and will export using the object name.')

        for obj in objects:
            animation_data = getattr(obj, "animation_data", None)
            action = getattr(animation_data, "action", None) if animation_data else None
            segments = _physics_object_sequence_ranges(obj, action)
            if not segments:
                continue
            sorted_segments = sorted(
                segments,
                key=lambda item: (int(item.get("frame_start", 0)), int(item.get("frame_end", 0))),
            )
            for segment in sorted_segments:
                start = int(segment.get("frame_start", 0))
                end = int(segment.get("frame_end", start))
                if start < 0 or end < 0:
                    warnings.append(f'Object "{obj.name}" has negative GOH sequence range frames.')
                if start == end:
                    warnings.append(f'Object "{obj.name}" has one-frame GOH sequence range "{segment.get("name", "")}".')
            for left, right in zip(sorted_segments, sorted_segments[1:]):
                left_start = int(left.get("frame_start", 0))
                left_end = int(left.get("frame_end", left_start))
                right_start = int(right.get("frame_start", 0))
                right_end = int(right.get("frame_end", right_start))
                if _physics_ranges_overlap(left_start, left_end, right_start, right_end):
                    warnings.append(
                        f'Object "{obj.name}" has overlapping GOH sequence ranges '
                        f'"{left.get("name", "")}" and "{right.get("name", "")}".'
                    )

        for material in materials:
            if not _material_has_goh_texture(material):
                inferred = _infer_material_texture_props(material)
                if inferred:
                    warnings.append(f'Material "{material.name}" has image textures but no GOH texture fields. Run Auto-Fill GOH Materials.')
                elif material.node_tree:
                    warnings.append(f'Material "{material.name}" has no recognized GOH texture naming pattern.')
            if material.node_tree:
                for node in material.node_tree.nodes:
                    if node.type != "TEX_IMAGE" or not node.image:
                        continue
                    image_path = _image_source_path(node.image)
                    if image_path is not None and not image_path.exists():
                        warnings.append(f'Material "{material.name}" references missing texture file: {image_path}')

        lines = [
            "GOH Validation Report",
            f"Scope: {scope}",
            f"Objects: {len(objects)}",
            f"Materials: {len(materials)}",
            f"Errors: {len(errors)}",
            f"Warnings: {len(warnings)}",
            f"Info: {len(info)}",
            "",
        ]
        for title, bucket in (("ERRORS", errors), ("WARNINGS", warnings), ("INFO", info)):
            lines.append(title)
            if bucket:
                lines.extend(f"- {entry}" for entry in bucket)
            else:
                lines.append("- None")
            lines.append("")

        report_text = "\n".join(lines).rstrip() + "\n"
        _write_text_block("GOH_Validation_Report.txt", report_text)
        context.window_manager.clipboard = report_text
        if errors:
            self.report({"ERROR"}, f"GOH validation found {len(errors)} error(s) and {len(warnings)} warning(s).")
            return {"CANCELLED"}
        self.report({"INFO"}, f"GOH validation finished with {len(warnings)} warning(s).")
        return {"FINISHED"}


class OBJECT_OT_goh_assign_lod_files(Operator):
    bl_idname = "object.goh_assign_lod_files"
    bl_label = "Assign LOD Files"
    bl_description = "Write goh_lod_files for selected visual mesh objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}
        count = 0
        for obj in sorted(context.selected_objects, key=lambda item: item.name.lower()):
            if obj.type != "MESH" or _is_tool_helper_object(obj):
                continue
            stem = sanitized_file_stem(str(obj.get("goh_bone_name") or obj.name))
            files = [f"{stem}.ply"]
            files.extend(f"{stem}_lod{index}.ply" for index in range(1, settings.lod_levels + 1))
            obj["goh_lod_files"] = ";".join(files)
            _set_custom_bool_prop(obj, "goh_lod_off", bool(settings.lod_mark_off))
            count += 1
        if count == 0:
            self.report({"WARNING"}, "No visual mesh objects were selected for LOD assignment.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Assigned LOD file lists to {count} mesh object(s).")
        return {"FINISHED"}


from .tools.collision_cage import export_to as _export_collision_cage_symbols
_export_collision_cage_symbols(globals())
del _export_collision_cage_symbols


class OBJECT_OT_goh_create_auto_convex_volume(Operator):
    bl_idname = "object.goh_create_auto_convex_volume"
    bl_label = "Auto Collision Cage Volume"
    bl_description = "Create closed triangle/quad GOH polyhedron volume helpers from the selected meshes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        for obj in context.selected_objects:
            if obj.type == "MESH" and not _is_tool_helper_object(obj):
                return True
            if any(child.type == "MESH" and not _is_tool_helper_object(child) for child in _iter_object_tree(obj)):
                return True
        return False

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}

        created: list[bpy.types.Object] = []
        skipped: list[str] = []
        used_volume_names: dict[str, int] = {}
        source_objects = _auto_convex_source_objects(
            context,
            str(settings.auto_convex_source_scope) == "HIERARCHY",
        )
        if bool(settings.auto_convex_clear_existing):
            _clear_existing_auto_convex_helpers(context.scene, source_objects)

        max_hulls = max(1, int(settings.auto_convex_max_hulls))
        source_groups: list[AutoConvexSourceGroup] = []
        for obj in source_objects:
            try:
                groups = _mesh_world_point_groups(
                    context,
                    obj,
                    bool(settings.auto_convex_use_evaluated),
                    bool(settings.auto_convex_split_loose_parts),
                    int(settings.auto_convex_min_part_vertices),
                )
                groups = sorted(groups, key=lambda group: _point_bounds_volume(group.points), reverse=True)
                if not groups:
                    raise ValueError("source mesh has no usable vertices")
            except Exception as exc:
                skipped.append(f"{obj.name}: {exc}")
                continue
            source_groups.extend(groups)

        tasks, dropped_groups = _build_auto_quad_cage_task_queue(
            source_groups,
            max_hulls,
        )
        if dropped_groups:
            skipped.append(f"{dropped_groups} small source group(s): max hull limit reached")

        for task_index, task in enumerate(tasks, start=1):
            try:
                result = _build_auto_quad_cage(task, settings)
            except Exception as exc:
                skipped.append(f"{task.source.name}: {exc}")
                continue
            bone_name = str(task.source.get("goh_bone_name") or task.source.name).strip()
            base_stem = sanitized_file_stem(bone_name) or sanitized_file_stem(task.source.name) or "auto_convex"
            suffix = task.label or f"hull{task_index:02d}"
            proposed_name = f"{base_stem}_{suffix}" if suffix else base_stem
            volume_name = _unique_auto_convex_stem(proposed_name, used_volume_names)
            helper = _create_auto_convex_volume_helper(
                context,
                task.source,
                result,
                int(settings.auto_convex_target_faces),
                float(settings.auto_convex_margin),
                bool(settings.auto_convex_smooth_display),
                volume_name,
            )
            helper["goh_auto_convex_group"] = task.label or task.source.name
            helper["goh_auto_convex_group_vertices"] = int(task.vertex_count)
            helper["goh_auto_convex_output_topology"] = str(settings.auto_convex_output_topology)
            created.append(helper)

        return _finish_auto_convex_volume_operator(self, context, created, skipped)


class OBJECT_OT_goh_create_volume_from_bounds(Operator):
    bl_idname = "object.goh_create_volume_from_bounds"
    bl_label = "Volume From Bounds"
    bl_description = "Create GOH collision volume helpers from the selected mesh bounding boxes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return any(obj.type == "MESH" and not _is_tool_helper_object(obj) for obj in context.selected_objects)

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}

        created: list[bpy.types.Object] = []
        source_objects = [
            obj for obj in sorted(context.selected_objects, key=lambda item: item.name.lower())
            if obj.type == "MESH" and not _is_tool_helper_object(obj)
        ]
        for obj in source_objects:
            world_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            if not world_corners:
                continue
            min_corner = Vector((
                min(point.x for point in world_corners),
                min(point.y for point in world_corners),
                min(point.z for point in world_corners),
            ))
            max_corner = Vector((
                max(point.x for point in world_corners),
                max(point.y for point in world_corners),
                max(point.z for point in world_corners),
            ))
            center = (min_corner + max_corner) * 0.5
            size = max_corner - min_corner
            if size.length <= EPSILON:
                continue
            bone_name = str(obj.get("goh_bone_name") or obj.name).strip()
            volume_name = sanitized_file_stem(bone_name)
            helper_name = f"{volume_name}_vol"

            bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
            helper = context.active_object
            helper.name = helper_name
            helper.display_type = "WIRE"
            helper.show_in_front = True
            helper.dimensions = (max(size.x, EPSILON), max(size.y, EPSILON), max(size.z, EPSILON))
            context.view_layer.update()
            helper["goh_is_volume"] = True
            helper["goh_volume_name"] = volume_name
            helper["goh_volume_bone"] = bone_name
            helper["goh_volume_kind"] = settings.helper_volume_kind.lower()
            _link_to_helper_collection(context.scene, helper, "GOH_VOLUMES")
            created.append(helper)

        if not created:
            self.report({"WARNING"}, "No bounds volumes were created.")
            return {"CANCELLED"}
        bpy.ops.object.select_all(action="DESELECT")
        for helper in created:
            helper.select_set(True)
        context.view_layer.objects.active = created[-1]
        self.report({"INFO"}, f"Created {len(created)} GOH volume helper(s) from mesh bounds.")
        return {"FINISHED"}


class OBJECT_OT_goh_create_recoil_action(Operator):
    bl_idname = "object.goh_create_recoil_action"
    bl_label = "Create Recoil Action"
    bl_description = "Generate a baked local-axis recoil action on selected objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.selected_objects)

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}
        start = int(context.scene.frame_current)
        total = max(3, int(settings.recoil_frames))
        peak = start + max(1, total // 4)
        settle = start + max(2, total // 2)
        end = start + total
        local_axis = _local_axis_vector(settings.recoil_axis)
        count = 0

        for obj in sorted(context.selected_objects, key=lambda item: item.name.lower()):
            original_location = obj.location.copy()
            direction = obj.matrix_world.to_3x3() @ local_axis
            if direction.length <= EPSILON:
                direction = local_axis
            direction.normalize()
            offset = direction * float(settings.recoil_distance)

            obj.animation_data_create()
            previous_action = getattr(obj.animation_data, "action", None)
            sequence_name, file_stem = _physics_sequence_names("recoil", previous_action, obj)
            action = _physics_prepare_action(
                obj,
                "goh_recoil",
                sequence_name,
                file_stem,
                start=start,
                end=end,
                data_paths={"location"},
            )
            obj.location = original_location
            obj.keyframe_insert(data_path="location", frame=start)
            obj.location = original_location + _object_local_offset_from_world(obj, offset)
            obj.keyframe_insert(data_path="location", frame=peak)
            obj.location = original_location - _object_local_offset_from_world(obj, offset * 0.18)
            obj.keyframe_insert(data_path="location", frame=settle)
            obj.location = original_location
            obj.keyframe_insert(data_path="location", frame=end)
            if settings.recoil_set_sequence:
                _physics_mark_sequence(obj, sequence_name, file_stem)
                _physics_mark_sequence(action, sequence_name, file_stem)
            count += 1

        if count == 0:
            self.report({"WARNING"}, "No objects were available for recoil action generation.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Created baked recoil action on {count} object(s).")
        return {"FINISHED"}


class OBJECT_OT_goh_assign_physics_link(Operator):
    bl_idname = "object.goh_assign_physics_link"
    bl_label = "Assign Physics Link"
    bl_description = "Store a GOH physics-bake link from the active source object to the other selected objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.object is not None and len(context.selected_objects) >= 2

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        source = context.object
        if settings is None or source is None:
            self.report({"ERROR"}, "GOH tool settings or active source object are not available.")
            return {"CANCELLED"}
        source_id = _physics_object_id(source)
        count = 0
        for obj in sorted(context.selected_objects, key=lambda item: item.name.lower()):
            if obj == source:
                obj["goh_physics_source"] = source_id
                obj["goh_physics_role"] = "SOURCE"
                continue
            obj["goh_physics_source"] = source_id
            obj["goh_physics_role"] = settings.physics_link_role
            weight, delay, frequency, damping, jitter, rotation = _physics_effective_link_values(settings, settings.physics_link_role)
            obj["goh_physics_weight"] = weight
            obj["goh_physics_delay"] = delay
            obj["goh_physics_frequency"] = frequency
            obj["goh_physics_damping"] = damping
            obj["goh_physics_jitter"] = jitter
            obj["goh_physics_rotation"] = rotation
            obj["goh_physics_solver_space"] = settings.physics_solver_space
            obj["goh_physics_substeps"] = int(settings.physics_substeps)
            obj["goh_physics_force_limit"] = float(settings.physics_force_limit)
            obj["goh_physics_end_fade"] = float(settings.physics_end_fade)
            if settings.physics_link_role == "ANTENNA_WHIP":
                obj["goh_antenna_root_anchor"] = float(settings.physics_antenna_root_anchor)
                obj["goh_antenna_segments"] = int(settings.physics_antenna_segments)
            count += 1
        if count == 0:
            self.report({"WARNING"}, "Select at least one linked object in addition to the active source.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Assigned GOH physics link from {source.name} to {count} object(s).")
        return {"FINISHED"}


class OBJECT_OT_goh_bake_linked_recoil(Operator):
    bl_idname = "object.goh_bake_linked_recoil"
    bl_label = "Bake Linked Recoil"
    bl_description = "Bake source recoil plus linked spring/jitter responses into regular object keyframes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.object is not None

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        source = context.object
        if settings is None or source is None:
            self.report({"ERROR"}, "GOH tool settings or active source object are not available.")
            return {"CANCELLED"}

        linked = _physics_linked_objects(context, source, settings.physics_include_scene_links)

        start = int(context.scene.frame_current)
        total = max(3, int(settings.recoil_frames))
        clip_total = _physics_max_clip_frames(settings, linked, total)
        source_end = start + total
        end = start + clip_total
        peak = start + max(1, total // 4)
        settle = start + max(2, total // 2)
        source_axis = _physics_axis_world(source, settings.recoil_axis)
        distance = float(settings.recoil_distance)
        sequence_name, file_stem = _physics_sequence_names(
            "recoil",
            getattr(getattr(source, "animation_data", None), "action", None),
            source,
        )

        _physics_bake_source_recoil(
            source,
            source_axis,
            distance,
            start,
            peak,
            settle,
            source_end,
            sequence_name=sequence_name,
            file_stem=file_stem,
            write_object_sequence=settings.recoil_set_sequence,
            create_nla=settings.physics_create_nla_clips,
            clip_end=end,
        )
        for obj in sorted(linked, key=lambda item: item.name.lower()):
            linked_sequence_name, linked_file_stem = _physics_sequence_names(
                sequence_name,
                obj,
                source,
            )
            _physics_bake_linked_response(
                obj,
                source_axis,
                distance,
                start,
                end,
                settings,
                sequence_name=linked_sequence_name,
                file_stem=linked_file_stem,
                create_nla=settings.physics_create_nla_clips,
                base_duration=total,
                source_obj=source,
            )

        self.report({"INFO"}, f"Baked linked recoil: source {source.name}, linked parts {len(linked)}.")
        return {"FINISHED"}


class OBJECT_OT_goh_bake_directional_recoil_set(Operator):
    bl_idname = "object.goh_bake_directional_recoil_set"
    bl_label = "Bake Directional Set"
    bl_description = "Bake a set of directional recoil clips and optional linked spring responses into NLA strips"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.object is not None

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        source = context.object
        if settings is None or source is None:
            self.report({"ERROR"}, "GOH tool settings or active source object are not available.")
            return {"CANCELLED"}

        linked = _physics_linked_objects(context, source, settings.physics_include_scene_links)
        start_base = int(getattr(context.scene, "frame_start", context.scene.frame_current))
        context.scene.frame_set(start_base)
        total = max(3, int(settings.recoil_frames))
        clip_total = _physics_max_clip_frames(settings, linked, total)
        distance = float(settings.recoil_distance)
        gap = 2
        clip_specs = _physics_direction_specs(settings.physics_direction_set, settings.physics_clip_prefix)

        for index, (clip_name, axis_key) in enumerate(clip_specs):
            start = start_base + index * (clip_total + gap)
            source_end = start + total
            end = start + clip_total
            peak = start + max(1, total // 4)
            settle = start + max(2, total // 2)
            # Direction-set clip names describe the GOH fire direction. The barrel
            # itself always performs a straight local-X recoil/return stroke.
            # Linked hull responses still use the named fire direction as their
            # impulse proxy, while turret-scoped parts and antenna whip stay on
            # the same X/-X gun axis because the turret rotation supplies heading.
            fire_axis = _physics_axis_world(source, axis_key)
            barrel_axis = _physics_axis_world(source, "X")
            source_axis = -barrel_axis
            _physics_bake_source_recoil(
                source,
                source_axis,
                distance,
                start,
                peak,
                settle,
                source_end,
                action_prefix="goh_directional_recoil_source",
                sequence_name=clip_name,
                file_stem=clip_name,
                create_nla=settings.physics_create_nla_clips,
                clip_end=end,
            )
            antenna_mount = str(getattr(settings, "physics_antenna_mount", "TURRET") or "TURRET").upper()
            for obj in sorted(linked, key=lambda item: item.name.lower()):
                linked_role = _physics_role_from_object(obj, settings)
                turret_scoped = _physics_is_turret_scoped_object(obj)
                if linked_role == "ANTENNA_WHIP":
                    linked_axis = fire_axis if antenna_mount == "BODY" else barrel_axis
                    linked_source_obj = None if antenna_mount == "BODY" else source
                elif turret_scoped:
                    linked_axis = barrel_axis
                    linked_source_obj = source
                else:
                    linked_axis = fire_axis
                    linked_source_obj = source
                _physics_bake_linked_response(
                    obj,
                    linked_axis,
                    distance,
                    start,
                    end,
                    settings,
                    action_prefix="goh_directional_recoil_link",
                    sequence_name=clip_name,
                    file_stem=clip_name,
                    create_nla=settings.physics_create_nla_clips,
                    base_duration=total,
                    source_obj=linked_source_obj,
                    invert_body_rotation=True,
                    invert_body_primary_translation=True,
                    force_procedural_source_motion=True,
                    procedural_source_axis=-linked_axis,
                )

        context.scene.frame_set(start_base)
        self.report({"INFO"}, f"Baked {len(clip_specs)} directional recoil clip(s) from {source.name}.")
        return {"FINISHED"}


class OBJECT_OT_goh_create_fire_recoil_triggers(Operator):
    bl_idname = "object.goh_create_fire_recoil_triggers"
    bl_label = "Create Fire Trigger Volumes"
    bl_description = "Create basis-level recoil_gun_* pie-slice volumes and a turret-level gun_recoil point"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene is not None

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}
        try:
            created, point = _physics_create_fire_trigger_volumes(context, settings)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Created {created} fire trigger volume(s) and prepared {point.name}.")
        return {"FINISHED"}


class OBJECT_OT_goh_bake_impact_response(Operator):
    bl_idname = "object.goh_bake_impact_response"
    bl_label = "Bake Impact Response"
    bl_description = "Bake a damped hit/impact shake action on selected objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.selected_objects)

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}
        clip_name = sanitized_file_stem(settings.physics_impact_clip_name or "hit") or "hit"
        start = int(context.scene.frame_current)
        base_total = max(3, int(settings.recoil_frames))
        selected_objects = list(context.selected_objects)
        end = start + _physics_max_duration_frames(settings, selected_objects, base_total)
        distance = float(settings.recoil_distance)
        count = 0
        for obj in sorted(selected_objects, key=lambda item: item.name.lower()):
            axis = _physics_axis_world(obj, settings.recoil_axis)
            _physics_bake_impact_response(
                obj,
                axis,
                distance,
                start,
                end,
                settings,
                sequence_name=clip_name,
                create_nla=settings.physics_create_nla_clips,
                base_duration=base_total,
            )
            count += 1
        self.report({"INFO"}, f"Baked impact response on {count} object(s).")
        return {"FINISHED"}


class OBJECT_OT_goh_create_armor_ripple(Operator):
    bl_idname = "object.goh_create_armor_ripple"
    bl_label = "Create Armor Ripple"
    bl_description = "Create per-frame shape keys for a small armor ripple mesh-animation effect around the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}
        clip_name = sanitized_file_stem(settings.physics_impact_clip_name or "hit") or "hit"
        start = int(context.scene.frame_current)
        end = start + max(3, int(settings.recoil_frames))
        center_world = context.scene.cursor.location.copy()
        count = 0
        for obj in sorted(context.selected_objects, key=lambda item: item.name.lower()):
            if obj.type != "MESH":
                continue
            axis = _physics_axis_world(obj, settings.recoil_axis)
            if _physics_create_armor_ripple(
                obj,
                center_world,
                axis,
                start,
                end,
                settings,
                sequence_name=clip_name,
                create_nla=settings.physics_create_nla_clips,
            ):
                count += 1
        if count == 0:
            self.report({"WARNING"}, "Select at least one mesh object for armor ripple generation.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Created armor ripple shape-key animation on {count} mesh object(s).")
        return {"FINISHED"}


class OBJECT_OT_goh_load_physics_defaults(Operator):
    bl_idname = "object.goh_load_physics_defaults"
    bl_label = "Load Role Defaults"
    bl_description = "Load useful spring, damping, jitter, and rotation defaults for the selected link role"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        if settings is None:
            self.report({"ERROR"}, "GOH tool settings are not available.")
            return {"CANCELLED"}
        weight, frequency, damping, rotation = _physics_role_defaults(settings.physics_link_role)
        settings.physics_link_weight = weight
        settings.physics_link_delay = _physics_role_delay_default(settings.physics_link_role)
        settings.physics_link_frequency = frequency
        settings.physics_link_damping = damping
        settings.physics_link_rotation = rotation
        settings.physics_link_jitter = _physics_role_jitter_default(settings.physics_link_role)
        settings.physics_solver_space = "PARENT_LOCAL"
        settings.physics_substeps = 4
        settings.physics_force_limit = 0.0
        settings.physics_end_fade = 0.16
        self.report({"INFO"}, f"Loaded physics defaults for {settings.physics_link_role}.")
        return {"FINISHED"}


class OBJECT_OT_goh_clear_physics_links(Operator):
    bl_idname = "object.goh_clear_physics_links"
    bl_label = "Clear Physics Links"
    bl_description = "Clear GOH physics link metadata and optionally detach generated physics actions/NLA strips"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.selected_objects)

    def execute(self, context: bpy.types.Context):
        settings = getattr(context.scene, "goh_tool_settings", None)
        clear_actions = bool(getattr(settings, "physics_clear_actions", False))
        count = 0
        for obj in sorted(context.selected_objects, key=lambda item: item.name.lower()):
            if _physics_clear_object(obj, clear_actions):
                count += 1
        self.report({"INFO"}, f"Cleared GOH physics data on {count} object(s).")
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
        texture_box.prop(settings, "material_overwrite")
        texture_box.operator(SCENE_OT_goh_autofill_materials.bl_idname, text="Auto-Fill GOH Materials")
        texture_box.operator(SCENE_OT_goh_report_textures.bl_idname, text="Report Texture Names")

        validation_box = layout.box()
        validation_box.label(text="Validation")
        validation_box.prop(settings, "validation_scope")
        validation_box.operator(SCENE_OT_goh_validate_scene.bl_idname, text="Validate GOH Scene")

        lod_box = layout.box()
        lod_box.label(text="LOD Helpers")
        lod_box.prop(settings, "lod_levels")
        lod_box.prop(settings, "lod_mark_off")
        lod_box.operator(OBJECT_OT_goh_assign_lod_files.bl_idname, text="Assign LOD Files")

        collision_box = layout.box()
        collision_box.label(text="Collision Helpers")
        collision_box.prop(settings, "helper_volume_kind")
        collision_box.operator(OBJECT_OT_goh_create_volume_from_bounds.bl_idname, text="Volume From Bounds")
        collision_box.separator()
        collision_box.prop(settings, "auto_convex_template")
        collision_box.prop(settings, "auto_convex_fit_mode")
        collision_box.prop(settings, "auto_convex_source_scope")
        collision_box.prop(settings, "auto_convex_output_topology")
        collision_box.prop(settings, "auto_convex_target_faces")
        collision_box.prop(settings, "auto_convex_optimize_iterations", slider=True)
        collision_box.prop(settings, "auto_convex_max_hulls")
        collision_box.prop(settings, "auto_convex_margin")
        row = collision_box.row(align=True)
        row.prop(settings, "auto_convex_use_evaluated")
        row.prop(settings, "auto_convex_smooth_display")
        collision_box.prop(settings, "auto_convex_clear_existing")
        row = collision_box.row(align=True)
        row.prop(settings, "auto_convex_split_loose_parts")
        collision_box.prop(settings, "auto_convex_min_part_vertices")
        row = collision_box.row(align=True)
        row.prop(settings, "auto_convex_smooth_iterations")
        row.prop(settings, "auto_convex_planarize_quads")
        if settings.auto_convex_planarize_quads:
            collision_box.prop(settings, "auto_convex_planarize_strength")
        collision_box.operator(OBJECT_OT_goh_create_auto_convex_volume.bl_idname, text="Auto Collision Cage Volume")

        physics_box = layout.box()
        physics_box.label(text="Physics Bake Presets")
        physics_box.prop(settings, "recoil_axis")
        physics_box.prop(settings, "recoil_distance")
        physics_box.prop(settings, "recoil_frames")
        physics_box.prop(settings, "recoil_set_sequence")
        physics_box.operator(OBJECT_OT_goh_create_recoil_action.bl_idname, text="Create Recoil Action")
        physics_box.separator()
        physics_box.prop(settings, "physics_direction_set")
        physics_box.prop(settings, "physics_clip_prefix")
        trigger_box = physics_box.box()
        trigger_box.label(text="Fire Trigger Volumes")
        row = trigger_box.row(align=True)
        row.prop(settings, "fire_trigger_radius")
        row.prop(settings, "fire_trigger_thickness")
        trigger_box.prop(settings, "fire_trigger_point_distance")
        row = trigger_box.row(align=True)
        row.prop(settings, "fire_trigger_arc_segments")
        row.prop(settings, "fire_trigger_replace_existing")
        trigger_box.operator(OBJECT_OT_goh_create_fire_recoil_triggers.bl_idname, text="Create Fire Trigger Volumes")
        physics_box.prop(settings, "physics_impact_clip_name")
        physics_box.prop(settings, "physics_ripple_amplitude")
        physics_box.prop(settings, "physics_ripple_radius")
        physics_box.prop(settings, "physics_ripple_waves")
        physics_box.prop(settings, "physics_power")
        row = physics_box.row(align=True)
        row.prop(settings, "physics_body_sway_strength")
        row.prop(settings, "physics_antenna_sway_strength")
        physics_box.prop(settings, "physics_antenna_mount")
        physics_box.prop(settings, "physics_duration_scale")
        physics_box.prop(settings, "physics_create_nla_clips")
        row = physics_box.row(align=True)
        row.operator(OBJECT_OT_goh_bake_directional_recoil_set.bl_idname, text="Bake Directional Set")
        row.operator(OBJECT_OT_goh_bake_impact_response.bl_idname, text="Bake Impact Response")
        physics_box.operator(OBJECT_OT_goh_create_armor_ripple.bl_idname, text="Create Armor Ripple")
        physics_box.separator()
        physics_box.prop(settings, "physics_link_role")
        physics_box.operator(OBJECT_OT_goh_load_physics_defaults.bl_idname, text="Load Role Defaults")
        physics_box.prop(settings, "physics_link_weight")
        physics_box.prop(settings, "physics_link_delay")
        physics_box.prop(settings, "physics_link_frequency")
        physics_box.prop(settings, "physics_link_damping")
        physics_box.prop(settings, "physics_link_jitter")
        physics_box.prop(settings, "physics_link_rotation")
        physics_box.prop(settings, "physics_solver_space")
        row = physics_box.row(align=True)
        row.prop(settings, "physics_substeps")
        row.prop(settings, "physics_end_fade")
        physics_box.prop(settings, "physics_force_limit")
        if settings.physics_link_role == "ANTENNA_WHIP":
            physics_box.prop(settings, "physics_antenna_root_anchor")
            physics_box.prop(settings, "physics_antenna_segments")
        physics_box.prop(settings, "physics_include_scene_links")
        row = physics_box.row(align=True)
        row.operator(OBJECT_OT_goh_assign_physics_link.bl_idname, text="Assign Physics Link")
        row.operator(OBJECT_OT_goh_bake_linked_recoil.bl_idname, text="Bake Linked Recoil")
        physics_box.prop(settings, "physics_clear_actions")
        physics_box.operator(OBJECT_OT_goh_clear_physics_links.bl_idname, text="Clear Physics Links")


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
        if settings.auto_number:
            layout.prop(settings, "numbering_rule")
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
        layout.operator(IMPORT_SCENE_OT_goh_model.bl_idname, text="Import GOH Model")
        layout.operator(IMPORT_SCENE_OT_goh_anm.bl_idname, text="Import GOH Animation")
        layout.label(text="网格对象 Mesh objects 会导出为 GOH bones。", translate=False)
        layout.label(text='辅助体 Helpers 可用 "_vol"、GOH_VOLUMES、GOH_OBSTACLES、GOH_AREAS 识别。', translate=False)
        layout.label(text="预设 GOH Presets 用结构化字段替代旧版 Max 文本模板。", translate=False)
        layout.label(text="骨架 Armature + 顶点组 Vertex Groups 可导出 skinned PLY。", translate=False)
        layout.label(text="动作 Action / NLA strips 可导出 ANM 与 shape-key mesh chunks。", translate=False)
        layout.label(text=f"SOEdit / Max round-trip 推荐使用 Axis=None、Scale={int(GOH_NATIVE_SCALE)}、Flip V=On、Defer Basis Flip=On。", translate=False)


def menu_func_export(self, _context):
    self.layout.operator(EXPORT_SCENE_OT_goh_model.bl_idname, text="GOH Model (.mdl)")


def menu_func_import(self, _context):
    self.layout.operator(IMPORT_SCENE_OT_goh_model.bl_idname, text="GOH Model (.mdl)")
    self.layout.operator(IMPORT_SCENE_OT_goh_anm.bl_idname, text="GOH Animation (.anm)")


CLASSES = (
    GOHAddonPresetSettings,
    GOHBasisSettings,
    GOHToolSettings,
    EXPORT_SCENE_OT_goh_model,
    IMPORT_SCENE_OT_goh_model,
    IMPORT_SCENE_OT_goh_anm,
    OBJECT_OT_goh_apply_preset,
    SCENE_OT_goh_copy_basis_legacy,
    OBJECT_OT_goh_sync_basis_helper,
    OBJECT_OT_goh_apply_transform_block,
    OBJECT_OT_goh_weapon_tool,
    SCENE_OT_goh_report_textures,
    SCENE_OT_goh_autofill_materials,
    SCENE_OT_goh_validate_scene,
    OBJECT_OT_goh_assign_lod_files,
    OBJECT_OT_goh_create_auto_convex_volume,
    OBJECT_OT_goh_create_volume_from_bounds,
    OBJECT_OT_goh_create_recoil_action,
    OBJECT_OT_goh_assign_physics_link,
    OBJECT_OT_goh_bake_linked_recoil,
    OBJECT_OT_goh_bake_directional_recoil_set,
    OBJECT_OT_goh_create_fire_recoil_triggers,
    OBJECT_OT_goh_bake_impact_response,
    OBJECT_OT_goh_create_armor_ripple,
    OBJECT_OT_goh_load_physics_defaults,
    OBJECT_OT_goh_clear_physics_links,
    VIEW3D_PT_goh_basis,
    VIEW3D_PT_goh_tools,
    VIEW3D_PT_goh_presets,
    VIEW3D_PT_goh_export_help,
)


def _legacy_register() -> None:
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


def _legacy_unregister() -> None:
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


def register() -> None:
    from .registration import register as _register

    _register()


def unregister() -> None:
    from .registration import unregister as _unregister

    _unregister()
