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

        # Loop through all materials
        for mat in bpy.data.materials:
            if mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'NORMAL_MAP':
                        # Check connected texture nodes
                        for input_name, input in node.inputs.items():
                            if input.is_linked:
                                from_node = input.links[0].from_node
                                if from_node.type == 'TEX_IMAGE' and from_node.image:
                                    normal_maps.add(from_node.image.name)

        # Report results
        if normal_maps:
            message = f"Normal maps found: {', '.join(normal_maps)}"
            self.report({'INFO'}, message)
            print("\n--- Normal Maps in Scene ---")
            for nm in normal_maps:
                print(" -", nm)
        else:
            self.report({'INFO'}, "No normal maps found in the scene")
            print("No normal maps found in the scene")

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

# Register classes
classes = [SCAN_OT_normal_maps, SCAN_PT_panel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
