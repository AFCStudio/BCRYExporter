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
    imp.reload(exceptions)
else:
    import bpy
    from io_bcry_exporter import utils, exceptions

from io_bcry_exporter.rc import RCInstance
from io_bcry_exporter.outpipe import bcPrint
from collections import OrderedDict
from xml.dom.minidom import Document, Element, parse, parseString
import bpy
import re
import math
import os
import xml.dom.minidom


#------------------------------------------------------------------------------
# Generate Materials:
#------------------------------------------------------------------------------

def generate_mtl_files(_config, materials=None):
    if materials is None:
        materials = get_materials(_config.export_selected_nodes)

    for node in get_material_groups(materials):
        _doc = Document()
        parent_material = _doc.createElement('Material')
        parent_material.setAttribute("MtlFlags", "524544")
        parent_material.setAttribute("vertModifType", "0")
        sub_material = _doc.createElement('SubMaterials')
        parent_material.appendChild(sub_material)
        set_public_params(_doc, None, parent_material)

        print()
        bcPrint("'{}' material is being processed...".format(node))

        for material_name, material in materials.items():
            if material_name.split('__')[0] != node:
                continue

            print()
            write_material_information(material_name)

            material_node = _doc.createElement('Material')

            set_material_attributes(material, material_name, material_node)
            add_textures(_doc, material, material_node, _config)
            set_public_params(_doc, material, material_node)

            sub_material.appendChild(material_node)

        _doc.appendChild(parent_material)

        filename = "{!s}.mtl".format(node)
        filepath = os.path.join(os.path.dirname(_config.filepath), filename)
        utils.generate_xml(filepath, _doc, True, 1)
        utils.clear_xml_header(filepath)

        print()
        bcPrint("'{}' material file has been generated.".format(filename))


def write_material_information(material_name):
    parts = material_name.split('__')
    bcPrint("Subname: '{}'  -  Index: '{}'  -  Physic Type: '{}'".format(
        parts[2], parts[1], parts[3]))


def get_material_groups(materials):
    material_groups = []

    for material_name, material in materials.items():
        group_name = material_name.split('__')[0]

        if not (group_name in material_groups):
            material_groups.append(group_name)

    return material_groups


def sort_materials_by_names(unordered_materials):
    materials = OrderedDict()
    for material_name in sorted(unordered_materials):
        materials[material_name] = unordered_materials[material_name]

    return materials


def get_materials(just_selected=False):
    materials = OrderedDict()
    material_counter = {}

    for group in utils.get_mesh_export_nodes(just_selected):
        material_counter[group.name] = 0
        for object in group.objects:
            for i in range(0, len(object.material_slots)):
                slot = object.material_slots[i]
                material = slot.material
                if material is None:
                    continue

                if material not in materials.values():
                    node_name = utils.get_node_name(group)

                    material.name = utils.replace_invalid_rc_characters(
                        material.name)
                    for image in get_textures(material):
                        try:
                            image.name = utils.replace_invalid_rc_characters(
                                image.name)
                        except AttributeError:
                            pass

                    node, index, name, physics = get_material_parts(
                        node_name, slot.material.name)

                    # check if material has no position defined
                    if index == 0:
                        material_counter[group.name] += 1
                        index = material_counter[group.name]

                    material_name = "{}__{:02d}__{}__{}".format(
                        node, index, name, physics)
                    materials[material_name] = material

    return sort_materials_by_names(materials)


def set_material_attributes(material, material_name, material_node):
    material_node.setAttribute("Name", get_material_name(material_name))
    material_node.setAttribute("MtlFlags", "524416")

    shader = "Illum"
    if "physProxyNoDraw" == get_material_physic(material_name):
        shader = "Nodraw"
    material_node.setAttribute("Shader", shader)
    material_node.setAttribute("GenMask", "60400000")
    material_node.setAttribute(
        "StringGenMask",
        "%NORMAL_MAP%SPECULAR_MAP%SUBSURFACE_SCATTERING")
    material_node.setAttribute("SurfaceType", "")
    material_node.setAttribute("MatTemplate", "")

    material_node.setAttribute(
        "Diffuse", color_to_xml_string(
            material.diffuse_color))
    material_node.setAttribute(
        "Specular", color_to_xml_string(
            material.specular_color))
    material_node.setAttribute("Opacity", str(material.alpha))
    material_node.setAttribute("Shininess", str(material.specular_hardness))

    material_node.setAttribute("vertModifType", "0")
    material_node.setAttribute("LayerAct", "1")

    if material.emit:
        emit_color = "1,1,1,{}".format(str(int(material.emit * 100)))
        material_node.setAttribute("Emittance", emit_color)


def set_public_params(_doc, material, material_node):
    public_params = _doc.createElement('PublicParams')
    public_params.setAttribute("EmittanceMapGamma", "1")
    public_params.setAttribute("SSSIndex", "0")
    public_params.setAttribute("IndirectColor", "0.25, 0.25, 0.25")

    material_node.appendChild(public_params)


def add_textures(_doc, material, material_node, _config):
    textures_node = _doc.createElement("Textures")

    diffuse = get_diffuse_texture(material)
    specular = get_specular_texture(material)
    normal = get_normal_texture(material)

    if diffuse:
        texture_node = _doc.createElement('Texture')
        texture_node.setAttribute("Map", "Diffuse")
        path = get_image_path_for_game(diffuse, _config.game_dir)
        texture_node.setAttribute("File", path)
        textures_node.appendChild(texture_node)
        bcPrint("Diffuse Path: {}.".format(path))
    else:
        if "physProxyNoDraw" != get_material_physic(material.name):
            texture_node = _doc.createElement('Texture')
            texture_node.setAttribute("Map", "Diffuse")
            path = "textures/defaults/white.dds"
            texture_node.setAttribute("File", path)
            textures_node.appendChild(texture_node)
            bcPrint("Diffuse Path: {}.".format(path))
    if specular:
        texture_node = _doc.createElement('Texture')
        texture_node.setAttribute("Map", "Specular")
        path = get_image_path_for_game(specular, _config.game_dir)
        texture_node.setAttribute("File", path)
        textures_node.appendChild(texture_node)
        bcPrint("Specular Path: {}.".format(path))
    if normal:
        texture_node = _doc.createElement('Texture')
        texture_node.setAttribute("Map", "Normal")
        path = get_image_path_for_game(normal, _config.game_dir)
        texture_node.setAttribute("File", path)
        textures_node.appendChild(texture_node)
        bcPrint("Normal Path: {}.".format(path))

    if _config.convert_textures:
        convert_image_to_dds([diffuse, specular, normal], _config)

    material_node.appendChild(textures_node)


#------------------------------------------------------------------------------
# Convert DDS:
#------------------------------------------------------------------------------

def convert_image_to_dds(images, _config):
    converter = RCInstance(_config)
    converter.convert_tif(images)


#------------------------------------------------------------------------------
# Collections:
#------------------------------------------------------------------------------

def get_textures(material):
    images = []

    images.append(get_diffuse_texture(material))
    images.append(get_specular_texture(material))
    images.append(get_normal_texture(material))

    return images


def get_diffuse_texture(material):
    image = None
    try:
        if bpy.context.scene.render.engine == 'CYCLES':
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    if node.name == 'Image Texture' or \
                                    node.name.lower().find('diffuse') != -1:
                        image = node.image
                        if is_valid_image(image):
                            return image
        else:
            for slot in material.texture_slots:
                if slot.texture.type == 'IMAGE':
                    if slot.use_map_color_diffuse:
                        image = slot.texture.image
                        if is_valid_image(image):
                            return image
    except:
        pass

    return None


def get_specular_texture(material):
    image = None
    try:
        if bpy.context.scene.render.engine == 'CYCLES':
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    if node.name.lower().find('specular') != -1:
                        image = node.image
                        if is_valid_image(image):
                            return image
        else:
            for slot in material.texture_slots:
                if slot.texture.type == 'IMAGE':
                    if slot.use_map_color_spec or slot.use_map_specular:
                        image = slot.texture.image
                        if is_valid_image(image):
                            return image
    except:
        pass

    return None


def get_normal_texture(material):
    image = None
    try:
        if bpy.context.scene.render.engine == 'CYCLES':
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    if node.name.lower().find('normal') != -1:
                        image = node.image
                        if is_valid_image(image):
                            return image
        else:
            for slot in material.texture_slots:
                if slot.texture.type == 'IMAGE':
                    if slot.use_map_color_normal:
                        image = slot.texture.image
                        if is_valid_image(image):
                            return image
    except:
        pass

    return None


#------------------------------------------------------------------------------
# Conversions:
#------------------------------------------------------------------------------

def color_to_string(color, a):
    if type(color) in (float, int):
        return "{:f} {:f} {:f} {:f}".format(color, color, color, a)
    elif type(color).__name__ == "Color":
        return "{:f} {:f} {:f} {:f}".format(color.r, color.g, color.b, a)


def color_to_xml_string(color):
    if type(color) in (float, int):
        return "{:f},{:f},{:f}".format(color, color, color)
    elif type(color).__name__ == "Color":
        return "{:f},{:f},{:f}".format(color.r, color.g, color.b)


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
    physics = "physNone"

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
        physics = "physNone"

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


def is_bcry_material_with_numbers(material_name):
    if re.search("[0-9]+__.*", material_name):
        return True
    else:
        return False


def get_material_name(material_name):
    try:
        return material_name.split('__')[2]
    except:
        raise exceptions.BCryException(
            "Material name is not convenient for BCry!")


def get_material_physic(material_name):
    index = material_name.find("__phys")
    if index != -1:
        return material_name[index + 2:]

    return "physNone"


def set_material_physic(self, context, phys_name):
    if not phys_name.startswith("__"):
        phys_name = "__" + phys_name

    me = bpy.context.active_object
    if me.active_material:
        me.active_material.name = replace_phys_material(
            me.active_material.name, phys_name)

    return {'FINISHED'}


def replace_phys_material(material_name, phys):
    if "__phys" in material_name:
        return re.sub(r"__phys.*", phys, material_name)
    else:
        return "{}{}".format(material_name, phys)


#------------------------------------------------------------------------------
# Textures:
#------------------------------------------------------------------------------

def is_valid_image(image):
    try:
        return image.has_data and image.filepath
    except:
        return False


def get_image_path_for_game(image, game_dir):
    if not game_dir or not os.path.isdir(game_dir):
        raise exceptions.NoGameDirectorySelected

    image_path = os.path.normpath(bpy.path.abspath(image.filepath))
    image_path = "{}.dds".format(os.path.splitext(image_path)[0])
    image_path = os.path.relpath(image_path, game_dir)

    return image_path
