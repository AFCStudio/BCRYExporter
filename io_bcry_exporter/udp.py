#------------------------------------------------------------------------------
# Name:        udp.py
# Purpose:     Holds UDP and IK property functions.
#
# Author:      Özkan Afacan
#
# Created:     17/09/2016
# Copyright:   (c) Özkan Afacan 2016
# License:     GPLv2+
#------------------------------------------------------------------------------

# <pep8-80 compliant>


from bpy.props import *
from bpy_extras.io_utils import ExportHelper
import bpy
import bpy.ops
import bpy_extras
import re
import math


#------------------------------------------------------------------------------
# User Defined Properties:
#------------------------------------------------------------------------------

def get_udp(object_, udp_name, udp_value, is_checked=None):
    '''Get User Defined Property -- Overloaded function that have two variation'''

    if is_checked is None:
        try:
            temp_value = object_[udp_name]
            udp_value = True
        except:
            udp_value = False

        return udp_value

    else:
        try:
            udp_value = object_[udp_name]
            is_checked = True
        except:
            is_checked = False

        return udp_value, is_checked


def edit_udp(object_, udp_name, udp_value, is_checked=True):
    '''Edit User Defined Property'''

    if is_checked:
        object_[udp_name] = udp_value
    else:
        try:
            del object_[udp_name]
        except:
            pass


def is_user_defined_property(property_name):
    prop_list = [
        "phys_proxy",
        "colltype_player",
        "no_explosion_occlusion",
        "entity",
        "mass",
        "density",
        "pieces",
        "dynamic",
        "no_hit_refinement",
        "limit",
        "bend",
        "twist",
        "pull",
        "push",
        "shift",
        "player_can_break",
        "gameplay_critical",
        "constraint_limit",
        "constraint_minang",
        "consrtaint_maxang",
        "constraint_damping",
        "constraint_collides",
        "stiffness",
        "hardness",
        "max_stretch",
        "max_impulse",
        "skin_dist",
        "thickness",
        "explosion_scale",
        "notaprim",
        "hull",
        "wheel"]

    return property_name in prop_list


#------------------------------------------------------------------------------
# Bone Inverse Kinematics:
#------------------------------------------------------------------------------

def get_bone_ik_max_min(pose_bone):
    xIK = yIK = zIK = ""

    if pose_bone.lock_ik_x:
        xIK = '_xmax={!s}'.format(0.0) + '_xmin={!s}'.format(0.0)
    else:
        xIK = '_xmax={!s}'.format(math.degrees(-pose_bone.ik_min_y)) \
            + '_xmin={!s}'.format(math.degrees(-pose_bone.ik_max_y))

    if pose_bone.lock_ik_y:
        yIK = '_ymax={!s}'.format(0.0) + '_ymin={!s}'.format(0.0)
    else:
        yIK = '_ymax={!s}'.format(math.degrees(-pose_bone.ik_min_x)) \
            + '_ymin={!s}'.format(math.degrees(-pose_bone.ik_max_x))

    if pose_bone.lock_ik_z:
        zIK = '_zmax={!s}'.format(0.0) + '_zmin={!s}'.format(0.0)
    else:
        zIK = '_zmax={!s}'.format(math.degrees(pose_bone.ik_max_z)) \
            + '_zmin={!s}'.format(math.degrees(pose_bone.ik_min_z))

    return xIK, yIK, zIK


def get_bone_ik_properties(pose_bone):
    damping = [1.0, 1.0, 1.0]
    spring = [0.0, 0.0, 0.0]
    spring_tension = [1.0, 1.0, 1.0]

    try:
        damping = pose_bone['Damping']
    except:
        pass

    try:
        spring = pose_bone['Spring']
    except:
        pass

    try:
        spring_tension = pose_bone['Spring Tension']
    except:
        pass

    return damping, spring, spring_tension
