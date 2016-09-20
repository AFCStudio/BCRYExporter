#------------------------------------------------------------------------------
# Name:        material_utils.py
# Purpose:     Holds material and texture functions.
#
# Author:      Özkan Afacan
#              Angelo J. Miner, Mikołaj Milej, Daniel White,
#              Oscar Martin Garcia, Duo Oratar, David Marcelis
#
# Created:     17/09/2016
# Copyright:   (c) Özkan Afacan 2016
# License:     GPLv2+
#------------------------------------------------------------------------------


if "bpy" in locals():
    import imp
    imp.reload(utils)
else:
    import bpy
    from io_bcry_exporter import utils
from bpy.props import *
from bpy_extras.io_utils import ExportHelper
import bpy
import bpy.ops
import bpy_extras
import re
import math
import os


#------------------------------------------------------------------------------
# Generate Materials:
#------------------------------------------------------------------------------

def generate_mtl_file():
    return None


#------------------------------------------------------------------------------
# Collections:
#------------------------------------------------------------------------------

def get_materials():
    items = []
    allowed = {"MESH"}
    for object_ in utils.get_type("objects"):
        if object_.type in allowed:
            for material_slot in object_.material_slots:
                items.append(material_slot.material)

    return items


def get_texture_nodes_for_cycles():
    cycles_nodes = []

    for material in get_materials():
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if is_valid_cycles_texture_node(node):
                    cycles_nodes.append(node)

    return cycles_nodes


def get_texture_slots():
    items = []
    for material in get_materials():
        items.extend(get_texture_slots_for_material(material))

    return items


def get_textures():
    items = []
    for texture_slot in get_texture_slots():
        items.append(texture_slot.texture)

    return items


#------------------------------------------------------------------------------
# Conversions:
#------------------------------------------------------------------------------

def color_to_string(color, a):
    if type(color) in (float, int):
        return "{:f} {:f} {:f} {:f}".format(color, color, color, a)
    elif type(color).__name__ == "Color":
        return "{:f} {:f} {:f} {:f}".format(color.r, color.g, color.b, a)


#------------------------------------------------------------------------------
# Materials:
#------------------------------------------------------------------------------

def get_material_counter():
    """Returns a dictionary with all CryExportNodes."""
    materialCounter = {}
    for group in bpy.data.groups:
        if utils.is_export_node(group):
            materialCounter[group.name] = 0
    return materialCounter


def get_material_physics():
    """Returns a dictionary with the physics of all material names."""
    physicsProperties = {}
    for material in bpy.data.materials:
        properties = extract_bcry_properties(material.name)
        if properties:
            physicsProperties[properties["Name"]] = properties["Physics"]
    return physicsProperties


def get_materials_per_group(group):
    materials = []
    for _objtmp in bpy.data.groups[group].objects:
        for material in _objtmp.data.materials:
            if material is not None:
                if material.name not in materials:
                    materials.append(material.name)
    return materials


def get_material_color(material, type_):
    color = 0.0
    alpha = 1.0

    if type_ == "emission":
        color = material.emit
    elif type_ == "ambient":
        color = material.ambient
    elif type_ == "diffuse":
        color = material.diffuse_color
        alpha = material.alpha
    elif type_ == "specular":
        color = material.specular_color

    col = color_to_string(color, alpha)
    return col


def get_material_attribute(material, type_):
    if type_ == "shininess":
        float = material.specular_hardness
    elif type_ == "index_refraction":
        float = material.alpha

    return str(float)


def get_material_parts(node, material):
    VALID_PHYSICS = ("physDefault", "physProxyNoDraw", "physNoCollide",
                     "physObstruct", "physNone")

    parts = material.split("__")
    count = len(parts)

    group = node
    index = 0
    name = material
    physics = "physDefault"

    if count == 1:
        # name
        index = 0
    elif count == 2:
        # XXX__name or name__phys
        if parts[1] not in VALID_PHYSICS:
            # XXX__name
            index = int(parts[0])
            name = parts[1]
        else:
            # name__phys
            name = parts[0]
            physics = parts[1]
    elif count == 3:
        # XXX__name__phys
        index = int(parts[0])
        name = parts[1]
        physics = parts[2]
    elif count == 4:
        # group__XXX__name__phys
        group = parts[0]
        index = int(parts[1])
        name = parts[2]
        physics = parts[3]

    name = utils.replace_invalid_rc_characters(name)
    if physics not in VALID_PHYSICS:
        physics = "physDefault"

    return group, index, name, physics


def extract_bcry_properties(material_name):
    """Returns the BCry properties of a material_name as dict or
    None if name is invalid.
    """
    if is_bcry_material(material_name):
        groups = re.findall(
            "(.+)__([0-9]+)__(.*)__(phys[A-Za-z0-9]+)",
            material_name)
        properties = {}
        properties["ExportNode"] = groups[0][0]
        properties["Number"] = int(groups[0][1])
        properties["Name"] = groups[0][2]
        properties["Physics"] = groups[0][3]
        return properties
    return None


def remove_bcry_properties():
    """Removes BCry Exporter properties from all material names."""
    for material in bpy.data.materials:
        properties = extract_bcry_properties(material.name)
        if properties:
            material.name = properties["Name"]


def is_bcry_material(material_name):
    if re.search(".+__[0-9]+__.*__phys[A-Za-z0-9]+", material_name):
        return True
    else:
        return False

def add_phys_material(self, context, physName):
    if not physName.startswith("__"):
        physName = "__" + physName

    me = bpy.context.active_object
    if me.active_material:
        me.active_material.name = replace_phys_material(
            me.active_material.name, physName)

    return {'FINISHED'}


def replace_phys_material(material_name, phys):
    if "__phys" in material_name:
        return re.sub(r"__phys.*", phys, material_name)
    else:
        return "{}{}".format(material_name, phys)


#------------------------------------------------------------------------------
# Textures:
#------------------------------------------------------------------------------

def get_texture_nodes_for_material(material):
    cycles_nodes = []

    if material.use_nodes:
        for node in material.node_tree.nodes:
            if is_valid_cycles_texture_node(node):
                cycles_nodes.append(node)

    return cycles_nodes


def get_texture_slots_for_material(material):
    texture_slots = []
    for texture_slot in material.texture_slots:
        if texture_slot and texture_slot.texture.type == 'IMAGE':
            texture_slots.append(texture_slot)

    validate_texture_slots(texture_slots)

    return texture_slots


def validate_texture_slots(texture_slots):
    texture_types = count_texture_types(texture_slots)
    raise_exception_if_textures_have_same_type(texture_types)


def count_texture_types(texture_slots):
    texture_types = {
        'DIFFUSE': 0,
        'SPECULAR': 0,
        'NORMAL MAP': 0
    }

    for texture_slot in texture_slots:
        if texture_slot.use_map_color_diffuse:
            texture_types['DIFFUSE'] += 1
        if texture_slot.use_map_color_spec:
            texture_types['SPECULAR'] += 1
        if texture_slot.use_map_normal:
            texture_types['NORMAL MAP'] += 1

    return texture_types


def raise_exception_if_textures_have_same_type(texture_types):
    ERROR_TEMPLATE = "There is more than one texture of type {!r}."
    error_messages = []

    for type_name, type_count in texture_types.items():
        if type_count > 1:
            error_messages.append(ERROR_TEMPLATE.format(type_name.lower()))

    if error_messages:
        raise exceptions.BCryException(
            "\n".join(error_messages) +
            "\n" +
            "Please correct that and try again.")


def is_valid_image(image):
    return image.has_data and image.filepath


def is_valid_cycles_texture_node(node):
    ALLOWED_NODE_NAMES = ('Image Texture', 'Specular', 'Normal')
    if node.type == 'TEX_IMAGE' and node.name in ALLOWED_NODE_NAMES:
        if node.image:
            return True

    return False


def get_image_path_for_game(image, game_dir):
    if not game_dir or not os.path.isdir(game_dir):
        raise exceptions.NoGameDirectorySelected

    image_path = os.path.normpath(bpy.path.abspath(image.filepath))
    image_path = "{}.dds".format(os.path.splitext(image_path)[0])
    image_path = os.path.relpath(image_path, game_dir)

    return image_path
