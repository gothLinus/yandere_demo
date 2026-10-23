"""Anime hair: a scalp cap, layered strand cards (bangs, side and back), the braid and ribbon bows."""

import math
import os
import random

import numpy

import bpy
from mathutils import Matrix, Vector

from . import mesh_utils, pleats
from .face import HEAD_SCALE, head_center
from .materials import hex_to_srgb, principled
from .rig import BRAID_BONES, BRAID_BOW_BONE, add_bone, add_chain

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
                 tip_bend=0.0, theta_start=8.0, sway=0.0, cluster=None):
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
        # Secondary bone chain prefix this lock follows (None: rigid to the head).
        self.cluster = cluster


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
    # v runs from the root (1) to the tip (0), so glTF's flipped V reads root 0 -> tip 1 in Godot.
    vertex_uvs = [(across, 1.0 - index / (count - 1)) for index in range(count) for across in (0.0, 0.5, 1.0)]
    return vertices, faces, strand.material, vertex_uvs


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
    streak = Strand(38, 95, 0.012, 0.034, material=HAIR_STREAK, scale=1.075, theta_start=38, sway=-3)
    bangs.append(streak)
    for strand in bangs:
        if strand is not streak:
            strand.theta_start = 12
        strand.curl = -0.004
        strand.cluster = front_cluster(strand.phi)
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
    for strand in sides:
        strand.cluster = "hair_side_L" if strand.phi > 0 else "hair_side_R"
    back = []
    for index in range(11):
        phi = 112 + index * 13.6 + jitter(3)
        behind = abs(((phi + 180) % 360) - 180)
        hang = 0.155 + jitter(0.02) + (0.03 if behind > 160 else 0.0)
        back.append(Strand(phi, 100 + jitter(3), hang, 0.062 + jitter(0.006), scale=1.04 + jitter(0.01),
                           flare=0.035 + jitter(0.012), curl=0.004, tip_bend=0.018 + jitter(0.01), sway=jitter(6)))
    inner = []
    for index in range(16):
        phi = 70 + index * 14.0 + jitter(3)
        inner.append(Strand(phi, 100, 0.125 + jitter(0.015), 0.07, material=HAIR_SHADE, scale=0.985,
                            flare=0.02, tip_bend=0.008, sway=jitter(5)))
    crown = []
    for index in range(7):
        phi = -150 + index * 50 + jitter(8)
        crown.append(Strand(phi, 70 + jitter(6), 0.0, 0.07, scale=1.06, theta_start=4, tip_bend=-0.006, sway=jitter(8)))
    return {"bangs": bangs, "sides": sides, "back": back, "inner": inner, "crown": crown}


def paint_hair_texture(path: str, params, width: int = 64, height: int = 256) -> bpy.types.Image:
    """Base colour along a lock (v 1 at the root, 0 at the tip): shade at the roots, the hair colour through the
    middle, a slightly lighter tip, and faint strand lines across the lock. The shine band is added in Godot."""
    shade = numpy.array(hex_to_srgb(params.hair_shade_color))
    base = numpy.array(hex_to_srgb(params.hair_color))
    tip = base + (numpy.ones(3) - base) * 0.10
    across = (numpy.arange(width) + 0.5) / width
    along = 1.0 - (numpy.arange(height) + 0.5) / height
    across_grid, along_grid = numpy.meshgrid(across, along)
    root_mix = numpy.clip(along_grid / 0.22, 0.0, 1.0)[..., None]
    color = shade * (1 - root_mix) + base * root_mix
    tip_mix = numpy.clip((along_grid - 0.75) / 0.25, 0.0, 1.0)[..., None]
    color = color * (1 - tip_mix) + tip * tip_mix
    strands = (0.5 + 0.5 * numpy.cos(2 * numpy.pi * (across_grid * 3.0 + 0.15 * numpy.sin(along_grid * 9.0)))) ** 6
    color = color * (1.0 - 0.05 * strands[..., None])
    pixels = numpy.concatenate([numpy.clip(color, 0, 1), numpy.ones((height, width, 1))], axis=-1).astype(numpy.float32)
    name = os.path.basename(path)
    image = bpy.data.images.get(name)
    if image is None:
        image = bpy.data.images.new(name, width, height, alpha=False)
    elif tuple(image.size) != (width, height):
        image.scale(width, height)
    image.pixels.foreach_set(pixels.ravel())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.filepath_raw = path
    formats = [item.identifier for item in bpy.types.Image.bl_rna.properties["file_format"].enum_items]
    image.file_format = next(identifier for identifier in formats if identifier.startswith("PNG"))
    image.save()
    return image


FRONT_CLUSTER_PHI = 22.0
# Where along a lock (0 root, 1 tip) its chain takes over from the head, per chain family.
CLUSTER_TAKEOVER = {"hair_front": 0.45, "hair_side": 0.40, "ahoge": 0.05}
CLUSTER_BLEND = 0.3


def front_cluster(phi: float) -> str:
    if phi > FRONT_CLUSTER_PHI:
        return "hair_front_L"
    if phi < -FRONT_CLUSTER_PHI:
        return "hair_front_R"
    return "hair_front_C"


def _hair_materials(params, hair_texture_path: str | None = None) -> list:
    return [
        principled("M_Hair", "#ffffff" if hair_texture_path else params.hair_color, 0.5, hair_texture_path,
                   texture_alpha=False),
        principled("M_HairShade", params.hair_shade_color, 0.5),
        principled("M_HairStreak", params.hair_streak_color, 0.5),
    ]


def _strands_object(name: str, center: Vector, strands: list, params, armature) -> bpy.types.Object:
    parts = [_strand_geometry(center, strand) for strand in strands]
    vertices, faces, material_indices, uvs = mesh_utils.merge_geometry_with_uvs(parts)
    hair_object = mesh_utils.mesh_from_geometry(name, vertices, faces, _hair_materials(params, params.extra.get("hair_texture")),
                                                material_indices, uvs)
    vertex_bones = []
    for strand, part in zip(strands, parts):
        for _, along in part[3]:
            vertex_bones.append(_lock_bones(armature, strand.cluster, 1.0 - along))
    # Solidify copies the vertex groups onto the inner shell.
    mesh_utils.weight_by_segments(hair_object, armature, vertex_bones)
    mesh_utils.add_modifier(hair_object, "SOLIDIFY", thickness=STRAND_THICKNESS, offset=-1.0, use_even_offset=True)
    mesh_utils.apply_modifiers(hair_object)
    mesh_utils.recalculate_normals(hair_object)
    return hair_object


def _lock_bones(armature, cluster: str | None, along: float) -> list:
    """(bones, share) pairs for a hair vertex `along` its lock: the head holds the root, the chain the rest."""
    if cluster is None:
        return [(["head"], 1.0)]
    family = cluster.rsplit("_", 1)[0] if cluster.startswith("hair_") else cluster
    takeover = CLUSTER_TAKEOVER[family]
    chain = [bone.name for bone in armature.data.bones if bone.name.startswith(cluster + "_")]
    share = min(1.0, max(0.0, (along - takeover) / CLUSTER_BLEND))
    return [(["head"], 1.0 - share), (chain, share)]


def build_bangs(head, params) -> bpy.types.Object:
    armature = head.parent
    center = head_center(armature)
    layout = _layout_strands(params)
    bangs = _strands_object(f"{params.prefix}Bangs", center, layout["bangs"] + layout["crown"], params, armature)
    ahoge = _ahoge(center, params, armature)
    return mesh_utils.join_objects(f"{params.prefix}Bangs", [bangs, ahoge])


def build_side_hair(head, params) -> bpy.types.Object:
    armature = head.parent
    center = head_center(armature)
    layout = _layout_strands(params)
    return _strands_object(f"{params.prefix}SideHair", center, layout["sides"] + layout["back"] + layout["inner"], params,
                           armature)


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
    cap = mesh_utils.mesh_from_geometry(f"{params.prefix}HairCap", vertices, faces, _hair_materials(params, params.extra.get("hair_texture")),
                                        [HAIR_SHADE] * len(faces), [(0.5, 1.0)] * sum(len(face) for face in faces))
    cap.vertex_groups.new(name="head").add(range(len(cap.data.vertices)), 1.0, "REPLACE")
    mesh_utils.recalculate_normals(cap)
    mesh_utils.add_modifier(cap, "SUBSURF", levels=1, render_levels=1)
    mesh_utils.apply_modifiers(cap)
    return cap


def _hairline_theta(phi: float) -> float:
    behind = abs(((phi + 180) % 360) - 180) / 180.0
    return 72 + 40 * behind ** 1.5


AHOGE_OFFSETS = [(0, 0, 0), (0.004, -0.004, 0.02), (0.010, -0.012, 0.042), (0.016, -0.028, 0.052), (0.020, -0.044, 0.046),
                 (0.022, -0.052, 0.034)]


def ahoge_points(center: Vector, count: int) -> list:
    root = surface_point(center, 14, 12, 1.05)
    return _resample([root + Vector(offset) * HEAD_SCALE for offset in AHOGE_OFFSETS], count)


def _ahoge(center: Vector, params, armature) -> bpy.types.Object:
    points = ahoge_points(center, 10)
    widths = [0.012 * (1.0 - index / 10) ** 0.8 + 0.001 for index in range(11)]
    normals = []
    for index, point in enumerate(points):
        following = points[min(index + 1, 10)]
        previous = points[max(index - 1, 0)]
        tangent = (following - previous).normalized()
        normals.append(tangent.cross(Vector((1, 0, 0))).normalized() * -1)
    vertices, faces = ribbon(points, widths, normals, arch=0.15)
    vertex_uvs = [(across, 1.0 - index / 10) for index in range(11) for across in (0.0, 0.5, 1.0)]
    uvs = [vertex_uvs[index] for face in faces for index in face]
    ahoge = mesh_utils.mesh_from_geometry(f"{params.prefix}Ahoge", vertices, faces,
                                          _hair_materials(params, params.extra.get("hair_texture")), [HAIR] * len(faces), uvs)
    mesh_utils.weight_by_segments(ahoge, armature, [_lock_bones(armature, "ahoge", index / 10)
                                                    for index in range(11) for _ in range(3)])
    mesh_utils.add_modifier(ahoge, "SOLIDIFY", thickness=0.003, offset=0.0)
    mesh_utils.apply_modifiers(ahoge)
    return ahoge


def build_hair(head, armature, params) -> bpy.types.Object:
    parts = [build_hair_cap(head, params), build_bangs(head, params), build_side_hair(head, params)]
    hair_object = mesh_utils.join_objects(f"{params.prefix}Hair", parts)
    mesh_utils.shade_smooth(hair_object)
    mesh_utils.parent_to_armature(hair_object, armature)
    return hair_object


def add_hair_chains(armature, params) -> list:
    """Bone chains for the ahoge, the three bang clusters and the two side locks, laid along their locks."""
    center = head_center(armature)
    names = []
    ahoge = ahoge_points(center, 9)
    names += add_chain(armature, "ahoge", "head", [ahoge[0], ahoge[3], ahoge[6], ahoge[9]])
    for cluster, phi in (("L", 40.0), ("C", 2.0), ("R", -40.0)):
        path = _strand_path(center, Strand(phi, 97, 0.014, 0.04, scale=1.05, theta_start=12))
        names += add_chain(armature, f"hair_front_{cluster}", "head", [path[6], path[10], path[-1]])
    for cluster, sign in (("L", 1.0), ("R", -1.0)):
        path = _strand_path(center, Strand(sign * 90, 97, 0.095, 0.068, scale=1.05, flare=0.024, curl=0.010))
        names += add_chain(armature, f"hair_side_{cluster}", "head", [path[6], path[9], path[12], path[-1]])
    return names


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


BRAID_BOW_LENGTH = 0.06


def add_braid_chain(armature, params) -> list:
    """`braid_01..10` along the plait, then `braid_bow` from the tie down along the tuft."""
    curve = _braid_curve(armature, params, len(BRAID_BONES))
    names = add_chain(armature, "braid", "head", curve)
    tangent = (curve[-1] - curve[-2]).normalized()
    names.append(add_bone(armature, BRAID_BOW_BONE, curve[-1], curve[-1] + tangent * BRAID_BOW_LENGTH, names[-1]))
    return names


# Distance the braid's centre line keeps from the skirt's outer pleat faces: the plait's half-thickness plus a little
# air, so the plait and its bow rest on the skirt instead of sinking into it.
BRAID_SKIRT_CLEARANCE = 0.024
# Width of the soft blend between hanging free and resting on the skirt, so the plait has no kink where it meets it.
BRAID_SKIRT_BLEND = 0.012


def _rest_on_skirt(points: list, skirt: pleats.SkirtSurface) -> list:
    """Push every point at skirt height radially out to the skirt's outer surface plus the plait's clearance."""
    rested = []
    for point in points:
        if not skirt.covers(point.z):
            rested.append(point)
            continue
        radial = Vector((point.x, point.y - pleats.CENTER_Y, 0.0))
        radius = radial.length
        angle = math.atan2(radial.y, radial.x)
        minimum = skirt.radius(angle, point.z) + BRAID_SKIRT_CLEARANCE
        smooth = 0.5 * (radius + minimum + math.sqrt((radius - minimum) ** 2 + BRAID_SKIRT_BLEND ** 2))
        rested.append(point + radial.normalized() * (smooth - radius))
    return rested


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
    return _resample(_rest_on_skirt(dense, pleats.SkirtSurface(armature, params)), samples)


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
        # Each lobe runs root (top, v 1) to tip (v 0) like a lock, so the highlight band crosses every plait.
        lobe_uvs = [(0.5, 0.5 + vertex.z / 0.084) for vertex in vertices]
        parts.append((shaped, faces, 0 if lobe % 2 == 0 else 1, lobe_uvs))
    core_vertices, core_faces = _braid_core(curve)
    parts.append((core_vertices, core_faces, 1, [(0.5, 1.0)] * len(core_vertices)))
    for tuft_vertices, tuft_faces, material_index in _braid_tuft(curve[-1], frames[-1][0]):
        count = len(tuft_vertices) // 3
        parts.append((tuft_vertices, tuft_faces, material_index,
                      [(across, 1.0 - index / max(1, count - 1)) for index in range(count) for across in (0.0, 0.5, 1.0)]))
    vertices, faces, material_indices, uvs = mesh_utils.merge_geometry_with_uvs(parts)
    braid = mesh_utils.mesh_from_geometry(f"{params.prefix}Braid", vertices, faces,
                                          _hair_materials(params, params.extra.get("hair_texture")), material_indices, uvs)
    mesh_utils.recalculate_normals(braid)
    mesh_utils.add_modifier(braid, "SUBSURF", levels=1, render_levels=1)
    mesh_utils.apply_modifiers(braid)
    mesh_utils.assign_nearest_bone_weights(braid, armature, ["head"] + BRAID_BONES + [BRAID_BOW_BONE], blend=0.05)
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
    """Flat ribbon bow lying in the plane facing `outward`: two bow-tie loops, a small knot and two tails."""
    normal = outward.normalized()
    up = (up_hint - normal * normal.dot(up_hint)).normalized()
    across = up.cross(normal).normalized()
    basis = Matrix((across, up, normal)).transposed()
    parts = []
    knot_vertices, knot_faces = mesh_utils.ellipsoid(origin + normal * 0.0015 * size, Vector((0.0075, 0.0095, 0.0042)) * size, 12, 8, basis)
    parts.append((knot_vertices, knot_faces, 0))
    for sign in (1.0, -1.0):
        parts.append(_bow_loop(origin, across * sign, up, normal, size))
        parts.append(_bow_tail(origin, across * sign, up, normal, size))
    return parts


def _bow_loop(origin: Vector, outward_axis: Vector, up: Vector, normal: Vector, size: float):
    """A flat bow-tie loop: pinched at the knot, widening to a squared, softly rounded outer end."""
    angle = math.radians(14)
    direction = (outward_axis * math.cos(angle) + up * math.sin(angle)).normalized()
    perpendicular = normal.cross(direction).normalized()
    length, height, depth = 0.034 * size, 0.0175 * size, 0.0021 * size
    corner = 0.8
    rings = []
    steps = 14
    for step in range(1, steps + 1):
        fraction = step / steps * 0.995
        half_height = height * min(fraction, corner) ** 0.8
        if fraction > corner:
            half_height *= math.sqrt(max(0.0, 1.0 - ((fraction - corner) / (1.0 - corner)) ** 2))
        half_height = max(half_height, 0.0008 * size)
        # A shallow V across the ribbon reads as the fold of a pressed loop under toon shading.
        fold = 0.0018 * size * math.sin(math.pi * min(1.0, fraction / corner))
        center = origin + direction * length * fraction - normal * 0.002 * size * fraction * fraction
        ring = []
        for index in range(10):
            theta = 2 * math.pi * index / 10
            across = math.cos(theta)
            forward = math.sin(theta) * depth - fold * abs(across)
            ring.append(center + perpendicular * half_height * across + normal * forward)
        rings.append(ring)
    vertices, faces = mesh_utils.loft(rings, cap_start=True, cap_end=True)
    return vertices, faces, 0


def _bow_tail(origin: Vector, outward_axis: Vector, up: Vector, normal: Vector, size: float):
    """A short flat tail hanging from the knot, cut on a slant."""
    thickness = normal * 0.0011 * size
    rings = []
    for step in range(4):
        fraction = step / 3
        center = origin + (-up * 0.024 * fraction + outward_axis * (0.004 + 0.010 * fraction)) * size - normal * 0.0015 * size
        half_width = outward_axis * (0.0055 + 0.0015 * fraction) * size
        slant = -up * 0.006 * size if step == 3 else Vector((0, 0, 0))
        rings.append([
            center - half_width + thickness,
            center + half_width + thickness + slant,
            center + half_width - thickness + slant,
            center - half_width - thickness,
        ])
    vertices, faces = mesh_utils.loft(rings, cap_start=True, cap_end=True)
    return vertices, faces, 0


HEAD_BOW_PHI = 114.0


def head_bow_frames(armature) -> list:
    """(origin, facing, up hint) of the two head bows on the upper back sides, lying flat on the hair."""
    center = head_center(armature)
    frames = []
    for phi in (-HEAD_BOW_PHI, HEAD_BOW_PHI):
        origin = surface_point(center, 55, phi, 1.16)
        normal = surface_normal(center, origin)
        frames.append((origin, (normal + Vector((0, 0.3, 0))).normalized(), Vector((0, -0.25, 1))))
    return frames


def bow_parts(params, armature) -> tuple[list, list]:
    """Geometry of the two head bows and the braid-tip bow, as (head parts, braid parts)."""
    head_parts = []
    for origin, facing, up_hint in head_bow_frames(armature):
        head_parts += bow_geometry(origin, facing, up_hint, 1.6 * HEAD_SCALE)
    curve = _braid_curve(armature, params, 40)
    tip = curve[-1]
    tangent = (curve[-1] - curve[-3]).normalized()
    braid_parts = bow_geometry(tip + Vector((0, -0.022, 0.004)), Vector((0.1, -1.0, 0.05)), -tangent, 1.5)
    return head_parts, braid_parts


def build_ponytail(*arguments, **keywords):
    raise NotImplementedError("build_ponytail is implemented for the player in Task 10")
