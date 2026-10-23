"""Assembly steps shared by the supporting cast (player, students, teacher)."""

import bpy

from . import body, face, mesh_utils, rig
from .materials import hex_to_srgb


def build_figure(params: body.CharacterParams) -> tuple:
    """`<prefix>Char` with its heat-weighted `<prefix>Body` and `<prefix>Socks`. Secondary chains come after this, so
    they never claim body skin."""
    armature = rig.build_armature(f"{params.prefix}Char", params.height, body.body_proportions(params))
    body_object = body.build_body(armature, params)
    body.build_socks(body_object, params)
    return armature, body_object


def build_face(armature, params: body.CharacterParams, eye_texture_path: str, shape_keys: list[str]) -> bpy.types.Object:
    """`<prefix>Face`, `<prefix>Eyes` and `<prefix>Lashes` carrying `shape_keys`, with a freshly painted eye texture."""
    head = face.build_head(armature, params)
    face.paint_eye_texture(eye_texture_path, hex_to_srgb(params.eye_color), highlight=False, pupil=False)
    return face.build_face_features(head, params, eye_texture_path, shape_keys)


def finish(armature) -> None:
    for child in armature.children:
        if child.type == "MESH" and child.vertex_groups:
            mesh_utils.limit_influences(child)
