import bpy
import bmesh
import math

bl_info = {
    "name": "UV Cell Snap",
    "description": "Moves selected UV islands to a grid cell",
    "author": "Cyrill Vitkovskiy",
    "version": (0, 0, 1),
    "blender": (4, 3, 2),
    "location": "View3D",
    "category": "Mesh"
}


class UVCellSnapPreferences(bpy.types.AddonPreferences):
    """Preferences for the UV Cell Snap addon."""

    uv_channel: bpy.props.StringProperty(name="UV Channel", default="ch3")
    grid_columns: bpy.props.IntProperty(name="Columns", default=4, min=1)
    grid_rows: bpy.props.IntProperty(name="Rows", default=2, min=1)

    bl_idname = "uv_cell_snap"

    def draw(self, context):
        """Draw the addon preferences UI."""
        layout = self.layout
        layout.prop(self, "uv_channel")
        layout.prop(self, "grid_columns")
        layout.prop(self, "grid_rows")


class UVCellSnapOperator(bpy.types.Operator):
    """Snap selected UV islands to a grid"""
    bl_idname = "uv.cell_snap"
    bl_label = "Snap UVs to Grid"
    bl_options = {'REGISTER', 'UNDO'}

    cell_index: bpy.props.IntProperty(name="Cell Index", default=0, min=0)

    def execute(self, context):
        """Snap selected UV islands to the specified grid cell."""
        prefs = context.preferences.addons[__name__].preferences
        columns = prefs.grid_columns
        rows = prefs.grid_rows
        grid_x = [i / columns for i in range(columns)]
        grid_y = [1.0 - i / rows for i in range(rows)]  # Reverse Y for UV space

        # Determine row and column from cell index
        max_cells = columns * rows
        if self.cell_index >= max_cells:
            self.report({'ERROR'}, "Cell index out of bounds")
            return {'CANCELLED'}

        row = self.cell_index // columns
        column = self.cell_index % columns

        target_x = grid_x[column] + 1 / (2 * columns)  # Center of cell
        target_y = grid_y[row] - 1 / (2 * rows)

        # Iterate over selected objects
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            # Switch to edit mode and perform the UV snapping
            bpy.context.view_layer.objects.active = obj

            mesh = obj.data
            bm = bmesh.from_edit_mesh(mesh)

            uv_layer = bm.loops.layers.uv.get(prefs.uv_channel)
            if uv_layer is None:
                self.report({'ERROR'}, f"UV channel '{prefs.uv_channel}' not found")
                bpy.ops.object.mode_set(mode='OBJECT')
                return {'CANCELLED'}

            # Get selected faces and their UV coordinates
            islands = []
            processed_faces = set()

            def are_uvs_connected(face1, face2, uv_layer):
                """Check if two faces share any UV coordinates."""
                for loop1 in face1.loops:
                    for loop2 in face2.loops:
                        if (loop1[uv_layer].uv - loop2[uv_layer].uv).length < 0.001:
                            return True
                return False

            def get_uv_island(start_face, uv_layer):
                """Find all faces connected to the start face in UV space."""
                island_faces = {start_face}
                to_process = {start_face}

                while to_process:
                    face = to_process.pop()
                    for edge in face.edges:
                        for linked_face in edge.link_faces:
                            if (linked_face.select and
                                linked_face not in island_faces and
                                linked_face not in processed_faces and
                                are_uvs_connected(face, linked_face, uv_layer)):
                                island_faces.add(linked_face)
                                to_process.add(linked_face)

                return island_faces

            # Find all islands
            for face in bm.faces:
                if face.select and face not in processed_faces:
                    island_faces = get_uv_island(face, uv_layer)
                    processed_faces.update(island_faces)
                    
                    # Collect UVs for the island
                    island_uvs = []
                    for island_face in island_faces:
                        island_uvs.extend([loop[uv_layer].uv for loop in island_face.loops])
                    islands.append(island_uvs)

            if not islands:
                self.report({'WARNING'}, "No selected UVs found")
                # bpy.ops.object.mode_set(mode='OBJECT')
                # return {'CANCELLED'}

            # Move each island
            for island in islands:
                bbox_min = [math.inf, math.inf]
                bbox_max = [-math.inf, -math.inf]

                for uv in island:
                    bbox_min[0] = min(bbox_min[0], uv.x)
                    bbox_min[1] = min(bbox_min[1], uv.y)
                    bbox_max[0] = max(bbox_max[0], uv.x)
                    bbox_max[1] = max(bbox_max[1], uv.y)

                center_x = (bbox_min[0] + bbox_max[0]) / 2
                center_y = (bbox_min[1] + bbox_max[1]) / 2

                offset_x = target_x - center_x
                offset_y = target_y - center_y

                for uv in island:
                    uv.x += offset_x
                    uv.y += offset_y

            bmesh.update_edit_mesh(mesh)

        return {'FINISHED'}


class UVCellSnapOffset(bpy.types.Operator):
    """Offset selected UV islands"""
    bl_idname = "uv.cell_snap_offset"
    bl_label = "Offset UVs within grid"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.StringProperty(name="Offset Direction", default="up")
    # offset_x: bpy.props.FloatProperty(name="Offset U", default=0.25)
    # offset_y: bpy.props.FloatProperty(name="Offset V", default=0.5)

    def execute(self, context):
        """Offset selected UV islands in the specified direction within the grid."""
        prefs = context.preferences.addons[__name__].preferences
        # Iterate over selected objects
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            # Switch to edit mode and perform the UV snapping
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT')

            mesh = obj.data
            bm = bmesh.from_edit_mesh(mesh)

            uv_layer = bm.loops.layers.uv.get(prefs.uv_channel)
            if uv_layer is None:
                self.report({'ERROR'}, f"UV channel '{prefs.uv_channel}' not found")
                bpy.ops.object.mode_set(mode='OBJECT')
                return {'CANCELLED'}

            # Get selected faces and their UV coordinates
            islands = []
            processed_faces = set()

            def are_uvs_connected(face1, face2, uv_layer):
                """Check if two faces share any UV coordinates."""
                for loop1 in face1.loops:
                    for loop2 in face2.loops:
                        if (loop1[uv_layer].uv - loop2[uv_layer].uv).length < 0.001:
                            return True
                return False

            def get_uv_island(start_face, uv_layer):
                """Find all faces connected to the start face in UV space."""
                island_faces = {start_face}
                to_process = {start_face}

                while to_process:
                    face = to_process.pop()
                    for edge in face.edges:
                        for linked_face in edge.link_faces:
                            if (linked_face.select and
                                linked_face not in island_faces and
                                linked_face not in processed_faces and
                                are_uvs_connected(face, linked_face, uv_layer)):
                                island_faces.add(linked_face)
                                to_process.add(linked_face)

                return island_faces

            # Find all islands
            for face in bm.faces:
                if face.select and face not in processed_faces:
                    island_faces = get_uv_island(face, uv_layer)
                    processed_faces.update(island_faces)
                    
                    # Collect UVs for the island
                    island_uvs = []
                    for island_face in island_faces:
                        island_uvs.extend([loop[uv_layer].uv for loop in island_face.loops])
                    islands.append(island_uvs)

            if not islands:
                self.report({'WARNING'}, "No selected UVs found")
                # bpy.ops.object.mode_set(mode='OBJECT')
                # return {'CANCELLED'}

            # Move each island
            for island in islands:
                bbox_min = [math.inf, math.inf]
                bbox_max = [-math.inf, -math.inf]

                for uv in island:
                    bbox_min[0] = min(bbox_min[0], uv.x)
                    bbox_min[1] = min(bbox_min[1], uv.y)
                    bbox_max[0] = max(bbox_max[0], uv.x)
                    bbox_max[1] = max(bbox_max[1], uv.y)

                center_x = (bbox_min[0] + bbox_max[0]) / 2
                center_y = (bbox_min[1] + bbox_max[1]) / 2

                # Clamp the step sizes before applying them
                clamped_offset_x = max(0, min(1, 1/prefs.grid_columns))
                clamped_offset_y = max(0, min(1, 1/prefs.grid_rows))

                for uv in island:
                    if self.direction == "up" and center_y + clamped_offset_y < 1:
                        uv.y += clamped_offset_y
                    elif self.direction == "down" and center_y - clamped_offset_y > 0:
                        uv.y -= clamped_offset_y
                    elif self.direction == "right" and center_x + clamped_offset_x < 1:
                        uv.x += clamped_offset_x
                    elif self.direction == "left" and center_x - clamped_offset_x > 0:
                        uv.x -= clamped_offset_x
                    else:
                        continue

            bmesh.update_edit_mesh(mesh, loop_triangles=True)

        return {'FINISHED'}


class UVCellSnapPanel(bpy.types.Panel):
    """Creates a UI panel for UV Cell Snap"""
    bl_label = "UV Cell Snap"
    bl_idname = "UV_PT_cell_snap"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "UV"

    @classmethod
    def poll(cls, context):
        """Only show in UV Editor when in edit mode."""
        return context.mode == 'EDIT_MESH'

    def draw(self, context):
        """Draw the UV Cell Snap panel UI elements."""
        layout = self.layout
        prefs = context.preferences.addons[__name__].preferences

        for row in range(prefs.grid_rows):
            row_layout = layout.row()
            for col in range(prefs.grid_columns):
                index = row * prefs.grid_columns + col
                row_layout.operator("uv.cell_snap", text=str(index+1)).cell_index = index

        directions = ["up", "down", "left", "right"]
        arrows = ["TRIA_UP", "TRIA_DOWN", "TRIA_LEFT", "TRIA_RIGHT"]

        grid = layout.grid_flow(
            row_major=True,
            columns=4,
            even_columns=True,
            even_rows=True,
            align=True
        )

        for direction, arrow in zip(directions, arrows):
            grid.operator("uv.cell_snap_offset", text="", icon=arrow).direction = direction

        row = layout.row()
        row.prop(prefs, "uv_channel")


class VIEW3D_PT_UVCellSnap(bpy.types.Panel):
    """Creates a UI panel for UV Cell Snap in the 3D View"""
    bl_label = "UV Cell Snap"
    bl_idname = "VIEW3D_PT_cell_snap"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "UV"

    @classmethod
    def poll(cls, context):
        """Only show in 3D View when in edit mode."""
        return context.mode == 'EDIT_MESH'

    def draw(self, context):
        """Draw the UV Cell Snap panel UI elements."""
        layout = self.layout
        prefs = context.preferences.addons[__name__].preferences

        for row in range(prefs.grid_rows):
            row_layout = layout.row()
            for col in range(prefs.grid_columns):
                index = row * prefs.grid_columns + col
                row_layout.operator("uv.cell_snap", text=str(index+1)).cell_index = index

        directions = ["up", "down", "left", "right"]
        arrows = ["TRIA_UP", "TRIA_DOWN", "TRIA_LEFT", "TRIA_RIGHT"]

        grid = layout.grid_flow(
            row_major=True,
            columns=4,
            even_columns=True,
            even_rows=True,
            align=True
        )

        for direction, arrow in zip(directions, arrows):
            grid.operator("uv.cell_snap_offset", text="", icon=arrow).direction = direction

        row = layout.row()
        row.prop(prefs, "uv_channel")


class UVCellSnapMenu(bpy.types.Menu):
    """Popup menu for selecting UV cell"""
    bl_idname = "UV_MT_cell_snap_menu"
    bl_label = "Snap UVs to Cell"

    def draw(self, context):
        """Draw the popup menu for selecting UV grid cells."""
        layout = self.layout
        prefs = context.preferences.addons[__name__].preferences

        for row in range(prefs.grid_rows):
            row_layout = layout.row()
            for col in range(prefs.grid_columns):
                index = row * prefs.grid_columns + col
                row_layout.operator("uv.cell_snap", text=str(index)).cell_index = index


# Registering the Operator, Panel, Preferences, and Shortcut
classes = [
    UVCellSnapPreferences,
    UVCellSnapOperator,
    UVCellSnapPanel,
    UVCellSnapMenu,
    UVCellSnapOffset,
    VIEW3D_PT_UVCellSnap
]

def register():
    """Register the addon classes and operators."""
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    """Unregister the addon classes and operators."""
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
