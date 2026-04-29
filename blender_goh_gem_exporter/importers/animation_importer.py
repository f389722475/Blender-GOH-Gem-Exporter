from __future__ import annotations

from .. import blender_exporter as _legacy

for _name, _value in _legacy.__dict__.items():
    if _name not in globals():
        globals()[_name] = _value


class GOHAnimationImporter:
    def __init__(self, context: bpy.types.Context, operator: "IMPORT_SCENE_OT_goh_anm") -> None:
        self.context = context
        self.operator = operator
        self.axis_mode = operator.axis_mode
        self.axis_rotation = self._axis_rotation_matrix(self.axis_mode)
        self.scale_factor = operator.scale_factor
        self.warnings: list[str] = []
        self._handedness_warning_keys: set[str] = set()

    def import_animation(self) -> list[str]:
        animation = read_animation(self.operator.filepath)
        self._configure_import_space(animation)
        armature = self._target_armature()
        if armature is not None:
            self._apply_to_armature(animation, armature)
        else:
            self._apply_to_objects(animation)
        self._apply_mesh_animation(animation)
        return self.warnings

    def _configure_import_space(self, animation: AnimationFile) -> None:
        requested_axis = self.operator.axis_mode
        requested_scale = float(self.operator.scale_factor)
        if requested_axis == "AUTO":
            detected = self._detect_imported_model_space(animation)
            if detected is not None:
                self.axis_mode, self.scale_factor = detected
            else:
                self.axis_mode, self.scale_factor = "GOH_TO_BLENDER", requested_scale
        else:
            self.axis_mode, self.scale_factor = requested_axis, requested_scale
            detected = self._detect_imported_model_space(animation)
            if detected is not None and detected[0] != requested_axis:
                self.warnings.append(
                    f'Animation axis "{requested_axis}" differs from the imported model axis "{detected[0]}". '
                    'Use Auto / Match Imported Model if the animation appears rotated.'
                )
        self.axis_rotation = self._axis_rotation_matrix(self.axis_mode)

    def _detect_imported_model_space(self, animation: AnimationFile) -> tuple[str, float] | None:
        candidates = self._animation_object_pool(animation)
        selected_candidates = [obj for obj in candidates if obj.select_get()]
        pools = (selected_candidates, candidates)
        for pool in pools:
            matches: dict[tuple[str, float], int] = {}
            for obj in pool:
                axis = self._object_import_axis_mode(obj)
                if axis is None:
                    continue
                scale = self._object_import_scale_factor(obj)
                key = (axis, round(scale, 6))
                matches[key] = matches.get(key, 0) + 1
            if not matches:
                continue
            ordered = sorted(matches.items(), key=lambda item: item[1], reverse=True)
            if len(ordered) > 1:
                self.warnings.append("Animation targets have mixed imported model axis metadata; using the most common setting.")
            axis, scale = ordered[0][0]
            return axis, scale
        return None

    def _animation_target_names(self, animation: AnimationFile) -> set[str]:
        names = {name for name in animation.bone_names if name}
        for frame_state in animation.frames:
            names.update(name for name in frame_state if name)
        for frame_state in animation.mesh_frames:
            names.update(name for name in frame_state if name)
        return names

    def _animation_object_pool(self, animation: AnimationFile) -> list[bpy.types.Object]:
        target_names = self._animation_target_names(animation)
        objects = [obj for obj in self.context.view_layer.objects if obj.type in {"MESH", "EMPTY"}]
        if not target_names:
            return objects
        return [obj for obj in objects if self._object_name_keys(obj) & target_names]

    def _object_name_keys(self, obj: bpy.types.Object) -> set[str]:
        keys = {obj.name}
        custom_name = obj.get("goh_bone_name")
        if custom_name:
            keys.add(str(custom_name).strip())
        attach_name = obj.get("goh_attach_bone")
        if attach_name:
            keys.add(str(attach_name).strip())
        if obj.parent_type == "BONE" and obj.parent_bone:
            keys.add(obj.parent_bone.strip())
        return {key for key in keys if key}

    def _object_import_axis_mode(self, obj: bpy.types.Object) -> str | None:
        axis = str(obj.get("goh_import_axis_mode") or "").strip()
        if axis in {"NONE", "GOH_TO_BLENDER"}:
            return axis
        if obj.get("goh_source_mdl") is not None:
            return "NONE"
        return None

    def _object_import_scale_factor(self, obj: bpy.types.Object) -> float:
        try:
            return float(obj.get("goh_import_scale_factor", self.operator.scale_factor))
        except (TypeError, ValueError):
            return float(self.operator.scale_factor)

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

        shape_keys = getattr(obj.data, "shape_keys", None)
        animation_data = getattr(shape_keys, "animation_data", None) if shape_keys else None
        preserve_loop_vertices = bool(obj.get("goh_force_mesh_animation")) or (
            shape_keys is not None and len(shape_keys.key_blocks) > 1 and animation_data is not None
        )
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
                    if preserve_loop_vertices:
                        export_to_source.append(loop.vertex_index)
                        continue
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

        for fcurve in _action_fcurves(action):
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
        objects = self._animation_object_pool(animation)

        def put(name: str, obj: bpy.types.Object) -> None:
            if not name:
                return
            previous = object_map.get(name)
            if previous is None or self._prefer_animation_target(obj, previous):
                object_map[name] = obj

        for obj in objects:
            put(obj.name, obj)
            custom_name = obj.get("goh_bone_name")
            if custom_name:
                put(str(custom_name).strip(), obj)

        frame_start = self.operator.frame_start
        for offset, frame_state in enumerate(animation.frames):
            frame = frame_start + offset
            for bone_name, state in frame_state.items():
                obj = object_map.get(bone_name)
                if obj is None:
                    continue
                local_matrix = self._decode_matrix_rows_as_matrix(state.matrix)
                local_matrix = self._object_animation_display_matrix(obj, local_matrix)
                location, rotation, _scale = local_matrix.decompose()
                obj.rotation_mode = "QUATERNION"
                obj.location = location
                obj.rotation_quaternion = rotation
                obj.hide_viewport = not bool(state.visible)
                obj.hide_render = not bool(state.visible)
                obj.keyframe_insert("location", frame=frame)
                obj.keyframe_insert("rotation_quaternion", frame=frame)
                obj.keyframe_insert("hide_viewport", frame=frame)
                obj.keyframe_insert("hide_render", frame=frame)

    def _prefer_animation_target(self, obj: bpy.types.Object, previous: bpy.types.Object) -> bool:
        if obj.select_get() != previous.select_get():
            return obj.select_get()
        obj_imported = obj.get("goh_source_mdl") is not None
        previous_imported = previous.get("goh_source_mdl") is not None
        if obj_imported != previous_imported:
            return obj_imported
        return False

    def _object_animation_display_matrix(self, obj: bpy.types.Object, local_matrix: Matrix) -> Matrix:
        rest_matrix = self._stored_rest_local_matrix(obj)
        if rest_matrix is None:
            return local_matrix
        if obj.get("goh_deferred_basis_flip") and self._is_basis_helper_object(obj):
            return self._deferred_basis_object_animation_matrix(local_matrix)
        if self._matrix_handedness_mismatch(rest_matrix, local_matrix):
            key = str(obj.get("goh_bone_name") or obj.name)
            if key not in self._handedness_warning_keys:
                self._handedness_warning_keys.add(key)
                self.warnings.append(
                    f'Animation target "{key}" has handedness that differs from the imported MDL rest transform; '
                    "preserved the MDL rest handedness for Blender display."
                )
            preserved = rest_matrix.copy()
            preserved.translation = local_matrix.translation
            return preserved
        correction = self._mirrored_basis_animation_correction_matrix(obj)
        if correction is None:
            return local_matrix
        return self._convert_deferred_basis_animation_delta(rest_matrix, local_matrix, correction)

    def _deferred_basis_object_animation_matrix(self, local_matrix: Matrix) -> Matrix:
        # GOH basis keys carry coordinate-frame markers; the deferred Blender basis is display-space only.
        return Matrix.Translation(local_matrix.translation)

    def _matrix_handedness_mismatch(self, rest_matrix: Matrix, local_matrix: Matrix) -> bool:
        rest_det = rest_matrix.to_3x3().determinant()
        local_det = local_matrix.to_3x3().determinant()
        if abs(rest_det) <= EPSILON or abs(local_det) <= EPSILON:
            return False
        return (rest_det < 0.0) != (local_det < 0.0)

    def _convert_deferred_basis_animation_delta(
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

    def _basis_helper_ancestor(self, obj: bpy.types.Object) -> bpy.types.Object | None:
        parent = obj.parent
        while parent is not None:
            if self._is_basis_helper_object(parent):
                return parent
            parent = parent.parent
        return None

    def _is_basis_helper_object(self, obj: bpy.types.Object | None) -> bool:
        if obj is None:
            return False
        if obj.get("goh_basis_helper"):
            return True
        return obj.type == "EMPTY" and obj.name.lower() == GOH_BASIS_HELPER_NAME.lower()

    def _basis_helper_displays_mirrored_space(self, obj: bpy.types.Object) -> bool:
        if obj.get("goh_deferred_basis_flip"):
            return False
        return self._matrix_is_mirrored(obj.matrix_world)

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

    def _loc_rot_matrix(self, matrix: Matrix) -> Matrix:
        loc, rot, _scale = matrix.decompose()
        return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()

    def _basis_rotation_matrix(self) -> Matrix:
        return Matrix(
            (
                (1.0, 0.0, 0.0),
                (0.0, -1.0, 0.0),
                (0.0, 0.0, 1.0),
            )
        )

    def _matrix_is_mirrored(self, matrix: Matrix) -> bool:
        return matrix.to_3x3().determinant() < -EPSILON

    def _decode_matrix_rows(
        self,
        matrix_rows: tuple[tuple[float, float, float], ...],
    ) -> tuple[Vector, tuple[float, float, float, float]]:
        matrix = self._decode_matrix_rows_as_matrix(matrix_rows)
        location, rotation, _scale = matrix.decompose()
        return Vector((location.x, location.y, location.z)), (
            float(rotation.w),
            float(rotation.x),
            float(rotation.y),
            float(rotation.z),
        )

    def _decode_matrix_rows_as_matrix(self, matrix_rows: tuple[tuple[float, float, float], ...]) -> Matrix:
        axis3 = self.axis_rotation.to_3x3()
        rotation = Matrix((matrix_rows[0], matrix_rows[1], matrix_rows[2]))
        converted_rotation = axis3.inverted() @ rotation @ axis3
        location = axis3.inverted() @ Vector(matrix_rows[3])
        if abs(self.scale_factor) > EPSILON:
            location /= self.scale_factor
        return Matrix.Translation(location) @ converted_rotation.to_4x4()

    def _axis_rotation_matrix(self, axis_mode: str) -> Matrix:
        if axis_mode == "GOH_TO_BLENDER":
            return Matrix.Rotation(-math.pi / 2.0, 4, "Z")
        return Matrix.Identity(4)
