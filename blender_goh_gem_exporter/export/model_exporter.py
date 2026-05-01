from __future__ import annotations

from mathutils import Quaternion

from .. import blender_exporter as _legacy

for _name, _value in _legacy.__dict__.items():
    if _name not in globals():
        globals()[_name] = _value


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
        self.material_file_names: dict[str, tuple[str, int]] = {}
        self.file_name_counts: dict[str, int] = {}
        self.bone_file_names: dict[str, str] = {}
        self.volume_file_names: dict[str, str] = {}
        self.legacy_cache: dict[int, tuple[set[str], dict[str, list[str]]]] = {}
        self.armature_obj: bpy.types.Object | None = None
        self.armature_bone_order: list[str] = []
        self.mesh_groups: dict[MeshGroupKey, list[AttachmentObject]] = {}
        self.group_representatives: dict[MeshGroupKey, bpy.types.Object] = {}
        self.animation_attachments: dict[str, list[AttachmentObject]] = {}

    def _refresh_depsgraph(self) -> bpy.types.Depsgraph:
        self.context.view_layer.update()
        self.depsgraph = self.context.evaluated_depsgraph_get()
        return self.depsgraph

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
        written = write_export_bundle(self.output_path.parent, bundle)
        self._write_export_manifest(bundle, written)
        return bundle, self.warnings

    def _write_export_manifest(self, bundle: ExportBundle, written: dict[str, Path]) -> None:
        output_dir = self.output_path.parent
        files: list[dict[str, object]] = []
        for path in sorted({Path(value) for value in written.values()}, key=lambda item: str(item).lower()):
            if not path.exists() or not path.is_file():
                continue
            try:
                relative_path = path.relative_to(output_dir)
            except ValueError:
                relative_path = path
            files.append(
                {
                    "path": str(relative_path).replace("\\", "/"),
                    "size": path.stat().st_size,
                    "sha256": self._file_sha256(path),
                }
            )

        payload = {
            "name": "Blender GOH GEM Exporter Manifest",
            "addon_version": GOH_ADDON_VERSION,
            "blender_version": bpy.app.version_string,
            "model": bundle.model.file_name,
            "counts": {
                "meshes": len(bundle.meshes),
                "materials": len(bundle.materials),
                "volumes": len(bundle.model.volumes),
                "obstacles": len(bundle.model.obstacles),
                "areas": len(bundle.model.areas),
                "animations": len(bundle.animations),
            },
            "settings": {
                "axis_mode": self.operator.axis_mode,
                "scale_factor": float(self.scale_factor),
                "flip_v": bool(self.operator.flip_v),
                "material_blend": str(getattr(self.operator, "material_blend", "none") or "none"),
                "export_animations": bool(self.operator.export_animations),
            },
            "warnings": list(self.warnings),
            "files": files,
        }
        manifest_path = output_dir / "GOH_Export_Manifest.json"
        temp_path = manifest_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp_path.replace(manifest_path)

    def _file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fp:
            for chunk in iter(lambda: fp.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _collect_scope_objects(
        self,
    ) -> tuple[set[bpy.types.Object], list[bpy.types.Object], list[bpy.types.Object], list[bpy.types.Object]]:
        scope: set[bpy.types.Object] = set()
        if self.operator.selection_only:
            for obj in self.context.selected_objects:
                scope.update(self._iter_descendants(obj))
        else:
            scope = set(self.context.scene.objects)

        exportable_types = {"MESH", "EMPTY", "ARMATURE"}
        scope = {obj for obj in scope if obj.type in exportable_types}

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
                parent_matrix=self._root_parent_matrix_for_object(root, visual_objects),
                visual_scope=visual_objects,
                attachments=attachments,
                bone_name_map=bone_name_map,
            )
            basis_node.children.append(child_node)

        self.armature_bone_order = self._object_bone_order_for_weights(visual_objects, bone_name_map)
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

        bone_names = self._animation_export_bone_names(bundle.model.basis)
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
                if not frames:
                    continue
                if self._should_export_mesh_animation_frames():
                    mesh_frames = self._sample_mesh_animation_frames(clip, bundle.meshes, bundle.materials)
                else:
                    mesh_frames = [{} for _ in frames]
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

    def _should_export_mesh_animation_frames(self) -> bool:
        return str(self.operator.anm_format or "").strip().upper() == "FRM2"

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
        segment_specs: dict[tuple[str, int, int], AnimationClipSpec] = {}
        start_frame: int | None = None
        end_frame: int | None = None
        names: list[str] = []
        for owner in owners:
            animation_data = getattr(owner, "animation_data", None)
            action = getattr(animation_data, "action", None) if animation_data else None
            if action is None:
                continue
            for segment in _physics_object_sequence_ranges(owner, action) if isinstance(owner, bpy.types.Object) else _physics_load_action_segments(action):
                clip = self._clip_spec_from_action_segment(segment, action, owner)
                key = (
                    sanitized_file_stem(clip.file_stem or clip.name).lower(),
                    clip.frame_start,
                    clip.frame_end,
                )
                if key in segment_specs:
                    segment_specs[key] = self._merge_clip_specs(segment_specs[key], clip)
                else:
                    segment_specs[key] = clip
            clip_start, clip_end = self._action_frame_range(action)
            start_frame = clip_start if start_frame is None else min(start_frame, clip_start)
            end_frame = clip_end if end_frame is None else max(end_frame, clip_end)
            action_sources.append((owner, action))
            if action.name not in names:
                names.append(action.name)

        if segment_specs:
            for clip in legacy_specs:
                key = (
                    sanitized_file_stem(clip.file_stem or clip.name).lower(),
                    clip.frame_start,
                    clip.frame_end,
                )
                if key in segment_specs:
                    segment_specs[key] = self._merge_clip_specs(segment_specs[key], clip)
                else:
                    segment_specs[key] = clip
            return sorted(segment_specs.values(), key=lambda clip: (clip.frame_start, clip.frame_end, clip.name.lower()))

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
            helper_lines: list[str] = []
            for legacy_key in ("animation", "animationresume", "animationauto"):
                helper_lines.extend(f"{legacy_key}={value}" for value in values.get(legacy_key, []))
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
            elif lower_text.startswith("animationauto="):
                key = "animationauto"
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
                    autostart=key == "animationauto",
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

    def _clip_spec_from_action_segment(
        self,
        segment: dict[str, object],
        action: bpy.types.Action,
        owner,
    ) -> AnimationClipSpec:
        sources = [action, owner, self.context.scene]
        name = sanitized_file_stem(str(segment.get("name") or "").strip()) or action.name or self.model_name
        file_stem = sanitized_file_stem(str(segment.get("file_stem") or name).strip()) or name
        start_frame = int(segment.get("frame_start", 0))
        end_frame = int(segment.get("frame_end", start_frame))
        speed = self._first_custom_float(sources, "goh_sequence_speed")
        smooth = self._first_custom_float(sources, "goh_sequence_smooth")
        return AnimationClipSpec(
            name=name,
            frame_start=min(start_frame, end_frame),
            frame_end=max(start_frame, end_frame),
            file_stem=file_stem,
            speed=1.0 if speed is None else speed,
            smooth=0.0 if smooth is None else smooth,
            resume=self._any_custom_bool(sources, "goh_sequence_resume"),
            autostart=self._any_custom_bool(sources, "goh_sequence_autostart"),
            store=self._any_custom_bool(sources, "goh_sequence_store"),
        )

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

    def _animation_export_bone_names(self, basis: BoneNode) -> list[str]:
        names = self._animation_bone_names(basis)
        if self.armature_obj is None:
            # Official object-mode ANM clips leave the static GOH basis/root
            # transform in the MDL and only key the driven child bones.
            names = [name for name in names if name != self.basis_name]
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
            self._refresh_depsgraph()
            if self.armature_obj is not None:
                frame_states.append(self._sample_armature_frame_state(bone_names))
            else:
                assert object_map is not None
                frame_states.append(self._sample_object_frame_state(bone_names, object_map, visual_objects, clip))
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
            self._refresh_depsgraph()
            frame_states: dict[str, MeshAnimationState] = {}
            for bone_name, (attachments, base_mesh, _base_blob, base_stride) in candidates.items():
                animated_mesh = self._build_mesh_data(base_mesh.file_name, attachments, use_evaluated_mesh=True)
                if animated_mesh is None:
                    continue
                blob, stride = encode_mesh_vertex_stream(animated_mesh, materials)
                if stride != base_stride or len(animated_mesh.vertices) != len(base_mesh.vertices):
                    raise ExportError(
                        f'Mesh animation on "{bone_name}" changes vertex layout. '
                        f"Base has {len(base_mesh.vertices)} vertices/stride {base_stride}; "
                        f"frame {frame} has {len(animated_mesh.vertices)} vertices/stride {stride}. "
                        "GOH mesh animation requires a stable vertex count and stride."
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
        clip: AnimationClipSpec | None = None,
    ) -> dict[str, AnimationState]:
        frame_state: dict[str, AnimationState] = {}
        for bone_name in bone_names:
            if bone_name == self.basis_name:
                continue
            obj = object_map.get(bone_name)
            if obj is None:
                raise ExportError(f'Animation export could not find object for GOH bone "{bone_name}".')
            parent_matrix = Matrix.Identity(4)
            if obj.parent in visual_objects and not self._is_volume_object(obj.parent):
                parent_matrix = obj.parent.matrix_world
            elif obj.parent is not None and self._is_basis_helper_object(obj.parent):
                parent_matrix = obj.parent.matrix_world
            local_matrix = parent_matrix.inverted_safe() @ obj.matrix_world
            local_matrix = self._object_animation_export_matrix(obj, local_matrix, clip)
            loc, rot, _scale = local_matrix.decompose()
            frame_state[bone_name] = AnimationState(
                matrix=self._matrix_rows(loc, rot.to_matrix()),
                visible=1 if self._is_object_visible(obj) else 0,
            )
        return frame_state

    def _object_animation_export_matrix(
        self,
        obj: bpy.types.Object,
        local_matrix: Matrix,
        clip: AnimationClipSpec | None = None,
    ) -> Matrix:
        loc_rot_matrix = self._loc_rot_matrix(local_matrix)
        rest_matrix = self._stored_rest_local_matrix(obj)
        if not self._should_export_mesh_animation_frames():
            loc_rot_matrix = self._mesh_animation_rigid_fallback_matrix(obj, loc_rot_matrix)
        loc_rot_matrix = self._physics_link_animation_export_matrix(obj, loc_rot_matrix, rest_matrix, clip)
        if rest_matrix is not None:
            correction = self._mirrored_basis_animation_correction_matrix(obj)
            if correction is not None:
                return self._correct_deferred_basis_animation_delta(rest_matrix, loc_rot_matrix, correction)
        return loc_rot_matrix

    def _physics_link_animation_export_matrix(
        self,
        obj: bpy.types.Object,
        loc_rot_matrix: Matrix,
        rest_matrix: Matrix | None = None,
        clip: AnimationClipSpec | None = None,
    ) -> Matrix:
        role = str(obj.get("goh_physics_role") or "").strip().upper()
        generated_physics = self._is_generated_physics_animation(obj, clip)
        if role == "SOURCE" or self._is_generated_source_physics_animation(obj, clip):
            return loc_rot_matrix
        if not role and not generated_physics:
            return loc_rot_matrix
        if not generated_physics:
            return loc_rot_matrix
        if rest_matrix is None:
            return loc_rot_matrix
        correction = self._physics_link_animation_correction_matrix(obj, rest_matrix)
        if correction is None:
            return loc_rot_matrix
        return self._correct_animation_delta(rest_matrix, loc_rot_matrix, correction)

    def _correct_animation_delta(self, rest_matrix: Matrix, loc_rot_matrix: Matrix, correction: Matrix) -> Matrix:
        rest_loc_rot = self._loc_rot_matrix(rest_matrix)
        delta = rest_loc_rot.inverted_safe() @ loc_rot_matrix
        corrected_delta = correction @ delta @ correction.inverted_safe()
        return rest_loc_rot @ corrected_delta

    def _correct_deferred_basis_animation_delta(
        self,
        rest_matrix: Matrix,
        loc_rot_matrix: Matrix,
        correction: Matrix,
    ) -> Matrix:
        rest_loc_rot = self._loc_rot_matrix(rest_matrix)
        delta = rest_loc_rot.inverted_safe() @ loc_rot_matrix
        delta_loc, delta_rot, _delta_scale = delta.decompose()
        correction3 = correction.to_3x3()
        corrected_loc = correction3 @ delta_loc
        delta_rot_matrix = delta_rot.to_matrix().to_4x4()
        corrected_rot_matrix = correction @ delta_rot_matrix.inverted_safe() @ correction.inverted_safe()
        return rest_loc_rot @ Matrix.Translation(corrected_loc) @ corrected_rot_matrix

    def _deferred_basis_animation_correction_matrix(self, obj: bpy.types.Object) -> Matrix | None:
        basis = self._basis_helper_ancestor(obj)
        if basis is None or not basis.get("goh_deferred_basis_flip"):
            return None
        basis_rest = self._stored_rest_local_matrix(basis)
        if basis_rest is None or not self._matrix_is_mirrored(basis_rest):
            return None
        return self._basis_rotation_matrix().to_4x4()

    def _mirrored_basis_animation_correction_matrix(self, obj: bpy.types.Object) -> Matrix | None:
        correction = self._deferred_basis_animation_correction_matrix(obj)
        if correction is not None:
            return correction
        basis = self._basis_helper_ancestor(obj)
        if basis is None or not self._basis_helper_displays_mirrored_space(basis):
            return None
        return self._basis_rotation_matrix().to_4x4()

    def _physics_link_animation_correction_matrix(self, obj: bpy.types.Object, rest_matrix: Matrix) -> Matrix | None:
        correction = Matrix.Identity(4)
        corrected = False
        basis = self._basis_helper_ancestor(obj)
        if basis is not None and self._basis_helper_displays_mirrored_space(basis):
            correction = self._basis_rotation_matrix().to_4x4() @ correction
            corrected = True
        local_reflection = self._local_rest_reflection_matrix(rest_matrix)
        if local_reflection is not None:
            correction = correction @ local_reflection
            corrected = True
        return correction if corrected else None

    def _mesh_animation_rigid_fallback_matrix(self, obj: bpy.types.Object, loc_rot_matrix: Matrix) -> Matrix:
        if obj.type != "MESH":
            return loc_rot_matrix
        if not self._has_generated_antenna_whip_keys(obj):
            return loc_rot_matrix
        shape_keys = getattr(obj.data, "shape_keys", None)
        if shape_keys is None or len(shape_keys.key_blocks) < 2:
            return loc_rot_matrix
        if not any(key.name.startswith(GOH_ANTENNA_SHAPE_KEY_PREFIX) for key in shape_keys.key_blocks[1:]):
            return loc_rot_matrix

        basis_key = shape_keys.key_blocks.get("Basis") or shape_keys.key_blocks[0]
        base_positions = [point.co.copy() for point in basis_key.data]
        anchor_data = _physics_antenna_anchor_axis(obj.data)
        if anchor_data is None:
            return loc_rot_matrix
        anchor_axis, min_anchor, max_anchor = anchor_data
        root_indices, tip_indices = self._antenna_end_indices(base_positions, anchor_axis, min_anchor, max_anchor)
        if not root_indices or not tip_indices:
            return loc_rot_matrix

        active_mesh = self._active_antenna_shape_key_mesh(obj)
        if active_mesh is not None:
            try:
                evaluated_positions = [vertex.co.copy() for vertex in active_mesh.vertices]
            finally:
                bpy.data.meshes.remove(active_mesh)
        else:
            evaluated_positions = self._evaluated_mesh_positions(obj)
        if evaluated_positions is None or len(evaluated_positions) != len(base_positions):
            return loc_rot_matrix

        rest_root = self._average_indexed_vectors(base_positions, root_indices)
        rest_tip = self._average_indexed_vectors(base_positions, tip_indices)
        eval_root = self._average_indexed_vectors(evaluated_positions, root_indices)
        eval_tip = self._average_indexed_vectors(evaluated_positions, tip_indices)
        rest_direction = rest_tip - rest_root
        eval_direction = eval_tip - eval_root
        if rest_direction.length <= EPSILON or eval_direction.length <= EPSILON:
            return loc_rot_matrix

        rotation_delta = rest_direction.normalized().rotation_difference(eval_direction.normalized())
        if abs(rotation_delta.angle) <= 1e-5:
            return loc_rot_matrix

        max_degrees = max(1.0, min(35.0, float(obj.get("goh_physics_rotation", 28.0)) * 1.25))
        max_angle = math.radians(max_degrees)
        if rotation_delta.angle > max_angle:
            rotation_delta = Quaternion(rotation_delta.axis, max_angle)

        loc, rot, _scale = loc_rot_matrix.decompose()
        root_pivot = rest_root.copy()
        return (
            Matrix.Translation(loc)
            @ rot.to_matrix().to_4x4()
            @ Matrix.Translation(root_pivot)
            @ rotation_delta.to_matrix().to_4x4()
            @ Matrix.Translation(-root_pivot)
        )

    def _antenna_end_indices(
        self,
        positions: list[Vector],
        anchor_axis: Vector,
        min_anchor: float,
        max_anchor: float,
    ) -> tuple[list[int], list[int]]:
        length = max_anchor - min_anchor
        if not positions or length <= EPSILON:
            return [], []
        tolerance = max(length * 0.04, EPSILON)
        projections = [float(point.dot(anchor_axis)) for point in positions]
        root_indices = [
            index for index, projection in enumerate(projections)
            if projection <= min_anchor + tolerance
        ]
        tip_indices = [
            index for index, projection in enumerate(projections)
            if projection >= max_anchor - tolerance
        ]
        if not root_indices:
            root_indices = [projections.index(min(projections))]
        if not tip_indices:
            tip_indices = [projections.index(max(projections))]
        return root_indices, tip_indices

    def _average_indexed_vectors(self, positions: list[Vector], indices: list[int]) -> Vector:
        total = Vector((0.0, 0.0, 0.0))
        for index in indices:
            total += positions[index]
        return total / float(len(indices))

    def _evaluated_mesh_positions(self, obj: bpy.types.Object) -> list[Vector] | None:
        depsgraph = self._refresh_depsgraph()
        evaluated_obj = obj.evaluated_get(depsgraph)
        mesh = evaluated_obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
        try:
            return [vertex.co.copy() for vertex in mesh.vertices]
        finally:
            evaluated_obj.to_mesh_clear()

    def _active_antenna_shape_key_mesh(self, obj: bpy.types.Object) -> bpy.types.Mesh | None:
        if obj.type != "MESH":
            return None
        if not self._has_generated_antenna_whip_keys(obj):
            return None
        shape_keys = getattr(obj.data, "shape_keys", None)
        if shape_keys is None or len(shape_keys.key_blocks) < 2:
            return None
        candidates = [
            key for key in shape_keys.key_blocks[1:]
            if key.name.startswith(GOH_ANTENNA_SHAPE_KEY_PREFIX) and float(key.value) > 0.5
        ]
        if not candidates:
            basis_key = shape_keys.key_blocks.get("Basis") or shape_keys.key_blocks[0]
            if len(basis_key.data) != len(obj.data.vertices):
                return None
            mesh = obj.data.copy()
            for vertex, shape_point in zip(mesh.vertices, basis_key.data):
                vertex.co = shape_point.co
            mesh.update()
            return mesh
        key_block = max(candidates, key=lambda key: float(key.value))
        if len(key_block.data) != len(obj.data.vertices):
            return None
        mesh = obj.data.copy()
        for vertex, shape_point in zip(mesh.vertices, key_block.data):
            vertex.co = shape_point.co
        mesh.update()
        return mesh

    def _has_generated_antenna_whip_keys(self, obj: bpy.types.Object) -> bool:
        if obj.type != "MESH" or obj.data is None:
            return False
        shape_keys = getattr(obj.data, "shape_keys", None)
        if shape_keys is None or len(shape_keys.key_blocks) < 2:
            return False
        return any(
            key.name.startswith(GOH_ANTENNA_SHAPE_KEY_PREFIX)
            for key in shape_keys.key_blocks[1:]
        )

    def _basis_helper_ancestor(self, obj: bpy.types.Object) -> bpy.types.Object | None:
        parent = obj.parent
        while parent is not None:
            if self._is_basis_helper_object(parent):
                return parent
            parent = parent.parent
        return None

    def _basis_helper_displays_mirrored_space(self, obj: bpy.types.Object) -> bool:
        if obj.get("goh_deferred_basis_flip"):
            return False
        return self._matrix_is_mirrored(obj.matrix_world)

    def _is_generated_physics_animation(self, obj: bpy.types.Object, clip: AnimationClipSpec | None) -> bool:
        names: list[str] = []
        if clip is not None:
            names.extend(name for name in (clip.name, clip.file_stem) if name)
        animation_data = getattr(obj, "animation_data", None)
        action = getattr(animation_data, "action", None) if animation_data else None
        if action is not None:
            names.append(action.name)
        if animation_data is not None and getattr(animation_data, "use_nla", False):
            for track in animation_data.nla_tracks:
                if track.mute:
                    continue
                for strip in track.strips:
                    if strip.mute:
                        continue
                    names.append(strip.name)
                    strip_action = getattr(strip, "action", None)
                    if strip_action is not None:
                        names.append(strip_action.name)
        prefixes = tuple(prefix.lower() for prefix in GOH_PHYSICS_ACTION_PREFIXES)
        return any(str(name).strip().lower().startswith(prefixes) for name in names)

    def _is_generated_source_physics_animation(self, obj: bpy.types.Object, clip: AnimationClipSpec | None) -> bool:
        names: list[str] = []
        if clip is not None:
            names.extend(name for name in (clip.name, clip.file_stem) if name)
        animation_data = getattr(obj, "animation_data", None)
        action = getattr(animation_data, "action", None) if animation_data else None
        if action is not None:
            names.append(action.name)
        lowered = [str(name).strip().lower() for name in names]
        return any(
            name.startswith("goh_recoil_source")
            or name.startswith("goh_directional_recoil_source")
            for name in lowered
        )

    def _local_rest_reflection_matrix(self, rest_matrix: Matrix) -> Matrix | None:
        if not self._matrix_is_mirrored(rest_matrix):
            return None
        rest_loc_rot = self._loc_rot_matrix(rest_matrix)
        scale_space = rest_loc_rot.inverted_safe() @ rest_matrix
        reflection = scale_space.to_3x3().normalized()
        if reflection.determinant() >= -EPSILON:
            return None
        return reflection.to_4x4()

    def _matrix_is_mirrored(self, matrix: Matrix) -> bool:
        return matrix.to_3x3().determinant() < -EPSILON

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

    def _root_parent_matrix_for_object(
        self,
        obj: bpy.types.Object,
        visual_scope: set[bpy.types.Object],
    ) -> Matrix:
        parent = obj.parent
        if parent is not None and parent not in visual_scope and self._is_basis_helper_object(parent):
            return self._export_world_matrix(parent)
        return Matrix.Identity(4)

    def _export_world_matrix(self, obj: bpy.types.Object | None) -> Matrix:
        if obj is None:
            return Matrix.Identity(4)
        cached = self._stored_rest_local_matrix(obj)
        if cached is not None:
            parent_matrix = self._export_world_matrix(obj.parent)
            return parent_matrix @ cached
        if obj.parent is not None and self._has_deferred_basis_ancestor(obj):
            parent_matrix = self._export_world_matrix(obj.parent)
            local_matrix = obj.parent.matrix_world.inverted_safe() @ obj.matrix_world
            return parent_matrix @ local_matrix
        return obj.matrix_world.copy()

    def _has_deferred_basis_ancestor(self, obj: bpy.types.Object) -> bool:
        parent = obj.parent
        while parent is not None:
            if self._is_basis_helper_object(parent):
                return bool(parent.get("goh_deferred_basis_flip"))
            parent = parent.parent
        return False

    def _stored_rest_local_matrix(self, obj: bpy.types.Object | None) -> Matrix | None:
        if obj is None:
            return None
        values = obj.get("goh_rest_matrix_local")
        if values is None:
            return None
        try:
            floats = [float(value) for value in values]
        except (TypeError, ValueError):
            return None
        if len(floats) != 16:
            return None
        return Matrix(
            (
                floats[0:4],
                floats[4:8],
                floats[8:12],
                floats[12:16],
            )
        )

    def _reference_matrix_for_object_bone(
        self,
        bone_name: str,
        bone_name_map: dict[bpy.types.Object, str],
    ) -> Matrix | None:
        for obj, mapped_name in bone_name_map.items():
            if mapped_name == bone_name:
                return self._export_world_matrix(obj)
        return None

    def _build_object_node(
        self,
        obj: bpy.types.Object,
        parent_matrix: Matrix,
        visual_scope: set[bpy.types.Object],
        attachments: dict[str, list[AttachmentObject]],
        bone_name_map: dict[bpy.types.Object, str],
    ) -> BoneNode:
        obj_world_matrix = self._export_world_matrix(obj)
        local_matrix = parent_matrix.inverted() @ obj_world_matrix
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
                    parent_matrix=obj_world_matrix,
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
        fallback_bones: set[str] = set()
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
                        if not raw_vertex.influences:
                            fallback_bones.add(raw_vertex.fallback_bone or self.basis_name)

        if not raw_sections:
            return None

        skinned = any_weighted_vertices
        if skinned:
            for attachment in attachments:
                used_bones.update(self._preserved_skin_bones_for_object(attachment.obj))
            used_bones.update(fallback_bones)
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

        preserve_loop_vertices = False
        for attachment in attachments:
            obj = attachment.obj
            shape_keys = getattr(obj.data, "shape_keys", None)
            animation_data = getattr(shape_keys, "animation_data", None) if shape_keys else None
            if self._custom_bool(obj, "goh_force_mesh_animation") or (shape_keys and len(shape_keys.key_blocks) > 1 and animation_data is not None):
                preserve_loop_vertices = True
                break

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
                    if preserve_loop_vertices:
                        index = len(vertices)
                        vertices.append(final_vertex)
                    else:
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
        evaluated_obj = None
        if use_evaluated_mesh:
            mesh = self._active_antenna_shape_key_mesh(obj)
            if mesh is None:
                depsgraph = self._refresh_depsgraph()
                evaluated_obj = obj.evaluated_get(depsgraph)
                mesh = evaluated_obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
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
            local_matrix = reference_matrix.inverted() @ self._export_world_matrix(obj)
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

    def _object_bone_order_for_weights(
        self,
        visual_objects: set[bpy.types.Object],
        bone_name_map: dict[bpy.types.Object, str],
    ) -> list[str]:
        object_bones = set(bone_name_map.values())
        ordered: list[str] = []
        for obj in sorted((item for item in visual_objects if item.type == "MESH"), key=lambda item: item.name.lower()):
            for group in obj.vertex_groups:
                group_name = group.name
                if group_name in object_bones and group_name not in ordered:
                    ordered.append(group_name)
        for bone_name in bone_name_map.values():
            if bone_name not in ordered:
                ordered.append(bone_name)
        return ordered

    def _preserved_skin_bones_for_object(self, obj: bpy.types.Object) -> list[str]:
        if not (self._custom_bool(obj, "goh_humanskin_combined") or self._custom_text(obj, "goh_import_ply")):
            return []
        valid_bones = set(self.armature_bone_order)
        preserved: list[str] = []
        for group in obj.vertex_groups:
            group_name = group.name
            if (group_name == self.basis_name or group_name in valid_bones) and group_name not in preserved:
                preserved.append(group_name)
        return preserved

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
        file_name = self._material_file_name(material, fallback_name, key)
        material_def = self._build_material_definition(material, file_name)
        self.material_cache[key] = material_def
        return material_def

    def _material_file_name(
        self,
        material: bpy.types.Material | None,
        fallback_name: str,
        key: tuple[str, int],
    ) -> str:
        imported_name = self._custom_text(material, "goh_import_mtl") if material else None
        raw_name = Path(imported_name).name if imported_name else (material.name if material else fallback_name)
        raw_stem = Path(raw_name).stem if raw_name.lower().endswith(".mtl") else raw_name
        raw_stem = re.sub(r"\.\d{3}$", "", raw_stem)
        safe_stem = sanitized_file_stem(raw_stem)
        file_name = f"{safe_stem}.mtl"
        file_key = file_name.lower()
        owner = self.material_file_names.get(file_key)
        if owner is None or owner == key or imported_name:
            self.material_file_names[file_key] = key
            return file_name

        counter = 2
        while True:
            fallback_file = f"{safe_stem}_{counter}.mtl"
            fallback_key = fallback_file.lower()
            if fallback_key not in self.material_file_names:
                self.material_file_names[fallback_key] = key
                return fallback_file
            counter += 1

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
        operator_blend = str(getattr(self.operator, "material_blend", "") or "").lower()
        if operator_blend in {"none", "test", "blend"}:
            blend = operator_blend
        else:
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
            object_reference = self._reference_matrix_for_object_bone(custom_bone, bone_name_map)
            if object_reference is not None:
                return custom_bone, object_reference
            return custom_bone, self._reference_matrix_for_bone(custom_bone)

        if self.armature_obj and obj.parent == self.armature_obj and obj.parent_type == "BONE" and obj.parent_bone:
            return obj.parent_bone, self._reference_matrix_for_bone(obj.parent_bone)

        if obj.parent in bone_name_map:
            bone_name = bone_name_map[obj.parent]
            reference_matrix = self._export_world_matrix(obj.parent)
            return bone_name, reference_matrix

        derived = self._derive_volume_bone_from_name(obj.name)
        if derived:
            object_reference = self._reference_matrix_for_object_bone(derived, bone_name_map)
            if object_reference is not None:
                return derived, object_reference
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
        if self.armature_obj is None and not self.armature_bone_order:
            return ()

        valid_bones = set(self.armature_bone_order)
        influences: list[tuple[str, float]] = []
        for group_element in vertex.groups:
            if group_element.weight <= EPSILON:
                continue
            if group_element.group >= len(obj.vertex_groups):
                continue
            group_name = obj.vertex_groups[group_element.group].name
            if group_name == self.basis_name or group_name in valid_bones:
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

        owner_keys = []
        if hasattr(owner, "keys"):
            try:
                owner_keys = list(owner.keys())
            except Exception:
                owner_keys = []
        for raw_key in owner_keys:
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
            explicit = self._custom_text(self.basis_helper, "goh_parameters")
            if explicit:
                parts.append(explicit.strip())
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

    def _custom_get(self, owner, key: str):
        if owner is None or not hasattr(owner, "get"):
            return None
        try:
            return owner.get(key)
        except (AttributeError, TypeError, RuntimeError):
            return None

    def _custom_scalar(self, owner, key: str):
        if owner is None:
            return None
        value = self._custom_get(owner, key)
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
        value = self._custom_get(owner, key)
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
        value = bool(self._custom_get(owner, key))
        if value:
            return True
        for alias in GOH_CUSTOM_BOOL_ALIASES.get(key, ()):
            if bool(self._custom_get(owner, alias)):
                return True
        flag_names = GOH_LEGACY_BOOL_FLAGS.get(key)
        if flag_names and self._legacy_has_flag(owner, *flag_names):
            return True
        return False

    def _custom_int(self, owner, key: str) -> int | None:
        if owner is None:
            return None
        value = self._custom_get(owner, key)
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
        value = self._custom_get(owner, key)
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
        value = self._custom_get(owner, key)
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
        value = self._custom_get(owner, key)
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
