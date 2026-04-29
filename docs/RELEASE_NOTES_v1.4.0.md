# Blender GOH GEM Exporter v1.4.0

This medium release upgrades linked physics baking with a PhysX-inspired inertial solver and targeted recoil-response tuning for heavy vehicle body motion and flexible antenna deformation.

## Highlights

- Added a solver-space inertial bake core with source-motion acceleration sampling, mass/inertia-aware semi-implicit integration, D6-lite axis limits, force clamps, substeps, and end fade.
- Added `Solver Space`, `Substeps`, `Force Limit`, and `End Fade` controls to linked physics bake settings, plus matching custom properties on stored links.
- Migrated rigid linked recoil roles to the new inertial solver while preserving the established Antenna Whip beam and late-rebound mesh bake path.
- Body Spring now has a smoother crank-style pitch response: lift, rear/down dip, and subtle recovery rebounds after firing.
- Antenna Whip free-tip motion now lags opposite the anchored recoil/root motion while keeping the user-approved rebound shape.

## Validation

- Saved `tests/2.blend` inertial physics regression for 5 iterations.
- Inertia solver math regression for 5 iterations.
- Blender background runtime regression.
- M60A1 ANM import/material/animation regression.
- Random vehicle import regression over 12 samples for 5 iterations.
- Python compile and addon smoke tests.

## Release Assets

- `blender_goh_gem_exporter-1.4.0.zip`
  Blender addon install package.
- `blender_goh_gem_exporter-1.4.0-full.zip`
  Protected source, docs, tests, and regression snapshot for release review.
