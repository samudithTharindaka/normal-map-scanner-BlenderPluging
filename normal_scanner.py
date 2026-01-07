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
            message = f"Normal maps found: {', '.join(normal_maps)}"
            self.report({'INFO'}, message)
            print("\n--- Normal Maps in Scene ---")
            for nm in normal_maps:
                print(" -", nm)

            if material_usage:
                print("\n--- Materials Using Normal Maps ---")
                for mat_name, textures in material_usage:
                    print(f"{mat_name}:")
                    for tex in textures:
                        print(f"   - {tex}")
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

# Register classes
    classes = [SCAN_OT_normal_maps, SCAN_OT_remove_normal_maps, SCAN_PT_panel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
