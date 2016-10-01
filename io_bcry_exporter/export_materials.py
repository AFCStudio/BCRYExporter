#------------------------------------------------------------------------------
# Name:        export_materials.py
# Purpose:     Material exporter to CryEngine.
#
# Author:      Özkan Afacan
#              Angelo J. Miner, Mikołaj Milej, Daniel White,
#              Oscar Martin Garcia, Duo Oratar, David Marcelis
#
# Created:     30/09/2016
# Copyright:   (c) Özkan Afacan 2016
# License:     GPLv2+
#------------------------------------------------------------------------------

if "bpy" in locals():
    import imp
    imp.reload(utils)
    imp.reload(material_utils)
else:
    import bpy
    from io_bcry_exporter import utils, material_utils

from io_bcry_exporter.outpipe import bcPrint

from bpy_extras.io_utils import ExportHelper
from collections import OrderedDict
from xml.dom.minidom import Document, Element, parse, parseString
import copy
import os
import threading
import subprocess
import xml.dom.minidom


class CrytekMaterialExporter:

    def __init__(self, config):
        self._config = config
        self._doc = Document()
        self._materials = material_utils.get_materials(
                                            config.export_selected_nodes)

    def generate_materials(self):
        material_utils.generate_mtl_files(self._config, self._materials)

    def get_materials_for_object(self, object_):
        materials = OrderedDict()
        for material, materialname in self._materials.items():
            for object_material in object_.data.materials:
                if material.name == object_material.name:
                    materials[material] = materialname

        return materials


#------------------------------------------------------------------------------
# Library Images:
#------------------------------------------------------------------------------

    def export_library_images(self, library_images):
        images = []
        for node in utils.get_export_nodes():
            for material in self._materials:
                for image in material_utils.get_textures(material):
                    if image:
                        images.append(image)

        self._write_texture_nodes(list(set(images)), library_images)

    def _write_texture_nodes(self, images, library_images):
        for image in images:
            image_node = self._doc.createElement('image')
            image_node.setAttribute("id", image.name)
            image_node.setAttribute("name", image.name)
            init_form = self._doc.createElement('init_from')
            path = material_utils.get_image_path_for_game(image, self._config.game_dir)
            path_node = self._doc.createTextNode(path)
            init_form.appendChild(path_node)
            image_node.appendChild(init_form)
            library_images.appendChild(image_node)

        if self._config.convert_textures:
            material_utils.convert_image_to_dds(images, self._config)

#------------------------------------------------------------------------------
# Library Effects:
#------------------------------------------------------------------------------

    def export_library_effects(self, library_effects):
        for material, materialname in self._materials.items():
            self._export_library_effects_material(
                material, materialname, library_effects)

    def _export_library_effects_material(
            self, material, materialname, library_effects):

        images = material_utils.get_textures(material)

        effect_node = self._doc.createElement("effect")
        effect_node.setAttribute("id", "{}_fx".format(materialname))
        profile_node = self._doc.createElement("profile_COMMON")
        self._write_surface_and_sampler(images, profile_node)

        technique_common = self._doc.createElement("technique")
        technique_common.setAttribute("sid", "common")

        self._write_phong_node(material, images, technique_common)
        profile_node.appendChild(technique_common)

        extra = self._create_double_sided_extra("GOOGLEEARTH")
        profile_node.appendChild(extra)
        effect_node.appendChild(profile_node)

        extra = self._create_double_sided_extra("MAX3D")
        effect_node.appendChild(extra)
        library_effects.appendChild(effect_node)

    def _write_surface_and_sampler(self, images, profile_node):
        for image in images:
            if image == None:
                continue

            surface = self._doc.createElement("newparam")
            surface.setAttribute("sid", "{}-surface".format(image.name))
            surface_node = self._doc.createElement("surface")
            surface_node.setAttribute("type", "2D")
            init_from_node = self._doc.createElement("init_from")
            temp_node = self._doc.createTextNode(image.name)
            init_from_node.appendChild(temp_node)
            surface_node.appendChild(init_from_node)
            surface.appendChild(surface_node)
            sampler = self._doc.createElement("newparam")
            sampler.setAttribute("sid", "{}-sampler".format(image.name))
            sampler_node = self._doc.createElement("sampler2D")
            source_node = self._doc.createElement("source")
            temp_node = self._doc.createTextNode(
                "{}-surface".format(image.name))
            source_node.appendChild(temp_node)
            sampler_node.appendChild(source_node)
            sampler.appendChild(sampler_node)

            profile_node.appendChild(surface)
            profile_node.appendChild(sampler)

    def _write_phong_node(self, material, images, parent_node):
        phong = self._doc.createElement("phong")

        emission = self._create_color_node(material, "emission")
        ambient = self._create_color_node(material, "ambient")

        if images[0]:
            diffuse = self._create_texture_node(images[0].name, "diffuse")
        else:
            diffuse = self._create_color_node(material, "diffuse")

        if images[1]:
            specular = self._create_texture_node(images[1].name, "specular")
        else:
            specular = self._create_color_node(material, "specular")

        shininess = self._create_attribute_node(material, "shininess")
        index_refraction = self._create_attribute_node(
            material, "index_refraction")

        phong.appendChild(emission)
        phong.appendChild(ambient)
        phong.appendChild(diffuse)
        phong.appendChild(specular)
        phong.appendChild(shininess)
        phong.appendChild(index_refraction)

        if images[2]:
            normal = self._create_texture_node(images[2].name, "normal")
            phong.appendChild(normal)

        parent_node.appendChild(phong)

    def _create_color_node(self, material, type_):
        node = self._doc.createElement(type_)
        color = self._doc.createElement("color")
        color.setAttribute("sid", type_)
        col = material_utils.get_material_color(material, type_)
        color_text = self._doc.createTextNode(col)
        color.appendChild(color_text)
        node.appendChild(color)

        return node

    def _create_texture_node(self, image_name, type_):
        node = self._doc.createElement(type_)
        texture = self._doc.createElement("texture")
        texture.setAttribute("texture", "{}-sampler".format(image_name))
        node.appendChild(texture)

        return node

    def _create_attribute_node(self, material, type_):
        node = self._doc.createElement(type_)
        float = self._doc.createElement("float")
        float.setAttribute("sid", type_)
        val = material_utils.get_material_attribute(material, type_)
        value = self._doc.createTextNode(val)
        float.appendChild(value)
        node.appendChild(float)

        return node

    def _create_double_sided_extra(self, profile):
        extra = self._doc.createElement("extra")
        technique = self._doc.createElement("technique")
        technique.setAttribute("profile", profile)
        double_sided = self._doc.createElement("double_sided")
        double_sided_value = self._doc.createTextNode("1")
        double_sided.appendChild(double_sided_value)
        technique.appendChild(double_sided)
        extra.appendChild(technique)

        return extra

#------------------------------------------------------------------------------
# Library Materials:
#------------------------------------------------------------------------------

    def export_library_materials(self, library_materials):
        for material, materialname in self._materials.items():
            material_element = self._doc.createElement('material')
            material_element.setAttribute('id', materialname)
            instance_effect = self._doc.createElement('instance_effect')
            instance_effect.setAttribute('url', '#{}_fx'.format(materialname))
            material_element.appendChild(instance_effect)
            library_materials.appendChild(material_element)
