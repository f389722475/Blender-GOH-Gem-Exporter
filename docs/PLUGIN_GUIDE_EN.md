# GOH Blender Plugin Guide

This guide explains how to set up a Gates of Hell vehicle in Blender with the addon, especially the body, turret, gun, and tracks.

The short version: a GOH vehicle is not only a mesh. It is a named transform hierarchy. In Blender, that means every important moving part needs a correct object name, parent, pivot/origin, and GOH custom properties.

## 1. Mental Model

GOH `.mdl` files store a tree of named parts. Each part has:

- a transform
- optional mesh files such as `.ply`
- optional collision volumes
- optional animation clips
- optional helpers such as crew positions, muzzle points, shell points, or obstacle/area shapes

In this addon, you usually build that tree with ordinary Blender objects. You do not need a Blender Armature for a normal tank unless you are making skinned meshes. For vehicles, the usual workflow is:

- `Body` is the main chassis object.
- `Turret` is parented to `Body`.
- `Gun`, `Gun_rot`, or the mantlet is parented to `Turret`.
- Barrel, muzzle helpers, shell helpers, and sights are parented to the gun assembly.
- Tracks, wheels, bogies, suspension helpers, and track collision volumes are parented to `Body`.

The object's origin is the pivot. This is the most important rigging rule.

If a turret rotates around the wrong point, move the turret object's origin. If a gun elevates around the wrong point, move the gun or `Gun_rot` origin to the trunnion/elevation pivot.

## 2. Recommended Starting Workflow

Use an official model as a reference whenever possible.

1. Open Blender.
2. Use `GOH Export > Import GOH Model`.
3. Import an official vehicle close to your target.
4. Keep these import options for normal editing:
   - `Axis Conversion = None / GOH Native`
   - `Scale Factor = 20`
   - `Defer Basis Flip = On`
   - `Import Volumes = On`
   - `LOD0 Only = On` for quick study
5. Study the hierarchy in the Outliner.
6. Look for names like `body`, `root`, `turret`, `gun`, `gun_rot`, `track_l`, `track_r`, `wheel`, and objects ending in `_vol`.

Do not copy official game data blindly. Use it as a layout reference: parent order, pivots, helper names, and collision volume style.

## 3. Scene Setup

### Basis

Open `View3D > Sidebar > GOH > GOH Basis`.

Enable Basis metadata and fill:

- `Vehicle Name`
- `Type`
- `Entity Path`
- `Wheelradius`
- `SteerMax`

Then run:

- `Copy Legacy Text` if you need old Max-style text.
- `Sync Basis Helper` to create/update the hidden `Basis` object.

The `Basis` helper stores model-level metadata. Keep it at the scene origin with identity transform.

### Scale And Transforms

Recommended export settings:

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`

Before final export:

- Apply mesh scale on visual mesh objects when possible.
- Avoid negative object scale.
- Keep pivots/origins meaningful.
- Validate the scene before export.

## 4. Object Hierarchy

A simple tank hierarchy can look like this:

```text
Basis
Body
  TrackL
  TrackR
  WheelL_01
  WheelR_01
  Turret
    Mantled
    Gun_rot
      Gun
        Foresight3
        FxShell
```

Another common imported GOH hierarchy may use names like:

```text
vehicle#x_root_101
  vehicle#bone_turret_58
    vehicle#bone_gun_66
      vehicle#bone_gun_barrel_67
```

Both are acceptable if the exporter properties are correct. The visible Blender object name can be different from the exported GOH bone name; the important property is `goh_bone_name`.

## 5. Using GOH Presets

Open `View3D > Sidebar > GOH > GOH Presets`.

Important options:

- `Template Family`
  Use `Tank` for normal tracked vehicles.
- `Role`
  Choose what kind of object you are marking:
  - `visual`
  - `volume`
  - `attachment`
  - `obstacle`
  - `area`
- `Part`
  Choose the part type, such as `Body`, `Turret`, `Gun`, `TrackL`, `TrackR`, `Foresight3`, or `FxShell`.
- `Rename Objects`
  Renames selected Blender objects to the preset name.
- `Write Export Names`
  Writes GOH custom properties such as `goh_bone_name`.
- `Auto Number`
  Useful for repeated helpers such as seats, emit points, wheels, or effects.
- `Helper Collections`
  Moves helper objects into organized GOH collections.

Typical use:

1. Select your hull mesh.
2. Set `Role = visual`.
3. Set `Part = Body`.
4. Enable `Write Export Names`.
5. Run `Apply GOH Preset`.

Repeat for turret, gun, tracks, wheels, volumes, and helpers.

## 6. Body Setup

The body is the main vehicle root.

Recommended setup:

- Name or export name: `body` or a vehicle-specific root name.
- Parent: usually none, or parented under `Basis` only if you intentionally use that layout.
- Origin: near the vehicle center or original imported root pivot.
- Mesh role: `visual`.
- Part preset: `Body`.

The body should contain:

- hull mesh
- track meshes
- wheel meshes
- turret object as child
- collision volumes bound to `body`
- obstacle/selection helpers
- area helpers if needed

For a normal tank, keep the body stable. The turret and gun should move relative to it.

## 7. Turret Setup

The turret needs a correct yaw pivot.

Recommended setup:

- Parent: `Body`
- Origin: exact turret rotation center
- Local rotation: clean and predictable
- Preset role: `visual`
- Part: `Turret`
- `goh_bone_name`: usually `turret`

Steps:

1. Select the turret mesh.
2. Move the object origin to the turret ring center.
3. Parent it to the body while keeping transform.
4. Apply `GOH Presets > visual > Turret`.
5. Parent turret-mounted parts to the turret:
   - mantlet
   - gun pivot
   - gun barrel
   - coaxial MG
   - turret hatches
   - commander/gunner helpers
   - turret collision volume

Animation test:

1. Insert a keyframe on the turret rotation at frame 1.
2. Rotate the turret around its local vertical/yaw axis.
3. Insert another keyframe.
4. Scrub the timeline.

If the turret orbits around the vehicle instead of spinning in place, the origin is wrong.

## 8. Gun And Barrel Setup

The gun assembly usually has two motions:

- elevation around a trunnion/pitch pivot
- recoil along the barrel axis

A clean hierarchy is:

```text
Turret
  Gun_rot
    Gun
      Gun_barrel
      Foresight3
      FxShell
```

You can also use:

```text
Turret
  Mantled
    Gun
      Gun_barrel
```

Recommended setup:

- `Gun_rot` or `Mantled` origin: elevation pivot/trunnion.
- `Gun` or barrel origin: can stay at the same pivot or at its own mesh center if recoil is baked on the barrel object.
- Parent all muzzle and shell helpers to the recoiling object if they should move with recoil.
- Parent fixed mantlet armor to the elevation pivot if it elevates with the gun.

Presets:

- Main cannon mesh: `visual > Gun`
- Gun rotation pivot: `visual > Gun_rot`
- MG mesh: `visual > Mgun`
- MG pivot: `visual > Mgun_rot`
- Mantlet: `visual > Mantled`
- Muzzle/sight helper: `attachment > Foresight3`
- Shell ejection helper: `attachment > FxShell`
- Handle helper: `attachment > Handle`

Weapon helper buttons:

- `CommonMesh`
  Marks selected mesh for mesh-animation sampling.
- `Poly`
  Marks selected mesh as a legacy visual poly part.
- `Foresight3`
  Marks a point helper for muzzle/sight reference.
- `FxShell`
  Marks a shell/ejection helper.
- `Handle`
  Marks a handle helper.

## 9. Gun Recoil

Use `GOH Tools > Physics Bake Presets`.

For a simple recoil:

1. Select the gun or barrel object.
2. Set `Recoil Axis`.
3. Use the axis that moves the object backward in Blender.
   - `Local -Y` is a common starting point.
   - If the barrel moves forward, choose the opposite axis.
4. Set `Distance`.
5. Set `Frames`.
6. Enable `Write Sequence`.
7. Set `Clip Prefix`, usually `fire`.
8. Run `Create Recoil Action`.

For linked recoil:

1. Select the source gun first.
2. Select body, antenna, suspension, track, or accessories.
3. Make the gun active.
4. Choose a `Link Role`.
5. Run `Assign Physics Link`.
6. Run `Bake Linked Recoil`.

Useful link roles:

- `Body Spring`
  Heavy hull reaction to cannon fire.
- `Antenna Whip`
  Flexible antenna follow-through.
- `Accessory Jitter`
  Loose gear and stowage shake.
- `Suspension Bounce`
  Heavy vehicle bounce.
- `Track Rumble`
  Fast low-amplitude track/wheel chatter.

## 10. Tracks And Wheels

Tracks usually need three kinds of setup:

- visual mesh
- wheel/suspension helper hierarchy
- collision and obstacle helpers

### Visual Tracks

Recommended setup:

- Left track mesh:
  - preset `visual > TrackL` or `visual > Track`
  - parent to `Body`
- Right track mesh:
  - preset `visual > TrackR` or `visual > Track`
  - parent to `Body`

If the track mesh uses shape keys or frame-by-frame mesh deformation, mark it as mesh animation:

- use `GOH Presets` with mesh animation mode set to `Force`, or
- use the `CommonMesh` weapon helper button if that matches your legacy workflow.

Many GOH track motions are controlled by vehicle/entity configuration outside Blender. This addon exports geometry, hierarchy, helpers, and baked animation data; it does not replace all game-side vehicle track simulation.

### Wheels And Suspension

Useful visual/attachment part presets:

- `Wheel`
- `Wheell`
- `Wheelr`
- `TrackL`
- `TrackR`
- `SteerL`
- `SteerR`
- `SpringL`
- `SpringR`
- `WheelsL`
- `WheelsR`
- `WheelSL`
- `WheelSR`

Basic advice:

- Parent wheel meshes to `Body` unless they have a dedicated suspension parent.
- Place wheel origins at wheel centers.
- Keep left/right naming consistent.
- Use official imported vehicles as reference for dummy helper placement.

### Track Collision

For collision:

- Use volume presets `TrackL` and `TrackR`, or
- select the track mesh and run `Auto Collision Cage Volume`.

Suggested cage settings:

- `Face Budget = 200-500`
- `Optimize Iterations = 8-16`
- `Cage Template = Auto` or `Rounded Box`
- `Output Topology = Tri / Quad Legal`
- `Clear Previous = On`

For long track runs, a simple box-like or rounded box collision is often better than a very detailed cage. Collision should be stable and readable, not visually perfect.

## 11. Collision Volumes

GOH collision helpers are usually mesh objects ending in `_vol` or objects with GOH volume properties.

Important properties:

- `goh_is_volume = True`
- `goh_volume_name`
- `goh_volume_bone`
- `goh_volume_kind`

Common volume kinds:

- `polyhedron`
- `box`
- `sphere`
- `cylinder`

### Auto Collision Cage Volume

Open `GOH Tools > Collision Helpers`.

Recommended starting values:

- `Cage Template = Auto`
- `Fit Mode = OBB Only`
- `Cage Source = Selected` for focused work
- `Cage Source = Selected + Children` for root-object workflows
- `Output Topology = Tri / Quad Legal`
- `Face Budget = 500`
- `Optimize Iterations = 8-16`
- `Offset = 0.005`
- `Use Modifiers = On`
- `Clear Previous = On`

For detailed single parts:

- raise `Face Budget` up to `1000-5000`
- raise `Optimize Iterations` to `20-40`

For whole vehicles:

- keep `Optimize Iterations` lower
- select fewer source objects when possible
- split major parts manually: body, turret, gun, tracks

## 12. LOD Setup

Use `GOH Tools > LOD Helpers`.

Typical workflow:

1. Select visual mesh objects.
2. Set `LOD Levels`.
3. Enable `Write OFF` if the last LOD should disappear.
4. Run `Assign LOD Files`.

The addon writes `goh_lod_files` such as:

```text
body.ply;body_lod1.ply
```

Keep LOD names predictable and check the exported manifest.

## 13. Animation Clips And Sequences

The addon exports animation from Blender actions and stored clip ranges.

Useful properties:

- `goh_sequence_name`
- `goh_sequence_file`
- `goh_sequence_ranges`

Simple case:

```text
goh_sequence_name = fire
goh_sequence_file = fire
```

Multi-clip case:

```text
goh_sequence_ranges = fire:1-48; hit_body:49-96
```

Use separate short clips for:

- `fire`
- `fire_front`
- `fire_back`
- `fire_left`
- `fire_right`
- `hit`
- `open`
- `close`

## 14. Export

Before export:

1. Run `Validate GOH Scene`.
2. Fix errors first.
3. Review warnings.
4. Save the `.blend`.
5. Open `GOH Export`.
6. Export `.mdl`.

Recommended export settings:

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`

After export, inspect:

- `.mdl`
- `.ply`
- `.vol`
- `.anm`
- `GOH_Export_Manifest.json`
- `GOH_Validation_Report.txt`

## 15. Troubleshooting

### Turret rotates around the wrong point

Fix the turret object origin. The origin must be at the turret ring/yaw pivot.

### Gun elevates from the wrong point

Fix the `Gun_rot`, mantlet, or gun object origin. The pivot must be at the trunnion.

### Gun recoil moves forward

Change `Recoil Axis` to the opposite local axis.

### Muzzle helper does not follow the barrel

Parent `Foresight3`, muzzle, or `FxShell` to the recoiling gun/barrel object.

### Tracks export but do not animate in game

Check whether the movement is expected to come from game-side vehicle configuration. The addon exports meshes, helpers, and baked animation; it does not automatically create all runtime vehicle simulation logic.

### Collision cage is too heavy

Lower:

- `Face Budget`
- `Optimize Iterations`
- number of selected source objects

### Collision cage is too large

Use:

- `Cage Source = Selected`
- select the body or turret only
- `Cage Template = Rounded Box`
- `Optimize Iterations = 8-16`
- smaller `Offset`

### Exported animation direction is mirrored

For imported GOH-native models, keep `Defer Basis Flip = On`. This keeps Blender editing direction aligned with SOEdit/game export conversion.

## 16. Practical Checklist

Before exporting a vehicle, check:

- Body has correct export name.
- Turret is parented to body.
- Turret origin is at yaw pivot.
- Gun elevation pivot is correct.
- Barrel and muzzle helpers are parented to the gun assembly.
- Tracks and wheels are parented to body or correct suspension parents.
- Collision volumes are bound to the correct `goh_volume_bone`.
- `_vol` helpers are not accidentally selected as visual meshes.
- LOD file lists are assigned.
- Materials have GOH texture fields.
- Basis helper is synced.
- Validation report has no errors.

