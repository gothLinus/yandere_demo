"""Anime hair: a scalp cap, layered strand cards (bangs, side and back), the braid and ribbon bows."""

import math
import random

import bpy
from mathutils import Matrix, Vector

from . import mesh_utils
from .face import HEAD_SCALE, head_center
from .materials import principled
from .rig import BRAID_BONES, add_chain

HAIR_RADII = Vector((0.099, 0.099, 0.116))
HAIR_BACK_DEPTH = 0.112
STRAND_THICKNESS = 0.0035
RIBBON_SAMPLES = 14

HAIR = 0
HAIR_SHADE = 1
HAIR_STREAK = 2


class Strand:
    """One hair lock: follows the hair surface from the crown to `theta_end`, then hangs `hang` metres."""

    def __init__(self, phi, theta_end, hang, width, material=HAIR, scale=1.0, flare=0.0, curl=0.0,
                 tip_bend=0.0, theta_start=8.0, sway=0.0):
        self.phi = phi
        self.theta_end = theta_end
        self.hang = hang
        self.width = width
        self.material = material
        self.scale = scale
        self.flare = flare
        self.curl = curl
        self.tip_bend = tip_bend
        self.theta_start = theta_start
        self.sway = sway


def surface_point(center: Vector, theta_degrees: float, phi_degrees: float, scale: float = 1.0) -> Vector:
    """Point on the hair ellipsoid. phi 0 faces the front (-Y), positive phi turns to the character's left (+X)."""
    theta = math.radians(theta_degrees)
    phi = math.radians(phi_degrees)
    direction = Vector((math.sin(theta) * math.sin(phi), -math.sin(theta) * math.cos(phi), math.cos(theta)))
    depth = HAIR_RADII.y if direction.y < 0 else HAIR_BACK_DEPTH
    return center + Vector((0, 0.004, 0)) + Vector((direction.x * HAIR_RADII.x, direction.y * depth, direction.z * HAIR_RADII.z)) * scale * HEAD_SCALE


def surface_normal(center: Vector, point: Vector) -> Vector:
    local = (point - center - Vector((0, 0.004, 0))) / HEAD_SCALE
    depth = HAIR_RADII.y if local.y < 0 else HAIR_BACK_DEPTH
    return Vector((local.x / HAIR_RADII.x ** 2, local.y / depth ** 2, local.z / HAIR_RADII.z ** 2)).normalized()


def _strand_path(center: Vector, strand: Strand) -> list:
    surface_samples = 9
    points = []
    for index in range(surface_samples + 1):
        fraction = index / surface_samples
        theta = strand.theta_start + (strand.theta_end - strand.theta_start) * fraction
        phi = strand.phi + strand.sway * math.sin(math.pi * fraction)
        points.append(surface_point(center, theta, phi, strand.scale))
    if strand.hang > 0:
        start = points[-1]
        outward = Vector((math.sin(math.radians(strand.phi)), -math.cos(math.radians(strand.phi)), 0))
        hang_samples = 6
        for index in range(1, hang_samples + 1):
            fraction = index / hang_samples
            drop = strand.hang * fraction
            offset = outward * (strand.flare * fraction * fraction + strand.curl * math.sin(math.pi * fraction))
            lift = Vector((0, 0, strand.tip_bend * fraction ** 3))
            points.append(start + Vector((0, 0, -drop)) + offset + lift)
    elif strand.tip_bend:
        inward = (center - points[-1]).normalized()
        points[-1] = points[-1] + inward * strand.tip_bend
        points[-2] = points[-2] + inward * strand.tip_bend * 0.4
    return _resample(points, RIBBON_SAMPLES)


def _resample(points: list, count: int) -> list:
    lengths = [0.0]
    for index in range(1, len(points)):
        lengths.append(lengths[-1] + (points[index] - points[index - 1]).length)
    total = lengths[-1]
    result = []
    segment = 0
    for index in range(count + 1):
        target = total * index / count
        while segment < len(points) - 2 and lengths[segment + 1] < target:
            segment += 1
        span = lengths[segment + 1] - lengths[segment]
        fraction = 0.0 if span < 1e-9 else (target - lengths[segment]) / span
        result.append(points[segment].lerp(points[segment + 1], fraction))
    return result


def ribbon(points: list, widths: list, outward_normals: list, arch: float = 0.22):
    """A tapered strip with an outward-arched centre line, so toon shading shows a ridge."""
    vertices = []
    faces = []
    for index, point in enumerate(points):
        following = points[min(index + 1, len(points) - 1)]
        previous = points[max(index - 1, 0)]
        tangent = (following - previous).normalized()
        normal = outward_normals[index]
        lateral = tangent.cross(normal).normalized()
        half = widths[index] * 0.5
        vertices += [
            point - lateral * half - normal * half * arch * 0.3,
            point + normal * half * arch,
            point + lateral * half - normal * half * arch * 0.3,
        ]
    for index in range(len(points) - 1):
        row = index * 3
        following = row + 3
        faces.append((row, row + 1, following + 1, following))
        faces.append((row + 1, row + 2, following + 2, following + 1))
    return vertices, faces


def _strand_geometry(center: Vector, strand: Strand):
    points = _strand_path(center, strand)
    count = len(points)
    widths = []
    for index in range(count):
        fraction = index / (count - 1)
        profile = 0.45 + 0.55 * math.sin(math.pi * min(1.0, fraction * 1.25) * 0.5) ** 0.7
        taper = 1.0 if fraction < 0.62 else max(0.0, (1.0 - fraction) / 0.38) ** 0.9
        widths.append(strand.width * profile * taper)
    normals = []
    for index, point in enumerate(points):
        surface = surface_normal(center, point)
        horizontal = Vector((point.x - center.x, point.y - center.y - 0.004, 0))
        hang_normal = horizontal.normalized() if horizontal.length > 1e-6 else surface
        weight = min(1.0, max(0.0, (center.z - point.z) / 0.05))
        normals.append(surface.lerp(hang_normal, weight).normalized())
    vertices, faces = ribbon(points, widths, normals)
    return vertices, faces, strand.material


def _layout_strands(params, seed: int = 7) -> dict:
    generator = random.Random(seed)

    def jitter(amount: float) -> float:
        return generator.uniform(-amount, amount)

    bangs = [
        Strand(-66, 99, 0.034, 0.050, scale=1.03, tip_bend=0.004, sway=4),
        Strand(-48, 97, 0.016, 0.044, scale=1.045, sway=-3),
        Strand(-30, 92, 0.004, 0.044, scale=1.05, sway=5),
        Strand(-14, 94, 0.006, 0.040, scale=1.055, sway=-4),
        Strand(2, 99, 0.022, 0.026, scale=1.06, sway=3),
        Strand(16, 93, 0.004, 0.042, scale=1.05, sway=-5),
        Strand(31, 92, 0.006, 0.044, scale=1.05, sway=4),
        Strand(49, 97, 0.016, 0.046, scale=1.035, tip_bend=0.004, sway=-3),
        Strand(66, 99, 0.030, 0.050, scale=1.03, tip_bend=0.004, sway=3),
    ]
    for strand in bangs:
        strand.theta_start = 12
        strand.curl = -0.004
    streak = Strand(38, 95, 0.012, 0.034, material=HAIR_STREAK, scale=1.075, theta_start=38, sway=-3)
    streak.curl = -0.004
    bangs.append(streak)
    sides = [
        Strand(-78, 96, 0.110, 0.060, scale=1.03, flare=0.010, curl=0.006, tip_bend=0.004),
        Strand(-91, 97, 0.095, 0.068, scale=1.05, flare=0.024, curl=0.010, tip_bend=0.008),
        Strand(-105, 98, 0.088, 0.068, scale=1.045, flare=0.028, curl=0.008, tip_bend=0.010),
        Strand(76, 96, 0.105, 0.060, scale=1.03, flare=0.012, curl=0.006, tip_bend=0.004),
        Strand(89, 97, 0.090, 0.068, scale=1.05, flare=0.026, curl=0.010, tip_bend=0.008),
        Strand(103, 98, 0.088, 0.068, scale=1.045, flare=0.03, curl=0.008, tip_bend=0.010),
    ]
    for sign in (-1.0, 1.0):
        sides.append(Strand(sign * 60, 97, 0.062, 0.058, scale=1.07, flare=0.026, curl=0.012, tip_bend=0.006, sway=sign * 4))
        sides.append(Strand(sign * 118, 99, 0.075, 0.066, scale=1.075, flare=0.04, curl=0.01, tip_bend=0.02, sway=sign * -5))
    back = []
    for index in range(11):
        phi = 112 + index * 13.6 + jitter(3)
        behind = abs(((phi + 180) % 360) - 180)
        hang = 0.115 + jitter(0.02) + (0.03 if behind > 160 else 0.0)
        back.append(Strand(phi, 100 + jitter(3), hang, 0.062 + jitter(0.006), scale=1.04 + jitter(0.01),
                           flare=0.035 + jitter(0.012), curl=0.004, tip_bend=0.018 + jitter(0.01), sway=jitter(6)))
    inner = []
    for index in range(16):
        phi = 70 + index * 14.0 + jitter(3)
        inner.append(Strand(phi, 100, 0.09 + jitter(0.015), 0.07, material=HAIR_SHADE, scale=0.985,
                            flare=0.02, tip_bend=0.008, sway=jitter(5)))
    crown = []
    for index in range(7):
        phi = -150 + index * 50 + jitter(8)
        crown.append(Strand(phi, 70 + jitter(6), 0.0, 0.07, scale=1.06, theta_start=4, tip_bend=-0.006, sway=jitter(8)))
    return {"bangs": bangs, "sides": sides, "back": back, "inner": inner, "crown": crown}


def _hair_materials(params) -> list:
    return [
        principled("M_Hair", params.hair_color, 0.5),
        principled("M_HairShade", params.hair_shade_color, 0.5),
        principled("M_HairStreak", params.hair_streak_color, 0.5),
    ]


def _strands_object(name: str, center: Vector, strands: list, params) -> bpy.types.Object:
    parts = [_strand_geometry(center, strand) for strand in strands]
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    hair_object = mesh_utils.mesh_from_geometry(name, vertices, faces, _hair_materials(params), material_indices)
    mesh_utils.add_modifier(hair_object, "SOLIDIFY", thickness=STRAND_THICKNESS, offset=-1.0, use_even_offset=True)
    mesh_utils.apply_modifiers(hair_object)
    mesh_utils.recalculate_normals(hair_object)
    return hair_object


def build_bangs(head, params) -> bpy.types.Object:
    center = head_center(head.parent)
    layout = _layout_strands(params)
    bangs = _strands_object(f"{params.prefix}Bangs", center, layout["bangs"] + layout["crown"], params)
    ahoge = _ahoge(center, params)
    return mesh_utils.join_objects(f"{params.prefix}Bangs", [bangs, ahoge])


def build_side_hair(head, params) -> bpy.types.Object:
    center = head_center(head.parent)
    layout = _layout_strands(params)
    return _strands_object(f"{params.prefix}SideHair", center, layout["sides"] + layout["back"] + layout["inner"], params)


def build_hair_cap(head, params) -> bpy.types.Object:
    center = head_center(head.parent)
    rings = []
    for ring_index in range(15):
        theta = 2 + ring_index * 7.5
        ring = []
        for column in range(32):
            phi = column * 360 / 32
            hairline = _hairline_theta(phi)
            point = surface_point(center, min(theta, hairline), phi, 0.955)
            ring.append(point)
        rings.append(ring)
    vertices, faces = mesh_utils.loft(rings)
    cap = mesh_utils.mesh_from_geometry(f"{params.prefix}HairCap", vertices, faces, _hair_materials(params), [HAIR_SHADE] * len(faces))
    mesh_utils.recalculate_normals(cap)
    mesh_utils.add_modifier(cap, "SUBSURF", levels=1, render_levels=1)
    mesh_utils.apply_modifiers(cap)
    return cap


def _hairline_theta(phi: float) -> float:
    behind = abs(((phi + 180) % 360) - 180) / 180.0
    return 72 + 40 * behind ** 1.5


def _ahoge(center: Vector, params) -> bpy.types.Object:
    root = surface_point(center, 14, 12, 1.05)
    offsets = [(0, 0, 0), (0.004, -0.004, 0.02), (0.010, -0.012, 0.042), (0.016, -0.028, 0.052), (0.020, -0.044, 0.046), (0.022, -0.052, 0.034)]
    points = [root + Vector(offset) * HEAD_SCALE for offset in offsets]
    points = _resample(points, 10)
    widths = [0.012 * (1.0 - index / 10) ** 0.8 + 0.001 for index in range(11)]
    normals = []
    for index, point in enumerate(points):
        following = points[min(index + 1, 10)]
        previous = points[max(index - 1, 0)]
        tangent = (following - previous).normalized()
        normals.append(tangent.cross(Vector((1, 0, 0))).normalized() * -1)
    vertices, faces = ribbon(points, widths, normals, arch=0.15)
    ahoge = mesh_utils.mesh_from_geometry(f"{params.prefix}Ahoge", vertices, faces, _hair_materials(params), [HAIR] * len(faces))
    mesh_utils.add_modifier(ahoge, "SOLIDIFY", thickness=0.003, offset=0.0)
    mesh_utils.apply_modifiers(ahoge)
    return ahoge


def build_hair(head, armature, params) -> bpy.types.Object:
    parts = [build_hair_cap(head, params), build_bangs(head, params), build_side_hair(head, params)]
    hair_object = mesh_utils.join_objects(f"{params.prefix}Hair", parts)
    mesh_utils.shade_smooth(hair_object)
    mesh_utils.assign_single_bone(hair_object, armature, "head")
    return hair_object


def braid_points(armature, params) -> list:
    center = head_center(armature)
    shoulder_z = center.z - 0.20
    return [
        center + Vector((-0.070, 0.050, -0.070)),
        Vector((-0.112, 0.020, shoulder_z + 0.035)),
        Vector((-0.128, -0.050, shoulder_z - 0.035)),
        Vector((-0.118, -0.098, shoulder_z - 0.150)),
        Vector((-0.112, -0.112, shoulder_z - 0.275)),
        Vector((-0.108, -0.112, shoulder_z - 0.385)),
        Vector((-0.106, -0.106, shoulder_z - 0.470)),
    ]


def add_braid_chain(armature, params) -> list:
    return add_chain(armature, "braid", "head", braid_points(armature, params))


def _braid_curve(armature, params, samples: int) -> list:
    points = braid_points(armature, params)
    dense = []
    for index in range(len(points) - 1):
        before = points[max(index - 1, 0)]
        start = points[index]
        end = points[index + 1]
        after = points[min(index + 2, len(points) - 1)]
        for step in range(8):
            fraction = step / 8
            dense.append(_catmull_rom(before, start, end, after, fraction))
    dense.append(points[-1])
    return _resample(dense, samples)


def _catmull_rom(before, start, end, after, fraction):
    squared = fraction * fraction
    cubed = squared * fraction
    return 0.5 * ((2 * start) + (-before + end) * fraction + (2 * before - 5 * start + 4 * end - after) * squared
                  + (-before + 3 * start - 3 * end + after) * cubed)


def build_braid(armature, params) -> bpy.types.Object:
    lobe_count = 16
    curve = _braid_curve(armature, params, lobe_count * 4)
    frames = mesh_utils.frame_along(curve)
    parts = []
    for lobe in range(lobe_count):
        position = min(int((lobe + 0.5) * len(curve) / lobe_count), len(curve) - 1)
        tangent = frames[position][0]
        side = Vector((0, -1, 0)).cross(tangent).normalized()
        if side.length < 0.5:
            side = frames[position][2]
        facing = tangent.cross(side).normalized()
        fraction = lobe / (lobe_count - 1)
        width = 0.030 - 0.009 * fraction
        sign = 1 if lobe % 2 == 0 else -1
        tilt = math.radians(36 * sign)
        lobe_side = (side * math.cos(tilt) + tangent * math.sin(tilt)).normalized()
        lobe_axis = (tangent * math.cos(tilt) - side * math.sin(tilt)).normalized()
        rotation = Matrix((lobe_side, facing, lobe_axis)).transposed()
        lobe_center = curve[position] + side * width * 0.26 * sign
        vertices, faces = mesh_utils.ellipsoid(Vector((0, 0, 0)), Vector((width * 0.78, width * 0.7, 0.042)), 12, 10)
        shaped = []
        for vertex in vertices:
            along = vertex.z / 0.040
            pinch = 1.0 - 0.45 * along * along
            local = Vector((vertex.x * pinch, vertex.y * (0.75 + 0.25 * pinch), vertex.z))
            shaped.append(lobe_center + rotation @ local)
        parts.append((shaped, faces, 0 if lobe % 2 == 0 else 1))
    core_vertices, core_faces = _braid_core(curve)
    parts.append((core_vertices, core_faces, 1))
    parts += _braid_tuft(curve[-1], frames[-1][0])
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    braid = mesh_utils.mesh_from_geometry(f"{params.prefix}Braid", vertices, faces, _hair_materials(params), material_indices)
    mesh_utils.recalculate_normals(braid)
    mesh_utils.add_modifier(braid, "SUBSURF", levels=1, render_levels=1)
    mesh_utils.apply_modifiers(braid)
    mesh_utils.assign_nearest_bone_weights(braid, armature, ["head"] + BRAID_BONES, blend=0.05)
    return braid


def _braid_core(curve: list):
    """A thin darker tube inside the plait so no gaps show between lobes."""
    frames = mesh_utils.frame_along(curve)
    rings = []
    for index, point in enumerate(curve):
        _, normal, binormal = frames[index]
        radius = 0.016 - 0.005 * index / (len(curve) - 1)
        rings.append([point + (normal * math.cos(angle) + binormal * math.sin(angle)) * radius
                      for angle in (2 * math.pi * step / 10 for step in range(10))])
    return mesh_utils.loft(rings, cap_start=True, cap_end=True)


def _braid_tuft(tip: Vector, tangent: Vector) -> list:
    parts = []
    for index, (spread_x, spread_y, length) in enumerate(((-0.014, 0.0, 0.07), (0.0, -0.01, 0.085), (0.014, 0.004, 0.065), (0.004, 0.012, 0.06))):
        start = tip + tangent * 0.01
        points = [start + tangent * length * fraction + Vector((spread_x, spread_y, 0)) * fraction ** 1.5 for fraction in (0, 0.25, 0.5, 0.75, 1.0)]
        widths = [0.026, 0.024, 0.018, 0.009, 0.0005]
        normals = [Vector((spread_x, spread_y - 0.02, 0)).normalized()] * len(points)
        vertices, faces = ribbon(points, widths, normals, arch=0.6)
        parts.append((vertices, faces, 0))
        parts.append(([vertex + normals[0] * -0.003 for vertex in vertices], [tuple(reversed(face)) for face in faces], 1))
    return parts


def bow_geometry(origin: Vector, outward: Vector, up_hint: Vector, size: float = 1.0):
    """Ribbon bow: two pinched loops, a knot and two tails, in the plane facing `outward`."""
    normal = outward.normalized()
    up = (up_hint - normal * normal.dot(up_hint)).normalized()
    across = up.cross(normal).normalized()
    basis = Matrix((across, up, normal)).transposed()
    parts = []
    knot_vertices, knot_faces = mesh_utils.ellipsoid(origin, Vector((0.010, 0.012, 0.009)) * size, 12, 8, basis)
    parts.append((knot_vertices, knot_faces, 0))
    for sign in (1.0, -1.0):
        parts.append(_bow_loop(origin, across * sign, up, normal, size))
        outer = across * sign
        thickness = normal * 0.0016
        tail_rings = []
        for step in range(5):
            fraction = step / 4
            center = origin + (-up * 0.042 * fraction + outer * (0.010 + 0.014 * fraction)) * size - normal * 0.002
            half_width = outer * (0.0085 + 0.002 * fraction) * size
            # The tail end is cut on a slant: its outer edge reaches further down.
            slant = -up * 0.008 * size if step == 4 else Vector((0, 0, 0))
            tail_rings.append([
                center - half_width + thickness,
                center + half_width + thickness + slant,
                center + half_width - thickness + slant,
                center - half_width - thickness,
            ])
        vertices, faces = mesh_utils.loft(tail_rings, closed=True, cap_start=True, cap_end=True)
        parts.append((vertices, faces, 0))
    return parts


def _bow_loop(origin: Vector, outward_axis: Vector, up: Vector, normal: Vector, size: float):
    """A teardrop ribbon loop, pinched at the knot, rounded at the tip and dished on its face."""
    angle = math.radians(20)
    direction = (outward_axis * math.cos(angle) + up * math.sin(angle)).normalized()
    perpendicular = normal.cross(direction).normalized()
    length, height, depth = 0.037 * size, 0.020 * size, 0.0055 * size
    rings = []
    steps = 12
    for step in range(1, steps):
        fraction = step / steps
        half_height = height * math.sin(math.pi * fraction) ** 0.7 * (0.45 + 0.55 * fraction)
        half_depth = depth * (0.55 + 0.45 * math.sin(math.pi * fraction))
        center = origin + direction * length * fraction - normal * 0.007 * size * fraction * fraction
        ring = []
        for index in range(12):
            theta = 2 * math.pi * index / 12
            across = math.cos(theta)
            forward = math.sin(theta) * half_depth
            if forward > 0:
                forward -= 0.7 * half_depth * (1 - across * across) * math.sin(math.pi * fraction)
            ring.append(center + perpendicular * half_height * across + normal * forward)
        rings.append(ring)
    vertices, faces = mesh_utils.loft(rings, cap_start=True, cap_end=True)
    return vertices, faces, 0


def build_bows(params, armature) -> bpy.types.Object:
    center = head_center(armature)
    parts = []
    for phi in (-82.0, 80.0):
        origin = surface_point(center, 40, phi, 1.13)
        normal = surface_normal(center, origin)
        sideways = Vector((normal.x, normal.y, 0)).normalized()
        outward = (sideways * 0.65 + Vector((0, -1.0, 0.2))).normalized()
        parts += bow_geometry(origin, outward, Vector((-sideways.x * 0.35, 0.2, 1)), 1.25 * HEAD_SCALE)
    curve = _braid_curve(armature, params, 40)
    tip = curve[-1]
    tangent = (curve[-1] - curve[-3]).normalized()
    parts += bow_geometry(tip + Vector((0, -0.022, 0.004)), Vector((0.1, -1.0, 0.05)), -tangent, 1.35)
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    bows = mesh_utils.mesh_from_geometry(f"{params.prefix}Bows", vertices, faces, [principled("M_Bow", "#1d151b", 0.35)], material_indices)
    mesh_utils.recalculate_normals(bows)
    mesh_utils.add_modifier(bows, "SUBSURF", levels=1, render_levels=1)
    mesh_utils.apply_modifiers(bows)
    braid_tip = tip
    head_vertices = [vertex.index for vertex in bows.data.vertices if (vertex.co - braid_tip).length > 0.12]
    braid_vertices = [vertex.index for vertex in bows.data.vertices if (vertex.co - braid_tip).length <= 0.12]
    bows.vertex_groups.new(name="head").add(head_vertices, 1.0, "REPLACE")
    bows.vertex_groups.new(name=BRAID_BONES[-1]).add(braid_vertices, 1.0, "REPLACE")
    mesh_utils.parent_to_armature(bows, armature)
    return bows


def build_ponytail(*arguments, **keywords):
    raise NotImplementedError("build_ponytail is implemented for the player in Task 10")
