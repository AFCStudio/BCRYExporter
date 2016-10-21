# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####
#
#------------------------------------------------------------------------------
# Name:        __init__.py
# Purpose:     Primary python file for BCry Exporter add-on
#
# Author:      Özkan Afacan,
#              Angelo J. Miner, Mikołaj Milej, Daniel White,
#              Oscar Martin Garcia, David Marcelis, Duo Oratar
#
# Created:     23/02/2012
# Copyright:   (c) Angelo J. Miner 2012
# Copyright:   (c) Özkan Afacan 2016
# License:     GPLv2+
#------------------------------------------------------------------------------


bl_info = {
    "name": "BCry Exporter",
    "author": "Özkan Afacan, Angelo J. Miner, Mikołaj Milej, Daniel White, "
              "Oscar Martin Garcia, Duo Oratar, David Marcelis",
    "blender": (2, 70, 0),
    "version": (5, 0, 0),
    "location": "BCRY Exporter Menu",
    "description": "Export assets from Blender to CryEngine 3",
    "warning": "",
    "wiki_url": "https://github.com/AFCStudio/BCryExporter/wiki",
    "tracker_url": "https://github.com/AFCStudio/BCryExporter/issues",
    "support": 'OFFICIAL',
    "category": "Import-Export"}

# old wiki url: http://wiki.blender.org/
# index.php/Extensions:2.5/Py/Scripts/Import-Export/CryEngine3

VERSION = '.'.join(str(n) for n in bl_info["version"])


if "bpy" in locals():
    import imp
    imp.reload(export)
    imp.reload(exceptions)
    imp.reload(udp)
    imp.reload(utils)
    imp.reload(material_utils)
    imp.reload(desc)
else:
    import bpy
    from io_bcry_exporter import export, export_animations, exceptions, udp, utils, material_utils, desc

from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, \
    FloatProperty, IntProperty, StringProperty, BoolVectorProperty
from bpy.types import Menu, Panel
from bpy_extras.io_utils import ExportHelper
from io_bcry_exporter.configuration import Configuration
from io_bcry_exporter.outpipe import bcPrint
from io_bcry_exporter.desc import list
from xml.dom.minidom import Document, Element, parse, parseString
import bpy.utils.previews
import bmesh
import bpy.ops
import bpy_extras
import configparser
import os
import os.path
import pickle
import webbrowser
import subprocess
import math


new = 2  # For help -> Open in a new tab, if possible.


#------------------------------------------------------------------------------
# Configurations:
#------------------------------------------------------------------------------

class PathSelectTemplate(ExportHelper):
    check_existing = True

    def execute(self, context):
        self.process(self.filepath)

        Configuration.save()
        return {'FINISHED'}


class FindRC(bpy.types.Operator, PathSelectTemplate):
    '''Select the Resource Compiler executable.'''

    bl_label = "Find The Resource Compiler"
    bl_idname = "file.find_rc"

    filename_ext = ".exe"

    def process(self, filepath):
        Configuration.rc_path = filepath
        bcPrint("Found RC at {!r}.".format(Configuration.rc_path), 'debug')

    def invoke(self, context, event):
        self.filepath = Configuration.rc_path

        return ExportHelper.invoke(self, context, event)


class FindRCForTextureConversion(bpy.types.Operator, PathSelectTemplate):
    '''Select if you are using RC from cryengine \
newer than 3.4.5. Provide RC path from cryengine 3.4.5 \
to be able to export your textures as dds files.'''

    bl_label = "Find the Resource Compiler for Texture Conversion"
    bl_idname = "file.find_rc_for_texture_conversion"

    filename_ext = ".exe"

    def process(self, filepath):
        Configuration.texture_rc_path = filepath
        bcPrint("Found RC at {!r}.".format(
            Configuration.texture_rc_path),
            'debug')

    def invoke(self, context, event):
        self.filepath = Configuration.texture_rc_path

        return ExportHelper.invoke(self, context, event)


class SelectGameDirectory(bpy.types.Operator, PathSelectTemplate):
    '''This path will be used to create relative path \
for textures in .mtl file.'''

    bl_label = "Select Game Directory"
    bl_idname = "file.select_game_dir"

    filename_ext = ""

    def process(self, filepath):
        if not os.path.isdir(filepath):
            raise exceptions.NoGameDirectorySelected

        Configuration.game_dir = filepath
        bcPrint("Game directory: {!r}.".format(
            Configuration.game_dir),
            'debug')

    def invoke(self, context, event):
        self.filepath = Configuration.game_dir

        return ExportHelper.invoke(self, context, event)


class SaveBCryConfiguration(bpy.types.Operator):
    '''operator: Saves current BCry Exporter configuration.'''
    bl_label = "Save Config File"
    bl_idname = "config.save"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        Configuration.save()
        return {'FINISHED'}


#------------------------------------------------------------------------------
# Export Tools:
#------------------------------------------------------------------------------

class AddCryExportNode(bpy.types.Operator):
    '''Add selected objects to an existing or new CryExportNode'''
    bl_label = "Add Export Node"
    bl_idname = "object.add_cry_export_node"
    bl_options = {"REGISTER", "UNDO"}

    node_type = EnumProperty(
        name="Type",
        items=(
            ("cgf", "CGF",
             "Static Geometry"),
            ("cga", "CGA",
             "Animated Geometry"),
            ("chr", "CHR",
             "Character"),
            ("skin", "SKIN",
             "Skinned Render Mesh"),
        ),
        default="cgf",
    )
    node_name = StringProperty(name="Name")

    def __init__(self):
        bpy.ops.object.mode_set(mode='OBJECT')
        object_ = bpy.context.active_object
        self.node_name = object_.name
        self.node_type = 'cgf'

        if object_.type != 'MESH':
            self.report(
                {'ERROR'},
                "Selected object is not a mesh! Please select a mesh object.")
            return {'FINISHED'}

        if object_.parent and object_.parent.type == 'ARMATURE':
            if len(object_.data.vertices) <= 4:
                self.node_type = 'chr'
                self.node_name = object_.parent.name
            else:
                self.node_type = 'skin'
        elif object_.animation_data:
            self.node_type = 'cga'

    def execute(self, context):
        if bpy.context.selected_objects:
            scene = bpy.context.scene
            node_name = "{}.{}".format(self.node_name, self.node_type)
            group = bpy.data.groups.get(node_name)
            if group is None:
                bpy.ops.group.create(name=node_name)
            else:
                for object in bpy.context.selected_objects:
                    if object.name not in group.objects:
                        group.objects.link(object)
            message = "Adding Export Node"
        else:
            message = "No Objects Selected"

        self.report({"INFO"}, message)
        return {"FINISHED"}

    def invoke(self, context, event):
        if len(context.selected_objects) == 0:
            self.report(
                {'ERROR'},
                "Select one or more objects in OBJECT mode.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


class AddCryAnimationNode(bpy.types.Operator):
    '''Add animation node to selected armature or object'''
    bl_label = "Add Animation Node"
    bl_idname = "object.add_cry_animation_node"
    bl_options = {"REGISTER", "UNDO"}

    node_type = EnumProperty(
        name="Type",
        items=(
            ("anm", "ANM",
             "Geometry Animation"),
            ("i_caf", "I_CAF",
             "Character Animation"),
        ),
        default="i_caf",
    )
    node_name = StringProperty(name="Animation Name")
    range_type = EnumProperty(
        name="Range Type",
        items=(
            ("Timeline", "Timeline Editor",
             desc.list['range_timeline']),
            ("Values", "Limit with Values",
             desc.list['range_values']),
            ("Markers", "Limit with Markers",
             desc.list['range_markers']),
        ),
        default="Timeline",
    ) 
    node_start = IntProperty(name="Start Frame")
    node_end = IntProperty(name="End Frame")
    start_m_name = StringProperty(name="Marker Start Name")
    end_m_name = StringProperty(name="Marker End Name")

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "node_type")
        col.prop(self, "node_name")
        col.separator()
        col.label("Range Type:")

        col.prop(self, "range_type", expand=True)
        col.separator()
        col.separator()

        col.label("Animation Range Values:")
        col.prop(self, "node_start")
        col.prop(self, "node_end")
        col.separator()
        col.separator()

        col.label("Animation Range Markers:")
        col.prop(self, "start_m_name")
        col.prop(self, "end_m_name")

    def __init__(self):
        bpy.ops.object.mode_set(mode='OBJECT')

        self.node_start = bpy.context.scene.frame_start
        self.node_end = bpy.context.scene.frame_end

        if bpy.context.active_object.type == 'ARMATURE':
            self.node_type = 'i_caf'
        else:
            self.node_type = 'anm'

        tm = bpy.context.scene.timeline_markers
        for marker in tm:
            if marker.select:
                self.start_m_name = marker.name
                self.end_m_name = "{}_E".format(marker.name)
                self.is_use_markers = True

                self.node_start = marker.frame
                if tm.find(self.end_m_name) != -1:
                    self.node_end = tm[self.end_m_name].frame

                self.node_name = marker.name
                break

        return None

    def execute(self, context):
        object_ = bpy.context.active_object
        if object_:
            node_start = None
            node_end = None

            start_name = "{}_Start".format(self.node_name)
            end_name = "{}_End".format(self.node_name)

            if self.range_type == 'Values':
                node_start = self.node_start
                node_end = self.node_end

                object_[start_name] = node_start
                object_[end_name] = node_end

            elif self.range_type == 'Markers':
                node_start = self.start_m_name
                node_end = self.end_m_name

                tm = bpy.context.scene.timeline_markers
                if tm.find(self.start_m_name) == -1:
                    tm.new(name=self.start_m_name, frame=self.node_start)
                if tm.find(self.end_m_name) == -1:
                    tm.new(name=self.end_m_name, frame=self.node_end)

                object_[start_name] = node_start
                object_[end_name] = node_end

            node_name = "{}.{}".format(self.node_name, self.node_type)
            group = bpy.data.groups.get(node_name)
            if group is None:
                bpy.ops.group.create(name=node_name)
            else:
                for object in bpy.context.selected_objects:
                    if object.name not in group.objects:
                        group.objects.link(object)

            message = "Adding Export Node"
        else:
            message = "There is no a active armature! Please select a armature."

        self.report({"INFO"}, message)
        return {"FINISHED"}

    def invoke(self, context, event):
        object_ = bpy.context.active_object
        if not object_:
            self.report(
                {'ERROR'},
                "Please select and active a armature or object.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


class SelectedToCryExportNodes(bpy.types.Operator):
    '''Add selected objects to individual CryExportNodes.'''
    bl_label = "Nodes from Object Names"
    bl_idname = "object.selected_to_cry_export_nodes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected = bpy.context.selected_objects
        bpy.ops.object.select_all(action="DESELECT")
        for object_ in selected:
            object_.select = True
            if (len(object_.users_group) == 0):
                bpy.ops.group.create(name="{}.cgf".format(object_.name))
            object_.select = False

        for object_ in selected:
            object_.select = True

        message = "Adding Selected Objects to Export Nodes"
        self.report({"INFO"}, message)
        return {"FINISHED"}

    def invoke(self, context, event):
        if len(context.selected_objects) == 0:
            self.report(
                {'ERROR'},
                "Select one or more objects in OBJECT mode.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.label("Confirm...")


class ApplyTransforms(bpy.types.Operator):
    '''Click to apply transforms on selected objects.'''
    bl_label = "Apply Transforms"
    bl_idname = "object.apply_transforms"
    bl_options = {'REGISTER', 'UNDO'}

    loc = BoolProperty(name="Location", default=False)
    rot = BoolProperty(name="Rotation", default=True)
    scale = BoolProperty(name="Scale", default=True)

    def execute(self, context):
        selected = bpy.context.selected_objects
        if selected:
            message = "Applying object transforms."
            bpy.ops.object.transform_apply(
                location=self.loc, rotation=self.rot, scale=self.scale)
        else:
            message = "No Object Selected."
        self.report({'INFO'}, message)
        return {'FINISHED'}

    def invoke(self, context, event):
        if len(context.selected_objects) == 0:
            self.report(
                {'ERROR'},
                "Select one or more objects in OBJECT mode.")
            return {'FINISHED'}

        return self.execute(context)


#------------------------------------------------------------------------------
# CryEngine-Related Tools:
#------------------------------------------------------------------------------

class GenerateLODs(bpy.types.Operator):
    '''Generate LOD meshes for selected object.'''
    bl_label = "Generate LOD Meshes"
    bl_idname = "mesh.generate_lod_meshes"
    bl_options = {'REGISTER', 'UNDO'}

    lod_count = IntProperty(name="LOD Count", default=2, min=1, max=5, step=1,
                        description="LOD count to generate.")
    decimate_ratio = FloatProperty(name="Decimate Ratio", default=0.5,
                        min=0.001, max=1.000, precision=3, step=0.1,
                        description="Decimate ratio for LODs.")
    view_offset = FloatProperty(name="View Offset", default=1.5, precision=3,
                        description="View offset in scene.")

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "lod_count")
        col.prop(self, "decimate_ratio")
        col = layout.column()
        col.prop(self, "view_offset")
        col.separator()

    def __init__(self):
        object_ = bpy.context.active_object
        if not object_ or object_.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object!")
            return {'FINISHED'}

    def execute(self, context):
        object_ = bpy.context.active_object
    
        for obj in bpy.context.scene.objects:
            if object_.name != obj.name:
                obj.select = False

        node = None
        ALLOWED_NODE_TYPES = ('cgf', 'cga', 'skin')
        for group in object_.users_group:
            if utils.is_export_node(group):
                node_type = utils.get_node_type(group)
                if node_type in ALLOWED_NODE_TYPES:
                    node = group
                    break

        bpy.ops.object.duplicate()
        lod = bpy.context.active_object
        lod.location.x += self.view_offset

        bpy.ops.object.modifier_add(type='DECIMATE')
        decimate = lod.modifiers[len(lod.modifiers) - 1]
        decimate.ratio = self.decimate_ratio

        lod_name = "{}_LOD1".format(object_.name)
        lod.name = lod_name
        lod.data.name = lod_name

        for index in range(2, self.lod_count + 1):
            bpy.ops.object.duplicate()

            lod = bpy.context.active_object
            lod.location.x += self.view_offset

            decimate = lod.modifiers[len(lod.modifiers) - 1]

            decimate.ratio = self.decimate_ratio / math.pow(2, index)
            
            lod_name = "{}_LOD{}".format(object_.name, index)
            lod.name = lod_name
            lod.data.name = lod_name

        return {'FINISHED'}


class AddProxy(bpy.types.Operator):
    '''Click to add proxy to selected mesh. The proxy will always display as a box but will \
be converted to the selected shape in CryEngine.'''
    bl_label = "Add Proxy"
    bl_idname = "object.add_proxy"

    type_ = StringProperty()

    def execute(self, context):
        self.__add_proxy(bpy.context.active_object)
        message = "Adding {} proxy to active object".format(
            getattr(self, "type_"))
        self.report({'INFO'}, message)
        return {'FINISHED'}

    def __add_proxy(self, object_):
        old_origin = object_.location.copy()
        old_cursor = bpy.context.scene.cursor_location.copy()
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.mesh.primitive_cube_add()
        bound_box = bpy.context.active_object
        bound_box.name = "{}_{}-proxy".format(object_.name,
                                              getattr(self, "type_"))
        bound_box.draw_type = "WIRE"
        bound_box.dimensions = object_.dimensions
        bound_box.location = object_.location
        bound_box.rotation_euler = object_.rotation_euler
        bpy.ops.object.transform_apply(
            location=True, rotation=True, scale=True)
        bpy.ops.mesh.uv_texture_add()

        for group in object_.users_group:
            bpy.ops.object.group_link(group=group.name)

        name = "99__proxy__physProxyNoDraw"
        if name in bpy.data.materials:
            proxy_material = bpy.data.materials[name]
        else:
            proxy_material = bpy.data.materials.new(name)
        bound_box.data.materials.append(proxy_material)

        bound_box['phys_proxy'] = getattr(self, "type_")

        bpy.context.scene.cursor_location = old_origin
        bpy.ops.object.select_all(action="DESELECT")
        object_.select = True
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        object_.select = False
        bound_box.select = True
        utils.set_active(bound_box)
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        bpy.context.scene.cursor_location = old_cursor

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH" or context.object.mode != "OBJECT":
            self.report({'ERROR'}, "Select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return self.execute(context)


class AddBreakableJoint(bpy.types.Operator):
    '''Click to add a pre-broken breakable joint to current selection.'''
    bl_label = "Add Joint"
    bl_idname = "object.add_joint"

    def execute(self, context):
        # Reviewed in the future.
        #return add.add_joint(self, context)
        return None

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH" or context.object.mode != "OBJECT":
            self.report({'ERROR'}, "Select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return self.execute(context)


class AddBranch(bpy.types.Operator):
    '''Click to add a branch at active vertex or first vertex in a set of vertices.'''
    bl_label = "Add Branch"
    bl_idname = "mesh.add_branch"

    def execute(self, context):
        active_object = bpy.context.active_object
        bpy.ops.object.mode_set(mode='OBJECT')
        selected_vert_coordinates = get_vertex_data()
        if (selected_vert_coordinates):
            selected_vert = selected_vert_coordinates[0]
            bpy.ops.object.add(
                type='EMPTY',
                view_align=False,
                enter_editmode=False,
                location=(
                    selected_vert[0],
                    selected_vert[1],
                    selected_vert[2]))
            empty_object = bpy.context.active_object
            empty_object.name = name_branch(True)
            utils.set_active(active_object)
            bpy.ops.object.mode_set(mode='EDIT')

            message = "Adding Branch"
            self.report({'INFO'}, message)
            bcPrint(message)

        return {'FINISHED'}

    def invoke(self, context, event):
        if (context.object is None or context.object.type != "MESH" or
                context.object.mode != "EDIT" or not get_vertex_data()):
            self.report({'ERROR'}, "Select a vertex in EDIT mode.")
            return {'FINISHED'}

        return self.execute(context)


class AddBranchJoint(bpy.types.Operator):
    '''Click to add a branch joint at selected vertex or first vertex in a set of vertices.'''
    bl_label = "Add Branch Joint"
    bl_idname = "mesh.add_branch_joint"

    def execute(self, context):
        active_object = bpy.context.active_object
        bpy.ops.object.mode_set(mode='OBJECT')
        selected_vert_coordinates = get_vertex_data()
        if (selected_vert_coordinates):
            selected_vert = selected_vert_coordinates[0]
            bpy.ops.object.add(
                type='EMPTY',
                view_align=False,
                enter_editmode=False,
                location=(
                    selected_vert[0],
                    selected_vert[1],
                    selected_vert[2]))
            empty_object = bpy.context.active_object
            empty_object.name = name_branch(False)
            utils.set_active(active_object)
            bpy.ops.object.mode_set(mode='EDIT')

            message = "Adding Branch Joint"
            self.report({'INFO'}, message)
            bcPrint(message)

        return {'FINISHED'}

    def invoke(self, context, event):
        if (context.object is None or context.object.type != "MESH" or
                context.object.mode != "EDIT" or not get_vertex_data()):
            self.report({'ERROR'}, "Select a vertex in EDIT mode.")
            return {'FINISHED'}

        return self.execute(context)


def get_vertex_data():
    old_mode = bpy.context.active_object.mode
    bpy.ops.object.mode_set(mode="OBJECT")
    selected_vert_coordinates = [
        i.co for i in bpy.context.active_object.data.vertices if i.select]
    bpy.ops.object.mode_set(mode=old_mode)

    return selected_vert_coordinates


def name_branch(is_new_branch):
    highest_branch_number = 0
    highest_joint_number = {}
    for object in bpy.data.objects:
        if ((object.type == 'EMPTY') and ("branch" in object.name)):
            branch_components = object.name.split("_")
            if(branch_components):
                branch_name = branch_components[0]
                branch_number = int(branch_name[6:])
                joint_number = int(branch_components[1])
                if (branch_number > highest_branch_number):
                    highest_branch_number = branch_number
                    highest_joint_number[branch_number] = joint_number
                if (joint_number > highest_joint_number[branch_number]):
                    highest_joint_number[branch_number] = joint_number
    if (highest_branch_number != 0):
        if (is_new_branch):
            return "branch{}_1".format(highest_branch_number + 1)
        else:
            return "branch{}_{}".format(
                highest_branch_number,
                highest_joint_number[highest_branch_number] + 1)
    else:
        return "branch1_1"


#------------------------------------------------------------------------------
# Material Tools:
#------------------------------------------------------------------------------

class SetMaterialNames(bpy.types.Operator):
    '''Materials will be named after the first CryExportNode the Object is in.'''
    """Set Material Names by heeding the RC naming scheme:
        - CryExportNode group name
        - Strict number sequence beginning with 1 for each CryExportNode (max 999)
        - Physics
    """
    bl_label = "Update material names in CryExportNodes"
    bl_idname = "material.set_material_names"

    material_name = StringProperty(name="Cry Material Name")
    material_phys = EnumProperty(
        name="Physic Proxy",
        items=(
            ("physDefault", "Default", desc.list['physDefault']),
            ("physProxyNoDraw", "Physical Proxy", desc.list['physProxyNoDraw']),
            ("physNoCollide", "No Collide", desc.list['physNoCollide']),
            ("physObstruct", "Obstruct", desc.list['physObstruct']),
            ("physNone", "None", desc.list['physNone'])
        ),
        default="physDefault")

    just_rephysic = BoolProperty(
        name="Only Physic",
        description="Only change physic of selected material.")

    object_ = None
    errorReport = None

    def __init__(self):
        cryNodeReport = "Please select a object that in a Cry Export node" \
            + " for 'Do Material Convention'. If you have not created" \
            + " it yet, please create it with 'Add ExportNode' tool."

        self.object_ = bpy.context.active_object

        if self.object_ is None or self.object_.users_group is None:
            self.errorReport = cryNodeReport
            return None

        for group in self.object_.users_group:
            if utils.is_export_node(group):
                self.material_name = utils.get_node_name(group)
                return None

        self.errorReport = cryNodeReport

        return None

    def execute(self, context):
        if self.errorReport is not None:
            return {'FINISHED'}

        if self.just_rephysic:
            return material_utils.set_material_physic(self, context, self.material_phys)

        # Revert all materials to fetch also those that are no longer in a group
        # and store their possible physics properties in a dictionary.
        physicsProperties = material_utils.get_material_physics()

        # Create a dictionary with all CryExportNodes to store the current number
        # of materials in it.
        materialCounter = material_utils.get_material_counter()

        for group in self.object_.users_group:
            if utils.is_export_node(group):
                for object in group.objects:
                    for slot in object.material_slots:

                        # Skip materials that have been renamed already.
                        if not material_utils.is_bcry_material(slot.material.name):
                            materialCounter[group.name] += 1
                            materialOldName = slot.material.name

                            # Load stored Physics if available for that
                            # material.
                            if physicsProperties.get(slot.material.name):
                                physics = physicsProperties[slot.material.name]
                            else:
                                physics = self.material_phys

                            # Rename.
                            slot.material.name = "{}__{:02d}__{}__{}".format(
                                self.material_name,
                                materialCounter[group.name],
                                utils.replace_invalid_rc_characters(materialOldName),
                                physics)
                            message = "Renamed {} to {}".format(
                                materialOldName,
                                slot.material.name)
                            self.report({'INFO'}, message)
                            bcPrint(message)
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.errorReport is not None:
            return self.report({'ERROR'}, self.errorReport)

        return context.window_manager.invoke_props_dialog(self)


class RemoveMaterialNames(bpy.types.Operator):
    '''Removes all BCry Exporter properties from material names. This includes \
physics, so they get lost.'''
    bl_label = "Remove BCry Exporter properties from material names"
    bl_idname = "material.remove_material_names"

    def execute(self, context):
        material_utils.remove_bcry_properties()
        message = "Removed BCry Exporter properties from material names"
        self.report({'INFO'}, message)
        bcPrint(message)
        return {'FINISHED'}


class AddMaterial(bpy.types.Operator):
    '''Add material to node'''
    bl_label = "Add Material to Node"
    bl_idname = "material.add_cry_material"
    bl_options = {"REGISTER", "UNDO"}

    material_name = StringProperty(name="Material")

    physics_type = EnumProperty(
        name="Physics",
        items=(
            ("physDefault", "Default", list['physDefault']),
            ("physProxyNoDraw", "Proxy", list['physProxyNoDraw']),
            ("physNoCollide", "Collide", list['physNoCollide']),
            ("physObstruct", "Obstruct", list['physObstruct']),
            ("physNone", "None", list['physNone']),
        ),
        default="physDefault",
    )

    def execute(self, context):
        if bpy.context.selected_objects:
            materials = {}
            for _object in bpy.context.selected_objects:
                if (len(_object.users_group) > 0):
                    # get cryexport group
                    node_name = _object.users_group[0].name
                    # get material for this group
                    if node_name not in materials:
                        index = len(material_utils.get_materials_per_group(node_name)) + 1
                        # generate new material
                        material = bpy.data.materials.new(
                            "{}__{:03d}__{}__{}".format(
                                node_name.split(".")[0],
                                index, self.material_name, self.physics_type
                            )
                        )
                        materials[node_name] = material
                    _object.data.materials.append(material)
                else:
                    # ignoring object without group
                    bcPrint("Object " + _object.name +
                            " not assigned to any group")
            message = "Assigned material"
        else:
            message = "No Objects Selected"

        self.report({"INFO"}, message)
        return {"FINISHED"}

    def invoke(self, context, event):
        if len(context.selected_objects) == 0:
            self.report(
                {'ERROR'},
                "Select one or more objects in OBJECT mode.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


class GenerateMaterials(bpy.types.Operator, ExportHelper):
    '''Generate material files for CryEngine.'''
    bl_label = "Generate Maetrials"
    bl_idname = "material.generate_materials"
    filename_ext = ".mtl"
    filter_glob = StringProperty(default="*.mtl", options={'HIDDEN'})

    export_selected_nodes = BoolProperty(
        name="Just Selected Nodes",
        description="Generate material files just for selected nodes.",
        default=False,
    )
    convert_textures = BoolProperty(
        name="Convert Textures",
        description="Converts source textures to DDS while generating materials.",
        default=False,
    )
    
    merge_all_nodes = True
    make_layer = False

    class Config:

        def __init__(self, config):
            attributes = (
                'filepath',
                'export_selected_nodes',
                'convert_textures'
            )

            for attribute in attributes:
                setattr(self, attribute, getattr(config, attribute))

            setattr(self, 'bcry_version', VERSION)
            setattr(self, 'rc_path', Configuration.rc_path)
            setattr(self, 'texture_rc_path', Configuration.texture_rc_path)
            setattr(self, 'game_dir', Configuration.game_dir)

    def execute(self, context):
        bcPrint(Configuration.rc_path, 'debug')
        try:
            config = GenerateMaterials.Config(config=self)
        
            material_utils.generate_mtl_files(config)

            self.filepath = '//'

        except exceptions.BCryException as exception:
            bcPrint(exception.what(), 'error')
            bpy.ops.screen.display_error(
                'INVOKE_DEFAULT', message=exception.what())

        return {'FINISHED'}

    def invoke(self, context, event):
        if not Configuration.configured():
            self.report({'ERROR'}, "No RC found.")
            return {'FINISHED'}

        if not utils.get_export_nodes():
            self.report({'ERROR'}, "No export nodes found.")
            return {'FINISHED'}

        return ExportHelper.invoke(self, context, event)

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        box = col.box()
        box.label("Generate Materials", icon="MATERIAL")
        box.prop(self, "export_selected_nodes")
        box.prop(self, "convert_textures")


#------------------------------------------------------------------------------
# (UDP) Inverse Kinematics:
#------------------------------------------------------------------------------


class EditInverseKinematics(bpy.types.Operator):
    '''Edit inverse kinematics properties for selected bone.'''
    bl_label = "Edit Inverse Kinematics of Selected Bone"
    bl_idname = "object.edit_inverse_kinematics"

    info = "Force this bone proxy to be a {} primitive in the engine."

    proxy_type = EnumProperty(
        name="Physic Proxy",
        items=(
            ("box", "Box", info.format('Box')),
            ("cylinder", "Cylinder", info.format('Cylinder')),
            ("capsule", "Capsule", info.format('Capsule')),
            ("sphere", "Sphere", info.format('Sphere'))
        ),
        default="capsule")

    is_rotation_lock = BoolVectorProperty(
        name="Rotation Lock  [X, Y, Z]:",
        description="Bone Rotation Lock X, Y, Z")

    rotation_min = bpy.props.IntVectorProperty(
        name="Rot Limit Min:", description="Bone Rotation Minimum Limit X, Y, Z", default=(
            -180, -180, -180), min=-180, max=0)
    rotation_max = bpy.props.IntVectorProperty(
        name="Rot Limit Max:",
        description="Bone Rotation Maximum Limit X, Y, Z",
        default=(
            180,
            180,
            180),
        min=0,
        max=180)

    bone_spring = FloatVectorProperty(
        name="Spring  [X, Y, Z]:",
        description=desc.list['spring'],
        default=(
            0.0,
            0.0,
            0.0),
        min=0.0,
        max=1.0)

    bone_spring_tension = FloatVectorProperty(
        name="Spring Tension  [X, Y, Z]:",
        description=desc.list['spring'],
        default=(
            1.0,
            1.0,
            1.0),
        min=-3.14159,
        max=3.14159)

    bone_damping = FloatVectorProperty(
        name="Damping  [X, Y, Z]:",
        description=desc.list['damping'],
        default=(
            1.0,
            1.0,
            1.0),
        min=0.0,
        max=1.0)

    bone = None

    def __init__(self):
        armature = bpy.context.active_object
        if armature is None or armature.type != "ARMATURE":
            return None

        if bpy.context.active_pose_bone:
            self.bone = bpy.context.active_pose_bone
        else:
            return None

        try:
            self.proxy_type = self.bone['phys_proxy']
        except:
            pass

        self.is_rotation_lock[0] = self.bone.lock_ik_x
        self.is_rotation_lock[1] = self.bone.lock_ik_y
        self.is_rotation_lock[2] = self.bone.lock_ik_z

        self.rotation_min[0] = math.degrees(self.bone.ik_min_x)
        self.rotation_min[1] = math.degrees(self.bone.ik_min_y)
        self.rotation_min[2] = math.degrees(self.bone.ik_min_z)

        self.rotation_max[0] = math.degrees(self.bone.ik_max_x)
        self.rotation_max[1] = math.degrees(self.bone.ik_max_y)
        self.rotation_max[2] = math.degrees(self.bone.ik_max_z)

        try:
            self.bone_spring = self.bone['Spring']
            self.bone_spring_tension = self.bone['Spring Tension']
            self.bone_damping = self.bone['Damping']
        except:
            pass

        return None

    def execute(self, context):
        if self.bone is None:
            bcPrint("Please select a bone in pose mode!")
            return {'FINISHED'}

        self.bone['phys_proxy'] = self.proxy_type

        self.bone.lock_ik_x = self.is_rotation_lock[0]
        self.bone.lock_ik_y = self.is_rotation_lock[1]
        self.bone.lock_ik_z = self.is_rotation_lock[2]

        self.bone.ik_min_x = math.radians(self.rotation_min[0])
        self.bone.ik_min_y = math.radians(self.rotation_min[1])
        self.bone.ik_min_z = math.radians(self.rotation_min[2])

        self.bone.ik_max_x = math.radians(self.rotation_max[0])
        self.bone.ik_max_y = math.radians(self.rotation_max[1])
        self.bone.ik_max_z = math.radians(self.rotation_max[2])

        self.bone['Spring'] = self.bone_spring
        self.bone['Spring Tension'] = self.bone_spring_tension
        self.bone['Damping'] = self.bone_damping

        return {'FINISHED'}

    def invoke(self, context, event):
        if (context.object is None or context.object.type != "ARMATURE" or
                context.object.mode != "POSE" or self.bone is None):
            self.report({'ERROR'}, "Please select a bone in POSE mode!")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


class ApplyAnimationScale(bpy.types.Operator):
    '''Select to apply animation skeleton scaling and rotation'''
    bl_label = "Apply Animation Scaling"
    bl_idname = "ops.apply_animation_scaling"

    def execute(self, context):
        utils.apply_animation_scale(bpy.context.active_object)
        return {'FINISHED'}

    def invoke(self, context, event):
        if context.object is None or context.object.type != "ARMATURE" or context.object.mode != "OBJECT":
            self.report({'ERROR'}, "Select an armature in OBJECT mode.")
            return {'FINISHED'}

        return self.execute(context)


#------------------------------------------------------------------------------
# (UDP) Physics Proxy:
#------------------------------------------------------------------------------

class EditPhysicProxy(bpy.types.Operator):
    '''Edit Physic Proxy Properties for selected object.'''
    bl_label = "Edit physic proxy properties of active object."
    bl_idname = "object.edit_physics_proxy"

    ''' "phys_proxy", "colltype_player", "no_explosion_occlusion", "wheel" '''

    is_proxy = BoolProperty(
        name="Use Physic Proxy",
        description="If you want to use physic proxy properties. Please enable this.")

    info = "Force this proxy to be a {} primitive in the engine."

    proxy_type = EnumProperty(
        name="Physic Proxy",
        items=(
            ("box", "Box", info.format('Box')),
            ("cylinder", "Cylinder", info.format('Cylinder')),
            ("capsule", "Capsule", info.format('Capsule')),
            ("sphere", "Sphere", info.format('Sphere')),
            ("notaprim", "Not a primitive", desc.list['notaprim'])
        ),
        default="box")

    no_exp_occlusion = BoolProperty(name="No Explosion Occlusion",
                                    description=desc.list['no_exp_occlusion'])
    colltype_player = BoolProperty(name="Colltype Player",
                                   description=desc.list['colltpye_player'])
    wheel = BoolProperty(name="Wheel", description="Wheel for vehicles.")

    object_ = None

    def __init__(self):
        self.object_ = bpy.context.active_object

        if self.object_ is None:
            return None

        self.proxy_type, self.is_proxy = udp.get_udp(
            self.object_, "phys_proxy", self.proxy_type, self.is_proxy)
        self.no_exp_occlusion = udp.get_udp(
            self.object_,
            "no_explosion_occlusion",
            self.no_exp_occlusion)
        self.colltype_player = udp.get_udp(
            self.object_, "colltype_player", self.colltype_player)
        self.wheel = udp.get_udp(self.object_, "wheel", self.wheel)

        return None

    def execute(self, context):
        if self.object_ is None:
            bcPrint("Please select a object.")
            return {'FINISHED'}

        udp.edit_udp(
            self.object_,
            "phys_proxy",
            self.proxy_type,
            self.is_proxy)
        udp.edit_udp(
            self.object_,
            "no_explosion_occlusion",
            "no_explosion_occlusion",
            self.no_exp_occlusion)
        udp.edit_udp(
            self.object_,
            "colltype_player",
            "colltype_player",
            self.colltype_player)
        udp.edit_udp(self.object_, "wheel", "wheel", self.wheel)

        return {'FINISHED'}

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH":
            self.report({'ERROR'}, "Select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


#------------------------------------------------------------------------------
# (UDP) Render Mesh:
#------------------------------------------------------------------------------

class EditRenderMesh(bpy.types.Operator):
    '''Edit Render Mesh Properties for selected object.'''
    bl_label = "Edit render mesh properties of active object."
    bl_idname = "object.edit_render_mesh"

    ''' "entity", "mass", "density", "pieces", "dynamic", "no_hit_refinement" '''

    is_entity = BoolProperty(name="Entity", description=desc.list['is_entity'])

    info = "If you want to use {} property. Please enable this."

    is_mass = BoolProperty(name="Use Mass", description=info.format('mass'))
    mass = FloatProperty(name="Mass", description=desc.list['mass'])

    is_density = BoolProperty(
        name="Use Density",
        description=info.format('density'))
    density = FloatProperty(name="Density", description=desc.list['density'])

    is_pieces = BoolProperty(
        name="Use Pieces",
        description=info.format('pieces'))
    pieces = FloatProperty(name="Pieces", description=desc.list['pieces'])

    is_dynamic = BoolProperty(
        name="Dynamic",
        description=desc.list['is_dynamic'])

    no_hit_refinement = BoolProperty(
        name="No Hit Refinement",
        description=desc.list['no_hit_refinement'])

    other_rendermesh = BoolProperty(name="Other Rendermesh",
                                    description=desc.list['other_rendermesh'])

    object_ = None

    def __init__(self):
        self.object_ = bpy.context.active_object

        if self.object_ is None:
            return None

        self.mass, self.is_mass = udp.get_udp(self.object_,
                                              "mass", self.mass, self.is_mass)
        self.density, self.is_density = udp.get_udp(
            self.object_, "density", self.density, self.is_density)
        self.pieces, self.is_pieces = udp.get_udp(
            self.object_, "pieces", self.pieces, self.is_pieces)
        self.no_hit_refinement = udp.get_udp(
            self.object_, "no_hit_refinement", self.no_hit_refinement)
        self.other_rendermesh = udp.get_udp(
            self.object_, "other_rendermesh", self.other_rendermesh)

        self.is_entity = udp.get_udp(self.object_, "entity", self.is_entity)
        self.is_dynamic = udp.get_udp(self.object_, "dynamic", self.is_dynamic)

        return None

    def execute(self, context):
        if self.object_ is None:
            bcPrint("Please select a object.")
            return {'FINISHED'}

        udp.edit_udp(self.object_, "entity", "entity", self.is_entity)
        udp.edit_udp(self.object_, "mass", self.mass, self.is_mass)
        udp.edit_udp(self.object_, "density", self.density, self.is_density)
        udp.edit_udp(self.object_, "pieces", self.pieces, self.is_pieces)
        udp.edit_udp(self.object_, "dynamic", "dynamic", self.is_dynamic)
        udp.edit_udp(
            self.object_,
            "no_hit_refinement",
            "no_hit_refinement",
            self.no_hit_refinement)
        udp.edit_udp(
            self.object_,
            "other_rendermesh",
            "other_rendermesh",
            self.other_rendermesh)

        return {'FINISHED'}

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH":
            self.report({'ERROR'}, "Select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


#------------------------------------------------------------------------------
# (UDP) Joint Node:
#------------------------------------------------------------------------------

class EditJointNode(bpy.types.Operator):
    '''Edit Joint Node Properties for selected joint.'''
    bl_label = "Edit joint node properties of active object."
    bl_idname = "object.edit_joint_node"

    ''' "limit", "bend", "twist", "pull", "push",
        "shift", "player_can_break", "gameplay_critical" '''

    info = "If you want to use {} joint property. Please enable this."

    is_limit = BoolProperty(name="Use Limit Property",
                            description=info.format('limit'))
    limit = FloatProperty(name="Limit", description=desc.list['limit'])

    is_bend = BoolProperty(name="Use Bend Property",
                           description=info.format('bend'))
    bend = FloatProperty(name="Bend", description=desc.list['bend'])

    is_twist = BoolProperty(name="Use Twist Property",
                            description=info.format('twist'))
    twist = FloatProperty(name="Twist", description=desc.list['twist'])

    is_pull = BoolProperty(name="Use Pull Property",
                           description=info.format('pull'))
    pull = FloatProperty(name="Pull", description=desc.list['pull'])

    is_push = BoolProperty(name="Use Psuh Property",
                           description=info.format('push'))
    push = FloatProperty(name="Push", description=desc.list['push'])

    is_shift = BoolProperty(name="Use Shift Property",
                            description=info.format('shift'))
    shift = FloatProperty(name="Shift", description=desc.list['shift'])

    player_can_break = BoolProperty(name="Player can break",
                                    description=desc.list['player_can_break'])

    gameplay_critical = BoolProperty(
        name="Gameplay critical",
        description=desc.list['gameplay_critical'])

    object_ = None

    def __init__(self):
        self.object_ = bpy.context.active_object

        if self.object_ is None:
            return None

        self.limit, self.is_limit = udp.get_udp(
            self.object_, "limit", self.limit, self.is_limit)
        self.bend, self.is_bend = udp.get_udp(
            self.object_, "bend", self.bend, self.is_bend)
        self.twist, self.is_twist = udp.get_udp(
            self.object_, "twist", self.twist, self.is_twist)
        self.pull, self.is_pull = udp.get_udp(
            self.object_, "pull", self.pull, self.is_pull)
        self.push, self.is_push = udp.get_udp(
            self.object_, "push", self.push, self.is_push)
        self.shift, self.is_shift = udp.get_udp(
            self.object_, "shift", self.shift, self.is_shift)
        self.player_can_break = udp.get_udp(
            self.object_, "player_can_break", self.player_can_break)
        self.gameplay_critical = udp.get_udp(
            self.object_, "gameplay_critical", self.gameplay_critical)

        return None

    def execute(self, context):
        if self.object_ is None:
            bcPrint("Please select a object.")
            return {'FINISHED'}

        udp.edit_udp(self.object_, "limit", self.limit, self.is_limit)
        udp.edit_udp(self.object_, "bend", self.bend, self.is_bend)
        udp.edit_udp(self.object_, "twist", self.twist, self.is_twist)
        udp.edit_udp(self.object_, "pull", self.pull, self.is_pull)
        udp.edit_udp(self.object_, "push", self.push, self.is_push)
        udp.edit_udp(self.object_, "shift", self.shift, self.is_shift)
        udp.edit_udp(
            self.object_,
            "player_can_break",
            "player_can_break",
            self.player_can_break)
        udp.edit_udp(
            self.object_,
            "gameplay_critical",
            "gameplay_critical",
            self.gameplay_critical)

        return {'FINISHED'}

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH":
            self.report({'ERROR'}, "Select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


#------------------------------------------------------------------------------
# (UDP) Deformable:
#------------------------------------------------------------------------------

class EditDeformable(bpy.types.Operator):
    '''Edit Deformable Properties for selected skeleton mesh.'''
    bl_label = "Edit deformable properties of active skeleton mesh."
    bl_idname = "object.edit_deformable"

    ''' "stiffness", "hardness", "max_stretch", "max_impulse",
        "skin_dist", "thickness", "explosion_scale", "notaprim" '''

    info = "If you want to use {} deform property. Please enable this."

    is_stiffness = BoolProperty(name="Use Stiffness",
                                description=info.format('stiffness'))
    stiffness = FloatProperty(name="Stiffness",
                              description=desc.list['stiffness'], default=10.0)

    is_hardness = BoolProperty(name="Use Hardness",
                               description=info.format('hardness'))
    hardness = FloatProperty(name="Hardness",
                             description=desc.list['hardness'], default=10.0)

    is_max_stretch = BoolProperty(name="Use Max Stretch",
                                  description=info.format('max stretch'))
    max_stretch = FloatProperty(
        name="Max Stretch",
        description=desc.list['max_stretch'],
        default=0.01)

    is_max_impulse = BoolProperty(name="Use Max Impulse",
                                  description=info.format('max impulse'))
    max_impulse = FloatProperty(name="Max Impulse",
                                description=desc.list['max_impulse'])

    is_skin_dist = BoolProperty(name="Use Skin Dist",
                                description=info.format('skin dist'))
    skin_dist = FloatProperty(name="Skin Dist",
                              description=desc.list['skin_dist'])

    is_thickness = BoolProperty(name="Use Thickness",
                                description=info.format('thickness'))
    thickness = FloatProperty(name="Thickness",
                              description=desc.list['thickness'])

    is_explosion_scale = BoolProperty(
        name="Use Explosion Scale",
        description=info.format('explosion scale'))
    explosion_scale = FloatProperty(name="Explosion Scale",
                                    description=desc.list['explosion_scale'])

    notaprim = BoolProperty(name="Is not a primitive",
                            description=desc.list['notaprim'])

    object_ = None

    def __init__(self):
        self.object_ = bpy.context.active_object

        if self.object_ is None:
            return None

        self.stiffness, self.is_stiffness = udp.get_udp(
            self.object_, "stiffness", self.stiffness, self.is_stiffness)
        self.hardness, self.is_hardness = udp.get_udp(
            self.object_, "hardness", self.hardness, self.is_hardness)
        self.max_stretch, self.is_max_stretch = udp.get_udp(
            self.object_, "max_stretch", self.max_stretch, self.is_max_stretch)
        self.max_impulse, self.is_max_impulse = udp.get_udp(
            self.object_, "max_impulse", self.max_impulse, self.is_max_impulse)
        self.skin_dist, self.is_skin_dist = udp.get_udp(
            self.object_, "skin_dist", self.skin_dist, self.is_skin_dist)
        self.thickness, self.is_thickness = udp.get_udp(
            self.object_, "thickness", self.thickness, self.is_thickness)
        self.explosion_scale, self.is_explosion_scale = udp.get_udp(
            self.object_, "explosion_scale", self.explosion_scale, self.is_explosion_scale)

        self.notaprim = udp.get_udp(self.object_, "notaprim", self.notaprim)

        return None

    def execute(self, context):
        if self.object_ is None:
            bcPrint("Please select a object.")
            return {'FINISHED'}

        udp.edit_udp(
            self.object_,
            "stiffness",
            self.stiffness,
            self.is_stiffness)
        udp.edit_udp(self.object_, "hardness", self.hardness, self.is_hardness)
        udp.edit_udp(
            self.object_,
            "max_stretch",
            self.max_stretch,
            self.is_max_stretch)
        udp.edit_udp(
            self.object_,
            "max_impulse",
            self.max_impulse,
            self.is_max_impulse)
        udp.edit_udp(
            self.object_,
            "skin_dist",
            self.skin_dist,
            self.is_skin_dist)
        udp.edit_udp(
            self.object_,
            "thickness",
            self.thickness,
            self.is_thickness)
        udp.edit_udp(
            self.object_,
            "explosion_scale",
            self.explosion_scale,
            self.is_explosion_scale)
        udp.edit_udp(self.object_, "notaprim", "notaprim", self.notaprim)

        return {'FINISHED'}

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH":
            self.report({'ERROR'}, "Select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


#------------------------------------------------------------------------------
# (UDP) Vehicle:
#------------------------------------------------------------------------------

class FixWheelTransforms(bpy.types.Operator):
    bl_label = "Fix Wheel Transforms"
    bl_idname = "object.fix_wheel_transforms"

    def execute(self, context):
        ob = bpy.context.active_object
        ob.location.x = (ob.bound_box[0][0] + ob.bound_box[1][0]) / 2.0
        ob.location.y = (ob.bound_box[2][0] + ob.bound_box[3][0]) / 2.0
        ob.location.z = (ob.bound_box[4][0] + ob.bound_box[5][0]) / 2.0

        return {'FINISHED'}


#------------------------------------------------------------------------------
# Material Physics:
#------------------------------------------------------------------------------

class SetMaterialPhysDefault(bpy.types.Operator):
    '''The render geometry is used as physics proxy. This\
 is expensive for complex objects, so use this only for simple objects\
 like cubes or if you really need to fully physicalize an object.'''
    bl_label = "__physDefault"
    bl_idname = "material.set_phys_default"

    def execute(self, context):
        material_name = bpy.context.active_object.active_material.name
        message = "{} material physic has been set to physDefault".format(material_name)
        self.report({'INFO'}, message)
        bcPrint(message)
        return material_utils.set_material_physic(self, context, bl_label)


class SetMaterialPhysProxyNoDraw(bpy.types.Operator):
    '''Mesh is used exclusively for collision detection and is not rendered.'''
    bl_label = "__physProxyNoDraw"
    bl_idname = "material.set_phys_proxy_no_draw"

    def execute(self, context):
        material_name = bpy.context.active_object.active_material.name
        message = "{} material physic has been set to physProxyNoDraw".format(material_name)
        bcPrint(message)
        return material_utils.set_material_physic(self, context, self.bl_label)


class SetMaterialPhysNone(bpy.types.Operator):
    '''The render geometry have no physic just render it.'''
    bl_label = "__physNone"
    bl_idname = "material.set_phys_none"

    def execute(self, context):
        material_name = bpy.context.active_object.active_material.name
        message = "{} material physic has been set to physNone".format(material_name)
        bcPrint(message)
        return material_utils.set_material_physic(self, context, self.bl_label)


class SetMaterialPhysObstruct(bpy.types.Operator):
    '''Used for Soft Cover to block AI view (i.e. on dense foliage).'''
    bl_label = "__physObstruct"
    bl_idname = "material.set_phys_obstruct"

    def execute(self, context):
        material_name = bpy.context.active_object.active_material.name
        message = "{} material physic has been set to physObstruct".format(material_name)
        bcPrint(message)
        return material_utils.set_material_physic(self, context, self.bl_label)


class SetMaterialPhysNoCollide(bpy.types.Operator):
    '''Special purpose proxy which is used by the engine\
 to detect player interaction (e.g. for vegetation touch bending).'''
    bl_label = "__physNoCollide"
    bl_idname = "material.set_phys_no_collide"

    def execute(self, context):
        material_name = bpy.context.active_object.active_material.name
        message = "{} material physic has been set to physNoCollide".format(material_name)
        bcPrint(message)
        return material_utils.set_material_physic(self, context, self.bl_label)


#------------------------------------------------------------------------------
# Mesh Repair Tools:
#------------------------------------------------------------------------------

class FindDegenerateFaces(bpy.types.Operator):
    '''Select the object to test in object mode with nothing selected in \
it's mesh before running this.'''
    bl_label = "Find Degenerate Faces"
    bl_idname = "object.find_degenerate_faces"

    # Minimum face area to be considered non-degenerate
    area_epsilon = 0.000001

    def execute(self, context):
        # Deselect any vertices prevously selected in Edit mode
        saved_mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')

        # Vertices data should be actually manipulated in Object mode
        # to be displayed in Edit mode correctly.
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh = bpy.context.active_object.data

        vert_list = [vert for vert in mesh.vertices]
        context.tool_settings.mesh_select_mode = (True, False, False)
        bcPrint("Locating degenerate faces.")
        degenerate_count = 0

        for poly in mesh.polygons:
            if poly.area < self.area_epsilon:
                bcPrint("Found a degenerate face.")
                degenerate_count += 1

                for v in poly.vertices:
                    bcPrint("Selecting face vertices.")
                    vert_list[v].select = True

        if degenerate_count > 0:
            bpy.ops.object.mode_set(mode='EDIT')
            self.report({'WARNING'},
                        "Found {} degenerate faces".format(degenerate_count))
        else:
            self.report({'INFO'}, "No degenerate faces found")
            # Restore the original mode
            bpy.ops.object.mode_set(mode=saved_mode)

        return {'FINISHED'}

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH":
            self.report({'ERROR'}, "Select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return self.execute(context)


class FindMultifaceLines(bpy.types.Operator):
    '''Select the object to test in object mode with nothing selected in \
it's mesh before running this.'''
    bl_label = "Find Lines with 3+ Faces."
    bl_idname = "mesh.find_multiface_lines"

    def execute(self, context):
        mesh = bpy.context.active_object.data
        vert_list = [vert for vert in mesh.vertices]
        context.tool_settings.mesh_select_mode = (True, False, False)
        bpy.ops.object.mode_set(mode='OBJECT')
        bcPrint("Locating degenerate faces.")
        for i in mesh.edges:
            counter = 0
            for polygon in mesh.polygons:
                if (i.vertices[0] in polygon.vertices
                        and i.vertices[1] in polygon.vertices):
                    counter += 1
            if counter > 2:
                bcPrint('Found a multi-face line')
                for v in i.vertices:
                    bcPrint('Selecting line vertices.')
                    vert_list[v].select = True
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH":
            self.report({'ERROR'}, "Select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return self.execute(context)


class FindWeightless(bpy.types.Operator):
    '''Finds out unassigned vertices to any bone.'''
    bl_label = "Find Weightless Vertices"
    bl_idname = "mesh.find_weightless"

    weight_epsilon = 0.0001

    message = ""
    vert_count = 0

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(self.message)
        col.separator()
        
        if self.vert_count:
            col.separator()
            col.operator("view3d.view_selected", text="Focus")
            col.separator()

    def __init__(self):
        self.vert_count = 0

        if bpy.context.active_object is None or bpy.context.active_object.type != "MESH":
            self.report({'ERROR'}, "Please select a mesh in OBJECT mode.")
            return None

        object_ = bpy.context.active_object
        if object_.parent == None or object_.parent.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select a mesh in OBJECT mode.")
            return None

        armature = object_.parent

        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="OBJECT")
        if object_.type == "MESH":
            for v in object_.data.vertices:
                if (not v.groups):
                    v.select = True
                    self.vert_count += 1
                else:
                    weight = 0
                    for g in v.groups:
                        group_name = object_.vertex_groups[g.group].name
                        if group_name in armature.pose.bones:
                            weight += g.weight
                    if (weight < self.weight_epsilon):
                        v.select = True
        object_.data.update()

        if self.vert_count == 0:
            self.message = "Selected mesh has no any weightless vertex."
        else:
            self.message = "Selected mesh has {} weightless vertices.".format(self.vert_count)
            bpy.ops.object.mode_set(mode="EDIT")

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH":
            self.report({'ERROR'}, "Please select a mesh in OBJECT mode.")
            return {'FINISHED'}
        object_ = context.object
        if object_.parent == None or object_.parent.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select a mesh in OBJECT mode.")
            return {'FINISHED'}

        return context.window_manager.invoke_props_dialog(self)


class RemoveAllWeight(bpy.types.Operator):
    '''Select vertices from which to remove weight in edit mode.'''
    bl_label = "Remove All Weight from Selected Vertices"
    bl_idname = "mesh.remove_weight"

    def execute(self, context):
        object_ = bpy.context.active_object
        if object_.type == 'MESH':
            verts = []
            for v in object_.data.vertices:
                if v.select:
                    verts.append(v)
            for v in verts:
                for g in v.groups:
                    g.weight = 0
        return {'FINISHED'}

    def invoke(self, context, event):
        if context.object is None or context.object.type != "MESH" or context.object.mode != "EDIT":
            self.report({'ERROR'}, "Select one or more vertices in EDIT mode.")
            return {'FINISHED'}

        return self.execute(context)


class FindNoUVs(bpy.types.Operator):
    '''Use this with no objects selected in object mode \
to find all items without UVs.'''
    bl_label = "Find All Objects with No UV's"
    bl_idname = "scene.find_no_uvs"

    def execute(self, context):
        for object_ in bpy.data.objects:
            object_.select = False

        for object_ in bpy.context.selectable_objects:
            if object_.type == 'MESH' and not object_.data.uv_textures:
                object_.select = True

        return {'FINISHED'}


class AddUVTexture(bpy.types.Operator):
    '''Add UVs to all meshes without UVs.'''
    bl_label = "Add UV's to Objects"
    bl_idname = "mesh.add_uv_texture"

    def execute(self, context):
        for object_ in bpy.data.objects:
            if object_.type == 'MESH':
                uv = False
                for i in object_.data.uv_textures:
                    uv = True
                    break
                if not uv:
                    utils.set_active(object_)
                    bpy.ops.mesh.uv_texture_add()
                    message = "Added UV map to {}".format(object_.name)
                    self.report({'INFO'}, message)
                    bcPrint(message)

        return {'FINISHED'}


#------------------------------------------------------------------------------
# Bone Utilities:
#------------------------------------------------------------------------------

class AddRootBone(bpy.types.Operator):
    '''Click to add a root bone to the active armature.'''
    bl_label = "Add Root Bone"
    bl_idname = "armature.add_root_bone"
    bl_options = {'REGISTER', 'UNDO'}

    forward_direction = EnumProperty(
        name="Forward Direction",
        items=(
            ("y", "+Y",
             "The Locator Locomotion is faced to positive Y direction."),
            ("_y", "-Y",
             "The Locator Locomotion is faced to negative Y direction."),
            ("x", "+X",
             "The Locator Locomotion is faced to positive X direction."),
            ("_x", "-X",
             "The Locator Locomotion is faced to negative Y direction."),
            ("z", "+Z",
             "The Locator Locomotion is faced to positive Z direction."),
            ("_z", "-Z",
             "The Locator Locomotion is faced to negative Z direction."),
        ),
        default="y",
    )
    
    bone_length = FloatProperty(name="Bone Length", default=0.18,
                        description=desc.list['locator_length'])
    root_name = StringProperty(name="Name", default="Root")
    hips_bone = StringProperty(name="Hips Bone", default="hips")

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "forward_direction")
        col.separator()

        col.prop(self, "bone_length")
        col.separator()

        col.prop(self, "root_name")
        col.prop(self, "hips_bone")
        col.separator()

    def invoke(self, context, event):
        return self.execute(context)

    def __init__(self):
        armature = bpy.context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select a armature object!")
            return {'FINISHED'}
        elif armature.pose.bones.find('Root') != -1:
            message = "{} armature already has a Root bone!".format(armature.name)
            self.report({'INFO'}, message)
            return {'FINISHED'}

        bpy.ops.object.mode_set(mode='EDIT')
        root_bone = utils.get_root_bone(armature)
        loc = root_bone.head
        if loc.x == 0 and loc.y == 0 and loc.z == 0:
            message = "Armature already has a root/center bone!"
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.hips_bone = root_bone.name

    def execute(self, context):
        armature = bpy.context.active_object

        bpy.ops.object.mode_set(mode='EDIT')

        bpy.ops.armature.select_all(action='DESELECT')
        bpy.ops.armature.bone_primitive_add(name=self.root_name)
        root_bone = armature.data.edit_bones[self.root_name]
        for index in range(0, 32):
            root_bone.layers[index] = (index == 15)

        armature.data.layers[15] = True

        root_bone.head.zero()
        root_bone.tail.zero()
        if self.forward_direction == 'y':
            root_bone.tail.y = self.bone_length
        elif self.forward_direction == '_y':
            root_bone.tail.y = -self.bone_length
        elif self.forward_direction == 'x':
            root_bone.tail.x = self.bone_length
        elif self.forward_direction == '_x':
            root_bone.tail.x = -self.bone_length
        elif self.forward_direction == 'z':
            root_bone.tail.z = self.bone_length
        elif self.forward_direction == '_z':
            root_bone.tail.z = -self.bone_length

        armature.data.edit_bones[self.hips_bone].parent = root_bone

        bpy.ops.object.mode_set(mode='POSE')
        root_pose_bone = armature.pose.bones[self.root_name]
        root_pose_bone.bone.select = True
        armature.data.bones.active = root_pose_bone.bone
        
        bpy.ops.object.mode_set(mode="OBJECT")

        return {'FINISHED'}


class AddLocatorLocomotion(bpy.types.Operator):
    '''Add locator locomotion bone for movement in CryEngine.'''
    bl_label = "Add Locator Locomotion"
    bl_idname = "armature.add_locator_locomotion"
    bl_options = {'REGISTER', 'UNDO'}

    forward_direction = EnumProperty(
        name="Forward Direction",
        items=(
            ("y", "+Y",
             "The Locator Locomotion is faced to positive Y direction."),
            ("_y", "-Y",
             "The Locator Locomotion is faced to negative Y direction."),
            ("x", "+X",
             "The Locator Locomotion is faced to positive X direction."),
            ("_x", "-X",
             "The Locator Locomotion is faced to negative Y direction."),
            ("z", "+Z",
             "The Locator Locomotion is faced to positive Z direction."),
            ("_z", "-Z",
             "The Locator Locomotion is faced to negative Z direction."),
        ),
        default="y",
    )
    
    bone_length = FloatProperty(name="Bone Length", default=0.15,
                        description=desc.list['locator_length'])
    root_bone = StringProperty(name="Root Bone", default="Root",
                        description=desc.list['locator_root'])
    movement_bone = StringProperty(name="Movement Bone", default="hips",
                        description=desc.list['locator_move'])

    x_axis = BoolProperty(name="X Axis", default=False,
                        description="Use X axis from movement reference bone.")
    y_axis = BoolProperty(name="Y Axis", default=True,
                        description="Use Y axis from movement reference bone.")
    z_axis = BoolProperty(name="Z Axis", default=False,
                        description="Use Z axis from movement reference bone.")

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "forward_direction")
        col.separator()

        col.prop(self, "bone_length")
        col.separator()
        
        col.prop(self, "root_bone")
        col.prop(self, "movement_bone")
        col.separator()
        
        col.label("Movement Axis:")
        col.prop(self, "x_axis")
        col.prop(self, "y_axis")
        col.prop(self, "z_axis")

    def invoke(self, context, event):
        return self.execute(context)

    def __init__(self):
        armature = bpy.context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select a armature object!")
            return {'FINISHED'}
        elif armature.pose.bones.find('Locator_Locomotion') != -1:
            message = "{} armature already has a Locator Locomotion bone!".format(armature.name)
            self.report({'ERROR'}, message)
            return {'FINISHED'}

        root_bone = utils.get_root_bone(armature)
        self.root_bone = root_bone.name
        self.movement_bone = root_bone.children[0].name

    def execute(self, context):
        armature = bpy.context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select a armature object!")
            return {'FINISHED'}

        bpy.ops.object.mode_set(mode='EDIT')

        bpy.ops.armature.select_all(action='DESELECT')
        bpy.ops.armature.bone_primitive_add(name='Locator_Locomotion')
        locator_bone = armature.data.edit_bones['Locator_Locomotion']
        for index in range(0, 32):
            locator_bone.layers[index] = (index == 14)

        armature.data.layers[14] = True

        locator_bone.parent = armature.data.edit_bones[self.root_bone]
        locator_bone.head.zero()
        locator_bone.tail.zero()
        if self.forward_direction == 'y':
            locator_bone.tail.y = self.bone_length
        elif self.forward_direction == '_y':
            locator_bone.tail.y = -self.bone_length
        elif self.forward_direction == 'x':
            locator_bone.tail.x = self.bone_length
        elif self.forward_direction == '_x':
            locator_bone.tail.x = -self.bone_length
        elif self.forward_direction == 'z':
            locator_bone.tail.z = self.bone_length
        elif self.forward_direction == '_z':
            locator_bone.tail.z = -self.bone_length

        bpy.ops.object.mode_set(mode='POSE')
        locator_pose_bone = armature.pose.bones['Locator_Locomotion']
        locator_pose_bone.bone.select = True
        armature.data.bones.active = locator_pose_bone.bone

        locator_pose_bone.constraints.new(type='COPY_LOCATION')
        copy_location = locator_pose_bone.constraints['Copy Location']
        copy_location.use_x = self.x_axis
        copy_location.use_y = self.y_axis
        copy_location.use_z = self.z_axis
        copy_location.target = armature
        copy_location.subtarget = 'hips'

        return {'FINISHED'}


class AddPrimitiveMesh(bpy.types.Operator):
    '''Add primitive mesh for active skeleton.'''
    bl_label = "Add Primitive Mesh"
    bl_idname = "armature.add_primitive_mesh"
    bl_options = {'REGISTER', 'UNDO'}

    root_bone = StringProperty(name="Root Bone", default="Root",
                        description=desc.list['locator_root'])

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        col.prop(self, "root_bone")
        col.separator()

    def __init__(self):
        armature = bpy.context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select a armature object!")
            return {'FINISHED'}

        root_bone = utils.get_root_bone(armature)
        self.root_bone = root_bone.name

    def execute(self, context):
        armature = bpy.context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select a armature object!")
            return {'FINISHED'}

        bpy.ops.mesh.primitive_plane_add()
        triangle = bpy.context.active_object
        
        bm = bmesh.new()
        bm.verts.new((1.0, 1.0, 0.0))
        bm.verts.new((-1.0, -1.0, 0.0))
        bm.verts.new((1.0, -1.0, 0.0))
        
        bm.faces.new(bm.verts)
        bm.to_mesh(triangle.data)
        triangle.name = 'No_Draw'
        triangle.data.name = 'No_Draw'

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all()
        bpy.ops.object.vertex_group_assign_new()
        triangle.vertex_groups[0].name = self.root_bone
        bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.modifier_add(type='ARMATURE')
        triangle.modifiers['Armature'].object = armature
        
        triangle.parent = armature

        material_ = None
        mat_name = "{}__01__No_Draw__physProxyNoDraw".format(armature.name)

        if mat_name in bpy.data.materials:
            material_ = bpy.data.materials[mat_name]
        else:
            material_ = bpy.data.materials.new(mat_name)

        if triangle.material_slots:
            triangle.material_slots[0].material = material_
        else:
            bpy.ops.object.material_slot_add()
            if triangle.material_slots:
                triangle.material_slots[0].material = material_

        return {'FINISHED'}


class PhysicalizeSkeleton(bpy.types.Operator):
    '''Create physic skeleton and physical proxies for bones.'''
    bl_label = "Physicalize Skeleton"
    bl_idname = "armature.physicalize_skeleton"
    bl_options = {'REGISTER', 'UNDO'}
    
    physic_skeleton = BoolProperty(name='Physic Skeleton', default=True,
                            description='Creates physic skeleton.')
    physic_proxies = BoolProperty(name='Physic Proxies', default=True,
                            description='Creates physic proxies.')
    physic_proxy_settings = BoolProperty(name='Physic Proxy Settings', default=True,
                            description='Fill physic proxy settings to default.')
    physic_ik_settings = BoolProperty(name='IK Settings', default=True,
                            description='Fill IK settings to default.')

    radius_torso = FloatProperty(name='Torso Radius', default=0.12,
                            min=0.01, precision=3, step=0.1,
                            description='Torso bones radius')
    radius_head = FloatProperty(name='Head Radius', default=0.1,
                            min=0.01, precision=3, step=0.1,
                            description='Head bones radius')
    radius_arm = FloatProperty(name='Arm Radius', default=0.04,
                            min=0.01, precision=3, step=0.1,
                            description='Arm bones radius')
    radius_leg = FloatProperty(name='Leg Radius', default=0.05,
                            min=0.01, precision=3, step=0.1,
                            description='Leg bones radius')
    radius_foot = FloatProperty(name='Foot Radius', default=0.05,
                            min=0.01, precision=3, step=0.1,
                            description='Foot bones radius')
    radius_other = FloatProperty(name='Other Radius', default=0.05,
                            min=0.01, precision=3, step=0.1,
                            description='Other bones radius')

    physic_materials = BoolProperty(name='Create Physic Materials', default=True,
                            description='Creates materials for bone proxies.')
    physic_alpha = FloatProperty(name='Physic Alpha', default=0.2,
                            min=0.0, max=1.0, step=1.0,
                            description='Set physic proxy alpha value.')
    use_single_material = BoolProperty(name='Use Single Material', default=False,
                            description='Use single material for all bone proxies.')
    
    def __init__(self):
        armature = bpy.context.active_object
        if armature.type != 'ARMATURE':
            self.report({'ERROR'}, 'You have to select a armature object!')
            return {'FINISHED'}

        group = utils.get_chr_node_from_skeleton(armature)
        if not group:
            self.report({'ERROR'}, 'Your armature has to has a primitive mesh which added to a CHR node!')
            return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label("Physicalize Options:")
        col.prop(self, "physic_skeleton")
        col.prop(self, "physic_proxies")
        col.prop(self, "physic_proxy_settings")
        col.prop(self, "physic_ik_settings")
        col.separator()
        
        col.label("Physic Proxy Sizes:")
        col.prop(self, "radius_torso")
        col.prop(self, "radius_head")
        col.prop(self, "radius_arm")
        col.prop(self, "radius_leg")
        col.prop(self, "radius_foot")
        col.prop(self, "radius_other")
        col.separator()
        col.separator()

        col.label("Physic Materials:")
        col.prop(self, "physic_materials")
        col.prop(self, "physic_alpha")
        col.prop(self, "use_single_material")
        col.separator()
        col.separator()
    
    def execute(self, context):
        armature = bpy.context.active_object
        materials = {}
        physic_armature = None
        group = utils.get_chr_node_from_skeleton(armature)
        self.__create_materials(armature, materials)
        armature.data.pose_position = 'REST'
        bpy.ops.object.mode_set(mode='EDIT')

        for bone in armature.pose.bones:
            if not bone.bone.select:
                continue

            if self.physic_proxies:            
                name = "{}_boneGeometry".format(bone.name)
                bone_radius = {}
                bone_radius['torso'] = self.radius_torso
                bone_radius['head'] = self.radius_head
                bone_radius['arm'] = self.radius_arm
                bone_radius['leg'] = self.radius_leg
                bone_radius['foot'] = self.radius_foot
                bone_radius['other'] = self.radius_other
                bone_type = utils.get_bone_type(bone)
                rd = bone_radius[bone_type]
                
                bpy.ops.mesh.primitive_cube_add(radius=rd, location=(0, 0, 0))
                object_ = bpy.context.active_object
                object_.name = name
                object_.data.name = name
                
                bpy.ops.object.mode_set(mode='EDIT')
                
                bm = bmesh.from_edit_mesh(object_.data)
                scale_vertor = (1.07, 1.07, 1.07)
                
                for face in bm.faces:
                    if face.normal.x == -1.0:
                        for vert in face.verts:
                            vert.co.x = 0.0
                    elif face.normal.x == 1.0:
                        for vert in face.verts:
                            vert.co.x = bone.length
                        bmesh.ops.scale(bm, vec=scale_vertor, verts=face.verts)
                
                bpy.ops.object.mode_set(mode='OBJECT')

                object_.matrix_world = utils.transform_animation_matrix(bone.matrix)
                bpy.ops.object.transform_apply(scale=True)

                if group:
                    group.objects.link(object_)

                object_.show_transparent = True
                object_.show_wire = True

                if self.physic_materials:
                    mat = None
                    if self.use_single_material:
                        mat = materials['single']
                    else:
                        mat = materials[utils.get_bone_material_type(bone, bone_type)]

                    mat.use_transparency = True
                    mat.alpha = self.physic_alpha
                    if object_.material_slots:
                        object_.material_slot[0].material = mat
                    else:
                        bpy.ops.object.material_slot_add()
                        if object_.material_slots:
                            object_.material_slots[0].material = mat

                    bpy.ops.mesh.uv_texture_add()

                object_.select = False


                if self.physic_proxy_settings:
                    if bone_type == 'spine' or bone_type == 'head':
                        bone['phys_proxy'] = 'sphere'
                    elif bone_type == 'arm' or bone_type == 'leg' or bone_type == 'foot':
                        bone['phys_proxy'] = 'capsule'
                    else:
                        bone['phys_proxy'] = 'capsule'
                        
                    bone['Spring'] = (0.0, 0.0, 0.0)
                    bone['Spring Tension'] = (1.0, 1.0, 1.0)
                    bone['Damping'] = (1.0, 1.0, 1.0)
                    
                    hips_list = ['hips', 'pelvis']
                    if utils.is_in_list(bone.name, hips_list):
                        bone['Damping'] = (0.0, 0.0, 0.0)

                if self.physic_ik_settings:
                    self.__set_ik(bone)


        if self.physic_skeleton:
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.context.scene.objects.active = armature
            armature.select = True
            bpy.ops.object.duplicate()
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.armature.select_all(action='INVERT')
            bpy.ops.armature.delete()
            bpy.ops.object.mode_set(mode='OBJECT')

            armature_name = "{}.001".format(armature.name)
            physic_name = "{}_Phys".format(armature.name)
            armature.select = False
            location = armature.location.copy()
            location.x -= 1.63

            physic_armature = bpy.data.objects[armature_name]
            physic_armature.name = physic_name
            physic_armature.data.name = physic_name

            physic_armature.select = True
            bpy.context.scene.objects.active = physic_armature
        
            physic_armature.location = location
            physic_armature.draw_type = 'WIRE'
        
            for bone in physic_armature.data.bones:
                utils.make_physic_bone(bone)

            physic_armature.select = False


        self.__set_primitive_mesh_material(armature, materials)

        armature.select = True
        bpy.context.scene.objects.active = armature

        armature.data.pose_position = 'POSE'


        return {'FINISHED'}

    def __check_parent_relations(self, armature, physic_armature):
        for phys_bone in physic_armature.pose.bones:
            if not phys_bone.parent:
                bone_name = phys_bone.name[:-5]
                bone = armature.pose.bones[bone_name]
                while True:
                    if bone.parent == None:
                        break

                    bone = bone.parent
                    phys_bone_name = "{}_Phys".format(bone.name)
                    if phys_bone_name in physic_armature.pose.bones:
                        phys_edit_bone = physic_armature.data.edit_bones[phys_bone.name]
                        phys_parent_edit_bone = physic_armature.data.edit_bones[phys_bone_name]
                        phys_edit_bone.parent = phys_parent_edit_bone
                        break

    def __set_primitive_mesh_material(self, armature, materials):
        object_ = utils.get_chr_object_from_skeleton(armature)
        object_.select = True
        bpy.context.scene.objects.active = object_
        mat = None
        if self.use_single_material:
            mat = materials['single']
        else:
            mat = materials['primitive']

        if object_.material_slots:
            object_.material_slots[0].material = mat
        else:
            bpy.ops.object.material_slot_add()
            if object_.material_slots:
                object_.material_slots[0].material = mat

        object_.select = False

    def __create_materials(self, armature, materials):
        if self.use_single_material:
            single_material_name = "{}__01__proxy_bones__physProxyNoDraw".format(armature.name)
            if single_material_name in bpy.data.materials:
                materials['single'] = bpy.data.materials[single_material_name]
            else:
                materials['single'] = bpy.data.materials.new(single_material_name)
                
            materials['single'].diffuse_color = (0.016, 0.016, 0.016)
            return
        
        mat_primitive_name = "{}__01__No_Draw__physProxyNoDraw".format(armature.name)
        mat_larm_name = "{}__02__Skel_Arm_Left__physProxyNoDraw".format(armature.name)
        mat_rarm_name = "{}__03__Skel_Arm_Right__physProxyNoDraw".format(armature.name)
        mat_lleg_name = "{}__04__Skel_Leg_Left__physProxyNoDraw".format(armature.name)
        mat_rleg_name = "{}__05__Skel_Leg_Right__physProxyNoDraw".format(armature.name)
        mat_torso_name = "{}__06__Skel_Torso__physProxyNoDraw".format(armature.name)
        mat_head_name = "{}__07__Skel_Head__physProxyNoDraw".format(armature.name)
        mat_lfoot_name = "{}__08__Skel_Foot_Left__physProxyNoDraw".format(armature.name)
        mat_rfoot_name = "{}__09__Skel_Foot_Right__physProxyNoDraw".format(armature.name)

        if mat_primitive_name in bpy.data.materials:
            materials['primitive'] = bpy.data.materials[mat_primitive_name]
        else:
            materials['primitive'] = bpy.data.materials.new(mat_primitive_name)

        if mat_larm_name in bpy.data.materials:
            materials['larm'] = bpy.data.materials[mat_larm_name]
        else:
            materials['larm'] = bpy.data.materials.new(mat_larm_name)

        if mat_rarm_name in bpy.data.materials:
            materials['rarm'] = bpy.data.materials[mat_rarm_name]
        else:
            materials['rarm'] = bpy.data.materials.new(mat_rarm_name)

        if mat_lleg_name in bpy.data.materials:
            materials['lleg'] = bpy.data.materials[mat_lleg_name]
        else:
            materials['lleg'] = bpy.data.materials.new(mat_lleg_name)

        if mat_rleg_name in bpy.data.materials:
            materials['rleg'] = bpy.data.materials[mat_rleg_name]
        else:
            materials['rleg'] = bpy.data.materials.new(mat_rleg_name)

        if mat_torso_name in bpy.data.materials:
            materials['torso'] = bpy.data.materials[mat_torso_name]
        else:
            materials['torso'] = bpy.data.materials.new(mat_torso_name)

        if mat_head_name in bpy.data.materials:
            materials['head'] = bpy.data.materials[mat_head_name]
        else:
            materials['head'] = bpy.data.materials.new(mat_head_name)

        if mat_lfoot_name in bpy.data.materials:
            materials['lfoot'] = bpy.data.materials[mat_lfoot_name]
        else:
            materials['lfoot'] = bpy.data.materials.new(mat_lfoot_name)

        if mat_rfoot_name in bpy.data.materials:
            materials['rfoot'] = bpy.data.materials[mat_rfoot_name]
        else:
            materials['rfoot'] = bpy.data.materials.new(mat_rfoot_name)
        
        materials['larm'].diffuse_color = (0.800, 0.008, 0.019)
        materials['rarm'].diffuse_color = (1.000, 0.774, 0.013)
        materials['lleg'].diffuse_color = (0.023, 0.114, 1.000)
        materials['rleg'].diffuse_color = (0.013, 1.000, 0.048)
        materials['torso'].diffuse_color = (0.016, 0.016, 0.016)
        materials['head'].diffuse_color = (0.000, 0.450, 0.464)
        materials['lfoot'].diffuse_color = (1.000, 0.000, 0.632)
        materials['rfoot'].diffuse_color = (1.000, 0.32, 0.093)

    def __set_ik(self, bone):
        if utils.is_in_list(bone.name, ['spine']):
            bone.lock_ik_x = False
            bone.lock_ik_y = False
            bone.lock_ik_z = False

            bone.ik_min_x = math.radians(-18)
            bone.ik_min_y = math.radians(-18)
            bone.ik_min_z = math.radians(-18)

            bone.ik_max_x = math.radians(18)
            bone.ik_max_y = math.radians(18)
            bone.ik_max_z = math.radians(18)
            
        elif utils.is_in_list(bone.name, ['head']):
            bone.lock_ik_x = False
            bone.lock_ik_y = False
            bone.lock_ik_z = False

            bone.ik_min_x = math.radians(-30)
            bone.ik_min_y = math.radians(-70)
            bone.ik_min_z = math.radians(-20)

            bone.ik_max_x = math.radians(30)
            bone.ik_max_y = math.radians(70)
            bone.ik_max_z = math.radians(20)

        elif utils.is_in_list(bone.name, ['upper_arm']):
            bone.lock_ik_x = False
            bone.lock_ik_y = True
            bone.lock_ik_z = False

            bone.ik_min_x = math.radians(-60)
            bone.ik_min_y = math.radians(-180)
            if utils.is_in_list(bone.name, ['left', '.l']):
                bone.ik_min_z = math.radians(-90)
            else:
                bone.ik_min_z = math.radians(-140)

            bone.ik_max_x = math.radians(120)
            bone.ik_max_y = math.radians(180)
            if utils.is_in_list(bone.name, ['left', '.l']):
                bone.ik_max_z = math.radians(140)
            else:
                bone.ik_max_z = math.radians(90)
                
        elif utils.is_in_list(bone.name, ['forearm']):
            bone.lock_ik_x = False
            bone.lock_ik_y = True
            bone.lock_ik_z = True

            bone.ik_min_x = math.radians(-34)
            bone.ik_min_y = math.radians(-180)
            bone.ik_min_z = math.radians(-180)

            bone.ik_max_x = math.radians(120)
            bone.ik_max_y = math.radians(180)
            bone.ik_max_z = math.radians(180)

        elif utils.is_in_list(bone.name, ['thigh']):
            bone.lock_ik_x = False
            bone.lock_ik_y = True
            bone.lock_ik_z = False

            bone.ik_min_x = math.radians(-90)
            bone.ik_min_y = math.radians(-180)
            if utils.is_in_list(bone.name, ['left', '.l']):
                bone.ik_min_z = math.radians(-90)
            else:
                bone.ik_min_z = math.radians(-60)

            bone.ik_max_x = math.radians(80)
            bone.ik_max_y = math.radians(180)
            if utils.is_in_list(bone.name, ['left', '.l']):
                bone.ik_max_z = math.radians(60)
            else:
                bone.ik_max_z = math.radians(90)

        elif utils.is_in_list(bone.name, ['shin']):
            bone.lock_ik_x = False
            bone.lock_ik_y = True
            bone.lock_ik_z = True

            bone.ik_min_x = math.radians(0)
            bone.ik_min_y = math.radians(-180)
            bone.ik_min_z = math.radians(-180)

            bone.ik_max_x = math.radians(120)
            bone.ik_max_y = math.radians(180)
            bone.ik_max_z = math.radians(180)

        elif utils.is_in_list(bone.name, ['foot']):
            bone.lock_ik_x = False
            bone.lock_ik_y = False
            bone.lock_ik_z = False

            bone.ik_min_x = math.radians(-60)
            bone.ik_min_y = math.radians(-4)
            bone.ik_min_z = math.radians(-30)

            bone.ik_max_x = math.radians(15)
            bone.ik_max_y = math.radians(4)
            bone.ik_max_z = math.radians(30)
            
        else:
            bone.lock_ik_x = False
            bone.lock_ik_y = False
            bone.lock_ik_z = False

            bone.ik_min_x = math.radians(-180)
            bone.ik_min_y = math.radians(-180)
            bone.ik_min_z = math.radians(-180)

            bone.ik_max_x = math.radians(180)
            bone.ik_max_y = math.radians(180)
            bone.ik_max_z = math.radians(180)

class ClearSkeletonPhysics(bpy.types.Operator):
    '''Clear physics from selected skeleton.'''
    bl_label = "Clear Skeleton Physics"
    bl_idname = "armature.clear_skeleton_physics"
    bl_options = {'REGISTER', 'UNDO'}
    
    physic_skeleton = BoolProperty(name='Remove Physic Skeleton', default=True,
                            description='Removes physic skeleton.')
    physic_proxies = BoolProperty(name='Clear Physic Proxies', default=True,
                            description='Clears physic proxies.')
    
    def __init__(self):
        armature = bpy.context.active_object
        if armature.type != 'ARMATURE':
            self.report({'ERROR'}, 'You have to select a armature object!')
            return {'FINISHED'}

        group = utils.get_chr_node_from_skeleton(armature)
        if not group:
            self.report({'ERROR'}, 'Your armature has to has a primitive mesh which added to a CHR node!')
            return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label("Dephysicalize Options:")
        col.prop(self, "physic_skeleton")
        col.prop(self, "physic_proxies")
        col.separator()
        col.separator()
    
    def execute(self, context):
        armature = bpy.context.active_object
        physic_armature = None
        physic_name = "{}_Phys".format(armature.name)
        group = utils.get_chr_node_from_skeleton(armature)

        if self.physic_proxies and group:
            armature.select = False
            for object_ in group.objects:
                if utils.is_bone_geometry(object_):
                    object_.select = True
                    bpy.context.scene.objects.active = object_
            bpy.ops.object.delete()

        if self.physic_skeleton and (physic_name in bpy.data.objects):
            physic_armature = bpy.data.objects[physic_name]
            
            armature.select = False
            physic_armature.select = True
            bpy.context.scene.objects.active = physic_armature
            bpy.ops.object.delete()

        return {'FINISHED'}


#------------------------------------------------------------------------------
# Export Handler:
#------------------------------------------------------------------------------

class Export(bpy.types.Operator, ExportHelper):
    '''Select to export to game.'''
    bl_label = "Export to CryEngine"
    bl_idname = "scene.export_to_game"
    filename_ext = ".dae"
    filter_glob = StringProperty(default="*.dae", options={'HIDDEN'})

    merge_all_nodes = BoolProperty(
        name="Merge All Nodes",
        description=desc.list["merge_all_nodes"],
        default=False,
    )
    export_selected_nodes = BoolProperty(
        name="Export Selected Nodes",
        description="Just exports selected nodes.",
        default=False,
    )
    apply_modifiers = BoolProperty(
        name="Apply Modifiers",
        description="Apply all modifiers for objects before exporting.",
        default=False,
    )
    custom_normals = BoolProperty(
        name="Use Custom Normals",
        description="Use custom normals.",
        default=False,
    )
    vcloth_pre_process = BoolProperty(
        name="VCloth Pre-Process",
        description="Export skin as simulating mesh for VCloth V2.",
        default=False,
    )
    generate_materials = BoolProperty(
        name="Generate Materials",
        description="Generate material files for CryEngine.",
        default=False,
    )
    convert_textures = BoolProperty(
        name="Convert Textures",
        description="Converts source textures to DDS while exporting materials.",
        default=False,
    )
    make_chrparams = BoolProperty(
        name="Make CHRPARAMS File",
        description="Create a base CHRPARAMS file for character animations.",
        default=False,
    )
    make_cdf = BoolProperty(
        name="Make CDF File",
        description="Create a base CDF file for character attachments.",
        default=False,
    )
    fix_weights = BoolProperty(
        name="Fix Weights",
        description="For use with .chr files. Generally a good idea.",
        default=False,
    )
    export_for_lumberyard = BoolProperty(
        name="Export for LumberYard",
        description="Export for LumberYard engine instead of CryEngine.",
        default=False,
    )
    make_layer = BoolProperty(
        name="Make LYR File",
        description="Makes a LYR to reassemble your scene in CryEngine.",
        default=False,
    )
    disable_rc = BoolProperty(
        name="Disable RC",
        description="Do not run the resource compiler.",
        default=False,
    )
    save_dae = BoolProperty(
        name="Save DAE File",
        description="Save the DAE file for developing purposes.",
        default=False,
    )
    save_tiffs = BoolProperty(
        name="Save TIFFs",
        description="Saves TIFF images that are generated during conversion to DDS.",
        default=False,
    )
    run_in_profiler = BoolProperty(
        name="Profile BCry Exporter",
        description="Select only if you want to profile BCry Exporter.",
        default=False,
    )

    is_animation_process = False

    class Config:

        def __init__(self, config):
            attributes = (
                'filepath',
                'merge_all_nodes',
                'export_selected_nodes',
                'apply_modifiers',
                'custom_normals',
                'vcloth_pre_process',
                'generate_materials',
                'convert_textures',
                'make_chrparams',
                'make_cdf',
                'fix_weights',
                'export_for_lumberyard',
                'make_layer',
                'disable_rc',
                'save_dae',
                'save_tiffs',
                'run_in_profiler',
                'is_animation_process'
            )

            for attribute in attributes:
                setattr(self, attribute, getattr(config, attribute))

            setattr(self, 'bcry_version', VERSION)
            setattr(self, 'rc_path', Configuration.rc_path)
            setattr(self, 'texture_rc_path', Configuration.texture_rc_path)
            setattr(self, 'game_dir', Configuration.game_dir)

    def execute(self, context):
        bcPrint(Configuration.rc_path, 'debug', True)
        try:
            config = Export.Config(config=self)

            if self.run_in_profiler:
                import cProfile
                cProfile.runctx('export.save(config)', {},
                                {'export': export, 'config': config})
            else:
                export.save(config)

            self.filepath = '//'

        except exceptions.BCryException as exception:
            bcPrint(exception.what(), 'error')
            bpy.ops.screen.display_error(
                'INVOKE_DEFAULT', message=exception.what())

        return {'FINISHED'}

    def invoke(self, context, event):
        if not Configuration.configured():
            self.report({'ERROR'}, "No RC found.")
            return {'FINISHED'}

        if not utils.get_export_nodes():
            self.report({'ERROR'}, "No export nodes found.")
            return {'FINISHED'}

        return ExportHelper.invoke(self, context, event)

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        box = col.box()
        box.label("General", icon="WORLD")
        box.prop(self, "merge_all_nodes")
        box.prop(self, "export_selected_nodes")
        box.prop(self, "apply_modifiers")
        box.prop(self, "custom_normals")
        box.prop(self, "vcloth_pre_process")

        box = col.box()
        box.label("Material & Texture", icon="TEXTURE")
        box.prop(self, "generate_materials")
        box.prop(self, "convert_textures")

        box = col.box()
        box.label("Character", icon="ARMATURE_DATA")
        box.prop(self, "make_chrparams")
        box.prop(self, "make_cdf")

        box = col.box()
        box.label("Corrective", icon="BRUSH_DATA")
        box.prop(self, "fix_weights")

        box = col.box()
        box.label("LumberYard", icon="GAME")
        box.prop(self, "export_for_lumberyard")

        box = col.box()
        box.label("CryEngine Editor", icon="OOPS")
        box.prop(self, "make_layer")

        box = col.box()
        box.label("Developer Tools", icon="MODIFIER")
        box.prop(self, "disable_rc")
        box.prop(self, "save_dae")
        box.prop(self, "save_tiffs")
        box.prop(self, "run_in_profiler")


class ExportAnimations(bpy.types.Operator, ExportHelper):
    '''Export animations to CryEngine'''
    bl_label = "Export Animations"
    bl_idname = "scene.export_animations"
    filename_ext = ".dae"
    filter_glob = StringProperty(default="*.dae", options={'HIDDEN'})

    export_for_lumberyard = BoolProperty(
        name="Export for LumberYard",
        description="Export for LumberYard engine instead of CryEngine.",
        default=False,
    )
    disable_rc = BoolProperty(
        name="Disable RC",
        description="Do not run the resource compiler.",
        default=False,
    )
    save_dae = BoolProperty(
        name="Save DAE File",
        description="Save the DAE file for developing purposes.",
        default=False,
    )
    run_in_profiler = BoolProperty(
        name="Profile BCry Exporter",
        description="Select only if you want to profile BCry Exporter.",
        default=False,
    )
    merge_all_nodes = True
    generate_materials = False
    make_layer = False
    vcloth_pre_process = False
    is_animation_process = True

    class Config:

        def __init__(self, config):
            attributes = (
                'filepath',
                'merge_all_nodes',
                'vcloth_pre_process',
                'generate_materials',
                'export_for_lumberyard',
                'is_animation_process',
                'make_layer',
                'disable_rc',
                'save_dae',
                'run_in_profiler'
            )

            for attribute in attributes:
                setattr(self, attribute, getattr(config, attribute))

            setattr(self, 'bcry_version', VERSION)
            setattr(self, 'rc_path', Configuration.rc_path)
            setattr(self, 'texture_rc_path', Configuration.texture_rc_path)
            setattr(self, 'game_dir', Configuration.game_dir)

    def execute(self, context):
        bcPrint(Configuration.rc_path, 'debug')
        try:
            config = ExportAnimations.Config(config=self)

            if self.run_in_profiler:
                import cProfile
                cProfile.runctx(
                    'export_animations.save(config)', {}, {
                        'export_animations': export_animations, 'config': config})
            else:
                export_animations.save(config)

            self.filepath = '//'

        except exceptions.BCryException as exception:
            bcPrint(exception.what(), 'error')
            bpy.ops.screen.display_error(
                'INVOKE_DEFAULT', message=exception.what())

        return {'FINISHED'}

    def invoke(self, context, event):
        if not Configuration.configured():
            self.report({'ERROR'}, "No RC found.")
            return {'FINISHED'}

        if not utils.get_export_nodes():
            self.report({'ERROR'}, "No export nodes found.")
            return {'FINISHED'}

        return ExportHelper.invoke(self, context, event)

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        box = col.box()
        box.label("LumberYard", icon="GAME")
        box.prop(self, "export_for_lumberyard")

        box = col.box()
        box.label("Developer Tools", icon="MODIFIER")
        box.prop(self, "disable_rc")
        box.prop(self, "save_dae")
        box.prop(self, "run_in_profiler")


class ErrorHandler(bpy.types.Operator):
    bl_label = "Error:"
    bl_idname = "screen.display_error"

    message = bpy.props.StringProperty()

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(self.bl_label, icon='ERROR')
        col.split()
        multiline_label(col, self.message)
        col.split()
        col.split(0.2)


def multiline_label(col, text):
    for line in text.splitlines():
        row = col.split()
        row.label(line)


#------------------------------------------------------------------------------
# BCry Exporter Tab:
#------------------------------------------------------------------------------

class PropPanel():
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render_layer"
    COMPAT_ENGINES = {"BLENDER_RENDER"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return scene and (scene.render.engine in cls.COMPAT_ENGINES)


class View3DPanel():
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_category = "BCry Exporter"


class ExportUtilitiesPanel(View3DPanel, Panel):
    bl_label = "Export Utilities"

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.label("Export Nodes", icon="GROUP")
        col.separator()
        row = col.row(align=True)
        row.operator("object.add_cry_export_node", text="Add Export Node")
        row.operator(
            "object.add_cry_animation_node",
            text="Add Animation Node")
        col.operator(
            "object.selected_to_cry_export_nodes",
            text="Export Nodes from Objects")
        col.separator()
        col.operator("object.apply_transforms", text="Apply All Transforms")


class CryUtilitiesPanel(View3DPanel, Panel):
    bl_label = "Cry Utilities"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        col.label("Add Physics Proxy", icon="ROTATE")
        col.separator()
        row = col.row(align=True)
        add_box_proxy = row.operator("object.add_proxy", text="Box")
        add_box_proxy.type_ = "box"
        add_capsule_proxy = row.operator("object.add_proxy", text="Capsule")
        add_capsule_proxy.type_ = "capsule"

        row = col.row(align=True)
        add_cylinder_proxy = row.operator("object.add_proxy", text="Cylinder")
        add_cylinder_proxy.type_ = "cylinder"
        add_sphere_proxy = row.operator("object.add_proxy", text="Sphere")
        add_sphere_proxy.type_ = "sphere"
        col.separator()

        col.label("Breakables:", icon="PARTICLES")
        col.separator()
        col.operator("object.add_joint", text="Add Joint")
        col.separator()

        col.label("Touch Bending:", icon="MOD_SIMPLEDEFORM")
        col.separator()
        col.operator("mesh.add_branch", text="Add Branch")
        col.operator("mesh.add_branch_joint", text="Add Branch Joint")


class BoneUtilitiesPanel(View3DPanel, Panel):
    bl_label = "Bone Utilities"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        col.label("Skeleton", icon="ARMATURE_DATA")
        col.separator()
        col.operator("armature.add_root_bone", text="Add Root Bone")
        col.operator("armature.add_primitive_mesh", text="Add Primitive Mesh")
        col.operator("armature.add_locator_locomotion", text="Add Locator Locomotion")
        col.separator()

        col.label(text="Bone", icon="BONE_DATA")
        col.separator()
        col.operator(
            "object.edit_inverse_kinematics",
            text="Edit Bone Physic and IKs")
        col.operator(
            "ops.apply_animation_scaling",
            text="Apply Animation Scaling")
        col.separator()

        col.label("Physics", icon="PHYSICS")
        col.separator()
        col.operator("armature.physicalize_skeleton", text="Physicalize Skeleton")
        col.operator("armature.clear_skeleton_physics", text="Clear Skeleton Physics")


class MeshUtilitiesPanel(View3DPanel, Panel):
    bl_label = "Mesh Utilities"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        col.label(text="LODs", icon="EDIT_VEC")
        col.separator()
        col.operator("mesh.generate_lod_meshes", text="Create LODs")

        col.label(text="Weight Repair", icon="WPAINT_HLT")
        col.separator()
        col.operator("mesh.find_weightless", text="Find Weightless")
        col.operator("mesh.remove_weight", text="Remove Weight")
        col.separator()

        col.label(text="Mesh Repair", icon='ZOOM_ALL')
        col.separator()
        col.operator("object.find_degenerate_faces", text="Find Degenerate")
        col.operator("mesh.find_multiface_lines", text="Find Multi-face")
        col.separator()

        col.label(text="UV Repair", icon="UV_FACESEL")
        col.separator()
        col.operator("scene.find_no_uvs", text="Find All Objects with No UV's")
        col.operator("mesh.add_uv_texture", text="Add UV's to Objects")


class MaterialUtilitiesPanel(View3DPanel, Panel):
    bl_label = "Material Utilities"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        col.label(text="Material:", icon="MATERIAL_DATA")
        col.separator()
        col.operator("material.add_cry_material", text="Add Material")
        col.separator()
        col.operator(
            "material.set_material_names",
            text="Do Material Convention")
        col.operator(
            "material.remove_material_names",
            text="Undo Material Convention")
        col.separator()
        col.operator("material.generate_materials",
            text="Generate Materials")


class CustomPropertiesPanel(View3DPanel, Panel):
    bl_label = "Custom Properties"

    def draw(self, context):
        layout = self.layout

        layout.label("Properties:", icon="SCRIPT")
        layout.menu("menu.UDP", text="User Defined Properties")


class ConfigurationsPanel(View3DPanel, Panel):
    bl_label = "Configurations"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        col.label("Configure", icon="NEWFOLDER")
        col.separator()
        col.operator("file.find_rc", text="Find RC")
        col.operator(
            "file.find_rc_for_texture_conversion",
            text="Find Texture RC")
        col.separator()
        col.operator("file.select_game_dir", text="Select Game Directory")


class ExportPanel(View3DPanel, Panel):
    bl_label = "Export"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        col.label("Export Animations", icon="RENDER_ANIMATION")
        col.separator()
        col.operator("scene.export_animations", text="Export Animations")
        col.label("Export to CryEngine", icon_value=bcry_icons["crye"].icon_id)
        col.separator()
        col.operator("scene.export_to_game", text="Export to CryEngine")
        col.separator()

#------------------------------------------------------------------------------
# BCry Exporter Menu:
#------------------------------------------------------------------------------


class BCryMainMenu(bpy.types.Menu):
    bl_label = 'BCRY 5 Exporter'
    bl_idname = 'view3d.BCry_main_menu'

    def draw(self, context):
        layout = self.layout

        # version number
        layout.label(text='v{}'.format(VERSION))
        if not Configuration.configured():
            layout.label(text="No RC found.", icon='ERROR')
        layout.separator()

        # layout.operator("open_donate.wp", icon='FORCE_DRAG')
        layout.operator(
            "object.add_cry_export_node",
            text="Add Export Node",
            icon="GROUP")
        layout.operator(
            "object.add_cry_animation_node",
            text="Add Animation Node",
            icon="PREVIEW_RANGE")
        layout.operator(
            "object.selected_to_cry_export_nodes",
            text="Export Nodes from Objects",
            icon="SCENE_DATA")
        layout.separator()
        layout.operator(
            "object.apply_transforms",
            text="Apply All Transforms",
            icon="MESH_DATA")
        layout.separator()

        layout.menu("menu.add_physics_proxy", icon="ROTATE")
        layout.separator()
        layout.menu(CryUtilitiesMenu.bl_idname, icon='OUTLINER_OB_EMPTY')
        layout.separator()
        layout.menu(BoneUtilitiesMenu.bl_idname, icon='BONE_DATA')
        layout.separator()
        layout.menu(MeshUtilitiesMenu.bl_idname, icon='MESH_CUBE')
        layout.separator()
        layout.menu(MaterialUtilitiesMenu.bl_idname, icon="MATERIAL")
        layout.separator()
        layout.menu(CustomPropertiesMenu.bl_idname, icon='SCRIPT')
        layout.separator()
        layout.menu(ConfigurationsMenu.bl_idname, icon='NEWFOLDER')

        layout.separator()
        layout.separator()
        layout.operator("scene.export_to_game", icon_value=bcry_icons["crye"].icon_id)
        layout.separator()
        layout.operator("scene.export_animations", icon="RENDER_ANIMATION")


class AddPhysicsProxyMenu(bpy.types.Menu):
    bl_label = "Add Physics Proxy"
    bl_idname = "menu.add_physics_proxy"

    def draw(self, context):
        layout = self.layout

        layout.label("Proxies")
        add_box_proxy = layout.operator(
            "object.add_proxy", text="Box", icon="META_CUBE")
        add_box_proxy.type_ = "box"
        add_capsule_proxy = layout.operator(
            "object.add_proxy", text="Capsule", icon="META_ELLIPSOID")
        add_capsule_proxy.type_ = "capsule"
        add_cylinder_proxy = layout.operator(
            "object.add_proxy", text="Cylinder", icon="META_CAPSULE")
        add_cylinder_proxy.type_ = "cylinder"
        add_sphere_proxy = layout.operator(
            "object.add_proxy", text="Sphere", icon="META_BALL")
        add_sphere_proxy.type_ = "sphere"


class CryUtilitiesMenu(bpy.types.Menu):
    bl_label = "Cry Utilities"
    bl_idname = "view3d.cry_utilities"

    def draw(self, context):
        layout = self.layout

        layout.label(text="Breakables")
        layout.operator("object.add_joint", text="Add Joint", icon="PARTICLES")
        layout.separator()

        layout.label(text="Touch Bending")
        layout.operator(
            "mesh.add_branch",
            text="Add Branch",
            icon='MOD_SIMPLEDEFORM')
        layout.operator(
            "mesh.add_branch_joint",
            text="Add Branch Joint",
            icon='MOD_SIMPLEDEFORM')


class BoneUtilitiesMenu(bpy.types.Menu):
    bl_label = "Bone Utilities"
    bl_idname = "view3d.bone_utilities"

    def draw(self, context):
        layout = self.layout

        layout.label(text="Skeleton")
        layout.operator(
            "armature.add_root_bone",
            text="Add Root Bone",
            icon="BONE_DATA")
        layout.operator(
            "armature.add_primitive_mesh",
            text="Add Primitive Mesh",
            icon="BONE_DATA")
        layout.operator(
            "armature.add_locator_locomotion",
            text="Add Locator Locomotion",
            icon="BONE_DATA")
        layout.separator()

        layout.label(text="Bone")
        layout.operator(
            "object.edit_inverse_kinematics",
            text="Set Bone Physic and IKs",
            icon="OUTLINER_DATA_ARMATURE")
        layout.operator(
            "ops.apply_animation_scaling",
            text="Apply Animation Scaling",
            icon='OUTLINER_DATA_ARMATURE')
        layout.separator()

        layout.label(text="Physics")
        layout.operator(
            "armature.physicalize_skeleton",
            text="Physicalize Skeleton",
            icon='PHYSICS')
        layout.operator(
            "armature.clear_skeleton_physics",
            text="Clear Skeleton Physics",
            icon='PHYSICS')


class MeshUtilitiesMenu(bpy.types.Menu):
    bl_label = "Mesh Utilities"
    bl_idname = "view3d.mesh_utilities"

    def draw(self, context):
        layout = self.layout
        
        layout.label(text="LODs")
        layout.operator(
            "mesh.generate_lod_meshes",
            text="Generate LODs",
            icon="EDIT_VEC")
        layout.separator()

        layout.label(text="Weight Repair")
        layout.operator(
            "mesh.find_weightless",
            text="Find Weightless",
            icon="WPAINT_HLT")
        layout.operator(
            "mesh.remove_weight",
            text="Remove Weight",
            icon="WPAINT_HLT")
        layout.separator()

        layout.label(text="Mesh Repair")
        layout.operator(
            "object.find_degenerate_faces",
            text="Find Degenerate",
            icon='ZOOM_ALL')
        layout.operator(
            "mesh.find_multiface_lines",
            text="Find Multi-face",
            icon='ZOOM_ALL')
        layout.separator()

        layout.label(text="UV Repair")
        layout.operator(
            "scene.find_no_uvs",
            text="Find All Objects with No UV's",
            icon="UV_FACESEL")
        layout.operator(
            "mesh.add_uv_texture",
            text="Add UV's to Objects",
            icon="UV_FACESEL")


class MaterialUtilitiesMenu(bpy.types.Menu):
    bl_label = "Material Utilities"
    bl_idname = "view3d.material_utilities"

    def draw(self, context):
        layout = self.layout

        layout.operator(
            "material.add_cry_material",
            text="Add Material",
            icon="MATERIAL_DATA")
        layout.separator()
        layout.operator(
            "material.set_material_names",
            text="Do Material Convention",
            icon="MATERIAL")
        layout.operator(
            "material.remove_material_names",
            text="Undo Material Convention",
            icon="MATERIAL")
        layout.separator()
        layout.operator(
            "material.generate_materials",
            text="Generate Materials",
            icon="MATERIAL")


class CustomPropertiesMenu(bpy.types.Menu):
    bl_label = "User Defined Properties"
    bl_idname = "menu.UDP"

    def draw(self, context):
        layout = self.layout

        layout.operator(
            "object.edit_render_mesh",
            text="Edit Render Mesh",
            icon="FORCE_LENNARDJONES")
        layout.separator()
        layout.operator(
            "object.edit_physics_proxy",
            text="Edit Physics Proxy",
            icon="META_CUBE")
        layout.separator()
        layout.operator(
            "object.edit_joint_node",
            text="Edit Joint Node",
            icon="MOD_SCREW")
        layout.separator()
        layout.operator(
            "object.edit_deformable",
            text="Edit Deformable",
            icon="MOD_SIMPLEDEFORM")


class ConfigurationsMenu(bpy.types.Menu):
    bl_label = "Configurations"
    bl_idname = "view3d.configurations"

    def draw(self, context):
        layout = self.layout

        layout.label("Configure")
        layout.operator("file.find_rc", text="Find RC", icon="SPACE2")
        layout.operator(
            "file.find_rc_for_texture_conversion",
            text="Find Texture RC",
            icon="SPACE2")
        layout.separator()
        layout.operator(
            "file.select_game_dir",
            text="Select Game Directory",
            icon="FILE_FOLDER")


class SetMaterialPhysicsMenu(bpy.types.Menu):
    bl_label = "Set Material Physics"
    bl_idname = "menu.set_material_physics"

    def draw(self, context):
        layout = self.layout

        layout.label(text="Set Material Physics")
        layout.separator()
        layout.operator(
            "material.set_phys_default",
            text="physDefault",
            icon='PHYSICS')
        layout.operator(
            "material.set_phys_proxy_no_draw",
            text="physProxyNoDraw",
            icon='PHYSICS')
        layout.operator(
            "material.set_phys_none",
            text="physNone",
            icon='PHYSICS')
        layout.operator(
            "material.set_phys_obstruct",
            text="physObstruct",
            icon='PHYSICS')
        layout.operator(
            "material.set_phys_no_collide",
            text="physNoCollide",
            icon='PHYSICS')


class RemoveUnusedVertexGroups(bpy.types.Operator):
    bl_label = "Remove Unused Vertex Groups"
    bl_idname = "ops.remove_unused_vertex_groups"

    def execute(self, context):
        old_mode = bpy.context.mode
        if old_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        object_ = bpy.context.active_object

        used_indices = []

        for vertex in object_.data.vertices:
            for group in vertex.groups:
                index = group.group
                if index not in used_indices:
                    used_indices.append(index)

        used_vertex_groups = []
        for index in used_indices:
            used_vertex_groups.append(object_.vertex_groups[index])

        for vertex_group in object_.vertex_groups:
            if vertex_group not in used_vertex_groups:
                object_.vertex_groups.remove(vertex_group)

        if old_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=old_mode)

        return {'FINISHED'}


class BCryReducedMenu(bpy.types.Menu):
    bl_label = 'BCry Exporter'
    bl_idname = 'view3d.BCry_reduced_menu'

    def draw(self, context):
        layout = self.layout

        layout.operator(
            "object.apply_transforms",
            text="Apply All Transforms",
            icon="MESH_DATA")
        layout.separator()
        layout.menu("menu.add_physics_proxy", icon="ROTATE")
        layout.separator()
        layout.menu(CryUtilitiesMenu.bl_idname, icon='OUTLINER_OB_EMPTY')
        layout.separator()
        layout.menu(BoneUtilitiesMenu.bl_idname, icon='BONE_DATA')
        layout.separator()
        layout.menu(MeshUtilitiesMenu.bl_idname, icon='MESH_CUBE')
        layout.separator()
        layout.menu(MaterialUtilitiesMenu.bl_idname, icon='MATERIAL_DATA')
        layout.separator()
        layout.menu(CustomPropertiesMenu.bl_idname, icon='SCRIPT')


#------------------------------------------------------------------------------
# Registration:
#------------------------------------------------------------------------------

def get_classes_to_register():
    classes = (
        FindRC,
        FindRCForTextureConversion,
        SelectGameDirectory,
        SaveBCryConfiguration,

        AddCryExportNode,
        AddCryAnimationNode,
        SelectedToCryExportNodes,
        AddMaterial,
        SetMaterialNames,
        RemoveMaterialNames,
        GenerateMaterials,
        AddRootBone,
        AddLocatorLocomotion,
        AddPrimitiveMesh,
        ApplyTransforms,
        AddProxy,
        AddBreakableJoint,
        AddBranch,
        AddBranchJoint,
        
        GenerateLODs,

        EditInverseKinematics,
        PhysicalizeSkeleton,
        ClearSkeletonPhysics,

        EditRenderMesh,
        EditPhysicProxy,
        EditJointNode,
        EditDeformable,

        FixWheelTransforms,

        SetMaterialPhysDefault,
        SetMaterialPhysProxyNoDraw,
        SetMaterialPhysNone,
        SetMaterialPhysObstruct,
        SetMaterialPhysNoCollide,

        FindDegenerateFaces,
        FindMultifaceLines,
        FindWeightless,
        RemoveAllWeight,
        FindNoUVs,
        AddUVTexture,

        ApplyAnimationScale,

        Export,
        ExportAnimations,
        ErrorHandler,

        ExportUtilitiesPanel,
        CryUtilitiesPanel,
        BoneUtilitiesPanel,
        MeshUtilitiesPanel,
        MaterialUtilitiesPanel,
        CustomPropertiesPanel,
        ConfigurationsPanel,
        ExportPanel,

        BCryMainMenu,
        AddPhysicsProxyMenu,
        BoneUtilitiesMenu,
        CryUtilitiesMenu,
        MeshUtilitiesMenu,
        MaterialUtilitiesMenu,
        CustomPropertiesMenu,
        ConfigurationsMenu,

        SetMaterialPhysicsMenu,
        RemoveUnusedVertexGroups,
        BCryReducedMenu,
    )

    return classes


def draw_item(self, context):
    layout = self.layout
    layout.menu(BCryMainMenu.bl_idname)


def physics_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.label("BCry Exporter")
    layout.menu("menu.set_material_physics", icon="PHYSICS")
    layout.separator()


def remove_unused_vertex_groups(self, context):
    layout = self.layout
    layout.separator()
    layout.label("BCry Exporter")
    layout.operator("ops.remove_unused_vertex_groups", icon="X")


def register_bcry_icons():
    global bcry_icons
    bcry_icons = bpy.utils.previews.new()
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    bcry_icons.load("crye", os.path.join(icons_dir, "CryEngine.png"), 'IMAGE')


def unregister_bcry_icons():
    global bcry_icons
    bpy.utils.previews.remove(bcry_icons)


def register():
    register_bcry_icons()

    for classToRegister in get_classes_to_register():
        bpy.utils.register_class(classToRegister)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(
            'wm.call_menu',
            'Q',
            'PRESS',
            ctrl=False,
            shift=True)
        kmi.properties.name = "view3d.BCry_reduced_menu"

    bpy.types.INFO_HT_header.append(draw_item)
    bpy.types.MATERIAL_MT_specials.append(physics_menu)
    bpy.types.MESH_MT_vertex_group_specials.append(remove_unused_vertex_groups)


def unregister():
    unregister_bcry_icons()

    # Be sure to unregister operators.
    for classToRegister in get_classes_to_register():
        bpy.utils.unregister_class(classToRegister)
        wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps['3D View']
        for kmi in km.keymap_items:
            if kmi.idname == 'wm.call_menu':
                if kmi.properties.name == "view3d.BCry_reduced_menu":
                    km.keymap_items.remove(kmi)
                    break

    bpy.types.INFO_HT_header.remove(draw_item)
    bpy.types.MATERIAL_MT_specials.remove(physics_menu)
    bpy.types.MESH_MT_vertex_group_specials.remove(remove_unused_vertex_groups)


if __name__ == "__main__":
    register()

    # The menu can also be called from scripts
    bpy.ops.wm.call_menu(name=ExportUtilitiesPanel.bl_idname)
