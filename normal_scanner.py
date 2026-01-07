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
        fixed_count = 0
        meshes_fixed = []
        
        # Store original selection and active object
        original_selection = [obj for obj in context.selected_objects]
        original_active = context.active_object
        
        # Deselect all objects first
        bpy.ops.object.select_all(action='DESELECT')
        
        def has_texture_in_material(material):
            """Check if a material uses any texture nodes"""
            if not material or not material.use_nodes or not material.node_tree:
                return False
            
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    return True
            return False
        
        # Check all mesh objects
        for obj in context.scene.objects:
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
                # Select the object
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                # Enter Edit mode
                bpy.ops.object.mode_set(mode='EDIT')
                
                # Select all faces
                bpy.ops.mesh.select_all(action='SELECT')
                
                # Add UV coordinates using Smart UV Project
                bpy.ops.uv.smart_project(
                    angle_limit=66.0,
                    island_margin=0.0,
                    user_area_weight=0.0,
                    use_aspect=True,
                    stretch_to_bounds=False
                )
                
                # Return to Object mode
                bpy.ops.object.mode_set(mode='OBJECT')
                
                # Deselect
                obj.select_set(False)
                
                fixed_count += 1
                meshes_fixed.append(obj.name)
        
        # Restore original selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selection:
            obj.select_set(True)
        if original_active:
            context.view_layer.objects.active = original_active
        
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
        layout.label(text="glTF Export Tools:", icon='EXPORT')
        layout.operator("object.fix_uv_coordinates", icon='UV_DATA')

# Register classes
classes = [SCAN_OT_normal_maps_popup, SCAN_OT_normal_maps, SCAN_OT_remove_normal_maps, SCAN_OT_fix_uv_coordinates, SCAN_PT_panel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
