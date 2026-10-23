"""Anime head, painted eye texture and the expressive face-feature mesh with shape keys."""

import math
import os

import bpy
import numpy
from mathutils import Vector

from . import mesh_utils
from .materials import hex_to_srgb, principled
from .rig import bone_world_points

EXPRESSIONS = [
    "neutral", "startled", "suspicious", "happy", "blink",
    "smile", "sad", "blush", "wink_L", "wink_R", "mouth_A", "mouth_I", "mouth_U", "mouth_E", "mouth_O",
]
EYE_CONTROLS = ["pupil_small", "pupil_large"]
FACE_SHAPE_KEYS = EXPRESSIONS + EYE_CONTROLS
# Eye-texture coordinates (s from the inner corner, t up): pupil centre and radii, then the highlights.
PUPIL = (0.53, 0.47, 0.10, 0.17)
EYE_HIGHLIGHTS = ((0.40, 0.63, 0.095, 0.11), (0.67, 0.25, 0.05, 0.045), (0.60, 0.70, 0.03, 0.03))

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
    brow_z = -0.006


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
    mesh_utils.add_modifier(head, "SUBSURF", levels=params.subdivision_levels, render_levels=params.subdivision_levels)
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


def paint_eye_texture(path: str, iris_color: tuple, highlight: bool, size: int = 512, pupil: bool = True) -> bpy.types.Image:
    """Paint the left-eye texture (inner corner at u=0) with numpy and save it as PNG.

    With `pupil` or `highlight` off they are left out of the texture, for faces that model them as geometry
    (so shape keys can resize them).
    """
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

    if pupil:
        pupil_mask = _ellipse(s_grid, t_grid, iris_center_s, iris_center_t + 0.04, 0.10, 0.17, pixel * 3.0)
        color = color * (1 - pupil_mask[..., None] * 0.85) + dark[None, None, :] * 0.6 * pupil_mask[..., None] * 0.85

    lid_shadow = _soft_step(t_grid - (top - 0.13), 0.05) * iris_mask
    color = color * (1 - lid_shadow[..., None] * 0.35) + dark[None, None, :] * lid_shadow[..., None] * 0.35

    if highlight:
        for center_s, center_t, radius_s, radius_t in EYE_HIGHLIGHTS:
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
    # Repaint an existing datablock in place: materials built earlier in the same file still point at it.
    image = bpy.data.images.get(name)
    if image is None:
        image = bpy.data.images.new(name, size, size, alpha=True)
    elif tuple(image.size) != (size, size):
        image.scale(size, size)
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
    """One face shape. Lids, brows and mouth are shared by both eyes unless `sides` overrides a side.

    `sides` maps a side (+1 is the character's left, -1 the right) to (upper lid, lower lid, closed arch).
    `closed_arch` bends the line where closed lids meet: negative is a relaxed downward curve, positive a happy "^".
    """

    def __init__(self, eye_scale=1.0, upper_lid=0.0, lower_lid=0.0, closed_arch=-0.10, brow_raise=0.0, brow_tilt=0.0,
                 mouth="closed", pupil_scale=1.0, highlight_scale=1.0, sides=None):
        self.eye_scale = eye_scale
        self.upper_lid = upper_lid
        self.lower_lid = lower_lid
        self.closed_arch = closed_arch
        self.brow_raise = brow_raise
        self.brow_tilt = brow_tilt
        self.mouth = mouth
        self.pupil_scale = pupil_scale
        self.highlight_scale = highlight_scale
        self.sides = sides or {}

    def lids(self, side: float) -> tuple:
        return self.sides.get(side, (self.upper_lid, self.lower_lid, self.closed_arch))


# A closing lid spans most of the eye; flat quads that tall would sag into the curved skull under the pupil.
LID_ROWS = 5


def _lid_rows(start: float, end: float) -> tuple:
    return tuple((start + (end - start) * row / LID_ROWS, LID_OFFSET) for row in range(LID_ROWS + 1))


def _wink(side: float) -> _Expression:
    return _Expression(upper_lid=0.05, lower_lid=0.18, brow_raise=0.002, brow_tilt=-0.1, mouth="smile_closed",
                       sides={side: (1.0, 1.0, 0.30)})


EXPRESSION_SETTINGS = {
    "neutral": _Expression(),
    "startled": _Expression(eye_scale=1.13, upper_lid=-0.04, brow_raise=0.004, brow_tilt=-0.08, mouth="round",
                            pupil_scale=0.78),
    "suspicious": _Expression(upper_lid=0.48, lower_lid=0.18, brow_raise=-0.003, brow_tilt=0.35, mouth="flat"),
    "happy": _Expression(upper_lid=0.06, lower_lid=0.30, brow_raise=0.0025, brow_tilt=-0.1, mouth="smile"),
    "blink": _Expression(upper_lid=1.0, lower_lid=1.0),
    "smile": _Expression(upper_lid=0.08, lower_lid=0.24, brow_raise=0.0015, brow_tilt=-0.05, mouth="smile_closed"),
    "sad": _Expression(upper_lid=0.26, lower_lid=0.04, brow_raise=0.0022, brow_tilt=-0.65, mouth="frown"),
    "blush": _Expression(upper_lid=0.08, lower_lid=0.14, brow_raise=0.001, brow_tilt=-0.2, mouth="small"),
    "wink_L": _wink(1.0),
    "wink_R": _wink(-1.0),
    "mouth_A": _Expression(mouth="A"),
    "mouth_I": _Expression(mouth="I"),
    "mouth_U": _Expression(mouth="U"),
    "mouth_E": _Expression(mouth="E"),
    "mouth_O": _Expression(mouth="O"),
    "pupil_small": _Expression(pupil_scale=0.6, highlight_scale=0.8),
    "pupil_large": _Expression(pupil_scale=1.35, highlight_scale=1.3),
}

LID_COLUMNS = 13
LID_OFFSET = 0.0026
LID_EDGE_OFFSET = 0.0004
LASH_OFFSET = 0.0030
PUPIL_OFFSET = 0.0016
HIGHLIGHT_OFFSET = 0.0020
LID_COVER_REACH = 0.04
CARD_COLUMNS = 10
CARD_ROWS = 10
DISC_SEGMENTS = 16
# Long outer lashes: (column fraction along the lash band, length in eye heights, outward lean in eye widths).
LASH_FLICKS = ((0.80, 0.16, 0.05), (0.90, 0.22, 0.10), (0.985, 0.20, 0.14))

FACE = "face"
EYES = "eyes"
LASHES = "lashes"
# Material index of each part within its object.
FACE_SKIN, FACE_BROW, FACE_MOUTH, FACE_TONGUE, FACE_FANG = 1, 2, 3, 4, 5
EYE_CARD, EYE_PUPIL, EYE_HIGHLIGHT = 0, 1, 2


class _Parts:
    """Geometry of one expression split by output object; every expression yields the same topology."""

    def __init__(self):
        self.groups = {FACE: [], EYES: [], LASHES: []}
        self.uvs = {FACE: [], EYES: [], LASHES: []}

    def add(self, group: str, vertices: list, faces: list, material_index: int, uvs: list) -> None:
        self.groups[group].append((vertices, faces, material_index))
        self.uvs[group].extend(uvs)


class _FaceBuilder:
    """Generates the face-feature meshes for one expression with a fixed topology."""

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

    def geometry(self, expression: _Expression) -> _Parts:
        parts = _Parts()
        for side in (1.0, -1.0):
            self._eye_card(parts, side, expression)
            self._pupil(parts, side, expression)
            self._lids(parts, side, expression)
            self._brow(parts, side, expression)
        self._mouth(parts, expression)
        return parts

    def _eye_card(self, parts: _Parts, side: float, expression: _Expression) -> None:
        vertices = []
        for row in range(CARD_ROWS + 1):
            for column in range(CARD_COLUMNS + 1):
                vertices.append(self.eye_point(side, column / CARD_COLUMNS, row / CARD_ROWS, expression, 0.0012))
        faces, uvs = [], []
        for row in range(CARD_ROWS):
            for column in range(CARD_COLUMNS):
                first = row * (CARD_COLUMNS + 1) + column
                quad = [first, first + 1, first + CARD_COLUMNS + 2, first + CARD_COLUMNS + 1]
                faces.append(tuple(quad) if side > 0 else tuple(reversed(quad)))
                for corner in faces[-1]:
                    corner_row, corner_column = divmod(corner, CARD_COLUMNS + 1)
                    uvs.append((corner_column / CARD_COLUMNS, corner_row / CARD_ROWS))
        parts.add(EYES, vertices, faces, EYE_CARD, uvs)

    def _disc(self, parts: _Parts, side: float, expression: _Expression, ellipse: tuple, scale: float,
              offset: float, material_index: int) -> None:
        center_s, center_t, radius_s, radius_t = ellipse
        vertices = [self.eye_point(side, center_s, center_t, expression, offset)]
        for segment in range(DISC_SEGMENTS):
            angle = 2 * math.pi * segment / DISC_SEGMENTS
            vertices.append(self.eye_point(side, center_s + math.cos(angle) * radius_s * scale,
                                           center_t + math.sin(angle) * radius_t * scale, expression, offset))
        faces = []
        for segment in range(DISC_SEGMENTS):
            triangle = (0, 1 + segment, 1 + (segment + 1) % DISC_SEGMENTS)
            faces.append(triangle if side > 0 else tuple(reversed(triangle)))
        parts.add(EYES, vertices, faces, material_index, [(0.5, 0.5)] * 3 * DISC_SEGMENTS)

    def _pupil(self, parts: _Parts, side: float, expression: _Expression) -> None:
        self._disc(parts, side, expression, PUPIL, expression.pupil_scale, PUPIL_OFFSET, EYE_PUPIL)
        for ellipse in EYE_HIGHLIGHTS:
            self._disc(parts, side, expression, ellipse, expression.highlight_scale, HIGHLIGHT_OFFSET, EYE_HIGHLIGHT)

    def _lids(self, parts: _Parts, side: float, expression: _Expression) -> None:
        """Skin flaps that slide over the eye card, plus the geometric upper lash band and its outer flicks.

        Each flap reaches well past the painted lashes and its outer row sits almost on the skin, so a
        closed lid leaves no sliver of lash or flap edge where the open eye's outline was.
        """
        upper_lid, lower_lid, closed_arch = expression.lids(side)
        cover_rows, lash_rows, lower_rows = [], [], []
        for column in range(LID_COLUMNS + 1):
            s = column / LID_COLUMNS
            top = float(eye_top(s))
            bottom = float(eye_bottom(s))
            closed = 0.5 * (top + bottom) + closed_arch * math.sin(math.pi * s)
            closure = min(1.0, max(0.0, upper_lid))
            lash_bottom_open = top - 0.075
            lash_bottom = lash_bottom_open + (closed - 0.03 - lash_bottom_open) * upper_lid
            lash_top = lash_bottom + 0.12 - 0.05 * closure
            cover_inner = max(top + 0.045, lash_top)
            cover_rows.append(((cover_inner + LID_COVER_REACH, LID_EDGE_OFFSET),)
                              + _lid_rows(cover_inner, lash_top))
            lash_rows.append(((lash_top, LASH_OFFSET), (lash_bottom, LASH_OFFSET)))
            lower_fixed = bottom - 0.03
            lower_edge = lower_fixed + (closed - 0.03 - lower_fixed) * lower_lid
            lower_rows.append(((lower_fixed - LID_COVER_REACH, LID_EDGE_OFFSET),) + _lid_rows(lower_fixed, lower_edge))
        for rows, group, material_index, flip in ((cover_rows, FACE, FACE_SKIN, False), (lash_rows, LASHES, 0, False),
                                                  (lower_rows, FACE, FACE_SKIN, True)):
            for band in range(len(rows[0]) - 1):
                vertices = []
                for column in range(LID_COLUMNS + 1):
                    s = column / LID_COLUMNS
                    for t, offset in rows[column][band:band + 2]:
                        vertices.append(self.eye_point(side, s, t, expression, offset))
                self._strip(parts, group, vertices, side, material_index, flip=flip)
        self._lash_flicks(parts, side, expression, lash_rows, closure)

    def _lash_flicks(self, parts: _Parts, side: float, expression: _Expression, lash_rows: list, closure: float) -> None:
        """Thin tapered lashes rising from the outer lash line; they fold down onto the lid as it closes."""
        for fraction, length, lean in LASH_FLICKS:
            position = fraction * LID_COLUMNS
            column = min(int(position), LID_COLUMNS - 1)
            blend = position - column
            lash_top = lash_rows[column][0][0] * (1 - blend) + lash_rows[column + 1][0][0] * blend
            base_width = 0.03
            rise = length * (1.0 - 0.75 * closure)
            outward = lean + 0.05 * closure
            vertices = [
                self.eye_point(side, fraction - base_width, lash_top - 0.02, expression, LASH_OFFSET),
                self.eye_point(side, fraction + base_width * 0.4, lash_top - 0.02, expression, LASH_OFFSET),
                self.eye_point(side, fraction + outward, lash_top + rise, expression, LASH_OFFSET),
            ]
            triangle = (0, 1, 2) if side < 0 else (0, 2, 1)
            parts.add(LASHES, vertices, [triangle], 0, [(0.5, 0.5)] * 3)

    def _strip(self, parts: _Parts, group: str, vertices: list, side: float, material_index: int, flip: bool = False):
        faces = []
        for column in range(len(vertices) // 2 - 1):
            first = column * 2
            quad = (first, first + 2, first + 3, first + 1)
            if (side > 0) != flip:
                quad = tuple(reversed(quad))
            faces.append(quad)
        parts.add(group, vertices, faces, material_index, [(0.5, 0.5)] * 4 * len(faces))

    def _brow(self, parts: _Parts, side: float, expression: _Expression) -> None:
        vertices = []
        columns = 7
        for column in range(columns + 1):
            s = 0.08 + 0.84 * column / columns
            arch = 0.004 * math.sin(math.pi * s)
            tilt = expression.brow_tilt * (0.5 - s) * 0.012
            z = FaceLayout.brow_z + arch + expression.brow_raise - tilt
            thickness = 0.0030 * (1.0 - 0.6 * s)
            x = side * (FaceLayout.eye_center_x + (s - 0.5) * FaceLayout.eye_width * 1.05)
            vertices += [self.project(x, z + thickness, 0.0016), self.project(x, z - thickness * 0.4, 0.0016)]
        self._strip(parts, FACE, vertices, side, FACE_BROW)

    def _mouth(self, parts: _Parts, expression: _Expression) -> None:
        for columns, offset, material_index in ((_mouth_columns(expression.mouth), 0.0012, FACE_MOUTH),
                                                (_tongue_columns(expression.mouth), 0.0017, FACE_TONGUE)):
            vertices = []
            for x, top, bottom in columns:
                vertices += [self.project(x, FaceLayout.mouth_z + top, offset), self.project(x, FaceLayout.mouth_z + bottom, offset)]
            self._strip(parts, FACE, vertices, 1.0, material_index)
        fang = _fang_outline(expression.mouth)
        fang_vertices = [self.project(x, FaceLayout.mouth_z + z, 0.0021) for x, z in fang]
        parts.add(FACE, fang_vertices, [(0, 2, 1)], FACE_FANG, [(0.5, 0.5)] * 3)


MOUTH_COLUMNS = 12
TONGUE_MOUTHS = ("smile", "A")


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
        elif mouth == "smile_closed":
            top = 0.0032 * across * across - 0.0014
            bottom = top - 0.0012 * roundness ** 0.5
            x = 0.0092 * across
        elif mouth == "frown":
            top = -0.0024 * across * across + 0.0006
            bottom = top - 0.0011 * roundness ** 0.5
            x = 0.0062 * across
        elif mouth == "small":
            top = 0.0012 * across * across
            bottom = top - 0.0011 * roundness ** 0.5
            x = 0.0058 * across
        elif mouth == "A":
            top = 0.0014 * across * across + 0.0008
            bottom = top - 0.0115 * roundness ** 0.85
            x = 0.0085 * across
        elif mouth == "I":
            top = 0.0010 * across * across + 0.0004
            bottom = top - 0.0034 * roundness ** 0.6
            x = 0.0108 * across
        elif mouth == "U":
            top = 0.0026 * roundness ** 0.9 - 0.0010
            bottom = -0.0032 * roundness ** 0.9 - 0.0010
            x = 0.0036 * across
        elif mouth == "E":
            top = 0.0012 * across * across + 0.0008
            bottom = top - 0.0068 * roundness ** 0.7
            x = 0.0102 * across
        elif mouth == "O":
            top = 0.0044 * roundness ** 0.9 - 0.0006
            bottom = -0.0078 * roundness ** 0.9 - 0.0016
            x = 0.0060 * across
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
        if mouth not in TONGUE_MOUTHS:
            columns.append((0.0, -0.0005, -0.0005))
            continue
        roundness = math.sqrt(max(0.0, 1.0 - across * across))
        if mouth == "A":
            columns.append((0.0050 * across, -0.0085 + 0.0022 * roundness, -0.0085 - 0.0020 * roundness))
        else:
            columns.append((0.0015 + 0.0068 * across, -0.0112 + 0.0030 * roundness, -0.0112 - 0.0028 * roundness))
    return columns


def _fang_outline(mouth: str) -> list:
    if mouth != "smile":
        return [(0.0, -0.0005), (0.0, -0.0005), (0.0, -0.0005)]
    base_x = -0.0052
    base_z = 0.0028 * (base_x / 0.0125) ** 2 - 0.0025 - 0.0002
    return [(base_x - 0.0022, base_z), (base_x + 0.0022, base_z), (base_x + 0.0004, base_z - 0.0042)]


def _face_materials(params, eye_texture_path: str) -> dict:
    hair_dark = tuple(channel * 0.78 for channel in hex_to_srgb(params.hair_shade_color))
    iris_dark = tuple(channel * 0.28 + shade for channel, shade in zip(hex_to_srgb(params.eye_color), (0.12, 0.05, 0.22)))
    return {
        FACE: [
            principled("M_Skin", params.skin_color, 0.55),
            principled("M_FaceSkin", params.skin_color, 0.55),
            principled("M_FaceBrow", hair_dark, 0.6),
            principled("M_Mouth", "#7a2836", 0.6),
            principled("M_MouthTongue", "#e46f7e", 0.6),
            principled("M_MouthFang", "#ffffff", 0.4),
        ],
        EYES: [
            principled("M_Eye", (1.0, 1.0, 1.0), 0.4, eye_texture_path),
            principled("M_EyePupil", iris_dark, 0.4),
            principled("M_EyeHighlight", "#ffffff", 0.3),
        ],
        LASHES: [principled("M_EyeLash", "#33202c", 0.6)],
    }


def build_face_features(head, params, eye_texture_path: str, shape_keys: list[str] | None = None) -> bpy.types.Object:
    """Build `<prefix>Face` (the skull plus lids, brows and mouth), `<prefix>Eyes` and `<prefix>Lashes`.

    All three carry the same shape keys (`shape_keys`, default all of `FACE_SHAPE_KEYS`), so setting an
    expression by name moves every part of it. The skull `head` is joined into the face and no longer exists
    afterwards.
    """
    armature = head.parent
    builder = _FaceBuilder(head, params)
    neutral = builder.geometry(EXPRESSION_SETTINGS["neutral"])
    keyed = {name: builder.geometry(EXPRESSION_SETTINGS[name]) for name in (shape_keys or FACE_SHAPE_KEYS)}
    materials = _face_materials(params, eye_texture_path)
    names = {FACE: f"{params.prefix}Face", EYES: f"{params.prefix}Eyes", LASHES: f"{params.prefix}Lashes"}
    objects = {}
    for group, name in names.items():
        vertices, faces, material_indices = mesh_utils.merge_geometry(neutral.groups[group])
        feature = mesh_utils.mesh_from_geometry(f"{name}Features" if group == FACE else name, vertices, faces,
                                                materials[group], material_indices, neutral.uvs[group])
        feature.shape_key_add(name="Basis", from_mix=False)
        for key_name, parts in keyed.items():
            key = feature.shape_key_add(name=key_name, from_mix=False)
            key.value = 0.0
            key_vertices, _, _ = mesh_utils.merge_geometry(parts.groups[group])
            for index, point in enumerate(key_vertices):
                key.data[index].co = point
        _use_head_normals(feature, builder.tree, builder.center)
        mesh_utils.assign_single_bone(feature, armature, "head")
        objects[group] = feature
    # The joined skull keeps its own vertices in every shape key; the features object stays active so its keys win.
    face = mesh_utils.join_objects(names[FACE], [objects[FACE], head])
    mesh_utils.assign_single_bone(face, armature, "head")
    return face


def build_blush(head_face, params) -> bpy.types.Object:
    """Cheek blush patches that exist only through the `blush` shape key: in the basis every patch collapses
    to a point (zero area), so nothing renders at blush 0."""
    armature = head_face.parent
    builder = _FaceBuilder(head_face, params)
    rings, sectors = 4, 14
    vertices, key_vertices, faces, uvs = [], [], [], []
    for side in (1.0, -1.0):
        center_x = side * (FaceLayout.eye_center_x + 0.006)
        center_z = FaceLayout.eye_center_z - 0.036
        radius_x, radius_z = 0.0175, 0.0085
        start = len(vertices)
        collapsed = builder.project(center_x, center_z, 0.0015)
        grid = [(0.0, 0.0)] + [(ring / rings * math.cos(2 * math.pi * sector / sectors),
                                 ring / rings * math.sin(2 * math.pi * sector / sectors))
                                for ring in range(1, rings + 1) for sector in range(sectors)]
        for across, up in grid:
            vertices.append(collapsed)
            key_vertices.append(builder.project(center_x + across * radius_x, center_z + up * radius_z, 0.0015))

        def grid_index(ring: int, sector: int) -> int:
            return start if ring == 0 else start + 1 + (ring - 1) * sectors + sector % sectors

        for ring in range(rings):
            for sector in range(sectors):
                if ring == 0:
                    corners = (grid_index(0, 0), grid_index(1, sector), grid_index(1, sector + 1))
                else:
                    corners = (grid_index(ring, sector), grid_index(ring + 1, sector), grid_index(ring + 1, sector + 1),
                               grid_index(ring, sector + 1))
                if side < 0:
                    corners = tuple(reversed(corners))
                faces.append(corners)
                for corner in corners:
                    across, up = grid[corner - start]
                    uvs.append((0.5 + 0.5 * across, 0.5 + 0.5 * up))
    blush = mesh_utils.mesh_from_geometry(f"{params.prefix}Blush", vertices, faces,
                                          [principled("M_FaceBlush", "#f27d93", 0.6, alpha=0.6)], [0] * len(faces), uvs)
    blush.shape_key_add(name="Basis", from_mix=False)
    key = blush.shape_key_add(name="blush", from_mix=False)
    key.value = 0.0
    for index, point in enumerate(key_vertices):
        key.data[index].co = point
    _use_head_normals(blush, builder.tree, builder.center)
    mesh_utils.assign_single_bone(blush, armature, "head")
    return blush


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
