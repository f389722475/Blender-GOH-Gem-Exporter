# GOH Physics Bake Workflow

The physics bake tools create ordinary Blender keyframes.
They do not export a live physics simulation to GOH.

This is intentional: GOH animation resources are pre-baked, so the safest workflow is to simulate or approximate the physical response in Blender and export the resulting `Action` / `NLA` animation.

## Source-Only Recoil

Use `GOH Tools > Physics Bake Presets > Create Recoil Action` when only the selected part needs a recoil motion.

Typical use:

- select `Gun`
- choose `Recoil Axis`
- set `Distance` and `Frames`
- run `Create Recoil Action`

The operator writes a short recoil-return action on the selected object.

## Linked Recoil

Use linked recoil when one part should push other parts.

Example:

- `Gun` recoils backward
- `Body` reacts with a damped spring push
- `Antenna` reacts later with a higher-frequency whip
- external tools or loose props add small jitter

### Assign Links

1. Select the source object first, such as `Gun`.
2. Select one or more driven objects, such as `Body` or `Antenna`.
3. Make the source object active.
4. Pick a `Link Role`.
5. Run `Assign Physics Link`.

The addon stores:

- `goh_physics_source`
- `goh_physics_role`
- `goh_physics_weight`
- `goh_physics_delay`
- optional frequency, damping, jitter, and rotation fields

### Bake Linked Motion

1. Select or activate the source object.
2. Enable `Use Stored Links` if linked objects are not currently selected.
3. Run `Bake Linked Recoil`.

The operator writes ordinary keyframes into the active Blender action on the source and linked objects.
Each bake also records a clip range on that action, so one part can keep multiple baked clips, such as `fire` on frames `1-48` and `hit_body` on frames `49-96`, without the later bake replacing the earlier one.
This mirrors the 3ds Max workflow where dense timeline keys are sliced into GEM sequences by explicit frame ranges.

The readable object custom property is:

```text
goh_sequence_ranges = fire:1-48; hit_body:49-96
```

It does not replace `goh_sequence_name`.
Instead, it acts as a multi-sequence range table; `goh_sequence_name` remains the single-clip fallback when no range table exists.
Use `sequence->file:1-48` if the visible GEM sequence name and output `.anm` file stem need to differ.

## Directional Recoil Set

Use `Bake Directional Set` when one weapon needs several GOH clips.

Typical use:

- assign linked parts once
- set `Direction Set` to `Four Fire Directions`
- keep `Clip Prefix` as `fire`
- run `Bake Directional Set`

The addon writes timeline clip ranges such as `fire_front`, `fire_back`, `fire_left`, and `fire_right`.
The six-axis mode also adds `up` and `down` clips for special cases.

## Impact Response

Use `Bake Impact Response` for a hit or shell impact shake.
The selected objects receive a damped impulse along `Recoil Axis`, with the same weight, damping, jitter, and rotation controls used by linked recoil.

Use `Impact Clip` to name the exported sequence, such as `hit`, `hit_left`, or `armor_hit`.

## Armor Ripple

Use `Create Armor Ripple` on selected mesh objects when you want a small pre-baked surface deformation.

Workflow:

1. Put the 3D Cursor where the shell hit should happen.
2. Select one or more mesh objects.
3. Set `Impact Clip`, `Ripple Amplitude`, `Ripple Radius`, and `Ripple Waves`.
4. Run `Create Armor Ripple`.

The operator creates per-frame shape keys named `GOH_Ripple_*`, writes an action on the mesh shape-key datablock, and enables `goh_force_mesh_animation`.

For GOH compatibility, the exporter keeps mesh-animation vertices in a stable loop layout. This avoids frame-to-frame vertex-count changes when shape keys alter normals or tangents.

## Physics Power

`Physics Power` is a global intensity multiplier.
Use it when the curve feels correct but the whole effect is too weak or too strong.

Suggested ranges:

- `0.5-0.8`
  subtle editor-safe motion
- `1.0`
  default production motion
- `1.4-2.2`
  heavy cannon recoil, close camera shots, and more cinematic shake
- `2.5+`
  stylized exaggeration; check clipping and parent transforms carefully

## Duration Scale

`Duration Scale` is a global timing multiplier for linked physics and impact responses.
Each role has its own default duration, so this control stretches or compresses the final baked clip while preserving the preset personality.

Suggested ranges:

- `0.65-0.85`
  snappy light weapons, small accessories, or gameplay-readable short clips
- `1.0`
  default role timing
- `1.2-1.6`
  heavier gun recoil, visible hull recovery, and more antenna follow-through
- `1.8+`
  cinematic slow recovery; check that the exported sequence does not feel late in GOH

## Link Roles

- `Body Spring`
Heavy hull recoil with a hard initial shove, nose-up hull swing, and multiple damped pitch and side reversals, inspired by Sherman-style cannon recoil. Default tail: `1.65x`.
- `Antenna Whip`
Flexible tank-antenna whip with a fast source-driven kick and a longer smooth spring tail. Mesh antennas are baked as anchored shape-key mesh animation when possible, so the lower root segment remains fixed while the free tip bends and springs back. Sparse antenna meshes can be auto-subdivided along their length by `Antenna Bend Segments`; set it to `0` if you need to keep the mesh topology unchanged. The bend direction prefers the linked source mesh principal axis, so elongated cannon/barrel sources drive front-back sway along the gun and vehicle body instead of a side-axis artifact. The bend shape is solved as a principal-axis constrained spine using a minimum-bending-energy cubic beam profile, a first-mode cantilever blend, distance constraints, a light bending constraint, and tangent-rotated sections, so it forms one elastic arc like a real whip antenna instead of a snake-like S-curve or straight-line tip interpolation. The time response uses a soft-limited muzzle impulse on the source recoil timing, a low-pass filtered tip target, a separate low-amplitude late rebound mode, and a long quintic end fade so late frames keep small over-zero spring motion before easing back to rest. `Antenna Root Anchor` can be negative to place the virtual bend root below the visible mesh bottom while keeping the lowest vertices pinned. Default tail: `2.15x`.
- `Accessory Jitter`
  Loose external equipment with fast rattle, asymmetric side shake, and noisy secondary vibration. Default tail: `0.70x`.
- `Follower`
  Generic mild follow-through for linked pieces that should move but not dominate the shot. Default tail: `1.00x`.
- `Suspension Bounce`
  Vehicle movement bounce with vertical travel, pitch, compression, rebound, and a longer soft recovery. Default tail: `1.90x`.
- `Track Rumble`
  Tracks, wheels, and bogies with fast low-amplitude vibration and chatter. Default tail: `0.58x`.

Internally, these roles use damped oscillator responses, pendulum-style underdamped swings, quintic smoothing, modal blends, and a forced end fade rather than a single shared curve.
That makes the role names meaningful: a hull kick, antenna whip, and track rumble should look different even with the same source recoil.

## Math Notes

The current bake system is intentionally a low-order, art-directable approximation.
It borrows ideas from real-time physically based animation without running a heavy solver inside Blender:

- `PBD / XPBD`
  Constraint-style thinking is useful for stable secondary motion and future part-link constraints. See Muller et al., [Position Based Dynamics](https://matthias-research.github.io/pages/publications/posBasedDyn.pdf), and Macklin et al., [XPBD](https://mmacklin.com/xpbd.pdf).
- `Projective Dynamics`
  The local/global projection idea is a good future path for more robust multi-part link networks. See Bouaziz et al., [Projective Dynamics](https://www.projectivedynamics.org/Projective_Dynamics/index.html).
- `Reduced / modal dynamics`
  Low-dimensional modal responses match this addon's goal: convincing deformation and secondary motion without full FEM cost. See Barbič and James, [Real-Time Subspace Integration](https://graphics.cs.cmu.edu/projects/stvk/).
- `Minimum bending-energy beam curve`
  `Antenna Whip` uses a cubic free-tip beam profile, `0.5 * u^2 * (3 - u)`, blended with the first cantilever mode. This keeps the root clamped, lets the tip bend freely, and avoids high-order oscillation artifacts while still reading like a flexible tank antenna.

## Export Notes

- The baked motion is exported through the active `Action` timeline and recorded clip ranges, with NLA still supported for manual advanced workflows.
- Generated GOH physics actions under a legacy mirrored imported `basis` are mirror-corrected at ANM export time. The source recoil object is left unchanged, and ordinary hand-keyed actions are not flipped just because an object has link-role metadata.
- For new GOH-native imports, keep `Defer Basis Flip` enabled when you need Blender to match SOEdit/game helper placement while preserving the mirrored source basis for export. Disable it only when you intentionally need to inspect the raw mirrored file-space parent; ANM import and export both apply the matching basis handedness compensation in the default display mode.
- Mesh ripple is exported through the existing mesh-animation path.
- For GOH use, keep the motion short and readable.
- If one animation must cover many fire directions, create separate directional clips such as `fire_front`, `fire_left`, `fire_right`, or bake each turret direction separately.
- `Assign Physics Link` writes role defaults automatically when the UI fields are still at generic values, so a role behaves like a real preset immediately.
- `Clear Physics Links` removes stored physics links, and can also detach generated GOH physics actions or clip-range metadata when `Clear Baked Actions` is enabled.
