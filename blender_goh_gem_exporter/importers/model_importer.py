from __future__ import annotations

from .. import blender_exporter as _legacy

for _name, _value in _legacy.__dict__.items():
    if _name not in globals():
        globals()[_name] = _value


class GOHModelImporter:
    def __init__(self, context: bpy.types.Context, operator: "IMPORT_SCENE_OT_goh_model") -> None:
        self.context = context
        self.operator = operator
        self.input_path = Path(operator.filepath)
        self.input_dir = self.input_path.parent
        self.axis_rotation = self._axis_rotation_matrix(operator.axis_mode)
        self.scale_factor = operator.scale_factor
        self.defer_basis_flip = bool(getattr(operator, "defer_basis_flip", False))
        self.warnings: list[str] = []
        self.material_cache: dict[str, bpy.types.Material] = {}
        self.bone_objects: dict[str, bpy.types.Object] = {}
        self.imported_objects: list[bpy.types.Object] = []
        self.root_collection: bpy.types.Collection | None = None
        self.volume_collection: bpy.types.Collection | None = None
        self.obstacle_collection: bpy.types.Collection | None = None
        self.area_collection: bpy.types.Collection | None = None

    def import_model(self) -> tuple[int, list[str]]:
        model = read_model(self.input_path)
        self.root_collection = self._ensure_child_collection(f"GOH_{self.input_path.stem}", self.context.scene.collection)
        if self.operator.import_volumes:
            self.volume_collection = self._ensure_child_collection("GOH_VOLUMES", self.root_collection)
        if self.operator.import_shapes:
            self.obstacle_collection = self._ensure_child_collection("GOH_OBSTACLES", self.root_collection)
            self.area_collection = self._ensure_child_collection("GOH_AREAS", self.root_collection)
        self._import_bone_node(model.basis, None)
        if self.operator.import_volumes:
            self._import_volumes(model.volumes)
        if self.operator.import_shapes:
            self._import_shape2d_entries(model.obstacles, is_obstacle=True)
            self._import_shape2d_entries(model.areas, is_obstacle=False)
        for obj in self.imported_objects:
            obj["goh_source_mdl"] = str(self.input_path)
            obj["goh_import_axis_mode"] = self.operator.axis_mode
            obj["goh_import_scale_factor"] = float(self.scale_factor)
            obj["goh_import_flip_v"] = bool(self.operator.flip_v)
        return len(self.imported_objects), self.warnings

    def _import_bone_node(self, bone: BoneNode, parent: bpy.types.Object | None) -> bpy.types.Object:
        local_matrix = self._decode_matrix_rows(bone.matrix or self._identity_matrix_rows())
        defer_basis_flip = self._should_defer_basis_flip(bone, parent, local_matrix)
        display_matrix = self._deferred_basis_display_matrix(local_matrix) if defer_basis_flip else local_matrix
        views = list(bone.mesh_views)
        if not views and bone.volume_view:
            views = [MeshViewDef(bone.volume_view, bone.volume_flags, bone.layer)]
        if self.operator.import_lod0_only:
            views = views[:1]

        primary: bpy.types.Object | None = None
        for view_index, view in enumerate(views):
            if not view.file_name:
                continue
            mesh_path = self._resolve_asset_path(view.file_name)
            if mesh_path is None:
                self.warnings.append(f'Mesh "{view.file_name}" referenced by bone "{bone.name}" was not found.')
                continue
            try:
                mesh_data = read_mesh(mesh_path)
            except ExportError as exc:
                self.warnings.append(str(exc))
                continue
            object_name = bone.name if primary is None else f"{bone.name}_lod{view_index}"
            obj = self._create_mesh_object(object_name, mesh_data)
            obj["goh_bone_name"] = bone.name
            obj["goh_import_mesh"] = view.file_name
            if primary is None:
                self._set_parent_and_matrix(obj, parent, local_matrix, display_matrix=display_matrix)
                primary = obj
                self.bone_objects[bone.name] = obj
            else:
                self._set_parent_and_matrix(obj, primary, Matrix.Identity(4))
                obj.hide_viewport = True
                obj.hide_render = True

        if primary is None:
            primary = bpy.data.objects.new(bone.name, None)
            primary.empty_display_type = "PLAIN_AXES"
            primary.empty_display_size = 0.35
            primary["goh_bone_name"] = bone.name
            self._link_object(primary)
            self._set_parent_and_matrix(primary, parent, local_matrix, display_matrix=display_matrix)
            self.bone_objects[bone.name] = primary

        if defer_basis_flip:
            primary["goh_basis_helper"] = True
            primary["goh_deferred_basis_flip"] = True

        if bone.bone_type:
            primary["goh_bone_type"] = bone.bone_type
        if bone.limits:
            primary["goh_limits"] = " ".join(f"{value:g}" for value in bone.limits)
        if bone.speed is not None:
            primary["goh_speed2" if bone.speed_uses_speed2 else "goh_speed"] = bone.speed
        if bone.parameters:
            primary["goh_parameters"] = bone.parameters

        for child in bone.children:
            self._import_bone_node(child, primary)
        return primary

    def _should_defer_basis_flip(self, bone: BoneNode, parent: bpy.types.Object | None, local_matrix: Matrix) -> bool:
        if not self.defer_basis_flip:
            return False
        if self.operator.axis_mode != "NONE":
            return False
        if parent is not None:
            return False
        if bone.name.lower() != GOH_BASIS_HELPER_NAME.lower():
            return False
        return local_matrix.to_3x3().determinant() < -EPSILON

    def _deferred_basis_display_matrix(self, local_matrix: Matrix) -> Matrix:
        location = local_matrix.to_translation()
        return Matrix.Translation(location)

    def _create_mesh_object(self, object_name: str, mesh_data: MeshData) -> bpy.types.Object:
        vertices = [self._decode_point(vertex.position) for vertex in mesh_data.vertices]
        faces: list[tuple[int, int, int]] = []
        loop_normals: list[Vector] = []
        face_material_indices: list[int] = []
        material_files: list[str] = []
        material_index_by_file: dict[str, int] = {}
        for section in mesh_data.sections:
            material_file = section.material_file or f"{mesh_data.file_name}.mtl"
            if material_file not in material_index_by_file:
                material_index_by_file[material_file] = len(material_files)
                material_files.append(material_file)
            material_index = material_index_by_file[material_file]
            for triangle in section.triangle_indices:
                faces.append(triangle)
                for vertex_index in triangle:
                    if 0 <= vertex_index < len(mesh_data.vertices):
                        loop_normals.append(self._decode_direction(mesh_data.vertices[vertex_index].normal))
                    else:
                        loop_normals.append(Vector((0.0, 0.0, 1.0)))
                face_material_indices.append(material_index)

        mesh = bpy.data.meshes.new(f"{object_name}_mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        self._apply_imported_loop_normals(mesh, loop_normals, mesh_data.file_name)

        if mesh_data.vertices and mesh.polygons:
            uv_layer = mesh.uv_layers.new(name="UVMap")
            for polygon, triangle in zip(mesh.polygons, faces):
                for loop_index, vertex_index in zip(polygon.loop_indices, triangle):
                    if vertex_index >= len(mesh_data.vertices):
                        continue
                    u, v = mesh_data.vertices[vertex_index].uv
                    uv_layer.data[loop_index].uv = (float(u), float(1.0 - v) if self.operator.flip_v else float(v))

        for material_file in material_files:
            mesh.materials.append(self._material_for_file(material_file))
        for polygon, material_index in zip(mesh.polygons, face_material_indices):
            polygon.material_index = material_index

        obj = bpy.data.objects.new(object_name, mesh)
        obj["goh_import_ply"] = mesh_data.file_name
        self._link_object(obj)
        self._apply_vertex_groups(obj, mesh_data)
        return obj

    def _apply_imported_loop_normals(self, mesh: bpy.types.Mesh, loop_normals: list[Vector], source_name: str) -> None:
        if not loop_normals:
            return
        if len(loop_normals) != len(mesh.loops):
            self.warnings.append(
                f'Mesh "{source_name}" skipped imported normals: {len(loop_normals)} normals for {len(mesh.loops)} loops.'
            )
            return
        normalized_normals: list[tuple[float, float, float]] = []
        missing_normals = 0
        for normal in loop_normals:
            converted = Vector(normal)
            if converted.length <= EPSILON:
                missing_normals += 1
                converted = Vector((0.0, 0.0, 1.0))
            else:
                converted.normalize()
            normalized_normals.append((float(converted.x), float(converted.y), float(converted.z)))
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        if not hasattr(mesh, "normals_split_custom_set"):
            self.warnings.append(f'Mesh "{source_name}" could not apply imported normals: Blender custom split normals API unavailable.')
            return
        try:
            mesh.normals_split_custom_set(normalized_normals)
            mesh.update()
            mesh["goh_imported_custom_normals"] = True
            mesh["goh_imported_custom_normal_loops"] = len(normalized_normals)
            if missing_normals:
                mesh["goh_imported_custom_normal_missing"] = missing_normals
                self.warnings.append(f'Mesh "{source_name}" had {missing_normals} zero imported normal(s); used fallback normals.')
        except Exception as exc:
            self.warnings.append(f'Mesh "{source_name}" could not apply imported normals: {exc}')

    def _apply_vertex_groups(self, obj: bpy.types.Object, mesh_data: MeshData) -> None:
        if not mesh_data.skinned_bones:
            return
        groups = [obj.vertex_groups.new(name=name) for name in mesh_data.skinned_bones]
        for vertex_index, vertex in enumerate(mesh_data.vertices):
            weights = list(vertex.weights)
            if len(weights) < 4:
                weights.append(max(0.0, 1.0 - sum(weights)))
            for slot, bone_index in enumerate(vertex.bone_indices[:4]):
                if bone_index >= len(groups):
                    continue
                weight = weights[slot] if slot < len(weights) else 0.0
                if weight > EPSILON:
                    groups[bone_index].add([vertex_index], weight, "ADD")

    def _import_volumes(self, volumes: list[VolumeData]) -> None:
        for volume in volumes:
            parent = self.bone_objects.get(volume.bone_name or "")
            try:
                obj = self._create_volume_object(volume)
            except ExportError as exc:
                self.warnings.append(str(exc))
                continue
            self._set_parent_and_matrix(obj, parent, self._decode_matrix_rows(volume.matrix or self._identity_matrix_rows()))
            obj["goh_is_volume"] = True
            obj["goh_volume_name"] = volume.entry_name
            obj["goh_volume_bone"] = volume.bone_name or ""
            obj["goh_volume_kind"] = volume.volume_kind
            if (volume.volume_kind or "").lower() == "cylinder":
                obj["goh_volume_axis"] = "z"
            obj.display_type = "WIRE"
            obj.hide_render = True
            if self.volume_collection is not None and self.volume_collection.objects.get(obj.name) is None:
                self.volume_collection.objects.link(obj)

    def _import_shape2d_entries(self, entries: list[Shape2DEntry], *, is_obstacle: bool) -> None:
        collection = self.obstacle_collection if is_obstacle else self.area_collection
        role_name = "obstacle" if is_obstacle else "area"
        flag_name = "goh_is_obstacle" if is_obstacle else "goh_is_area"
        name_prop = "goh_obstacle_name" if is_obstacle else "goh_area_name"
        for entry in entries:
            obj = self._create_shape2d_object(entry, role_name)
            obj[flag_name] = True
            obj[name_prop] = entry.entry_name
            obj["goh_shape_name"] = entry.entry_name
            obj["goh_shape_2d"] = (entry.shape_type or "Obb2").strip().lower()
            if entry.rotate:
                obj["goh_rotate_2d"] = True
            if entry.tags:
                obj["goh_tags"] = entry.tags
            obj.display_type = "WIRE"
            obj.show_in_front = True
            obj.hide_render = True
            if collection is not None and collection.objects.get(obj.name) is None:
                collection.objects.link(obj)

    def _create_shape2d_object(self, entry: Shape2DEntry, role_name: str) -> bpy.types.Object:
        shape_type = (entry.shape_type or "Obb2").strip().lower()
        safe_name = sanitized_file_stem(entry.entry_name or role_name) or role_name
        object_name = f"{safe_name}_{role_name}"
        if shape_type == "circle2":
            center = entry.center or (0.0, 0.0)
            radius = self._decode_length(entry.radius or 1.0)
            vertices: list[Vector] = []
            segments = 32
            for segment in range(segments):
                theta = 2.0 * math.pi * segment / segments
                vertices.append(Vector((math.cos(theta) * radius, math.sin(theta) * radius, 0.0)))
            faces: list[tuple[int, ...]] = [tuple(range(segments))]
            matrix = self._shape2d_frame_matrix(center, (1.0, 0.0))
        elif shape_type == "polygon2":
            points = entry.vertices
            if not points and entry.center and entry.extent:
                cx, cy = entry.center
                ex, ey = entry.extent
                points = [(cx - ex, cy - ey), (cx + ex, cy - ey), (cx + ex, cy + ey), (cx - ex, cy + ey)]
            vertices = [self._decode_point((point[0], point[1], 0.0)) for point in points]
            faces = [tuple(range(len(vertices)))] if len(vertices) >= 3 else []
            matrix = Matrix.Identity(4)
        else:
            center = entry.center or (0.0, 0.0)
            extent = entry.extent or (0.5, 0.5)
            ex = self._decode_length(extent[0])
            ey = self._decode_length(extent[1])
            vertices = [
                Vector((-ex, -ey, 0.0)),
                Vector((ex, -ey, 0.0)),
                Vector((ex, ey, 0.0)),
                Vector((-ex, ey, 0.0)),
            ]
            faces = [(0, 1, 2, 3)]
            matrix = self._shape2d_frame_matrix(center, entry.axis or (1.0, 0.0))

        mesh = bpy.data.meshes.new(f"{object_name}_mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(object_name, mesh)
        self._link_object(obj)
        obj.matrix_world = matrix
        return obj

    def _shape2d_frame_matrix(self, center: tuple[float, float], axis: tuple[float, float]) -> Matrix:
        axis_go = Vector((float(axis[0]), float(axis[1]), 0.0))
        if axis_go.length <= EPSILON:
            axis_go = Vector((1.0, 0.0, 0.0))
        axis_go.normalize()
        perp_go = Vector((-axis_go.y, axis_go.x, 0.0))
        z_go = Vector((0.0, 0.0, 1.0))
        inverse_axis = self.axis_rotation.to_3x3().inverted()
        axis_bl = inverse_axis @ axis_go
        perp_bl = inverse_axis @ perp_go
        z_bl = inverse_axis @ z_go
        if axis_bl.length <= EPSILON:
            axis_bl = Vector((1.0, 0.0, 0.0))
        if perp_bl.length <= EPSILON:
            perp_bl = Vector((0.0, 1.0, 0.0))
        if z_bl.length <= EPSILON:
            z_bl = Vector((0.0, 0.0, 1.0))
        axis_bl.normalize()
        perp_bl.normalize()
        z_bl.normalize()
        matrix = Matrix.Identity(4)
        for row in range(3):
            matrix[row][0] = axis_bl[row]
            matrix[row][1] = perp_bl[row]
            matrix[row][2] = z_bl[row]
        matrix.translation = self._decode_point((center[0], center[1], 0.0))
        return matrix

    def _create_volume_object(self, volume: VolumeData) -> bpy.types.Object:
        kind = (volume.volume_kind or "polyhedron").lower()
        if kind == "polyhedron":
            if not volume.file_name:
                raise ExportError(f'Volume "{volume.entry_name}" has no .vol file reference.')
            volume_path = self._resolve_asset_path(volume.file_name)
            if volume_path is None:
                raise ExportError(f'Volume file "{volume.file_name}" referenced by "{volume.entry_name}" was not found.')
            volume_data = read_volume(volume_path)
            vertices = [self._decode_point(vertex) for vertex in volume_data.vertices]
            faces = list(volume_data.triangles)
        elif kind == "box":
            size = volume.box_size or (1.0, 1.0, 1.0)
            vertices, faces = self._box_mesh(size)
        elif kind == "sphere":
            vertices, faces = self._sphere_mesh(volume.sphere_radius or 1.0)
        elif kind == "cylinder":
            vertices, faces = self._cylinder_mesh(volume.cylinder_radius or 0.5, volume.cylinder_length or 1.0)
        else:
            raise ExportError(f'Unsupported volume kind "{kind}" on "{volume.entry_name}".')
        mesh = bpy.data.meshes.new(f"{volume.entry_name}_vol_mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(f"{volume.entry_name}_vol", mesh)
        self._link_object(obj)
        return obj

    def _box_mesh(self, size: tuple[float, float, float]) -> tuple[list[Vector], list[tuple[int, ...]]]:
        sx, sy, sz = (self._decode_length(value) * 0.5 for value in size)
        vertices = [
            Vector((-sx, -sy, -sz)), Vector((sx, -sy, -sz)), Vector((sx, sy, -sz)), Vector((-sx, sy, -sz)),
            Vector((-sx, -sy, sz)), Vector((sx, -sy, sz)), Vector((sx, sy, sz)), Vector((-sx, sy, sz)),
        ]
        faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        return vertices, faces

    def _sphere_mesh(self, radius: float, segments: int = 16, rings: int = 8) -> tuple[list[Vector], list[tuple[int, ...]]]:
        radius = self._decode_length(radius)
        vertices = [Vector((0.0, 0.0, radius))]
        for ring in range(1, rings):
            phi = math.pi * ring / rings
            z = math.cos(phi) * radius
            r = math.sin(phi) * radius
            for segment in range(segments):
                theta = 2.0 * math.pi * segment / segments
                vertices.append(Vector((math.cos(theta) * r, math.sin(theta) * r, z)))
        vertices.append(Vector((0.0, 0.0, -radius)))
        bottom_index = len(vertices) - 1
        faces: list[tuple[int, ...]] = []
        for segment in range(segments):
            faces.append((0, 1 + segment, 1 + ((segment + 1) % segments)))
        for ring in range(rings - 2):
            start = 1 + ring * segments
            next_start = start + segments
            for segment in range(segments):
                faces.append((start + segment, next_start + segment, next_start + ((segment + 1) % segments), start + ((segment + 1) % segments)))
        last_ring = 1 + (rings - 2) * segments
        for segment in range(segments):
            faces.append((last_ring + ((segment + 1) % segments), last_ring + segment, bottom_index))
        return vertices, faces

    def _cylinder_mesh(self, radius: float, length: float, segments: int = 16) -> tuple[list[Vector], list[tuple[int, ...]]]:
        radius = self._decode_length(radius)
        half_length = self._decode_length(length) * 0.5
        vertices: list[Vector] = []
        for z in (-half_length, half_length):
            for segment in range(segments):
                theta = 2.0 * math.pi * segment / segments
                vertices.append(Vector((math.cos(theta) * radius, math.sin(theta) * radius, z)))
        faces: list[tuple[int, ...]] = []
        faces.append(tuple(reversed(range(segments))))
        faces.append(tuple(range(segments, segments * 2)))
        for segment in range(segments):
            faces.append((segment, (segment + 1) % segments, segments + ((segment + 1) % segments), segments + segment))
        return vertices, faces

    def _material_for_file(self, material_file: str) -> bpy.types.Material:
        if material_file in self.material_cache:
            return self.material_cache[material_file]
        material_path = self._resolve_asset_path(material_file)
        if self.operator.import_materials and material_path is not None:
            try:
                material_def = read_material(material_path)
            except ExportError as exc:
                self.warnings.append(str(exc))
                material_def = MaterialDef(file_name=material_file)
        else:
            material_def = MaterialDef(file_name=material_file)
        material = bpy.data.materials.new(sanitized_file_stem(Path(material_file).stem))
        alpha = material_def.color_rgba[3] / 255.0 if material_def.blend in {"alpha", "blend"} else 1.0
        material.diffuse_color = (
            material_def.color_rgba[0] / 255.0,
            material_def.color_rgba[1] / 255.0,
            material_def.color_rgba[2] / 255.0,
            alpha,
        )
        material["goh_import_mtl"] = material_file
        for prop_name, value in (
            ("goh_diffuse", material_def.diffuse_texture),
            ("goh_bump", material_def.bump_texture),
            ("goh_specular", material_def.specular_texture),
            ("goh_lightmap", material_def.lightmap_texture),
            ("goh_mask", material_def.mask_texture),
            ("goh_height", material_def.height_texture),
            ("goh_diffuse1", material_def.diffuse1_texture),
            ("goh_simple", material_def.simple_texture),
            ("goh_envmap_texture", material_def.envmap_texture),
            ("goh_bump_volume", material_def.bump_volume_texture),
        ):
            if value:
                material[prop_name] = value
        if material_def.needs_bump:
            material["goh_material_kind"] = "bump"
        elif material_def.shader:
            material["goh_material_kind"] = material_def.shader
        if material_def.specular_texture:
            material["goh_specular_role"] = self._specular_texture_role(material_def)
        self._configure_goh_principled_defaults(material, material_def)
        if self.operator.load_textures:
            self._attach_goh_material_textures(material, material_def)
        self.material_cache[material_file] = material
        return material

    def _specular_texture_role(self, material_def: MaterialDef) -> str:
        return "specular"

    def _configure_goh_principled_defaults(self, material: bpy.types.Material, material_def: MaterialDef) -> None:
        material.use_nodes = True
        node_tree = material.node_tree
        if node_tree is None:
            return
        principled = self._principled_node(node_tree)
        if principled is None:
            return
        self._set_node_input_default(principled, ("Metallic",), 0.0)
        self._set_node_input_default(principled, ("Roughness",), 0.82 if material_def.shader == "bump" else 0.68)
        self._set_node_input_default(principled, ("Specular IOR Level", "Specular"), 0.28)
        self._set_node_input_default(principled, ("Alpha",), material.diffuse_color[3])
        base_color = tuple(float(channel) for channel in material.diffuse_color[:4])
        self._set_node_input_default(principled, ("Base Color",), base_color)
        blend = (material_def.blend or "none").strip().lower()
        if blend in {"alpha", "blend", "test"} or material.diffuse_color[3] < 0.999:
            material.blend_method = "BLEND" if blend in {"alpha", "blend"} else "CLIP"
            material.use_screen_refraction = False
            material.show_transparent_back = True
            if blend == "test" and material_def.alpharef is not None:
                alpha_threshold = float(material_def.alpharef)
                if alpha_threshold > 1.0:
                    alpha_threshold /= 255.0
                material.alpha_threshold = max(0.0, min(1.0, alpha_threshold))

    def _principled_node(self, node_tree: bpy.types.NodeTree) -> bpy.types.Node | None:
        return next((node for node in node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)

    def _set_node_input_default(self, node: bpy.types.Node, names: tuple[str, ...], value) -> None:
        for name in names:
            socket = node.inputs.get(name)
            if socket is None or not hasattr(socket, "default_value"):
                continue
            try:
                socket.default_value = value
            except (TypeError, ValueError):
                continue
            return

    def _attach_goh_material_textures(self, material: bpy.types.Material, material_def: MaterialDef) -> None:
        material.use_nodes = True
        node_tree = material.node_tree
        if node_tree is None:
            return
        principled = self._principled_node(node_tree)
        if principled is None:
            return

        diffuse_node = self._texture_node(node_tree, material_def.diffuse_texture or material_def.simple_texture, colorspace="sRGB")
        if diffuse_node is not None:
            base_output = diffuse_node.outputs.get("Color")
            if base_output is not None and "Base Color" in principled.inputs:
                node_tree.links.new(base_output, principled.inputs["Base Color"])

        specular_node = self._texture_node(node_tree, material_def.specular_texture, colorspace="Non-Color")
        if specular_node is not None:
            specular_output = self._grayscale_texture_output(node_tree, specular_node)
            if specular_output is not None:
                specular_socket = principled.inputs.get("Specular IOR Level") or principled.inputs.get("Specular")
                if specular_socket is not None:
                    node_tree.links.new(specular_output, specular_socket)

        normal_node = self._texture_node(node_tree, material_def.bump_texture, colorspace="Non-Color")
        if normal_node is not None and "Normal" in principled.inputs:
            try:
                normal_map = node_tree.nodes.new(type="ShaderNodeNormalMap")
                if "Strength" in normal_map.inputs:
                    normal_map.inputs["Strength"].default_value = 1.0
                node_tree.links.new(normal_node.outputs["Color"], normal_map.inputs["Color"])
                node_tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
            except Exception as exc:
                self.warnings.append(f'Material "{material.name}" could not link normal map: {exc}')

    def _texture_node(
        self,
        node_tree: bpy.types.NodeTree,
        texture_name: str | None,
        *,
        colorspace: str,
    ) -> bpy.types.Node | None:
        if not texture_name:
            return None
        image_path = self._resolve_texture_path(texture_name)
        if image_path is None:
            self.warnings.append(f'Texture "{texture_name}" was not found near "{self.input_path.name}".')
            return None
        try:
            image = bpy.data.images.load(str(image_path), check_existing=True)
        except RuntimeError:
            self.warnings.append(f'Texture "{texture_name}" could not be loaded by Blender.')
            return None
        try:
            image.colorspace_settings.name = colorspace
        except TypeError:
            pass
        tex_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        tex_node.image = image
        tex_node.label = texture_name
        return tex_node

    def _grayscale_texture_output(
        self,
        node_tree: bpy.types.NodeTree,
        texture_node: bpy.types.Node,
    ) -> bpy.types.NodeSocket | None:
        try:
            rgb_to_bw = node_tree.nodes.new(type="ShaderNodeRGBToBW")
            node_tree.links.new(texture_node.outputs["Color"], rgb_to_bw.inputs["Color"])
            return rgb_to_bw.outputs["Val"]
        except Exception as exc:
            self.warnings.append(f"Could not convert GOH specular texture to grayscale: {exc}")
            return None

    def _resolve_asset_path(self, file_name: str) -> Path | None:
        raw = Path(file_name.replace("\\", "/"))
        candidates = [raw] if raw.is_absolute() else [self.input_dir / raw, self.input_dir / raw.name]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _resolve_texture_path(self, texture_name: str) -> Path | None:
        raw = Path(texture_name.replace("\\", "/"))
        extensions = ("", ".dds", ".tga", ".png", ".jpg", ".jpeg")
        search_dirs = [
            self.input_dir,
            self.input_dir / "texture",
            self.input_dir / "textures",
            self.input_dir.parent / "texture",
            self.input_dir.parent / "textures",
        ]
        candidates: list[Path] = []
        if raw.is_absolute():
            candidates.extend(raw.with_suffix(ext) if ext and not raw.suffix else raw for ext in extensions)
        else:
            for search_dir in search_dirs:
                for ext in extensions:
                    candidates.append(search_dir / (raw.with_suffix(ext) if ext and not raw.suffix else raw))
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _link_object(self, obj: bpy.types.Object) -> None:
        collection = self.root_collection or self.context.scene.collection
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)
        self.imported_objects.append(obj)

    def _ensure_child_collection(self, name: str, parent: bpy.types.Collection) -> bpy.types.Collection:
        existing = parent.children.get(name)
        if existing is not None:
            return existing
        collection = bpy.data.collections.new(name)
        parent.children.link(collection)
        return collection

    def _set_parent_and_matrix(
        self,
        obj: bpy.types.Object,
        parent: bpy.types.Object | None,
        local_matrix: Matrix,
        *,
        display_matrix: Matrix | None = None,
    ) -> None:
        applied_matrix = display_matrix if display_matrix is not None else local_matrix
        obj.parent = parent
        if parent is None:
            obj.matrix_world = applied_matrix
        else:
            obj.matrix_parent_inverse = Matrix.Identity(4)
            obj.matrix_local = applied_matrix
        self._store_rest_local_matrix(obj, local_matrix)

    def _store_rest_local_matrix(self, obj: bpy.types.Object, local_matrix: Matrix) -> None:
        obj["goh_rest_matrix_local"] = [
            float(local_matrix[row][column])
            for row in range(4)
            for column in range(4)
        ]

    def _decode_matrix_rows(self, matrix_rows: tuple[tuple[float, float, float], ...]) -> Matrix:
        axis3 = self.axis_rotation.to_3x3()
        rotation = Matrix((matrix_rows[0], matrix_rows[1], matrix_rows[2]))
        converted_rotation = axis3.inverted() @ rotation @ axis3
        location = axis3.inverted() @ Vector(matrix_rows[3])
        if abs(self.scale_factor) > EPSILON:
            location /= self.scale_factor
        return Matrix.Translation(location) @ converted_rotation.to_4x4()

    def _decode_point(self, point: tuple[float, float, float]) -> Vector:
        converted = self.axis_rotation.to_3x3().inverted() @ Vector(point)
        if abs(self.scale_factor) > EPSILON:
            converted /= self.scale_factor
        return Vector((converted.x, converted.y, converted.z))

    def _decode_direction(self, direction: tuple[float, float, float]) -> Vector:
        converted = self.axis_rotation.to_3x3().inverted() @ Vector(direction)
        if converted.length > EPSILON:
            converted.normalize()
        return Vector((converted.x, converted.y, converted.z))

    def _decode_length(self, value: float) -> float:
        if abs(self.scale_factor) <= EPSILON:
            return float(value)
        return float(value) / self.scale_factor

    def _axis_rotation_matrix(self, axis_mode: str) -> Matrix:
        if axis_mode == "GOH_TO_BLENDER":
            return Matrix.Rotation(-math.pi / 2.0, 4, "Z")
        return Matrix.Identity(4)

    def _identity_matrix_rows(self) -> tuple[tuple[float, float, float], ...]:
        return (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),
        )
