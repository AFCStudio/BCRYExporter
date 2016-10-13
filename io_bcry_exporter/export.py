#------------------------------------------------------------------------------
# Name:        export.py
# Purpose:     Main exporter to CryEngine
#
# Author:      Özkan Afacan,
#              Angelo J. Miner, Mikołaj Milej, Daniel White,
#              Oscar Martin Garcia, Duo Oratar, David Marcelis
#              Some code borrowed from fbx exporter Campbell Barton
#
# Created:     23/01/2012
# Copyright:   (c) Angelo J. Miner 2012
# Copyright:   (c) Özkan Afacan 2016
# License:     GPLv2+
#------------------------------------------------------------------------------


if "bpy" in locals():
    import imp
    imp.reload(utils)
    imp.reload(export_materials)
    imp.reload(udp)
    imp.reload(exceptions)
else:
    import bpy
    from io_bcry_exporter import utils, export_materials, udp, exceptions

from io_bcry_exporter.rc import RCInstance
from io_bcry_exporter.outpipe import bcPrint
from io_bcry_exporter.utils import join

from bpy_extras.io_utils import ExportHelper
from collections import OrderedDict
from datetime import datetime
from mathutils import Matrix, Vector
from time import clock
from xml.dom.minidom import Document, Element, parse, parseString
import bmesh
import copy
import os
import threading
import subprocess
import time
import xml.dom.minidom


class CrytekDaeExporter:

    def __init__(self, config):
        self._config = config
        self._doc = Document()
        self._m_exporter = export_materials.CrytekMaterialExporter(config)

    def export(self):
        self._prepare_for_export()

        root_element = self._doc.createElement('collada')
        root_element.setAttribute(
            "xmlns", "http://www.collada.org/2005/11/COLLADASchema")
        root_element.setAttribute("version", "1.4.1")
        self._doc.appendChild(root_element)
        self._create_file_header(root_element)
        
        if self._config.generate_materials:
            self._m_exporter.generate_materials()

        # Just here for future use:
        self._export_library_cameras(root_element)
        self._export_library_lights(root_element)
        ###

        self._export_library_images(root_element)
        self._export_library_effects(root_element)
        self._export_library_materials(root_element)
        self._export_library_geometries(root_element)

        utils.add_fakebones()
        try:
            self._export_library_controllers(root_element)
            self._export_library_animation_clips_and_animations(root_element)
            self._export_library_visual_scenes(root_element)
        except RuntimeError:
            pass
        finally:
            utils.remove_fakebones()

        self._export_scene(root_element)

        converter = RCInstance(self._config)
        converter.convert_dae(self._doc)

        write_scripts(self._config)

    def _prepare_for_export(self):
        utils.clean_file(self._config.export_selected_nodes)

        if self._config.apply_modifiers:
            utils.apply_modifiers(self._config.export_selected_nodes)

        if self._config.fix_weights:
            utils.fix_weights()

    def _create_file_header(self, parent_element):
        asset = self._doc.createElement('asset')
        parent_element.appendChild(asset)
        contributor = self._doc.createElement('contributor')
        asset.appendChild(contributor)
        author = self._doc.createElement('author')
        contributor.appendChild(author)
        author_name = self._doc.createTextNode('Blender User')
        author.appendChild(author_name)
        author_tool = self._doc.createElement('authoring_tool')
        author_name_text = self._doc.createTextNode(
            'BCry v{}'.format(self._config.bcry_version))
        author_tool.appendChild(author_name_text)
        contributor.appendChild(author_tool)
        created = self._doc.createElement('created')
        created_value = self._doc.createTextNode(
            datetime.now().isoformat(' '))
        created.appendChild(created_value)
        asset.appendChild(created)
        modified = self._doc.createElement('modified')
        asset.appendChild(modified)
        unit = self._doc.createElement('unit')
        unit.setAttribute('name', 'meter')
        unit.setAttribute('meter', '1')
        asset.appendChild(unit)
        up_axis = self._doc.createElement('up_axis')
        z_up = self._doc.createTextNode('Z_UP')
        up_axis.appendChild(z_up)
        asset.appendChild(up_axis)

#------------------------------------------------------------------
# Library Cameras:
#------------------------------------------------------------------

    def _export_library_cameras(self, root_element):
        library_cameras = self._doc.createElement('library_cameras')
        root_element.appendChild(library_cameras)

#------------------------------------------------------------------
# Library Lights:
#------------------------------------------------------------------

    def _export_library_lights(self, root_element):
        library_lights = self._doc.createElement('library_lights')
        root_element.appendChild(library_lights)

#------------------------------------------------------------------
# Library Images:
#------------------------------------------------------------------

    def _export_library_images(self, parent_element):
        library_images = self._doc.createElement('library_images')
        self._m_exporter.export_library_images(library_images)
        parent_element.appendChild(library_images)

#--------------------------------------------------------------
# Library Effects:
#--------------------------------------------------------------

    def _export_library_effects(self, parent_element):
        library_effects = self._doc.createElement('library_effects')
        self._m_exporter.export_library_effects(library_effects)
        parent_element.appendChild(library_effects)

#------------------------------------------------------------------
# Library Materials:
#------------------------------------------------------------------

    def _export_library_materials(self, parent_element):
        library_materials = self._doc.createElement('library_materials')
        self._m_exporter.export_library_materials(library_materials)
        parent_element.appendChild(library_materials)

#------------------------------------------------------------------
# Library Geometries:
#------------------------------------------------------------------

    def _export_library_geometries(self, parent_element):
        libgeo = self._doc.createElement("library_geometries")
        parent_element.appendChild(libgeo)
        for group in utils.get_mesh_export_nodes(self._config.export_selected_nodes):
            for object_ in group.objects:
                bmesh_, layer_state, scene_layer = utils.get_bmesh(object_)
                geometry_node = self._doc.createElement("geometry")
                geometry_name = utils.get_geometry_name(group, object_)
                geometry_node.setAttribute("id", geometry_name)
                mesh_node = self._doc.createElement("mesh")

                print()
                bcPrint('"{}" object is being processed...'.format(object_.name))

                start_time = clock()
                self._write_positions(bmesh_, mesh_node, geometry_name)
                bcPrint('Positions have been writed {:.4f} seconds.'.format(clock() - start_time))

                start_time = clock()
                self._write_normals(object_, bmesh_, mesh_node, geometry_name)
                bcPrint('Normals have been writed {:.4f} seconds.'.format(clock() - start_time))

                start_time = clock()
                self._write_uvs(object_, bmesh_, mesh_node, geometry_name)
                bcPrint('UVs have been writed {:.4f} seconds.'.format(clock() - start_time))

                start_time = clock()
                self._write_vertex_colors(object_, bmesh_, mesh_node, geometry_name)
                bcPrint(
                    'Vertex colors have been writed {:.4f} seconds.'.format(
                        clock() - start_time))

                start_time = clock()
                self._write_vertices(mesh_node, geometry_name)
                bcPrint('Vertices have been writed {:.4f} seconds.'.format(clock() - start_time))

                start_time = clock()
                self._write_triangle_list(object_, bmesh_, mesh_node, geometry_name)
                bcPrint('Triangle list have been writed {:.4f} seconds.'.format(clock() - start_time))

                extra = self._create_double_sided_extra("MAYA")
                mesh_node.appendChild(extra)
                geometry_node.appendChild(mesh_node)
                libgeo.appendChild(geometry_node)

                utils.clear_bmesh(object_, layer_state, scene_layer)
                bcPrint(
                    '"{}" object has been processed for "{}" node.'.format(
                        object_.name, group.name))

    def _write_positions(self, bmesh_, mesh_node, geometry_name):
        float_positions = []
        for vertex in bmesh_.verts:
            float_positions.extend(vertex.co)

        id_ = "{!s}-pos".format(geometry_name)
        source = utils.write_source(id_, "float", float_positions, "XYZ")
        mesh_node.appendChild(source)

    def _write_normals(self, object_, bmesh_, mesh_node, geometry_name):
        split_angle = 0
        use_edge_angle = False
        use_edge_sharp = False

        if object_.data.use_auto_smooth:
            use_edge_angle = True
            use_edge_sharp = True
            split_angle = object_.data.auto_smooth_angle
        else:
            for modifier in object_.modifiers:
                if modifier.type == 'EDGE_SPLIT' and modifier.show_viewport:
                    use_edge_angle = modifier.use_edge_angle
                    use_edge_sharp = modifier.use_edge_sharp
                    split_angle = modifier.split_angle

        float_normals = None
        if self._config.custom_normals:
            float_normals = utils.get_custom_normals(bmesh_, use_edge_angle,
                                               split_angle)
        else:
            float_normals = utils.get_normal_array(bmesh_, use_edge_angle,
                                               use_edge_sharp, split_angle)

        id_ = "{!s}-normal".format(geometry_name)
        source = utils.write_source(id_, "float", float_normals, "XYZ")
        mesh_node.appendChild(source)

    def _write_uvs(self, object_, bmesh_, mesh_node, geometry_name):
        uv_layer = bmesh_.loops.layers.uv.active
        if object_.data.uv_layers.active is None:
            bcPrint("{} object has no a UV map, creating a default UV...".format(object_.name))
            uv_layer = bmesh_.loops.layers.uv.new()

        float_uvs = []
        
        for face in bmesh_.faces:
            for loop in face.loops:
                float_uvs.extend(loop[uv_layer].uv)

        id_ = "{!s}-uvs".format(geometry_name)
        source = utils.write_source(id_, "float", float_uvs, "ST")
        mesh_node.appendChild(source)

    def _write_vertex_colors(self, object_, bmesh_, mesh_node, geometry_name):
        float_colors = []
        alpha_found = False

        color_layer = bmesh_.loops.layers.color.active
        if object_.data.vertex_colors:
            for vert in bmesh_.verts:
                loop = vert.link_loops[0]
                float_colors.extend(loop[color_layer])

        if float_colors:
            id_ = "{!s}-vcol".format(geometry_name)
            params = ("RGBA" if alpha_found else "RGB")
            source = utils.write_source(id_, "float", float_colors, params)
            mesh_node.appendChild(source)

    def _write_vertices(self, mesh_node, geometry_name):
        vertices = self._doc.createElement("vertices")
        vertices.setAttribute("id", "{}-vtx".format(geometry_name))
        input = utils.write_input(geometry_name, None, "pos", "POSITION")
        vertices.appendChild(input)
        mesh_node.appendChild(vertices)

    def _write_triangle_list(self, object_, bmesh_, mesh_node, geometry_name):
        tessfaces = utils.get_tessfaces(bmesh_)
        current_material_index = 0
        for material, materialname in self._m_exporter.get_materials_for_object(
                object_).items():
            triangles = ''
            triangle_count = 0
            normal_uv_index = 0
            for face in bmesh_.faces:
                norm_uv_indices = {}

                for index in range(0, len(face.verts)):
                    norm_uv_indices[str(face.verts[index].index)] = normal_uv_index + index

                if face.material_index == current_material_index:
                    for tessface in tessfaces[face.index]:
                        triangle_count += 1
                        for vert in tessface:
                            normal_uv = norm_uv_indices[str(vert)]
                            dae_vertex = self._write_vertex_data(
                                vert, normal_uv, normal_uv, object_.data.vertex_colors)
                            triangles = join(triangles, dae_vertex)

                normal_uv_index += len(face.verts)

            current_material_index += 1

            if triangle_count == 0:
                continue

            triangle_list = self._doc.createElement('triangles')
            triangle_list.setAttribute('material', materialname)
            triangle_list.setAttribute('count', str(triangle_count))

            inputs = []
            inputs.append(
                utils.write_input(
                    geometry_name,
                    0,
                    'vtx',
                    'VERTEX'))
            inputs.append(
                utils.write_input(
                    geometry_name,
                    1,
                    'normal',
                    'NORMAL'))
            inputs.append(
                utils.write_input(
                    geometry_name,
                    2,
                    'uvs',
                    'TEXCOORD'))
            if object_.data.vertex_colors:
                inputs.append(
                    utils.write_input(
                        geometry_name,
                        3,
                        'vcol',
                        'COLOR'))

            for input in inputs:
                triangle_list.appendChild(input)

            p = self._doc.createElement('p')
            p_text = self._doc.createTextNode(triangles)
            p.appendChild(p_text)

            triangle_list.appendChild(p)
            mesh_node.appendChild(triangle_list)

    def _write_vertex_data(self, vert, normal, uv, vertex_colors):
        if vertex_colors:
            return "{:d} {:d} {:d} {:d} ".format(
                vert, normal, uv, vert)
        else:
            return "{:d} {:d} {:d} ".format(vert, normal, uv)

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

# -------------------------------------------------------------------------
# Library Controllers: --> Skeleton Armature and List of Bone Names
#                      --> Skin Geometry, Weights, Transform Matrices
# -------------------------------------------------------------------------

    def _export_library_controllers(self, parent_element):
        library_node = self._doc.createElement("library_controllers")

        for group in utils.get_mesh_export_nodes(
                    self._config.export_selected_nodes):
            for object_ in group.objects:
                if not utils.is_bone_geometry(object_):
                    armature = utils.get_armature_for_object(object_)
                    if armature is not None:
                        self._process_bones(library_node,
                                            group,
                                            object_,
                                            armature)

        parent_element.appendChild(library_node)

    def _process_bones(self, parent_node, group, object_, armature):
        id_ = "{!s}_{!s}".format(armature.name, object_.name)

        controller_node = self._doc.createElement("controller")
        parent_node.appendChild(controller_node)
        controller_node.setAttribute("id", id_)

        skin_node = self._doc.createElement("skin")
        skin_node.setAttribute("source", "#{!s}".format(utils.get_geometry_name(group, object_)))
        controller_node.appendChild(skin_node)

        bind_shape_matrix = self._doc.createElement("bind_shape_matrix")
        utils.write_matrix(Matrix(), bind_shape_matrix)
        skin_node.appendChild(bind_shape_matrix)

        self._process_bone_joints(object_, armature, skin_node)
        self._process_bone_matrices(object_, armature, skin_node)
        self._process_bone_weights(object_, armature, skin_node)

        joints = self._doc.createElement("joints")
        input = utils.write_input(id_, None, "joints", "JOINT")
        joints.appendChild(input)
        input = utils.write_input(id_, None, "matrices", "INV_BIND_MATRIX")
        joints.appendChild(input)
        skin_node.appendChild(joints)

    def _process_bone_joints(self, object_, armature, skin_node):

        bones = utils.get_bones(armature)
        id_ = "{!s}_{!s}-joints".format(armature.name, object_.name)
        group = utils.get_armature_node(object_)
        bone_names = []
        for bone in bones:
            props_name = self._create_properties_name(bone, group)
            bone_name = "{!s}{!s}".format(bone.name, props_name)
            bone_names.append(bone_name)
        source = utils.write_source(id_, "IDREF", bone_names, [])
        skin_node.appendChild(source)

    def _process_bone_matrices(self, object_, armature, skin_node):

        bones = utils.get_bones(armature)
        bone_matrices = []
        for bone in armature.pose.bones:

            bone_matrix = utils.transform_bone_matrix(bone)
            bone_matrices.extend(utils.matrix_to_array(bone_matrix))

        id_ = "{!s}_{!s}-matrices".format(armature.name, object_.name)
        source = utils.write_source(id_, "float4x4", bone_matrices, [])
        skin_node.appendChild(source)

    def _process_bone_weights(self, object_, armature, skin_node):

        bones = utils.get_bones(armature)
        group_weights = []
        vw = ""
        vertex_groups_lengths = ""
        vertex_count = 0
        bone_list = {}

        for bone_id, bone in enumerate(bones):
            bone_list[bone.name] = bone_id

        for vertex in object_.data.vertices:
            vertex_group_count = 0
            for group in vertex.groups:
                group_name = object_.vertex_groups[group.group].name
                if (group.weight == 0 or
                        group_name not in bone_list):
                    continue
                if vertex_group_count == 8:
                    bcPrint("Too many bone references in {}:{} vertex group"
                            .format(object_.name, group_name))
                    continue
                group_weights.append(group.weight)
                vw = "{}{} {} ".format(vw, bone_list[group_name], vertex_count)
                vertex_count += 1
                vertex_group_count += 1

            vertex_groups_lengths = "{}{} ".format(vertex_groups_lengths,
                                                   vertex_group_count)

        id_ = "{!s}_{!s}-weights".format(armature.name, object_.name)
        source = utils.write_source(id_, "float", group_weights, [])
        skin_node.appendChild(source)

        vertex_weights = self._doc.createElement("vertex_weights")
        vertex_weights.setAttribute("count", str(len(object_.data.vertices)))

        id_ = "{!s}_{!s}".format(armature.name, object_.name)
        input = utils.write_input(id_, 0, "joints", "JOINT")
        vertex_weights.appendChild(input)
        input = utils.write_input(id_, 1, "weights", "WEIGHT")
        vertex_weights.appendChild(input)

        vcount = self._doc.createElement("vcount")
        vcount_text = self._doc.createTextNode(vertex_groups_lengths)
        vcount.appendChild(vcount_text)
        vertex_weights.appendChild(vcount)

        v = self._doc.createElement("v")
        v_text = self._doc.createTextNode(vw)
        v.appendChild(v_text)
        vertex_weights.appendChild(v)

        skin_node.appendChild(vertex_weights)

# -----------------------------------------------------------------------------
# Library Animation and Clips: --> Animations, F-Curves
# -----------------------------------------------------------------------------

    def _export_library_animation_clips_and_animations(self, parent_element):
        libanmcl = self._doc.createElement("library_animation_clips")
        libanm = self._doc.createElement("library_animations")
        parent_element.appendChild(libanmcl)
        parent_element.appendChild(libanm)


# ---------------------------------------------------------------------
# Library Visual Scene: --> Skeleton and _Phys bones, Bone
#       Transformations, and Instance URL (_boneGeometry) and extras.
# ---------------------------------------------------------------------

    def _export_library_visual_scenes(self, parent_element):
        current_element = self._doc.createElement("library_visual_scenes")
        visual_scene = self._doc.createElement("visual_scene")
        visual_scene.setAttribute("id", "scene")
        visual_scene.setAttribute("name", "scene")
        current_element.appendChild(visual_scene)
        parent_element.appendChild(current_element)

        if utils.get_mesh_export_nodes(self._config.export_selected_nodes):
            if utils.are_duplicate_nodes():
                message = "Duplicate Node Names"
                bpy.ops.screen.display_error('INVOKE_DEFAULT', message=message)

            for group in utils.get_mesh_export_nodes(
                    self._config.export_selected_nodes):
                self._write_export_node(group, visual_scene)
        else:
            pass  # TODO: Handle No Export Nodes Error

    def _write_export_node(self, group, visual_scene):
        if not self._config.export_for_lumberyard:
            node_name = "CryExportNode_{}".format(utils.get_node_name(group))
            node = self._doc.createElement("node")
            node.setAttribute("id", node_name)
            node.setIdAttribute("id")
        else:
            node_name = "{}".format(utils.get_node_name(group))
            node = self._doc.createElement("node")
            node.setAttribute("id", node_name)
            node.setAttribute("LumberyardExportNode", "1")
            node.setIdAttribute("id")

        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        self._write_transforms(bpy.context.active_object, node)
        bpy.ops.object.delete(use_global=False)

        root_objects = []
        for object_ in group.objects:
            if utils.is_visual_scene_node_writed(object_, group):
                root_objects.append(object_)

        node = self._write_visual_scene_node(root_objects, node, group)

        extra = self._create_cryengine_extra(group)
        node.appendChild(extra)
        visual_scene.appendChild(node)

    def _write_visual_scene_node(self, objects, parent_node, group):
        for object_ in objects:
            if object_.type == "MESH" and not utils.is_fakebone(object_):
                prop_name = join(object_.name,
                                 self._create_properties_name(object_, group))
                node = self._doc.createElement("node")
                node.setAttribute("id", prop_name)
                node.setAttribute("name", prop_name)
                node.setIdAttribute("id")

                self._write_transforms(object_, node)

                ALLOWED_NODE_TYPES = ('cgf', 'cga', 'chr', 'skin')
                if utils.get_node_type(group) in ALLOWED_NODE_TYPES:
                    instance = self._create_instance(group, object_)
                    if instance is not None:
                        node.appendChild(instance)

                udp_extra = self._create_user_defined_property(object_)
                if udp_extra is not None:
                    node.appendChild(udp_extra)

                parent_node.appendChild(node)

                if object_.parent is not None and object_.parent.type == "ARMATURE":
                    self._write_bone_list([utils.get_root_bone(
                        object_.parent)], object_, parent_node, group)

            elif object_.type == "ARMATURE" and utils.is_physic_bone(object_):
                self._write_bone_list([utils.get_root_bone(
                    object_)], object_, parent_node, group)

        return parent_node

    def _write_bone_list(self, bones, object_, parent_node, group):
        scene = bpy.context.scene
        bone_names = []

        for bone in bones:
            props_name = self._create_properties_name(bone, group)
            props_ik = self._create_ik_properties(bone, object_)
            bone_name = join(bone.name, props_name, props_ik)
            bone_names.append(bone_name)

            node = self._doc.createElement("node")
            node.setAttribute("id", bone_name)
            node.setAttribute("name", bone_name)
            node.setIdAttribute("id")

            fakebone = utils.get_fakebone(bone.name)
            if fakebone is not None:
                self._write_transforms(fakebone, node)

                bone_geometry = utils.get_bone_geometry(bone)
                if bone_geometry is not None:
                    instance = self._create_bone_instance(
                        bone, bone_geometry)
                    node.appendChild(instance)

                    extra = self._create_physic_proxy_for_bone(
                        object_.parent, bone)
                    if extra is not None:
                        node.appendChild(extra)

            elif utils.is_physic_bone(bone):
                bone_geometry = utils.get_bone_geometry(bone)
                if bone_geometry is not None:
                    self._write_transforms(bone_geometry, node)

            parent_node.appendChild(node)

            if bone.children:
                self._write_bone_list(bone.children, object_, node, group)

    def _create_bone_instance(self, bone, bone_geometry):
        instance = None

        instance = self._doc.createElement("instance_geometry")
        instance.setAttribute("url", "#{}_boneGeometry".format(bone.name))
        bm = self._doc.createElement("bind_material")
        tc = self._doc.createElement("technique_common")

        for mat in bone_geometry.material_slots:
            im = self._doc.createElement("instance_material")
            im.setAttribute("symbol", mat.name)
            im.setAttribute("target", "#{}".format(mat.name))
            bvi = self._doc.createElement("bind_vertex_input")
            bvi.setAttribute("semantic", "UVMap")
            bvi.setAttribute("input_semantic", "TEXCOORD")
            bvi.setAttribute("input_set", "0")
            im.appendChild(bvi)
            tc.appendChild(im)

        bm.appendChild(tc)
        instance.appendChild(bm)

        return instance

    def _create_physic_proxy_for_bone(self, object_, bone):
        extra = None
        try:
            bonePhys = object_.pose.bones[bone.name]['phys_proxy']
            bcPrint(bone.name + " physic proxy is " + bonePhys)

            extra = self._doc.createElement("extra")
            techcry = self._doc.createElement("technique")
            techcry.setAttribute("profile", "CryEngine")
            prop2 = self._doc.createElement("properties")

            cryprops = self._doc.createTextNode(bonePhys)
            prop2.appendChild(cryprops)
            techcry.appendChild(prop2)
            extra.appendChild(techcry)
        except:
            pass

        return extra

    def _write_transforms(self, object_, node):
        trans = self._create_translation_node(object_)
        rotx, roty, rotz = self._create_rotation_node(object_)
        scale = self._create_scale_node(object_)

        node.appendChild(trans)
        node.appendChild(rotx)
        node.appendChild(roty)
        node.appendChild(rotz)
        node.appendChild(scale)

    def _create_translation_node(self, object_):
        trans = self._doc.createElement("translate")
        trans.setAttribute("sid", "translation")
        trans_text = self._doc.createTextNode("{:f} {:f} {:f}".format(
            * object_.location))
        trans.appendChild(trans_text)

        return trans

    def _create_rotation_node(self, object_):
        rotz = self._write_rotation(
            "z", "0 0 1 {:f}", object_.rotation_euler[2])
        roty = self._write_rotation(
            "y", "0 1 0 {:f}", object_.rotation_euler[1])
        rotx = self._write_rotation(
            "x", "1 0 0 {:f}", object_.rotation_euler[0])

        return rotz, roty, rotx

    def _write_rotation(self, axis, textFormat, rotation):
        rot = self._doc.createElement("rotate")
        rot.setAttribute("sid", "rotation_{}".format(axis))
        rot_text = self._doc.createTextNode(textFormat.format(
            rotation * utils.to_degrees))
        rot.appendChild(rot_text)

        return rot

    def _create_scale_node(self, object_):
        scale = self._doc.createElement("scale")
        scale.setAttribute("sid", "scale")
        scale_text = self._doc.createTextNode(
            utils.floats_to_string(object_.scale, " ", "%s"))
        scale.appendChild(scale_text)

        return scale

    def _create_instance(self, group, object_):
        armature = utils.get_armature_for_object(object_)
        instance = None
        if armature is not None:
            instance = self._doc.createElement("instance_controller")
            # This binds the mesh object to the armature in control of it
            instance.setAttribute("url", "#{!s}_{!s}".format(
                armature.name,
                object_.name))
        elif object_.name[:6] != "_joint" and object_.type == "MESH":
            instance = self._doc.createElement("instance_geometry")
            instance.setAttribute("url", "#{!s}".format(utils.get_geometry_name(group, object_)))

        if instance is not None:
            bind_material = self._create_bind_material(object_)
            instance.appendChild(bind_material)
            return instance

    def _create_bind_material(self, object_):
        bind_material = self._doc.createElement('bind_material')
        technique_common = self._doc.createElement('technique_common')

        for material, materialname in self._m_exporter.get_materials_for_object(
                object_).items():
            instance_material = self._doc.createElement(
                'instance_material')
            instance_material.setAttribute('symbol', materialname)
            instance_material.setAttribute('target', '#{!s}'.format(
                materialname))

            technique_common.appendChild(instance_material)

        bind_material.appendChild(technique_common)

        return bind_material

    def _create_cryengine_extra(self, node):
        extra = self._doc.createElement("extra")
        technique = self._doc.createElement("technique")
        technique.setAttribute("profile", "CryEngine")
        properties = self._doc.createElement("properties")

        ALLOWED_NODE_TYPES = ("cgf", "cga", "chr", "skin")

        if utils.is_export_node(node):
            node_type = utils.get_node_type(node)
            if node_type in ALLOWED_NODE_TYPES:
                prop = self._doc.createTextNode(
                    "fileType={}".format(node_type))
                properties.appendChild(prop)
            if not self._config.merge_all_nodes:
                prop = self._doc.createTextNode("DoNotMerge")
                properties.appendChild(prop)

            prop = self._doc.createTextNode("UseCustomNormals")
            properties.appendChild(prop)

            if self._config.vcloth_pre_process and node_type == 'skin':
                prop = self._doc.createTextNode("VClothPreProcess")
                properties.appendChild(prop)

            prop = self._doc.createTextNode("CustomExportPath=")
            properties.appendChild(prop)
        else:
            if not node.rna_type.id_data.items():
                return

        technique.appendChild(properties)

        if (node.name[:6] == "_joint"):
            helper = self._create_helper_joint(node)
            technique.appendChild(helper)

        extra.appendChild(technique)
        extra.appendChild(self._create_xsi_profile(node))

        return extra

    def _create_xsi_profile(self, node):
        technique_xsi = self._doc.createElement("technique")
        technique_xsi.setAttribute("profile", "XSI")

        xsi_custom_p_set = self._doc.createElement("XSI_CustomPSet")
        xsi_custom_p_set.setAttribute("name", "ExportProperties")

        propagation = self._doc.createElement("propagation")
        propagation.appendChild(self._doc.createTextNode("NODE"))
        xsi_custom_p_set.appendChild(propagation)

        type_node = self._doc.createElement("type")
        type_node.appendChild(self._doc.createTextNode("CryExportNodeProperties"))
        xsi_custom_p_set.appendChild(type_node)

        xsi_parameter = self._doc.createElement("XSI_Parameter")
        xsi_parameter.setAttribute("id", "FileType")
        xsi_parameter.setAttribute("type", "Integer")
        xsi_parameter.setAttribute("value", utils.get_xsi_filetype_value(node))
        xsi_custom_p_set.appendChild(xsi_parameter)

        xsi_parameter = self._doc.createElement("XSI_Parameter")
        xsi_parameter.setAttribute("id", "Filename")
        xsi_parameter.setAttribute("type", "Text")
        xsi_parameter.setAttribute("value", utils.get_node_name(node))
        xsi_custom_p_set.appendChild(xsi_parameter)

        xsi_parameter = self._doc.createElement("XSI_Parameter")
        xsi_parameter.setAttribute("id", "Exportable")
        xsi_parameter.setAttribute("type", "Boolean")
        xsi_parameter.setAttribute("value", "1")
        xsi_custom_p_set.appendChild(xsi_parameter)

        xsi_parameter = self._doc.createElement("XSI_Parameter")
        xsi_parameter.setAttribute("id", "MergeObjects")
        xsi_parameter.setAttribute("type", "Boolean")
        xsi_parameter.setAttribute("value", str(int(self._config.merge_all_nodes)))
        xsi_custom_p_set.appendChild(xsi_parameter)

        technique_xsi.appendChild(xsi_custom_p_set)

        return technique_xsi

    def _create_user_defined_property(self, object_):        
        udp_buffer = None
        for prop in object_.rna_type.id_data.items():
            if prop:
                prop_name = prop[0]
                if udp.is_user_defined_property(prop_name):
                    udp_buffer = "\n"

                    if isinstance(prop[1], str):
                        udp_buffer += "{!s}\n".format(prop[1])
                    else:
                        udp_buffer += "{!s}={!s}\n".format(prop[0], prop[1])

        if udp_buffer:
            extra = self._doc.createElement("extra")
            technique = self._doc.createElemen("technique")
            technique.setAttribute("profile", "CryEngine")
            properties = self._doc.createElement("properties")
            properties._doc.createTextNode(udp_buffer)
            technique.appendChild(properties)
            extra.appendChild(technique)
            
            return extra
        else:
            return None

    def _create_helper_joint(self, object_):
        x1, y1, z1, x2, y2, z2 = utils.get_bounding_box(object_)

        min = self._doc.createElement("bound_box_min")
        min_text = self._doc.createTextNode(
            "{:f} {:f} {:f}".format(x1, y1, z1))
        min.appendChild(min_text)

        max = self._doc.createElement("bound_box_max")
        max_text = self._doc.createTextNode(
            "{:f} {:f} {:f}".format(x2, y2, z2))
        max.appendChild(max_text)

        joint = self._doc.createElement("helper")
        joint.setAttribute("type", "dummy")
        joint.appendChild(min)
        joint.appendChild(max)

        return joint

    def _create_properties_name(self, bone, group):
        bone_name = bone.name.replace("__", "*")
        node_name = utils.get_node_name(group)
        props_name = '%{!s}%--PRprops_name={!s}'.format(node_name, bone_name)

        return props_name

    def _create_ik_properties(self, bone, object_):
        props = ""
        if utils.is_physic_bone(bone):

            armature_object = bpy.data.objects[object_.name[:-5]]
            pose_bone = armature_object.pose.bones[bone.name[:-5]]

            xIK, yIK, zIK = udp.get_bone_ik_max_min(pose_bone)

            damping, spring, spring_tension = udp.get_bone_ik_properties(
                pose_bone)

            props = join(
                xIK,
                '_xdamping={}'.format(damping[0]),
                '_xspringangle={}'.format(spring[0]),
                '_xspringtension={}'.format(spring_tension[0]),

                yIK,
                '_ydamping={}'.format(damping[1]),
                '_yspringangle={}'.format(spring[1]),
                '_yspringtension={}'.format(spring_tension[1]),

                zIK,
                '_zdamping={}'.format(damping[2]),
                '_zspringangle={}'.format(spring[2]),
                '_zspringtension={}'.format(spring_tension[2])
            )

        return props

    def _export_scene(self, parent_element):
        scene = self._doc.createElement("scene")
        instance_visual_scene = self._doc.createElement(
            "instance_visual_scene")
        instance_visual_scene.setAttribute("url", "#scene")
        scene.appendChild(instance_visual_scene)
        parent_element.appendChild(scene)


def write_scripts(config):
    filepath = bpy.path.ensure_ext(config.filepath, ".dae")
    if not config.make_chrparams and not config.make_cdf:
        return

    dae_path = utils.get_absolute_path_for_rc(filepath)
    output_path = os.path.dirname(dae_path)

    for chr_name in utils.get_chr_names(self._config.export_selected_nodes):
        if config.make_chrparams:
            filepath = "{}/{}.chrparams".format(output_path, chr_name)
            contents = utils.generate_file_contents("chrparams")
            utils.generate_xml(filepath, contents)
        if config.make_cdf:
            filepath = "{}/{}.cdf".format(output_path, chr_name)
            contents = utils.generate_file_contents("cdf")
            utils.generate_xml(filepath, contents)


def save(config):
    # prevent wasting time for exporting if RC was not found
    if not config.disable_rc and not os.path.isfile(config.rc_path):
        raise exceptions.NoRcSelectedException

    exporter = CrytekDaeExporter(config)
    exporter.export()


def register():
    bpy.utils.register_class(CrytekDaeExporter)

    bpy.utils.register_class(TriangulateMeError)
    bpy.utils.register_class(Error)


def unregister():
    bpy.utils.unregister_class(CrytekDaeExporter)
    bpy.utils.unregister_class(TriangulateMeError)
    bpy.utils.unregister_class(Error)


if __name__ == "__main__":
    register()

    # test call
    bpy.ops.export_mesh.crytekdae('INVOKE_DEFAULT')
