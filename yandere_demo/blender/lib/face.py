"""Anime head, painted eye texture and the expressive face-feature mesh with shape keys."""

import math
import os

import bpy
import numpy
from mathutils import Vector

from . import mesh_utils
from .materials import hex_to_srgb, principled
from .rig import bone_world_points

EXPRESSIONS = ["neutral", "startled", "suspicious", "happy", "blink"]

# Head cross-sections relative to the cranium centre: (z, half width, front depth, back depth).
HEAD_RINGS = [
    (0.100, 0.022, 0.020, 0.026),
    (0.092, 0.042, 0.040, 0.050),
    (0.078, 0.060, 0.060, 0.070),
    (0.058, 0.073, 0.075, 0.084),
    (0.032, 0.080, 0.083, 0.092),
    (0.004, 0.082, 0.087, 0.095),
    (-0.022, 0.081, 0.088, 0.091),
    (-0.046, 0.077, 0.086, 0.082),
    (-0.066, 0.068, 0.082, 0.066),
    (-0.083, 0.055, 0.076, 0.048),
    (-0.098, 0.040, 0.069, 0.032),
    (-0.110, 0.025, 0.062, 0.019),
    (-0.118, 0.012, 0.056, 0.010),
]
HEAD_TOP = 0.104
CHIN = (-0.121, -0.052)
RING_POINTS = 32
# Uniform enlargement of the whole head (skull, face features, hair) for anime head-to-body proportions.
HEAD_SCALE = 1.07
FRONT_EXPONENT = 2.6
BACK_EXPONENT = 2.1


class FaceLayout:
    """Face feature placement in head-centre coordinates (x right of viewer, z up)."""

    eye_center_x = 0.036
    eye_center_z = -0.034
    eye_width = 0.043
    eye_height = 0.047
    nose_z = -0.066
    mouth_z = -0.091
    brow_z = -0.002


def head_center(armature) -> Vector:
    head_start, head_end = bone_world_points(armature, "head")
    return Vector((0.0, 0.004, head_start.z + 0.095))


def build_head(armature, params) -> bpy.types.Object:
    center = head_center(armature)
    rings = []
    for z, half_width, front, back in HEAD_RINGS:
        rings.append([center + offset for offset in _ring(z, half_width, front, back)])
    vertices, faces = mesh_utils.loft(rings)
    top_index = len(vertices)
    vertices.append(center + Vector((0, 0.003, HEAD_TOP)))
    chin_index = len(vertices)
    vertices.append(center + Vector((0, CHIN[1], CHIN[0])))
    vertices = [center + (vertex - center) * HEAD_SCALE for vertex in vertices]
    for column in range(RING_POINTS):
        following = (column + 1) % RING_POINTS
        faces.append((top_index, following, column))
        last = (len(rings) - 1) * RING_POINTS
        faces.append((chin_index, last + column, last + following))
    head = mesh_utils.mesh_from_geometry(f"{params.prefix}Head", vertices, faces, [principled("M_Skin", params.skin_color, 0.55)])
    mesh_utils.recalculate_normals(head)
    mesh_utils.add_modifier(head, "SUBSURF", levels=2, render_levels=2)
    mesh_utils.apply_modifiers(head)
    _add_nose(head, center)
    mesh_utils.shade_smooth(head)
    head.data.normals_split_custom_set_from_vertices(
        [shading_normal(center, vertex.co, vertex.normal) for vertex in head.data.vertices])
    mesh_utils.assign_single_bone(head, armature, "head")
    return head


def shading_normal(center: Vector, point: Vector, surface_normal: Vector) -> Vector:
    """Face normals bent toward an ellipsoid around the skull, so toon bands fall in clean anime shapes
    instead of tracing the nose, cheeks and jaw."""
    pivot = center + Vector((0, 0.04, -0.02))
    spherical = (point - pivot).normalized()
    blended = surface_normal.lerp(spherical, 0.6).normalized()
    facing = max(0.0, -blended.y) ** 2 * 0.55
    return blended.lerp(Vector((0, -1, 0.12)).normalized(), facing).normalized()


def _ring(z: float, half_width: float, front: float, back: float) -> list:
    points = []
    for index in range(RING_POINTS):
        angle = 2 * math.pi * index / RING_POINTS - math.pi / 2
        cosine, sine = math.cos(angle), math.sin(angle)
        exponent = FRONT_EXPONENT if sine < 0 else BACK_EXPONENT
        depth = front if sine < 0 else back
        x = half_width * math.copysign(abs(cosine) ** (2 / exponent), cosine)
        y = depth * math.copysign(abs(sine) ** (2 / exponent), sine)
        points.append(Vector((x, y, z)))
    return points


def _add_nose(head, center: Vector) -> None:
    nose = center + Vector((0, -0.08, FaceLayout.nose_z)) * HEAD_SCALE
    for vertex in head.data.vertices:
        if vertex.co.y > center.y - 0.05:
            continue
        horizontal = (vertex.co.x - nose.x) / 0.0075
        vertical = (vertex.co.z - nose.z) / 0.011
        falloff = math.exp(-(horizontal * horizontal + vertical * vertical))
        lift = 0.0045 * falloff * (0.5 + 0.5 * max(0.0, min(1.0, -(vertex.co.z - nose.z) / 0.011 + 0.4)))
        vertex.co.y -= lift
    head.data.update()


def paint_eye_texture(path: str, iris_color: tuple, highlight: bool, size: int = 512) -> bpy.types.Image:
    """Paint the left-eye texture (inner corner at u=0) with numpy and save it as PNG."""
    coordinates = (numpy.arange(size) + 0.5) / size
    s_grid, t_grid = numpy.meshgrid(coordinates, coordinates)
    pixel = 1.0 / size
    top = eye_top(s_grid)
    bottom = eye_bottom(s_grid)
    inside_horizontal = _soft_step(0.012 - numpy.abs(s_grid - 0.5) + 0.488, pixel * 1.5)
    opening = _soft_step(top - t_grid, pixel * 1.5) * _soft_step(t_grid - bottom, pixel * 1.5) * inside_horizontal

    iris = numpy.array(iris_color, dtype=float)
    dark = _mix(iris, numpy.array((0.16, 0.07, 0.30)), 0.72)
    light = _mix(iris, numpy.array((0.97, 0.90, 1.0)), 0.55)
    sclera = numpy.array((1.0, 0.99, 1.0))
    sclera_shadow = numpy.array((0.83, 0.78, 0.92))
    lash_color = numpy.array((0.20, 0.11, 0.17))

    shadow_amount = numpy.clip((t_grid - (top - 0.16)) / 0.16, 0, 1)
    color = sclera[None, None, :] * (1 - shadow_amount[..., None]) + sclera_shadow[None, None, :] * shadow_amount[..., None]

    iris_center_s, iris_center_t, iris_radius_s, iris_radius_t = 0.53, 0.43, 0.31, 0.43
    iris_distance = numpy.sqrt(((s_grid - iris_center_s) / iris_radius_s) ** 2 + ((t_grid - iris_center_t) / iris_radius_t) ** 2)
    iris_mask = _soft_step(1.0 - iris_distance, pixel * 3.0)
    gradient = numpy.clip((t_grid - (iris_center_t - iris_radius_t)) / (2 * iris_radius_t), 0, 1) ** 0.9
    iris_fill = light[None, None, :] * (1 - gradient[..., None]) + dark[None, None, :] * gradient[..., None]
    rim = numpy.clip((iris_distance - 0.82) / 0.18, 0, 1)[..., None]
    iris_fill = iris_fill * (1 - rim * 0.65) + dark[None, None, :] * rim * 0.65
    lower_glow = _soft_step(0.30 - numpy.sqrt(((s_grid - iris_center_s) / 0.20) ** 2 + ((t_grid - 0.20) / 0.13) ** 2), 0.08)[..., None]
    iris_fill = iris_fill * (1 - lower_glow * 0.5) + numpy.array((1.0, 0.82, 0.98))[None, None, :] * lower_glow * 0.5
    color = color * (1 - iris_mask[..., None]) + iris_fill * iris_mask[..., None]

    pupil = _ellipse(s_grid, t_grid, iris_center_s, iris_center_t + 0.04, 0.10, 0.17, pixel * 3.0)
    color = color * (1 - pupil[..., None] * 0.85) + dark[None, None, :] * 0.6 * pupil[..., None] * 0.85

    lid_shadow = _soft_step(t_grid - (top - 0.13), 0.05) * iris_mask
    color = color * (1 - lid_shadow[..., None] * 0.35) + dark[None, None, :] * lid_shadow[..., None] * 0.35

    if highlight:
        for center_s, center_t, radius_s, radius_t in ((0.40, 0.63, 0.095, 0.11), (0.67, 0.25, 0.05, 0.045), (0.60, 0.70, 0.03, 0.03)):
            spot = _ellipse(s_grid, t_grid, center_s, center_t, radius_s, radius_t, pixel * 2.0)
            color = color * (1 - spot[..., None]) + numpy.ones(3)[None, None, :] * spot[..., None]

    lash_thickness = 0.055 + 0.06 * s_grid ** 2
    upper_lash = _soft_step(t_grid - (top - lash_thickness), pixel * 2) * _soft_step(top + 0.035 - t_grid, pixel * 2) * inside_horizontal
    wing = _soft_step(0.03 - numpy.abs(t_grid - (top - 0.02 - (s_grid - 0.82) * 0.5)), pixel * 2) * _soft_step(s_grid - 0.82, pixel * 2) * _soft_step(0.995 - s_grid, pixel * 2)
    lower_lash = _soft_step(0.012 - numpy.abs(t_grid - (bottom - 0.005)), pixel * 2) * _soft_step(s_grid - 0.55, 0.06) * inside_horizontal
    lash = numpy.clip(upper_lash + wing + lower_lash * 0.8, 0, 1)
    color = color * (1 - lash[..., None]) + lash_color[None, None, :] * lash[..., None]

    alpha = numpy.clip(opening + lash, 0, 1)
    pixels = numpy.concatenate([numpy.clip(color, 0, 1), alpha[..., None]], axis=-1).astype(numpy.float32)

    name = os.path.basename(path)
    existing = bpy.data.images.get(name)
    if existing is not None:
        bpy.data.images.remove(existing)
    image = bpy.data.images.new(name, size, size, alpha=True)
    image.pixels.foreach_set(pixels.ravel())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.filepath_raw = path
    formats = [item.identifier for item in bpy.types.Image.bl_rna.properties["file_format"].enum_items]
    image.file_format = next(identifier for identifier in formats if identifier.startswith("PNG"))
    image.save()
    return image


def eye_top(s):
    s = numpy.clip(s, 0.0, 1.0)
    return 0.60 + 0.10 * s + 0.30 * numpy.sin(numpy.pi * s) ** 0.75


def eye_bottom(s):
    s = numpy.clip(s, 0.0, 1.0)
    return 0.56 - 0.04 * s - 0.52 * numpy.sin(numpy.pi * s) ** 0.85


def closed_line(s):
    s = numpy.clip(s, 0.0, 1.0)
    return 0.5 * (eye_top(s) + eye_bottom(s)) - 0.10 * numpy.sin(numpy.pi * s)


def _soft_step(signed_distance, width):
    return numpy.clip(signed_distance / width + 0.5, 0.0, 1.0)


def _ellipse(s_grid, t_grid, center_s, center_t, radius_s, radius_t, softness):
    distance = numpy.sqrt(((s_grid - center_s) / radius_s) ** 2 + ((t_grid - center_t) / radius_t) ** 2)
    return _soft_step(1.0 - distance, softness / min(radius_s, radius_t))


def _mix(first, second, amount):
    return first * (1 - amount) + second * amount


class _Expression:
    def __init__(self, eye_scale=1.0, upper_lid=0.0, lower_lid=0.0, brow_raise=0.0, brow_tilt=0.0, mouth="closed"):
        self.eye_scale = eye_scale
        self.upper_lid = upper_lid
        self.lower_lid = lower_lid
        self.brow_raise = brow_raise
        self.brow_tilt = brow_tilt
        self.mouth = mouth


EXPRESSION_SETTINGS = {
    "neutral": _Expression(),
    "startled": _Expression(eye_scale=1.13, upper_lid=-0.04, brow_raise=0.004, brow_tilt=-0.08, mouth="round"),
    "suspicious": _Expression(upper_lid=0.48, lower_lid=0.18, brow_raise=-0.003, brow_tilt=0.35, mouth="flat"),
    "happy": _Expression(upper_lid=0.06, lower_lid=0.30, brow_raise=0.0025, brow_tilt=-0.1, mouth="smile"),
    "blink": _Expression(upper_lid=1.0, lower_lid=1.0),
}

LID_COLUMNS = 13
CARD_COLUMNS = 10
CARD_ROWS = 10


class _FaceBuilder:
    """Generates the face-feature mesh for one expression with a fixed topology."""

    def __init__(self, head, params):
        self.tree = mesh_utils.build_bvh(head)
        self.center = head_center(head.parent)
        self.params = params

    def project(self, x: float, z: float, offset: float) -> Vector:
        origin = Vector((self.center.x + x * HEAD_SCALE, self.center.y - 0.5, self.center.z + z * HEAD_SCALE))
        location, normal, _, _ = self.tree.ray_cast(origin, Vector((0, 1, 0)))
        if location is None:
            raise RuntimeError(f"face projection missed the head at x={x:.3f} z={z:.3f}")
        return location + normal * offset

    def eye_point(self, side: float, s: float, t: float, expression: _Expression, offset: float) -> Vector:
        scale = expression.eye_scale
        local_s = (s - 0.5) * scale
        local_t = (t - 0.5) * scale
        x = side * (FaceLayout.eye_center_x + local_s * FaceLayout.eye_width)
        z = FaceLayout.eye_center_z + local_t * FaceLayout.eye_height
        return self.project(x, z, offset)

    def geometry(self, expression: _Expression):
        parts = []
        uvs = []
        for side in (1.0, -1.0):
            parts.append(self._eye_card(side, expression, uvs))
            parts.extend(self._lids(side, expression, uvs))
            parts.append(self._brow(side, expression, uvs))
        parts.extend(self._mouth(expression, uvs))
        vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
        return vertices, faces, material_indices, uvs

    def _eye_card(self, side: float, expression: _Expression, uvs: list):
        vertices = []
        for row in range(CARD_ROWS + 1):
            for column in range(CARD_COLUMNS + 1):
                s = column / CARD_COLUMNS
                t = row / CARD_ROWS
                vertices.append(self.eye_point(side, s, t, expression, 0.0012))
        faces = []
        for row in range(CARD_ROWS):
            for column in range(CARD_COLUMNS):
                first = row * (CARD_COLUMNS + 1) + column
                quad = [first, first + 1, first + CARD_COLUMNS + 2, first + CARD_COLUMNS + 1]
                faces.append(tuple(quad) if side > 0 else tuple(reversed(quad)))
                for corner in faces[-1]:
                    corner_row, corner_column = divmod(corner, CARD_COLUMNS + 1)
                    u = corner_column / CARD_COLUMNS
                    uvs.append((u, corner_row / CARD_ROWS))
        return vertices, faces, 0

    def _lids(self, side: float, expression: _Expression, uvs: list):
        upper_rows = []
        lower_rows = []
        for column in range(LID_COLUMNS + 1):
            s = column / LID_COLUMNS
            top = float(eye_top(s))
            bottom = float(eye_bottom(s))
            closed = float(closed_line(s))
            lash_bottom_open = top - 0.075
            lash_bottom = lash_bottom_open + (closed - 0.03 - lash_bottom_open) * expression.upper_lid
            lash_top = lash_bottom + 0.11 - 0.04 * min(1.0, max(0.0, expression.upper_lid))
            cover_top = max(top + 0.035, lash_top)
            lower_fixed = bottom - 0.03
            lower_edge = lower_fixed + (closed - 0.03 - lower_fixed) * expression.lower_lid
            upper_rows.append((cover_top, lash_top, lash_bottom))
            lower_rows.append((lower_fixed, lower_edge))
        flap_vertices, lash_vertices, lower_vertices = [], [], []
        for column in range(LID_COLUMNS + 1):
            s = column / LID_COLUMNS
            cover_top, lash_top, lash_bottom = upper_rows[column]
            flap_vertices += [self.eye_point(side, s, cover_top, expression, 0.0022), self.eye_point(side, s, lash_top, expression, 0.0022)]
            lash_vertices += [self.eye_point(side, s, lash_top, expression, 0.0026), self.eye_point(side, s, lash_bottom, expression, 0.0026)]
            lower_fixed, lower_edge = lower_rows[column]
            lower_vertices += [self.eye_point(side, s, lower_fixed, expression, 0.0022), self.eye_point(side, s, lower_edge, expression, 0.0022)]
        return [
            self._strip(flap_vertices, side, 1, uvs),
            self._strip(lash_vertices, side, 2, uvs),
            self._strip(lower_vertices, side, 1, uvs, flip=True),
        ]

    def _strip(self, vertices: list, side: float, material_index: int, uvs: list, flip: bool = False):
        faces = []
        for column in range(len(vertices) // 2 - 1):
            first = column * 2
            quad = (first, first + 2, first + 3, first + 1)
            if (side > 0) != flip:
                quad = tuple(reversed(quad))
            faces.append(quad)
            uvs.extend([(0.5, 0.5)] * 4)
        return vertices, faces, material_index

    def _brow(self, side: float, expression: _Expression, uvs: list):
        vertices = []
        columns = 7
        for column in range(columns + 1):
            s = 0.08 + 0.84 * column / columns
            arch = 0.004 * math.sin(math.pi * s)
            tilt = expression.brow_tilt * (0.5 - s) * 0.012
            z = FaceLayout.brow_z + arch + expression.brow_raise - tilt
            thickness = 0.0028 * (1.0 - 0.6 * s)
            x = side * (FaceLayout.eye_center_x + (s - 0.5) * FaceLayout.eye_width * 1.05)
            vertices += [self.project(x, z + thickness, 0.0016), self.project(x, z - thickness * 0.4, 0.0016)]
        return self._strip(vertices, side, 3, uvs)

    def _mouth(self, expression: _Expression, uvs: list):
        parts = []
        for columns, offset, material_index in ((_mouth_columns(expression.mouth), 0.0012, 4), (_tongue_columns(expression.mouth), 0.0017, 5)):
            vertices = []
            for x, top, bottom in columns:
                vertices += [self.project(x, FaceLayout.mouth_z + top, offset), self.project(x, FaceLayout.mouth_z + bottom, offset)]
            parts.append(self._strip(vertices, 1.0, material_index, uvs))
        fang = _fang_outline(expression.mouth)
        fang_vertices = [self.project(x, FaceLayout.mouth_z + z, 0.0021) for x, z in fang]
        uvs.extend([(0.5, 0.5)] * 3)
        parts.append((fang_vertices, [(0, 2, 1)], 6))
        return parts


MOUTH_COLUMNS = 12


def _mouth_columns(mouth: str) -> list:
    """Mouth as (x, top z, bottom z) columns across its width, relative to the mouth centre."""
    columns = []
    for index in range(MOUTH_COLUMNS + 1):
        across = -1.0 + 2.0 * index / MOUTH_COLUMNS
        roundness = math.sqrt(max(0.0, 1.0 - across * across))
        if mouth == "smile":
            top = 0.0028 * across * across - 0.0025
            bottom = top - 0.0125 * roundness ** 0.8
            x = 0.0125 * across
        elif mouth == "round":
            top = 0.0045 * roundness ** 0.9 - 0.0015
            bottom = -0.0065 * roundness ** 0.9 - 0.003
            x = 0.0055 * across
        elif mouth == "flat":
            top = -0.0006 * across * across + 0.0003 * across
            bottom = top - 0.0012 * roundness ** 0.5
            x = 0.0075 * across
        else:
            top = 0.0017 * across * across
            bottom = top - 0.0013 * roundness ** 0.5
            x = 0.0075 * across
        columns.append((x, top, bottom))
    return columns


def _tongue_columns(mouth: str) -> list:
    columns = []
    for index in range(MOUTH_COLUMNS + 1):
        across = -1.0 + 2.0 * index / MOUTH_COLUMNS
        if mouth != "smile":
            columns.append((0.0, -0.0005, -0.0005))
            continue
        roundness = math.sqrt(max(0.0, 1.0 - across * across))
        columns.append((0.0015 + 0.0068 * across, -0.0112 + 0.0030 * roundness, -0.0112 - 0.0028 * roundness))
    return columns


def _fang_outline(mouth: str) -> list:
    if mouth != "smile":
        return [(0.0, -0.0005), (0.0, -0.0005), (0.0, -0.0005)]
    base_x = -0.0052
    base_z = 0.0028 * (base_x / 0.0125) ** 2 - 0.0025 - 0.0002
    return [(base_x - 0.0022, base_z), (base_x + 0.0022, base_z), (base_x + 0.0004, base_z - 0.0042)]


def build_face_features(head, params, eye_texture_path: str) -> bpy.types.Object:
    builder = _FaceBuilder(head, params)
    vertices, faces, material_indices, uvs = builder.geometry(EXPRESSION_SETTINGS["neutral"])
    hair_dark = tuple(channel * 0.78 for channel in hex_to_srgb(params.hair_shade_color))
    materials = [
        principled("M_Eye", (1.0, 1.0, 1.0), 0.4, eye_texture_path),
        principled("M_FaceSkin", params.skin_color, 0.55),
        principled("M_EyeLash", "#33202c", 0.6),
        principled("M_FaceBrow", hair_dark, 0.6),
        principled("M_Mouth", "#7a2836", 0.6),
        principled("M_MouthTongue", "#e46f7e", 0.6),
        principled("M_MouthFang", "#ffffff", 0.4),
    ]
    face = mesh_utils.mesh_from_geometry(f"{params.prefix}Face", vertices, faces, materials, material_indices, uvs)
    face.shape_key_add(name="Basis", from_mix=False)
    for name in EXPRESSIONS:
        key = face.shape_key_add(name=name, from_mix=False)
        key.value = 0.0
        expression_vertices, _, _, _ = builder.geometry(EXPRESSION_SETTINGS[name])
        for index, point in enumerate(expression_vertices):
            key.data[index].co = point
    _use_head_normals(face, builder.tree, builder.center)
    mesh_utils.assign_single_bone(face, head.parent, "head")
    return face


def _use_head_normals(face, tree, center: Vector) -> None:
    """Lids collapse to zero area in the basis; borrowing the skull's shading normals keeps them defined."""
    normals = []
    for vertex in face.data.vertices:
        location, normal, _, _ = tree.find_nearest(face.matrix_world @ vertex.co)
        if normal is None:
            normals.append(Vector((0, -1, 0)))
            continue
        normals.append(shading_normal(center, location, normal.normalized()))
    face.data.normals_split_custom_set_from_vertices(normals)

