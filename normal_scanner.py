bl_info = {
    "name": "Normal Map Scanner",
    "author": "Samudith",
    "version": (1, 0),
    "blender": (3, 5, 0),
    "location": "View3D > Sidebar > Normal Map Scanner",
    "description": "Lists all textures used as normal maps in the scene",
    "category": "Material"
}

import bpy

# Popup operator to display scan results
class SCAN_OT_normal_maps_popup(bpy.types.Operator):
    bl_idname = "scan.normal_maps_popup"
    bl_label = "Normal Map Scan Results"
    bl_options = {'INTERNAL'}

    normal_maps: bpy.props.StringProperty()
    material_usage: bpy.props.StringProperty()

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        
        # Parse the data
        import json
        try:
            normal_maps = json.loads(self.normal_maps) if self.normal_maps else []
            material_usage = json.loads(self.material_usage) if self.material_usage else []
        except:
            normal_maps = []
            material_usage = []
        
        # Show normal maps list
        col.label(text=f"Normal Maps Found ({len(normal_maps)}):", icon='TEXTURE')
        box = col.box()
        for nm in sorted(normal_maps):
            box.label(text=f"  • {nm}")
        
        # Show materials using normal maps
        if material_usage:
            col.separator()
            col.label(text=f"Materials Using Normal Maps ({len(material_usage)}):", icon='MATERIAL')
            box = col.box()
            for mat_name, textures in sorted(material_usage, key=lambda x: x[0]):
                box.label(text=f"  {mat_name}:", icon='MATERIAL_DATA')
                for tex in textures:
                    box.label(text=f"    → {tex}")

# Operator to scan normal maps
class SCAN_OT_normal_maps(bpy.types.Operator):
    bl_idname = "object.scan_normal_maps"
    bl_label = "Scan Normal Maps"
    bl_description = "List all textures used as normal maps in the scene"

    def execute(self, context):
        normal_maps = set()
        material_usage = []  # (material name, set of texture names)

        # Loop through all materials
        for mat in bpy.data.materials:
            if mat.node_tree:
                mat_normals = set()
                for node in mat.node_tree.nodes:
                    if node.type == 'NORMAL_MAP':
                        # Check connected texture nodes
                        for input_name, input in node.inputs.items():
                            if input.is_linked:
                                from_node = input.links[0].from_node
                                if from_node.type == 'TEX_IMAGE' and from_node.image:
                                    tex_name = from_node.image.name
                                    normal_maps.add(tex_name)
                                    mat_normals.add(tex_name)

                if mat_normals:
                    material_usage.append((mat.name, sorted(mat_normals)))

        # Report results
        if normal_maps:
            # Build report message with materials
            message = f"Found {len(normal_maps)} normal map(s)"
            if material_usage:
                message += f" in {len(material_usage)} material(s)"
            self.report({'INFO'}, message)
            
            print("\n--- Normal Maps in Scene ---")
            for nm in sorted(normal_maps):
                print(" -", nm)

            if material_usage:
                print("\n--- Materials Using Normal Maps ---")
                for mat_name, textures in material_usage:
                    print(f"{mat_name}:")
                    for tex in textures:
                        print(f"   - {tex}")

            # Show a popup so results are visible without checking the console
            import json
            # Store data temporarily for the popup
            normal_maps_list = sorted(list(normal_maps))
            material_usage_list = material_usage
            
            # Use a timer to show popup after operator finishes
            def show_popup():
                bpy.ops.scan.normal_maps_popup(
                    'INVOKE_DEFAULT',
                    normal_maps=json.dumps(normal_maps_list),
                    material_usage=json.dumps(material_usage_list)
                )
                return None  # Timer runs once
            
            bpy.app.timers.register(show_popup, first_interval=0.01)
        else:
            self.report({'INFO'}, "No normal maps found in the scene")
            print("No normal maps found in the scene")

        return {'FINISHED'}


# Operator to remove normal maps
class SCAN_OT_remove_normal_maps(bpy.types.Operator):
    bl_idname = "object.remove_normal_maps"
    bl_label = "Remove Normal Maps"
    bl_description = "Remove normal map textures from all materials in the scene"

    def execute(self, context):
        removed_maps = set()
        removed_nodes = 0
        removed_links = 0

        for mat in bpy.data.materials:
            if not mat.use_nodes or not mat.node_tree:
                continue

            node_tree = mat.node_tree
            links_to_remove = []
            nodes_to_remove = []

            for node in list(node_tree.nodes):
                if node.type != 'NORMAL_MAP':
                    continue

                # Collect incoming links from image textures feeding this normal map
                color_input = node.inputs.get('Color')
                if color_input:
                    for link in list(color_input.links):
                        links_to_remove.append(link)
                        from_node = link.from_node
                        if from_node and from_node.type == 'TEX_IMAGE' and from_node.image:
                            removed_maps.add(from_node.image.name)

                # Collect outgoing links from the normal output
                normal_output = node.outputs.get('Normal')
                if normal_output:
                    for link in list(normal_output.links):
                        links_to_remove.append(link)

                nodes_to_remove.append(node)

            for link in links_to_remove:
                node_tree.links.remove(link)
                removed_links += 1

            for node in nodes_to_remove:
                node_tree.nodes.remove(node)
                removed_nodes += 1

        if removed_nodes:
            msg = f"Removed {removed_nodes} normal map node(s), {removed_links} link(s)"
            if removed_maps:
                msg += f"; textures: {', '.join(sorted(removed_maps))}"
            self.report({'INFO'}, msg)
            print("\n--- Removed Normal Maps ---")
            print(msg)
        else:
            self.report({'INFO'}, "No normal maps to remove")
            print("No normal maps to remove")

        return {'FINISHED'}

# Operator to fix UV coordinates for glTF export
class SCAN_OT_fix_uv_coordinates(bpy.types.Operator):
    bl_idname = "object.fix_uv_coordinates"
    bl_label = "Fix UV Coordinates for glTF"
    bl_description = "Add UV coordinates to meshes that have textured materials but no UV mapping"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import bmesh
        from mathutils import Vector
        
        fixed_count = 0
        meshes_fixed = []
        
        def has_texture_in_material(material):
            """Check if a material uses any texture nodes"""
            if not material or not material.use_nodes or not material.node_tree:
                return False
            
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    return True
            return False
        
        def add_box_uv(mesh):
            """Add simple box projection UV coordinates to a mesh"""
            # Skip empty meshes
            if len(mesh.polygons) == 0 or len(mesh.vertices) == 0:
                return False
            
            # Create UV layer if it doesn't exist
            if not mesh.uv_layers:
                mesh.uv_layers.new(name="UVMap")
            
            uv_layer = mesh.uv_layers.active.data
            
            # Simple box projection based on face normals
            for poly in mesh.polygons:
                normal = poly.normal
                
                # Determine dominant axis for projection
                abs_normal = [abs(normal.x), abs(normal.y), abs(normal.z)]
                max_axis = abs_normal.index(max(abs_normal))
                
                for loop_idx in poly.loop_indices:
                    loop = mesh.loops[loop_idx]
                    vert = mesh.vertices[loop.vertex_index]
                    co = vert.co
                    
                    # Project based on dominant axis
                    if max_axis == 0:  # X dominant - project on YZ
                        uv = (co.y, co.z)
                    elif max_axis == 1:  # Y dominant - project on XZ
                        uv = (co.x, co.z)
                    else:  # Z dominant - project on XY
                        uv = (co.x, co.y)
                    
                    uv_layer[loop_idx].uv = uv
            return True
        
        # Check all mesh objects
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            
            mesh = obj.data
            needs_uv = False
            
            # Check if mesh has UV coordinates
            has_uv = len(mesh.uv_layers) > 0
            
            # Check if any material uses textures
            if obj.data.materials:
                for mat in obj.data.materials:
                    if has_texture_in_material(mat):
                        needs_uv = True
                        break
            
            # If material has textures but mesh has no UV, add UV coordinates
            if needs_uv and not has_uv:
                try:
                    if add_box_uv(mesh):
                        fixed_count += 1
                        meshes_fixed.append(obj.name)
                except Exception as e:
                    print(f"Failed to add UV to {obj.name}: {e}")
        
        # Report results
        if fixed_count > 0:
            self.report({'INFO'}, f"Fixed UV coordinates for {fixed_count} mesh(es)")
            print(f"\n--- Fixed UV Coordinates ---")
            print(f"Successfully added UV coordinates to {fixed_count} mesh(es):")
            for name in meshes_fixed:
                print(f"  - {name}")
        else:
            self.report({'INFO'}, "All meshes already have UV coordinates")
            print("All meshes already have UV coordinates or don't need them")
        
        return {'FINISHED'}

# Operator to fix image dimensions for glTF export
class SCAN_OT_fix_image_dimensions(bpy.types.Operator):
    bl_idname = "object.fix_image_dimensions"
    bl_label = "Fix Image Dimensions for glTF"
    bl_description = "Resize images to power-of-2 dimensions for glTF compatibility"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        fixed_count = 0
        images_fixed = []
        
        def nearest_power_of_2(n):
            """Find the nearest power of 2 to n"""
            if n <= 0:
                return 1
            # Find lower and upper power of 2
            lower = 1
            while lower * 2 <= n:
                lower *= 2
            upper = lower * 2
            # Return the closer one
            if n - lower < upper - n:
                return lower
            return upper
        
        def is_power_of_2(n):
            """Check if n is a power of 2"""
            return n > 0 and (n & (n - 1)) == 0
        
        # Check all images
        for img in bpy.data.images:
            # Skip internal images
            if img.name in ["Render Result", "Viewer Node"]:
                continue
            
            width, height = img.size[0], img.size[1]
            
            # Skip if already valid (power of 2 or square)
            if width == 0 or height == 0:
                continue
            
            needs_fix = False
            new_width = width
            new_height = height
            
            # Check if dimensions need fixing
            if not is_power_of_2(width):
                new_width = nearest_power_of_2(width)
                needs_fix = True
            
            if not is_power_of_2(height):
                new_height = nearest_power_of_2(height)
                needs_fix = True
            
            if needs_fix:
                try:
                    # Scale the image
                    img.scale(new_width, new_height)
                    fixed_count += 1
                    images_fixed.append(f"{img.name}: {width}x{height} -> {new_width}x{new_height}")
                except Exception as e:
                    print(f"Failed to resize {img.name}: {e}")
        
        # Report results
        if fixed_count > 0:
            self.report({'INFO'}, f"Fixed {fixed_count} image(s) dimensions")
            print(f"\n--- Fixed Image Dimensions ---")
            print(f"Resized {fixed_count} image(s) to power-of-2 dimensions:")
            for info in images_fixed:
                print(f"  - {info}")
        else:
            self.report({'INFO'}, "All images already have valid dimensions")
            print("All images already have power-of-2 dimensions")
        
        return {'FINISHED'}

# Operator to remove unused textures/images
class SCAN_OT_remove_unused_textures(bpy.types.Operator):
    bl_idname = "object.remove_unused_textures"
    bl_label = "Remove Unused Textures"
    bl_description = "Remove all textures/images that are not used in any material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed_count = 0
        removed_images = []
        
        # Get all images used in materials
        used_images = set()
        
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        used_images.add(node.image.name)
        
        # Find and remove unused images
        images_to_remove = []
        for img in bpy.data.images:
            # Skip internal images
            if img.name in ["Render Result", "Viewer Node"]:
                continue
            
            if img.name not in used_images:
                images_to_remove.append(img)
        
        # Remove unused images
        for img in images_to_remove:
            removed_images.append(img.name)
            bpy.data.images.remove(img)
            removed_count += 1
        
        # Report results
        if removed_count > 0:
            self.report({'INFO'}, f"Removed {removed_count} unused texture(s)")
            print(f"\n--- Removed Unused Textures ---")
            print(f"Removed {removed_count} unused texture(s):")
            for name in removed_images:
                print(f"  - {name}")
        else:
            self.report({'INFO'}, "No unused textures found")
            print("No unused textures found")
        
        return {'FINISHED'}

# Operator to remove unused materials
class SCAN_OT_remove_unused_materials(bpy.types.Operator):
    bl_idname = "object.remove_unused_materials"
    bl_label = "Remove Unused Materials"
    bl_description = "Remove all materials that are not assigned to any mesh object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed_count = 0
        removed_materials = []
        
        # Get all materials used in mesh objects
        used_materials = set()
        
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data.materials:
                for mat in obj.data.materials:
                    if mat:
                        used_materials.add(mat.name)
        
        # Find and remove unused materials
        materials_to_remove = []
        for mat in bpy.data.materials:
            if mat.name not in used_materials:
                materials_to_remove.append(mat)
        
        # Remove unused materials
        for mat in materials_to_remove:
            removed_materials.append(mat.name)
            bpy.data.materials.remove(mat)
            removed_count += 1
        
        # Report results
        if removed_count > 0:
            self.report({'INFO'}, f"Removed {removed_count} unused material(s)")
            print(f"\n--- Removed Unused Materials ---")
            print(f"Removed {removed_count} unused material(s):")
            for name in removed_materials:
                print(f"  - {name}")
        else:
            self.report({'INFO'}, "No unused materials found")
            print("No unused materials found")
        
        return {'FINISHED'}

# Operator to pack images and export as FBX
class SCAN_OT_export_fbx_with_textures(bpy.types.Operator):
    bl_idname = "object.export_fbx_with_textures"
    bl_label = "Export FBX with Textures"
    bl_description = "Pack all images and export as FBX with textures"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Filepath used for exporting the FBX file",
        maxlen=1024,
        default="",
        subtype='FILE_PATH'
    )
    
    def invoke(self, context, event):
        # Set default filename
        if not self.filepath:
            blend_filepath = bpy.data.filepath
            if blend_filepath:
                import os
                filepath = os.path.splitext(blend_filepath)[0] + ".fbx"
            else:
                filepath = "untitled.fbx"
            self.filepath = filepath
        
        # Open file browser
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        import os
        
        # Get directory and base name for FBX file
        fbx_dir = os.path.dirname(self.filepath)
        fbx_basename = os.path.splitext(os.path.basename(self.filepath))[0]
        
        # Create textures folder next to FBX file
        textures_dir = os.path.join(fbx_dir, fbx_basename + "_textures")
        os.makedirs(textures_dir, exist_ok=True)
        
        saved_count = 0
        saved_images = []
        
        # Get all images used in materials
        used_images = set()
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        used_images.add(node.image)
        
        # Save all used images to disk
        print("\n=== Saving Images to Disk ===")
        for img in used_images:
            if img.name in ["Render Result", "Viewer Node"]:
                continue
            
            if not img.has_data:
                continue
            
            try:
                # Create safe filename
                safe_name = "".join(c for c in img.name if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                
                # Determine file extension based on original format or default to PNG
                if img.filepath:
                    ext = os.path.splitext(img.filepath)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.tga', '.bmp']:
                        file_ext = ext
                    else:
                        file_ext = '.png'
                else:
                    # Default to PNG if no filepath
                    file_ext = '.png'
                
                # If image is packed, unpack it first
                if img.packed_file:
                    img.unpack(method='USE_ORIGINAL')
                
                # Save image to textures folder
                texture_path = os.path.join(textures_dir, safe_name + file_ext)
                
                # Ensure unique filename
                counter = 1
                original_path = texture_path
                while os.path.exists(texture_path):
                    name_part = os.path.splitext(original_path)[0]
                    texture_path = f"{name_part}_{counter}{file_ext}"
                    counter += 1
                
                # Set image filepath and format
                img.filepath = texture_path
                if file_ext in ['.jpg', '.jpeg']:
                    img.file_format = 'JPEG'
                elif file_ext == '.png':
                    img.file_format = 'PNG'
                elif file_ext == '.tga':
                    img.file_format = 'TARGA'
                
                # Save the image
                img.save()
                
                saved_count += 1
                saved_images.append(os.path.basename(texture_path))
                print(f"Saved: {os.path.basename(texture_path)}")
                
            except Exception as e:
                print(f"Failed to save {img.name}: {e}")
        
        if saved_count > 0:
            self.report({'INFO'}, f"Saved {saved_count} texture(s) to disk")
            print(f"Saved {saved_count} texture(s) to: {textures_dir}")
        
        # Export as FBX
        print(f"\n=== Exporting FBX ===")
        print(f"Exporting to: {self.filepath}")
        
        try:
            # Export FBX with textures
            bpy.ops.export_scene.fbx(
                filepath=self.filepath,
                check_existing=True,
                filter_glob="*.fbx",
                use_selection=False,
                use_active_collection=False,
                global_scale=1.0,
                apply_unit_scale=True,
                apply_scale_options='FBX_SCALE_NONE',
                use_space_transform=True,
                bake_space_transform=False,
                object_types={'MESH', 'ARMATURE', 'EMPTY', 'OTHER'},
                use_mesh_modifiers=True,
                use_mesh_modifiers_render=True,
                mesh_smooth_type='OFF',
                use_subsurf=False,
                use_mesh_edges=False,
                use_tspace=False,
                use_custom_props=False,
                add_leaf_bones=True,
                primary_bone_axis='Y',
                secondary_bone_axis='X',
                use_armature_deform_only=False,
                armature_nodetype='NULL',
                bake_anim=True,
                bake_anim_use_all_bones=True,
                bake_anim_use_nla_strips=True,
                bake_anim_use_all_actions=True,
                bake_anim_force_startend_keying=True,
                bake_anim_step=1.0,
                bake_anim_simplify_factor=1.0,
                path_mode='COPY',  # Copy textures relative to FBX
                embed_textures=False,  # Don't embed, use external files
                batch_mode='OFF',
                use_batch_own_dir=True,
                use_metadata=True
            )
            
            self.report({'INFO'}, f"Exported FBX with {saved_count} texture(s)")
            print(f"✓ Successfully exported FBX!")
            print(f"✓ Textures saved to: {textures_dir}")
            print(f"  Keep the '{fbx_basename}_textures' folder with the FBX file!")
            
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            print(f"✗ Export failed: {e}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

# UI Panel
class SCAN_PT_panel(bpy.types.Panel):
    bl_label = "Normal Map Scanner"
    bl_idname = "SCAN_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scanner"

    def draw(self, context):
        layout = self.layout
        layout.operator("object.scan_normal_maps")
        layout.operator("object.remove_normal_maps")
        
        layout.separator()
        layout.label(text="Cleanup Tools:", icon='BRUSH_DATA')
        layout.operator("object.remove_unused_textures", icon='TRASH')
        layout.operator("object.remove_unused_materials", icon='MATERIAL_DATA')
        
        layout.separator()
        layout.label(text="Export Tools:", icon='EXPORT')
        layout.operator("object.export_fbx_with_textures", icon='EXPORT')
        
        layout.separator()
        layout.label(text="glTF Export Tools:", icon='EXPORT')
        layout.operator("object.fix_uv_coordinates", icon='UV_DATA')
        layout.operator("object.fix_image_dimensions", icon='IMAGE_DATA')

# Register classes
classes = [SCAN_OT_normal_maps_popup, SCAN_OT_normal_maps, SCAN_OT_remove_normal_maps, SCAN_OT_fix_uv_coordinates, SCAN_OT_fix_image_dimensions, SCAN_OT_remove_unused_textures, SCAN_OT_remove_unused_materials, SCAN_OT_export_fbx_with_textures, SCAN_PT_panel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
