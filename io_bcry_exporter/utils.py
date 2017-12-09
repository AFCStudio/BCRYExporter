#------------------------------------------------------------------------------
# Name:        utils.py
# Purpose:     Utility functions for use throughout the add-on
#
# Author:      Özkan Afacan,
#              Angelo J. Miner, Mikołaj Milej, Daniel White,
#              Oscar Martin Garcia, Duo Oratar, David Marcelis
#
# Created:     23/02/2012
# Copyright:   (c) Angelo J. Miner 2012
# Copyright:   (c) Özkan Afacan 2016
# Licence:     GPLv2+
#------------------------------------------------------------------------------

# <pep8-80 compliant>


if "bpy" in locals():
    import imp
    imp.reload(material_utils)
    imp.reload(exceptions)
else:
    import bpy
    from io_bcry_exporter import material_utils, exceptions


from io_bcry_exporter.outpipe import bcPrint
from mathutils import Matrix, Vector
from xml.dom.minidom import Document, parseString
import bpy
import fnmatch
import math
import os
import random
import re
import subprocess
import sys
import xml.dom.minidom
import time
import bmesh


# Globals:
to_degrees = 180.0 / math.pi


#------------------------------------------------------------------------------
# Conversions:
#------------------------------------------------------------------------------

def transform_bone_matrix(bone):
    if not bone.parent:
        return Matrix()

    i1 = Vector((1.0, 0.0, 0.0))
    i2 = Vector((0.0, 1.0, 0.0))
    i3 = Vector((0.0, 0.0, 1.0))

    x_axis = bone.y_axis
    y_axis = bone.x_axis
    z_axis = -bone.z_axis

    row_x = Vector((x_axis * i1, x_axis * i2, x_axis * i3))
    row_y = Vector((y_axis * i1, y_axis * i2, y_axis * i3))
    row_z = Vector((z_axis * i1, z_axis * i2, z_axis * i3))

    trans_matrix = Matrix((row_x, row_y, row_z))

    location = trans_matrix * bone.matrix.translation
    bone_matrix = trans_matrix.to_4x4()
    bone_matrix.translation = -location

    return bone_matrix


def transform_animation_matrix(matrix):
    eu = matrix.to_euler()
    eu.rotate_axis('Z', math.pi / 2.0)
    eu.rotate_axis('X', math.pi)

    new_matrix = eu.to_matrix()
    new_matrix = new_matrix.to_4x4()
    new_matrix.translation = matrix.translation

    return new_matrix


def frame_to_time(frame):
    fps_base = bpy.context.scene.render.fps_base
    fps = bpy.context.scene.render.fps
    return fps_base * frame / fps


def matrix_to_string(matrix):
    return str(matrix_to_array(matrix))


def floats_to_string(floats, separator=" ", precision="%.6f"):
    return separator.join(precision % x for x in floats)


def strings_to_string(strings, separator=" "):
    return separator.join(string for string in strings)


def matrix_to_array(matrix):
    array = []
    for row in matrix:
        array.extend(row)

    return array


def write_matrix(matrix, node):
    doc = Document()
    for row in matrix:
        row_string = floats_to_string(row)
        node.appendChild(doc.createTextNode(row_string))


def join(*items):
    strings = []
    for item in items:
        strings.append(str(item))
    return "".join(strings)


#------------------------------------------------------------------------------
# XSI Functions:
#------------------------------------------------------------------------------

def get_xsi_filetype_value(node):
    node_type = get_node_type(node)
    if node_type == 'cgf':
        return "1"
    elif node_type == 'chr':
        return "4"
    elif node_type == 'cga':
        return "18"
    elif node_type == 'skin':
        return "32"
    elif node_type == 'i_caf' or node_type == 'anm':
        return "64"
    else:
        return "1"


#------------------------------------------------------------------------------
# Geometry Functions:
#------------------------------------------------------------------------------

def get_geometry_name(group, object_):
    node_name = get_node_name(group)
    if is_bone_geometry(object_):
        return "{}_{}".format(node_name, object_.name)
    elif is_lod_geometry(object_):
        return "{}_{}".format(node_name, changed_lod_name(object_.name))
    else:
        return "{}_{}_geometry".format(node_name, object_.name)


def get_bmesh(object_, apply_modifiers=False):
    set_active(object_)

    # bmesh may be gotten only in edit mode for active object.
    # Unfortunately Blender goes in edit mode just objects
    # in which first layer with bpy.ops.object.mode_set(mode='EDIT')
    # So we must temporarily activate first layer for objects which it is not
    # already in first layer. Also scene first layer must be active.
    # That lacking related with Blender, if it will fix in future that
    # code will be clean.

    scene_first_layer = bpy.context.scene.layers[0]
    bpy.context.scene.layers[0] = True

    layer_state = not object_.layers[0]
    if layer_state:
        object_.layers[0] = True

    bcry_split_modifier(object_)

    backup_data = object_.data
    object_.data = object_.to_mesh(
        bpy.context.scene, apply_modifiers, 'PREVIEW')

    bpy.ops.object.mode_set(mode='EDIT')

    bmesh_ = bmesh.from_edit_mesh(object_.data)
    backup_info = (backup_data, layer_state, scene_first_layer)

    return bmesh_, backup_info


def clear_bmesh(object_, backup_info):
    backup_data = backup_info[0]
    layer_state = backup_info[1]
    scene_first_layer = backup_info[2]

    bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.scene.layers[0] = scene_first_layer

    if layer_state:
        object_.layers[0] = False

    export_data = object_.data
    object_.data = backup_data
    remove_bcry_split_modifier(object_)
    bpy.data.meshes.remove(export_data)


def bcry_split_modifier(object_):
    if object_.data.use_auto_smooth:
        modifier_unique_name = 'BCRY_EDGE_SPLIT'

        object_.modifiers.new(modifier_unique_name, 'EDGE_SPLIT')
        edge_split_modifier = object_.modifiers.get(modifier_unique_name)
        edge_split_modifier.use_edge_angle = True
        edge_split_modifier.use_edge_sharp = True
        edge_split_modifier.split_angle = object_.data.auto_smooth_angle

        object_.data.use_auto_smooth = False


def remove_bcry_split_modifier(object_):
    modifier_unique_name = 'BCRY_EDGE_SPLIT'

    edge_split_modifier = object_.modifiers.get(modifier_unique_name)
    if edge_split_modifier:
        object_.data.use_auto_smooth = True
        object_.modifiers.remove(edge_split_modifier)


def get_tessfaces(bmesh_):
    tessfaces = []
    tfs = bmesh_.calc_tessface()

    for face in bmesh_.faces:
        # initialize tessfaces array
        tessfaces.append([])

    for tf in tfs:
        vert_list = []
        for loop in tf:
            # tessfaces[loop.face.index].append(loop.vert.index)
            vert_list.append(loop.vert.index)

        tessfaces[tf[0].face.index].append(vert_list)

    return tessfaces


def get_custom_normals(bmesh_, use_edge_angle, split_angle):
    float_normals = []

    for face in bmesh_.faces:
        if not face.smooth:
            for vertex in face.verts:
                float_normals.extend(face.normal.normalized())
        else:
            for vertex in face.verts:
                v_normals = [[face.normal.normalized(), face.calc_area()]]
                for link_face in vertex.link_faces:
                    if face.index == link_face.index:
                        continue
                    if link_face.smooth:
                        if not use_edge_angle:
                            v_normals.append(
                                [link_face.normal.normalized(), link_face.calc_area()])

                        elif use_edge_angle:
                            face_angle = face.normal.normalized().dot(link_face.normal.normalized())
                            face_angle = min(1.0, max(face_angle, -1.0))
                            face_angle = math.acos(face_angle)
                            if face_angle < split_angle:
                                v_normals.append(
                                    [link_face.normal.normalized(), link_face.calc_area()])

                smooth_normal = Vector()
                area_sum = 0
                for vertex_normal in v_normals:
                    area_sum += vertex_normal[1]
                for vertex_normal in v_normals:
                    if area_sum:
                        smooth_normal += vertex_normal[0] * \
                            (vertex_normal[1] / area_sum)
                float_normals.extend(smooth_normal.normalized())

    return float_normals


def get_normal_array(bmesh_, use_edge_angle, use_edge_sharp, split_angle):
    float_normals = []

    for face in bmesh_.faces:
        if not face.smooth:
            for vertex in face.verts:
                float_normals.extend(face.normal.normalized())
        else:
            for vertex in face.verts:
                v_normals = [[face.normal.normalized(), face.calc_area()]]
                for link_face in vertex.link_faces:
                    if face.index == link_face.index:
                        continue
                    if link_face.smooth:
                        if not use_edge_angle and not use_edge_sharp:
                            v_normals.append(
                                [link_face.normal.normalized(), link_face.calc_area()])

                        elif use_edge_angle and not use_edge_sharp:
                            face_angle = face.normal.normalized().dot(link_face.normal.normalized())
                            face_angle = min(1.0, max(face_angle, -1.0))
                            face_angle = math.acos(face_angle)
                            if face_angle < split_angle:
                                v_normals.append(
                                    [link_face.normal.normalized(), link_face.calc_area()])

                        elif use_edge_sharp and not use_edge_angle:
                            is_neighbor_face = False
                            for edge in vertex.link_edges:
                                if (edge in face.edges) and (
                                        edge in link_face.edges):
                                    is_neighbor_face = True
                                    if edge.smooth:
                                        v_normals.append(
                                            [link_face.normal.normalized(), link_face.calc_area()])

                            if not is_neighbor_face:
                                if check_sharp_edges(
                                        vertex, face, None, link_face):
                                    v_normals.append(
                                        [link_face.normal.normalized(), link_face.calc_area()])

                        elif use_edge_angle and use_edge_sharp:
                            face_angle = face.normal.normalized().dot(link_face.normal.normalized())
                            face_angle = min(1.0, max(face_angle, -1.0))
                            face_angle = math.acos(face_angle)
                            if face_angle < split_angle:
                                is_neighbor_face = False
                                for edge in vertex.link_edges:
                                    if (edge in face.edges) and (
                                            edge in link_face.edges):
                                        is_neighbor_face = True
                                        if edge.smooth:
                                            v_normals.append(
                                                [link_face.normal.normalized(), link_face.calc_area()])

                                if not is_neighbor_face:
                                    if check_sharp_edges(
                                            vertex, face, None, link_face):
                                        v_normals.append(
                                            [link_face.normal.normalized(), link_face.calc_area()])

                smooth_normal = Vector()
                area_sum = 0
                for vertex_normal in v_normals:
                    area_sum += vertex_normal[1]
                for vertex_normal in v_normals:
                    if area_sum:
                        smooth_normal += vertex_normal[0] * \
                            (vertex_normal[1] / area_sum)
                float_normals.extend(smooth_normal.normalized())

    return float_normals


def check_sharp_edges(vertex, current_face, previous_face, target_face):
    for trans_edge in current_face.edges:
        if trans_edge in vertex.link_edges:
            for neighbor_face in trans_edge.link_faces:
                if neighbor_face == current_face or neighbor_face == previous_face:
                    continue
                if trans_edge.smooth:
                    if neighbor_face == target_face:
                        return True
                    else:
                        new_previous_face = current_face
                        return check_sharp_edges(
                            vertex, neighbor_face, new_previous_face, target_face)

    return False


def get_joint_name(object_, index=1):
    joint_name = "$joint{:02d}".format(index)

    for child in object_.children:
        if child.name == joint_name:
            return get_joint_name(object_, index + 1)

    return joint_name


#------------------------------------------------------------------------------
# Path Manipulations:
#------------------------------------------------------------------------------

def get_absolute_path(file_path):
    [is_relative, file_path] = strip_blender_path_prefix(file_path)

    if is_relative:
        blend_file_path = os.path.dirname(bpy.data.filepath)
        file_path = '{}/{}'.format(blend_file_path, file_path)

    return os.path.abspath(file_path)


def get_absolute_path_for_rc(file_path):
    # 'z:' is for wine (linux, mac) path
    # there should be better way to determine it
    WINE_DEFAULT_DRIVE_LETTER = 'z:'

    file_path = get_absolute_path(file_path)

    if sys.platform != 'win32':
        file_path = '{}{}'.format(WINE_DEFAULT_DRIVE_LETTER, file_path)

    return file_path


def get_relative_path(filepath, start=None):
    blend_file_directory = os.path.dirname(bpy.data.filepath)
    [is_relative_to_blend_file, filepath] = strip_blender_path_prefix(filepath)

    if not start:
        if is_relative_to_blend_file:
            return filepath

        # path is not relative, so create path relative to blend file.
        start = blend_file_directory

        if not start:
            raise exceptions.BlendNotSavedException

    else:
        # make absolute path to be able make relative to 'start'
        if is_relative_to_blend_file:
            filepath = os.path.normpath(os.path.join(blend_file_directory,
                                                     filepath))

    return make_relative_path(filepath, start)


def strip_blender_path_prefix(path):
    is_relative = False
    BLENDER_RELATIVE_PATH_PREFIX = '//'
    prefix_length = len(BLENDER_RELATIVE_PATH_PREFIX)

    if path.startswith(BLENDER_RELATIVE_PATH_PREFIX):
        path = path[prefix_length:]
        is_relative = True

    return (is_relative, path)


def make_relative_path(filepath, start):
    try:
        relative_path = os.path.relpath(filepath, start)
        return relative_path

    except ValueError:
        raise exceptions.TextureAndBlendDiskMismatchException(start, filepath)


def get_path_with_new_extension(path, extension):
    return '{}.{}'.format(os.path.splitext(path)[0], extension)


def strip_extension_from_path(path):
    return os.path.splitext(path)[0]


def get_extension_from_path(path):
    return os.path.splitext(path)[1]


def normalize_path(path):
    path = path.replace("\\", "/")

    multiple_paths = re.compile("/{2,}")
    path = multiple_paths.sub("/", path)

    if path[0] == "/":
        path = path[1:]

    if path[-1] == "/":
        path = path[:-1]

    return path


def build_path(*components):
    path = "/".join(components)
    path = path.replace("/.", ".")  # accounts for extension
    return normalize_path(path)


def get_filename(path):
    path_normalized = normalize_path(path)
    components = path_normalized.split("/")
    name = os.path.splitext(components[-1])[0]
    return name


def trim_path_to(path, trim_to):
    path_normalized = normalize_path(path)
    components = path_normalized.split("/")
    for index, component in enumerate(components):
        if component == trim_to:
            bcPrint("FOUND AN INSTANCE")
            break
    bcPrint(index)
    components_trimmed = components[index:]
    bcPrint(components_trimmed)
    path_trimmed = build_path(*components_trimmed)
    bcPrint(path_trimmed)
    return path_trimmed


#------------------------------------------------------------------------------
# File Clean-Up:
#------------------------------------------------------------------------------

def clean_file(just_selected=False):
    for node in get_export_nodes(just_selected):
        node_name = get_node_name(node)
        nodetype = get_node_type(node)
        node_name = replace_invalid_rc_characters(node_name)
        node.name = "{}.{}".format(node_name, nodetype)

        for object_ in node.objects:
            object_.name = replace_invalid_rc_characters(object_.name)
            try:
                object_.data.name = replace_invalid_rc_characters(
                    object_.data.name)
            except AttributeError:
                pass
            if object_.type == "ARMATURE":
                for bone in object_.data.bones:
                    bone.name = replace_invalid_rc_characters(bone.name)


def replace_invalid_rc_characters(string):
    # Remove leading and trailing spaces.
    string.strip()

    # Replace remaining white spaces with double underscores.
    string = "__".join(string.split())

    character_map = {
        "a": "àáâå",
        "c": "ç",
        "e": "èéêë",
        "i": "ìíîïı",
        "l": "ł",
        "n": "ñ",
        "o": "òóô",
        "u": "ùúû",
        "y": "ÿ",
        "ss": "ß",
        "ae": "äæ",
        "oe": "ö",
        "ue": "ü"
    }  # Expand with more individual replacement rules.

    # Individual replacement.
    for good, bad in character_map.items():
        for char in bad:
            string = string.replace(char, good)
            string = string.replace(char.upper(), good.upper())

    # Remove all remaining non alphanumeric characters except underscores,
    # dots, and dollar signs.
    string = re.sub("[^.^_^$0-9A-Za-z]", "", string)

    return string


def fix_weights():
    for object_ in get_type("skins"):
        override = get_3d_context(object_)
        try:
            bpy.ops.object.vertex_group_normalize_all(
                override, lock_active=False)
        except:
            raise exceptions.BCryException(
                "Please fix weightless vertices first.")
    bcPrint("Weights Corrected.")


#------------------------------------------------------------------------------
# Collections:
#------------------------------------------------------------------------------

def get_export_nodes(just_selected=False):
    export_nodes = []

    if just_selected:
        return __get_selected_nodes()

    for group in bpy.data.groups:
        if is_export_node(group) and len(group.objects) > 0:
            export_nodes.append(group)

    return export_nodes


def get_mesh_export_nodes(just_selected=False):
    export_nodes = []

    ALLOWED_NODE_TYPES = ('cgf', 'cga', 'chr', 'skin')
    for node in get_export_nodes(just_selected):
        if get_node_type(node) in ALLOWED_NODE_TYPES:
            export_nodes.append(node)

    return export_nodes


def get_chr_node_from_skeleton(armature):
    for child in armature.children:
        for group in child.users_group:
            if group.name.endswith('.chr'):
                return group

    return None


def get_chr_object_from_skeleton(armature):
    for child in armature.children:
        for group in child.users_group:
            if group.name.endswith('.chr'):
                return child

    return None


def get_chr_names(just_selected=False):
    chr_names = []

    for node in get_export_nodes(just_selected):
        if get_node_type(node) == 'chr':
            chr_nodes.append(get_node_name(node))

    return chr_names


def get_animation_export_nodes(just_selected=False):
    export_nodes = []

    if just_selected:
        return __get_selected_nodes()

    ALLOWED_NODE_TYPES = ('anm', 'i_caf')
    for group in bpy.data.groups:
        if is_export_node(group) and len(group.objects) > 0:
            if get_node_type(group) in ALLOWED_NODE_TYPES:
                export_nodes.append(group)

    return export_nodes


def __get_selected_nodes():
    export_nodes = []

    for object in bpy.context.selected_objects:
        for group in object.users_group:
            if is_export_node(group) and group not in export_nodes:
                export_nodes.append(group)

    return export_nodes


def get_type(type_):
    dispatch = {
        "objects": __get_objects,
        "geometry": __get_geometry,
        "controllers": __get_controllers,
        "skins": __get_skins,
        "fakebones": __get_fakebones,
        "bone_geometry": __get_bone_geometry,
    }
    return list(set(dispatch[type_]()))


def __get_objects():
    items = []
    for group in get_export_nodes():
        items.extend(group.objects)

    return items


def __get_geometry():
    items = []
    for object_ in get_type("objects"):
        if object_.type == "MESH" and not is_fakebone(object_):
            items.append(object_)

    return items


def __get_controllers():
    items = []
    for object_ in get_type("objects"):
        if not (is_bone_geometry(object_) or
                is_fakebone(object_)):
            if object_.parent is not None:
                if object_.parent.type == "ARMATURE":
                    items.append(object_.parent)

    return items


def __get_skins():
    items = []
    for object_ in get_type("objects"):
        if object_.type == "MESH":
            if not (is_bone_geometry(object_) or
                    is_fakebone(object_)):
                if object_.parent is not None:
                    if object_.parent.type == "ARMATURE":
                        items.append(object_)

    return items


def __get_fakebones():
    items = []
    for object_ in bpy.data.objects:
        if is_fakebone(object_):
            items.append(object_)

    return items


def __get_bone_geometry():
    items = []
    for object_ in get_type("objects"):
        if is_bone_geometry(object_):
            items.append(object_)

    return items


#------------------------------------------------------------------------------
# Export Nodes:
#------------------------------------------------------------------------------

def is_export_node(node):
    extensions = [".cgf", ".cga", ".chr", ".skin", ".anm", ".i_caf"]
    for extension in extensions:
        if node.name.endswith(extension):
            return True

    return False


def are_duplicate_nodes():
    node_names = []
    for group in get_export_nodes():
        node_names.append(get_node_name(group))
    unique_node_names = set(node_names)
    if len(unique_node_names) < len(node_names):
        return True


def get_node_name(node):
    node_type = get_node_type(node)
    return node.name[:-(len(node_type) + 1)]


def get_node_type(node):
    node_components = node.name.split(".")
    return node_components[-1]


def is_visual_scene_node_writed(object_, group):
    if is_bone_geometry(object_):
        return False
    if object_.parent is not None and object_.type not in ('MESH', 'EMPTY'):
        return False

    return True


def is_there_a_parent_releation(object_, group):
    while object_.parent:
        if is_object_in_group(
                object_.parent,
                group) and object_.parent.type in (
                'MESH',
                'EMPTY'):
            return True
        else:
            return is_there_a_parent_releation(object_.parent, group)

    return False


def is_object_in_group(object_, group):
    for obj in group.objects:
        if object_.name == obj.name:
            return True

    return False


def is_dummy(object_):
    return object_.type == 'EMPTY'


#------------------------------------------------------------------------------
# Fakebones:
#------------------------------------------------------------------------------


def get_fakebone(bone_name):
    return next((fakebone for fakebone in get_type("fakebones")
                 if fakebone.name == bone_name), None)


def is_fakebone(object_):
    if object_.get("fakebone") is not None:
        return True
    else:
        return False


def add_fakebones(group=None):
    '''Add helpers to track bone transforms.'''
    scene = bpy.context.scene
    remove_unused_meshes()

    if group:
        for object_ in group.objects:
            if object_.type == 'ARMATURE':
                armature = object_
    else:
        armature = get_armature()

    if armature is None:
        return

    skeleton = armature.data

    skeleton.pose_position = 'REST'
    time.sleep(0.5)

    scene.frame_set(scene.frame_start)
    for pose_bone in armature.pose.bones:
        bone_matrix = transform_bone_matrix(pose_bone)
        loc, rot, scl = bone_matrix.decompose()

        bpy.ops.mesh.primitive_cube_add(radius=.01)
        fakebone = bpy.context.active_object
        fakebone.matrix_world = bone_matrix
        fakebone.scale = (1, 1, 1)
        fakebone.name = pose_bone.name
        fakebone["fakebone"] = "fakebone"
        scene.objects.active = armature
        armature.data.bones.active = pose_bone.bone
        bpy.ops.object.parent_set(type='BONE_RELATIVE')

        if group:
            group.objects.link(fakebone)

    if group:
        if get_node_type(group) == 'i_caf':
            process_animation(armature, skeleton)


def remove_fakebones():
    '''Select to remove all fakebones from the scene.'''
    if len(get_type("fakebones")) == 0:
        return
    old_mode = bpy.context.mode
    if old_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    deselect_all()
    for fakebone in get_type("fakebones"):
        fakebone.select = True
        bpy.ops.object.delete(use_global=False)
    if old_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode=old_mode)


#------------------------------------------------------------------------------
# Animation and Keyframing:
#------------------------------------------------------------------------------

def process_animation(armature, skeleton):
    '''Process animation to export.'''
    skeleton.pose_position = 'POSE'
    time.sleep(0.5)

    location_list, rotation_list = get_keyframes(armature)
    set_keyframes(armature, location_list, rotation_list)


def get_keyframes(armature):
    '''Get each bone location and rotation for each frame.'''
    location_list = []
    rotation_list = []

    for frame in range(
            bpy.context.scene.frame_start,
            bpy.context.scene.frame_end + 1):
        bpy.context.scene.frame_set(frame)

        locations = {}
        rotations = {}

        for bone in armature.pose.bones:
            bone_matrix = transform_animation_matrix(bone.matrix)
            if bone.parent and bone.parent.parent:
                parent_matrix = transform_animation_matrix(bone.parent.matrix)
                bone_matrix = parent_matrix.inverted() * bone_matrix
            elif bone.name == 'Locator_Locomotion':
                bone_matrix = bone.matrix
            elif not bone.parent:
                bone_matrix = Matrix()

            loc, rot, scl = bone_matrix.decompose()

            locations[bone.name] = loc
            rotations[bone.name] = rot.to_euler()

        location_list.append(locations.copy())
        rotation_list.append(rotations.copy())

        del locations
        del rotations

    bcPrint("Keyframes have been appended to lists.")

    return location_list, rotation_list


def set_keyframes(armature, location_list, rotation_list):
    '''Insert each keyframe from lists.'''

    bpy.context.scene.frame_set(bpy.context.scene.frame_start)

    for frame in range(
            bpy.context.scene.frame_start,
            bpy.context.scene.frame_end + 1):
        set_keyframe(armature, frame, location_list, rotation_list)

    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    bcPrint("Keyframes have been inserted to armature fakebones.")


def set_keyframe(armature, frame, location_list, rotation_list):
    '''Inset keyframe for current frame from lists.'''
    bpy.context.scene.frame_set(frame)

    for bone in armature.pose.bones:
        index = frame - bpy.context.scene.frame_start

        fakeBone = bpy.data.objects[bone.name]

        fakeBone.location = location_list[index][bone.name]
        fakeBone.rotation_euler = rotation_list[index][bone.name]

        fakeBone.keyframe_insert(data_path="location")
        fakeBone.keyframe_insert(data_path="rotation_euler")


def apply_animation_scale(armature):
    '''Apply Animation Scale.'''
    scene = bpy.context.scene
    remove_unused_meshes()

    if armature is None or armature.type != "ARMATURE":
        return

    skeleton = armature.data
    empties = []

    deselect_all()
    scene.frame_set(scene.frame_start)
    for pose_bone in armature.pose.bones:
        bmatrix = pose_bone.bone.head_local
        bpy.ops.object.empty_add(type='PLAIN_AXES', radius=0.1)
        empty = bpy.context.active_object
        empty.name = pose_bone.name

        bpy.ops.object.constraint_add(type='CHILD_OF')
        bpy.data.objects[empty.name].constraints[
            'Child Of'].use_scale_x = False
        bpy.data.objects[empty.name].constraints[
            'Child Of'].use_scale_y = False
        bpy.data.objects[empty.name].constraints[
            'Child Of'].use_scale_z = False

        bpy.data.objects[empty.name].constraints['Child Of'].target = armature
        bpy.data.objects[empty.name].constraints[
            'Child Of'].subtarget = pose_bone.name

        bcPrint("Baking animation on " + empty.name + "...")
        bpy.ops.nla.bake(
            frame_start=scene.frame_start,
            frame_end=scene.frame_end,
            step=1,
            only_selected=True,
            visual_keying=True,
            clear_constraints=True,
            clear_parents=False,
            bake_types={'OBJECT'})

        empties.append(empty)

    for empty in empties:
        empty.select = True

    bcPrint("Baked Animation successfully on empties.")
    deselect_all()

    set_active(armature)
    armature.select = True
    bpy.ops.anim.keyframe_clear_v3d()

    bpy.ops.object.transform_apply(rotation=True, scale=True)

    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.user_transforms_clear()

    for pose_bone in armature.pose.bones:
        pose_bone.constraints.new(type='COPY_LOCATION')
        pose_bone.constraints.new(type='COPY_ROTATION')

        for empty in empties:
            if empty.name == pose_bone.name:
                pose_bone.constraints['Copy Location'].target = empty
                pose_bone.constraints['Copy Rotation'].target = empty
                break

        pose_bone.bone.select = True

    bcPrint("Baking Animation on skeleton...")
    bpy.ops.nla.bake(
        frame_start=scene.frame_start,
        frame_end=scene.frame_end,
        step=1,
        only_selected=True,
        visual_keying=True,
        clear_constraints=True,
        clear_parents=False,
        bake_types={'POSE'})

    bpy.ops.object.mode_set(mode='OBJECT')

    deselect_all()

    bcPrint("Clearing empty data...")
    for empty in empties:
        empty.select = True

    bpy.ops.object.delete()

    bcPrint("Apply Animation was completed.")


def get_animation_id(group):
    node_type = get_node_type(group)
    node_name = get_node_name(group)

    return "{!s}-{!s}".format(node_name, node_name)

    # Now anm files produces with name as node_name_node_name.anm
    # after the process is done anm files are renmaed by rc.py to
    # cga_name_node_name.anm
    # In the future we may export directly correct name
    # with using below codes. But there is a prerequisite for that:
    # Dae have to be one main visual_node, others have to be in that main node
    # To achieve that we must change a bit visual_exporting process for anm.
    # Deficiency at that way process export nodes show as one at console.
    if node_type == 'i_caf':
        return "{!s}-{!s}".format(node_name, node_name)
    else:
        cga_node = find_cga_node_from_anm_node(group)
        if cga_node:
            cga_name = get_node_name(cga_node)
            return "{!s}-{!s}".format(node_name, cga_name)
        else:
            cga_name = group.objects[0].name
            return "{!s}-{!s}".format(node_name, cga_name)


def get_geometry_animation_file_name(group):
    node_type = get_node_type(group)
    node_name = get_node_name(group)

    cga_node = find_cga_node_from_anm_node(group)
    if cga_node:
        cga_name = get_node_name(cga_node)
        return "{!s}_{!s}.anm".format(cga_name, node_name)
    else:
        cga_name = group.objects[0].name
        return "{!s}_{!s}.anm".format(cga_name, node_name)


def find_cga_node_from_anm_node(anm_group):
    for object_ in anm_group.objects:
        for group in object_.users_group:
            if get_node_type(group) == 'cga':
                return group
    return None


#------------------------------------------------------------------------------
# LOD Functions:
#------------------------------------------------------------------------------

def is_lod_geometry(object_):
    return object_.name[:-1].endswith('_LOD')


def is_has_lod(object_):
    return ("{}_LOD1".format(object_.name) in bpy.data.objects)


def changed_lod_name(lod_name):
    index = lod_name[len(lod_name) - 1]
    return "_lod{}_{}".format(index, lod_name[:-5])


def get_lod_geometries(object_):
    lods = []
    lod_base_name = "{}_LOD".format(object_.name)
    for obj in bpy.data.objects:
        if obj.name.startswith(lod_base_name):
            lods.append(obj)

    return lods


#------------------------------------------------------------------------------
# Bone Physics:
#------------------------------------------------------------------------------

def get_bone_geometry(bone):
    bone_name = bone.name
    if bone_name.endswith("_Phys"):
        bone_name = bone_name[:-5]

    return bpy.data.objects.get("{}_boneGeometry".format(bone_name), None)


def is_bone_geometry(object_):
    if object_.type == "MESH" and object_.name.endswith("_boneGeometry"):
        return True
    else:
        return False


def is_physic_bone(bone):
    if bone.name.endswith("_Phys"):
        return True
    else:
        return False


def make_physic_bone(bone):
    if bone.name.endswith('.001'):
        bone.name = bone.name.replace('.001', '_Phys')
    else:
        bone.name = "{}_Phys".format(bone.name)


def get_armature_physic(armature):
    physic_name = "{}_Phys".format(armature.name)
    if physic_name in bpy.data.objects:
        return bpy.data.objects[physic_name]
    else:
        return None


def get_bone_material_type(bone, bone_type):
    if bone_type == 'leg' or bone_type == 'arm' or bone_type == 'foot':
        left_list = ['left', '.l']
        if is_in_list(bone.name, left_list):
            return "l{}".format(bone_type)
        else:
            return "r{}".format(bone_type)

    elif bone_type == 'other':
        return 'primitive'

    return bone_type


def get_bone_type(bone):
    if is_leg_bone(bone):
        return 'leg'
    elif is_arm_bone(bone):
        return 'arm'
    elif is_torso_bone(bone):
        return 'torso'
    elif is_head_bone(bone):
        return 'head'
    elif is_foot_bone(bone):
        return 'foot'
    else:
        return 'other'


def is_leg_bone(bone):
    leg = ['leg', 'shin', 'thigh', 'calf']
    return is_in_list(bone.name, leg)


def is_arm_bone(bone):
    arm = ['arm', 'hand']
    return is_in_list(bone.name, arm)


def is_torso_bone(bone):
    torso = ['hips', 'pelvis', 'spine', 'chest', 'torso']
    return is_in_list(bone.name, torso)


def is_head_bone(bone):
    head = ['head', 'neck']
    return is_in_list(bone.name, head)


def is_foot_bone(bone):
    foot = ['foot', 'toe']
    return is_in_list(bone.name, foot)


def is_in_list(str, list_):
    for sub in list_:
        if str.lower().find(sub) != -1:
            return True
    return False


#------------------------------------------------------------------------------
# Skeleton:
#------------------------------------------------------------------------------

def get_root_bone(armature):
    for bone in get_bones(armature):
        if bone.parent is None:
            return bone


def count_root_bones(armature):
    count = 0
    for bone in get_bones(armature):
        if bone.parent is None:
            count += 1

    return count


def get_armature_for_object(object_):
    if object_.parent is not None:
        if object_.parent.type == "ARMATURE":
            return object_.parent


def get_armature():
    for object_ in get_type("controllers"):
        return object_


def get_bones(armature):
    return [bone for bone in armature.data.bones]


def get_animation_node_range(object_, node_name, initial_start, initial_end):
    try:
        start_frame = object_["{}_Start".format(node_name)]
        end_frame = object_["{}_End".format(node_name)]

        if isinstance(start_frame, str) and isinstance(end_frame, str):
            tm = bpy.context.scene.timeline_markers
            if tm.find(start_frame) != -1 and tm.find(end_frame) != -1:
                return tm[start_frame].frame, tm[end_frame].frame
            else:
                raise exceptions.MarkerNotFound
        else:
            return start_frame, end_frame
    except:
        return initial_start, initial_end


def get_armature_from_node(group):
    armature_count = 0
    armature = None
    for object_ in group.objects:
        if object_.type == "ARMATURE":
            armature_count += 1
            armature = object_

    if armature_count == 1:
        return armature

    error_message = None
    if armature_count == 0:
        raise exceptions.BCryException("i_caf node has no armature!")
        error_message = "i_caf node has no armature!"
    elif armature_count > 1:
        raise exceptions.BCryException(
            "{} i_caf node have more than one armature!".format(node_name))

    return None


def activate_all_bone_layers(armature):
    layers = []
    for index in range(0, 32):
        layers.append(armature.data.layers[index])
        armature.data.layers[index] = True

    return layers


def recover_bone_layers(armature, layers):
    for index in range(0, 32):
        armature.data.layers[index] = layers[index]


#------------------------------------------------------------------------------
# General:
#------------------------------------------------------------------------------

def select_all():
    for object_ in bpy.data.objects:
        object_.select = True


def deselect_all():
    for object_ in bpy.data.objects:
        object_.select = False


def set_active(object_):
    bpy.context.scene.objects.active = object_


def get_object_children(parent):
    return [child for child in parent.children
            if child.type in {'ARMATURE', 'EMPTY', 'MESH'}]


def parent(children, parent):
    for object_ in children:
        object_.parent = parent

    return


def remove_unused_meshes():
    for mesh in bpy.data.meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def get_bounding_box(object_):
    vmin = Vector()
    vmax = Vector()
    if object_.type == 'EMPTY':
        k = object_.empty_draw_size
        vmax = Vector((k, k, k))
        vmin = Vector((-k, -k, -k))
    elif object_.type == 'MESH':
        box = object_.bound_box
        vmin = Vector([box[0][0], box[0][1], box[0][2]])
        vmax = Vector([box[6][0], box[6][1], box[6][2]])

    return vmin[0], vmin[1], vmin[2], vmax[0], vmax[1], vmax[2]


#------------------------------------------------------------------------------
# Overriding Context:
#------------------------------------------------------------------------------

def get_3d_context(object_):
    window = bpy.context.window
    screen = window.screen
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area3d = area
            break
    for region in area3d.regions:
        if region.type == "WINDOW":
            region3d = region
            break
    override = {
        "window": window,
        "screen": screen,
        "area": area3d,
        "region": region3d,
        "object": object_
    }

    return override


def override(obj, active=True, selected=True):
    ctx = bpy.context.copy()
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            ctx['area'] = area
            ctx['region'] = area.regions[-1]
            break

    if active:
        ctx['active_object'] = obj
        ctx['active_base'] = obj
        ctx['object'] = obj

    if selected:
        ctx['selected_objects'] = [obj]
        ctx['selected_bases'] = [obj]
        ctx['selected_editable_objects'] = [obj]
        ctx['selected_editable_bases'] = [obj]

    return ctx


#------------------------------------------------------------------------------
# Layer File:
#------------------------------------------------------------------------------

def get_guid():
    GUID = "{{}-{}-{}-{}-{}}".format(random_hex_sector(8),
                                     random_hex_sector(4),
                                     random_hex_sector(4),
                                     random_hex_sector(4),
                                     random_hex_sector(12))
    return GUID


def random_hex_sector(length):
    fixed_length_hex_format = "%0{}x".format(length)
    return fixed_length_hex_format % random.randrange(16 ** length)


#------------------------------------------------------------------------------
# Scripting:
#------------------------------------------------------------------------------

def generate_file_contents(type_):
    if type_ == "chrparams":
        return """<Params>\
<AnimationList>\
<Animation name="???" path="???.caf"/>\
</AnimationList>\
</Params>"""

    elif type_ == "cdf":
        return """<CharacterDefinition>\
<Model File="???.chr" Material="???"/>\
<AttachmentList>\
<Attachment Type="CA_BONE" AName="???" Rotation="1,0,0,0" Position="0,0,0" BoneName="???" Flags="0"/>\
<Attachment Type="CA_SKIN" AName="???" Binding="???.skin" Flags="0"/>\
</AttachmentList>\
<ShapeDeformation COL0="0" COL1="0" COL2="0" COL3="0" COL4="0" COL5="0" COL6="0" COL7="0"/>\
</CharacterDefinition>"""


def generate_file(filepath, contents, overwrite=False):
    if not os.path.exists(filepath) or overwrite:
        file = open(filepath, 'w')
        file.write(contents)
        file.close()


def generate_xml(filepath, contents, overwrite=False, ind=4):
    if not os.path.exists(filepath) or overwrite:
        if isinstance(contents, str):
            script = parseString(contents)
        else:
            script = contents
        contents = script.toprettyxml(indent=' ' * ind)
        generate_file(filepath, contents, overwrite)


def clear_xml_header(filepath):
    lines = open(filepath, 'r').readlines()
    if lines[0].find("<?xml version") == -1:
        return filepath

    lines = lines[1:]
    file = open(filepath, 'w')
    for line in lines:
        file.write(line)
    file.close()


def remove_file(filepath):
    if os.path.exists(filepath):
        os.remove(filepath)


#------------------------------------------------------------------------------
# Collada:
#------------------------------------------------------------------------------

def write_source(id_, type_, array, params):
    doc = Document()
    length = len(array)
    if type_ == "float4x4":
        stride = 16
    elif len(params) == 0:
        stride = 1
    else:
        stride = len(params)
    count = int(length / stride)

    source = doc.createElement("source")
    source.setAttribute("id", id_)

    if type_ == "float4x4":
        source_data = doc.createElement("float_array")
    else:
        source_data = doc.createElement("{!s}_array".format(type_))
    source_data.setAttribute("id", "{!s}-array".format(id_))
    source_data.setAttribute("count", str(length))
    try:
        source_data.appendChild(doc.createTextNode(floats_to_string(array)))
    except TypeError:
        source_data.appendChild(doc.createTextNode(strings_to_string(array)))
    technique_common = doc.createElement("technique_common")
    accessor = doc.createElement("accessor")
    accessor.setAttribute("source", "#{!s}-array".format(id_))
    accessor.setAttribute("count", str(count))
    accessor.setAttribute("stride", str(stride))
    for param in params:
        param_node = doc.createElement("param")
        param_node.setAttribute("name", param)
        param_node.setAttribute("type", type_)
        accessor.appendChild(param_node)
    if len(params) == 0:
        param_node = doc.createElement("param")
        param_node.setAttribute("type", type_)
        accessor.appendChild(param_node)
    technique_common.appendChild(accessor)

    source.appendChild(source_data)
    source.appendChild(technique_common)

    return source


def write_input(name, offset, type_, semantic):
    doc = Document()
    id_ = "{!s}-{!s}".format(name, type_)
    input = doc.createElement("input")

    if offset is not None:
        input.setAttribute("offset", str(offset))
    input.setAttribute("semantic", semantic)
    input.setAttribute("source", "#{!s}".format(id_))

    return input


# this is needed if you want to access more than the first def
if __name__ == "__main__":
    register()
