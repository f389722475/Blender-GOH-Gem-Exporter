# Blender GOH GEM Exporter v1.3.1

This maintenance release tightens GOH-native import parity after broader 1.3.0 modularization.

## Fixes

- GOH material import now reflects the GEM material model more directly: diffuse, normal, and specular textures are wired for Blender preview, metallic is forced off, and AO is no longer treated as a separate engine channel.
- ANM import now preserves the handedness of the already-imported MDL rest hierarchy when animation matrices arrive with the opposite basis sign. This keeps Blender playback aligned with SOEdit and in-game orientation for mirrored GOH basis chains.

## Validation

- Blender background M60A1 model and animation regression using the WTREBUILD `m60a1` sample.
- Random vehicle import regression over 12 vehicle samples for 10 iterations.
- Python compile and addon smoke tests.

## Release Assets

- `blender_goh_gem_exporter-1.3.1.zip`
  Blender addon install package.
- `blender_goh_gem_exporter-1.3.1-full.zip`
  Protected source, docs, tests, and regression snapshot for release review.
