# Official 3ds Max Plugin Compatibility Notes

These notes summarize non-invasive observations from the official GOH 3ds Max 2020 plugins shipped with the game tools:

- `GemExport64.dle`
  Best Way GEM Engine MDL exporter.
- `EclipseMtl64.dle`
  3ds Max material plugin for Eclipse/GEM materials.

No proprietary implementation was copied into this Blender addon. The comparison used file metadata, PE imports/exports, and readable diagnostic strings only.

## Confirmed Overlap

The Blender addon already covers these concepts exposed by the official exporter strings:

- `mdl`, `ply`, `mtl`, `vol`, and `anm` export/import workflows
- `EPLY`, `EVLM`, and `EANM` resource chunks
- `Poly`, `CommonMesh`, `Volume`, `Obstacle`, and `Area` legacy concepts
- `Orientation`, `Position`, and `Matrix34` transform blocks
- `LODView`, `{OFF}`, and `VolumeView` mesh references
- `NoGroupMesh`, `NoCastShadows`, `NoGetShadows`, `DecalTarget`, and `Ground` mesh-view flags
- `Box`, `Sphere`, `Cylinder`, and `Polyhedron` collision volume blocks
- `IKMin`, `IKMax`, `IKSpeed`, `IKSpeed2`, `Terminator`, `Tags`, and support-point style metadata
- material color, blend, alpha, mip-map, lightmap, bump/specular, envmap, and extended texture option handling

## Added After Comparison

- Legacy `AnimationAuto=...` lines are parsed as GOH sequence clips with `Autostart`.
- Legacy `LODLastOff` is recognized as an `OFF` LOD marker.
- Legacy mesh-view flags such as `NoGroupMesh`, `NoCastShadows`, `NoGetShadows`, `DecalTarget`, and `Ground` can be supplied through old Max-style text/custom properties.
- `goh_force_commonmesh` is accepted as a Blender alias for `goh_force_mesh_animation`.
- Mesh export now rejects skinned meshes with more than 255 skin bones before writing, matching the official exporter limit warning.
- Blender-only linked physics helpers, including `Antenna Whip`, bake ordinary GOH animation data while preserving legacy-style timeline clip ranges.
- GOH-native root `basis` mirror transforms are imported faithfully by default so Blender helper placement matches SOEdit/game space. The optional deferred display mode is still available for non-mirrored authoring, and ANM import/export both compensate rotation parity so pitch playback matches Blender.

## Still Intentionally Not Mirrored

The official plugin exposes strings related to 3ds Max-specific UI or scene objects that are not currently first-class Blender workflows:

- preview cameras and preview extenders
- point/spot/directional light blocks
- some land-patch / structure extenders
- old `NoSkin` / `OldSkin` material or mesh modes
- 3ds Max material parameter-block UI behavior

These can be added later as clean-room Blender features if a real GOH asset needs them.
