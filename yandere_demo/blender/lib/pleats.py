"""Parameterised box-pleated skirt: a body-fitted drape profile, even box pleats, hem trim and 8 x 3 chains."""

import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import mesh_utils
from .materials import principled
from .rig import SKIRT_CHAIN_COUNT, SKIRT_CHAINS, SKIRT_SEGMENTS, add_chain, chain_names, skirt_chain_azimuth

PLEAT_COUNT_RANGE = (16, 24)
PLEAT_DEPTH = 0.012
HEM_FLARE = 0.18
SECTORS = 72
CENTER_Y = 0.004
# Ease between the body and the inside of the pleat recesses, and the flat stitched waistband.
CLEARANCE = 0.014
WAISTBAND_FRACTION = 0.07
# The pleats open fully from this fraction of the skirt length (they are stitched down above it).
PLEAT_OPEN_FRACTION = 0.30
# Box pleat profile across one pleat (0..1): the recessed fold, then the flat outer face as a chord.
PLEAT_SAMPLES = (0.0, 0.09, 0.36, 0.64, 0.91)
FOLD_SAMPLES = (0, 1, 4)
STRIPES = ((0.030, 0.038), (0.048, 0.056))
LOWER_BODY_BONES = {"hips", "spine", "thigh.L", "thigh.R", "shin.L", "shin.R"}
ARM_FREE_RADIUS = 0.3
REFERENCE_HEIGHT = 1.58

WHITE = 0
ACCENT = 1


class SkirtLevels:
    def __init__(self, armature):
        hips_head = armature.matrix_world @ armature.data.bones["hips"].head_local
        spine_head = armature.matrix_world @ armature.data.bones["spine"].head_local
        knee = armature.matrix_world @ armature.data.bones["thigh.L"].tail_local
        head_top = armature.matrix_world @ armature.data.bones["head"].tail_local
        self.scale = head_top.z / REFERENCE_HEIGHT
        self.waist_z = spine_head.z - 0.015 * self.scale
        self.hem_z = knee.z + 0.036 * self.scale
        self.hips_z = hips_head.z

    def fraction(self, z: float) -> float:
        return (self.waist_z - z) / (self.waist_z - self.hem_z)

    def height(self, fraction: float) -> float:
        return self.waist_z + (self.hem_z - self.waist_z) * fraction


class DrapeProfile:
    """Radius of the skirt's inner surface by azimuth and height.

    Fabric hangs straight down from the widest point of the body above it (a running maximum of the
    body's extent from the waist down), is smoothed around the waist so it does not follow the gap
    between the thighs, and flares by `hem_flare` toward the hem.
    """

    def __init__(self, body, levels: SkirtLevels, hem_flare: float, bands: int = 40):
        self.levels = levels
        self.hem_flare = hem_flare
        self.bands = bands
        tree = _lower_body_tree(body)
        running = [0.0] * SECTORS
        self.radii = []
        for band in range(bands + 1):
            z = levels.height(min(1.0, band / bands))
            extents = [_outer_radius(tree, z, 2 * math.pi * sector / SECTORS) for sector in range(SECTORS)]
            running = [max(previous, value) for previous, value in zip(running, extents)]
            self.radii.append(_smooth_circular(running, passes=6))

    def radius(self, angle: float, fraction: float) -> float:
        position = max(0.0, min(1.0, fraction)) * self.bands
        band = min(int(position), self.bands - 1)
        blend = position - band
        sector_position = (angle / (2 * math.pi) * SECTORS) % SECTORS
        sector = int(sector_position)
        sector_blend = sector_position - sector

        def at(band_index: int) -> float:
            ring = self.radii[band_index]
            return ring[sector] * (1 - sector_blend) + ring[(sector + 1) % SECTORS] * sector_blend

        body = at(band) * (1 - blend) + at(band + 1) * blend
        flare = 1.0 + self.hem_flare * max(0.0, fraction - PLEAT_OPEN_FRACTION) / (1.0 - PLEAT_OPEN_FRACTION)
        return (body + CLEARANCE * self.levels.scale) * flare


class SkirtSurface:
    """The skirt's outer surface (drape profile plus the open pleat depth), known before the skirt is built."""

    def __init__(self, armature, params, pleat_depth: float = PLEAT_DEPTH, hem_flare: float = HEM_FLARE):
        self.levels = SkirtLevels(armature)
        self.profile = DrapeProfile(_body(armature, params), self.levels, hem_flare)
        self.pleat_depth = pleat_depth

    def radius(self, angle: float, z: float) -> float:
        """Distance of the outer pleat faces from the skirt axis at an azimuth (atan2(y - CENTER_Y, x)) and height."""
        fraction = self.levels.fraction(z)
        return self.profile.radius(angle, fraction) + self.pleat_depth * self.levels.scale * _pleat_opening(max(0.0, fraction))

    def covers(self, z: float) -> bool:
        return 0.0 <= self.levels.fraction(z) <= 1.0


def _lower_body_tree(body) -> BVHTree:
    """BVH of the body faces skinned mainly to the torso and legs, so the hanging arms never widen the skirt."""
    names = {group.index: group.name for group in body.vertex_groups}
    lower = set()
    for vertex in body.data.vertices:
        dominant = max(vertex.groups, key=lambda element: element.weight, default=None)
        if dominant is not None and names[dominant.group] in LOWER_BODY_BONES:
            lower.add(vertex.index)
    vertices = [body.matrix_world @ vertex.co for vertex in body.data.vertices]
    polygons = [tuple(polygon.vertices) for polygon in body.data.polygons if all(index in lower for index in polygon.vertices)]
    return BVHTree.FromPolygons(vertices, polygons)


def _outer_radius(tree, z: float, angle: float) -> float:
    """Outermost torso or leg surface along a ray from the body axis."""
    direction = Vector((math.cos(angle), math.sin(angle), 0.0))
    origin = Vector((0.0, CENTER_Y, z))
    distance = 0.0
    outermost = 0.0
    for _ in range(8):
        location, _, _, hit_distance = tree.ray_cast(origin + direction * distance, direction, ARM_FREE_RADIUS - distance)
        if location is None:
            break
        distance += hit_distance + 1e-4
        outermost = distance
    return outermost


def _smooth_circular(values: list, passes: int) -> list:
    for _ in range(passes):
        count = len(values)
        values = [max(values[index], (values[index - 1] + 2 * values[index] + values[(index + 1) % count]) / 4)
                  for index in range(count)]
    return values


def _body(armature, params):
    body = bpy.data.objects.get(f"{params.prefix}Body")
    if body is None or body.parent != armature:
        raise ValueError(f"{params.prefix}Body must be built (and skinned to {armature.name}) before the skirt")
    return body


def add_skirt_bones(armature, params, hem_flare: float = HEM_FLARE) -> list:
    """Eight three-bone chains laid on the skirt's surface at each pleat group's centre, from waist to hem."""
    levels = SkirtLevels(armature)
    profile = DrapeProfile(_body(armature, params), levels, hem_flare)
    names = []
    for chain_index, prefix in enumerate(SKIRT_CHAINS):
        angle = skirt_chain_azimuth(chain_index)
        points = []
        for segment in range(SKIRT_SEGMENTS + 1):
            fraction = segment / SKIRT_SEGMENTS
            radius = profile.radius(angle, fraction)
            points.append(Vector((math.cos(angle) * radius, math.sin(angle) * radius + CENTER_Y, levels.height(fraction))))
        names += add_chain(armature, prefix, "hips", points)
    return names


def build_pleated_skirt(armature, params, pleat_count: int = 20, pleat_depth: float = PLEAT_DEPTH,
                        hem_flare: float = HEM_FLARE) -> bpy.types.Object:
    """Even box pleats with a white hem trim, skinned to the hips and the eight `skirt_NN` chains."""
    if not PLEAT_COUNT_RANGE[0] <= pleat_count <= PLEAT_COUNT_RANGE[1]:
        raise ValueError(f"pleat_count must be within {PLEAT_COUNT_RANGE[0]}..{PLEAT_COUNT_RANGE[1]}, got {pleat_count}")
    levels = SkirtLevels(armature)
    profile = DrapeProfile(_body(armature, params), levels, hem_flare)
    scale = levels.scale
    hem_length = levels.waist_z - levels.hem_z
    fractions = [0.0, WAISTBAND_FRACTION * 0.5, WAISTBAND_FRACTION]
    fractions += [WAISTBAND_FRACTION + (1.0 - WAISTBAND_FRACTION) * index / 12 for index in range(1, 12)]
    for low, high in STRIPES:
        fractions += [1.0 - high * scale / hem_length, 1.0 - low * scale / hem_length]
    fractions += [1.0 - 0.018 * scale / hem_length, 1.0 - 0.008 * scale / hem_length, 1.0]
    fractions = sorted(set(round(fraction, 5) for fraction in fractions if 0.0 <= fraction <= 1.0))

    samples = len(PLEAT_SAMPLES)
    columns = pleat_count * samples
    pleat_angle = 2 * math.pi / pleat_count
    # The last pleat is centred on the front (-pi/2), so the chains and the folds line up symmetrically.
    start_angle = -math.pi / 2 - pleat_angle / 2
    rings = []
    for fraction in fractions:
        depth = pleat_depth * scale * _pleat_opening(fraction)
        ring = []
        for pleat in range(pleat_count):
            corners = []
            for sample in PLEAT_SAMPLES:
                angle = start_angle - (pleat + sample) * pleat_angle
                radius = profile.radius(angle, fraction)
                corners.append((angle, radius))
            outer_first = _polar(corners[1][0], corners[1][1] + depth)
            outer_last = _polar(corners[4][0], corners[4][1] + depth)
            for index, (angle, radius) in enumerate(corners):
                if index == 0:
                    point = _polar(angle, radius)
                else:
                    # The outer face is a flat chord between its two folds, which reads as a pressed panel.
                    chord = (PLEAT_SAMPLES[index] - PLEAT_SAMPLES[1]) / (PLEAT_SAMPLES[4] - PLEAT_SAMPLES[1])
                    point = outer_first.lerp(outer_last, chord)
                    bulge = _polar(angle, radius + depth)
                    point = point.lerp(bulge, 0.35)
                ring.append(Vector((point.x, point.y + CENTER_Y, levels.height(fraction))))
        rings.append(ring)
    vertices, faces = mesh_utils.loft(rings)
    material_indices = []
    for ring_index in range(len(rings) - 1):
        middle = (1.0 - (fractions[ring_index] + fractions[ring_index + 1]) * 0.5) * hem_length / scale
        is_stripe = any(low < middle < high for low, high in STRIPES)
        material_indices += [WHITE if is_stripe else ACCENT] * columns
    materials = [principled("M_UniformWhite", _colors(params)["main"], 0.7),
                 principled(_colors(params)["accent_material"], _colors(params)["accent"], 0.65)]
    skirt = mesh_utils.mesh_from_geometry(f"{params.prefix}Skirt", vertices, faces, materials, material_indices)
    fold_edges = []
    for edge in skirt.data.edges:
        first, second = edge.vertices
        same_column = first % columns == second % columns
        fold_edges.append(same_column and (first % columns) % samples in FOLD_SAMPLES)
    mesh_utils.mark_sharp_edges(skirt, fold_edges)
    mesh_utils.recalculate_normals(skirt)
    _ensure_outward(skirt)
    mesh_utils.add_modifier(skirt, "SOLIDIFY", thickness=0.003, offset=-1.0, use_even_offset=True)
    _weight(skirt, armature, levels)
    mesh_utils.apply_modifiers(skirt)
    skirt["pleat_count"] = pleat_count
    skirt["pleat_depth"] = pleat_depth
    skirt["hem_flare"] = hem_flare
    mesh_utils.parent_to_armature(skirt, armature)
    return skirt


def _pleat_opening(fraction: float) -> float:
    if fraction <= WAISTBAND_FRACTION:
        return 0.0
    opening = min(1.0, (fraction - WAISTBAND_FRACTION) / (PLEAT_OPEN_FRACTION - WAISTBAND_FRACTION))
    return 0.25 + 0.75 * opening * opening * (3 - 2 * opening)


def _polar(angle: float, radius: float) -> Vector:
    return Vector((math.cos(angle) * radius, math.sin(angle) * radius, 0.0))


def _colors(params) -> dict:
    from .clothing import _uniform_colors
    return _uniform_colors(params.uniform)


def _ensure_outward(skirt) -> None:
    outward = 0.0
    for polygon in skirt.data.polygons:
        radial = polygon.center - Vector((0.0, CENTER_Y, polygon.center.z))
        outward += polygon.normal.dot(radial)
    if outward < 0:
        skirt.data.flip_normals()


# Segment weight keys along the skirt length: the hips hold the stitched yoke (so swinging panels never push
# the pleats out through the top's hem), then each bone peaks at its middle.
YOKE_FRACTION = 0.14
SEGMENT_KEYS = ([(0.0, "hips"), (YOKE_FRACTION, "hips")]
                + [(max(YOKE_FRACTION + 0.08, (segment + 0.5) / SKIRT_SEGMENTS), segment) for segment in range(SKIRT_SEGMENTS)])


def _skirt_bones(point: Vector, levels: SkirtLevels) -> dict:
    """Bone weights of a skirt point: azimuth blends the two nearest chains, height blends their segments."""
    fraction = max(0.0, min(1.0, levels.fraction(point.z)))
    angle = math.atan2(point.y - CENTER_Y, point.x)
    # Chain n sits at -90 - n * 45 degrees (clockwise from the front seen from above).
    position = ((-math.pi / 2 - angle) / (2 * math.pi) * SKIRT_CHAIN_COUNT) % SKIRT_CHAIN_COUNT
    first = int(position) % SKIRT_CHAIN_COUNT
    second = (first + 1) % SKIRT_CHAIN_COUNT
    chain_blend = position - int(position)
    segment_weights = {}
    for (low, low_key), (high, high_key) in zip(SEGMENT_KEYS, SEGMENT_KEYS[1:]):
        if low <= fraction <= high:
            blend = (fraction - low) / (high - low)
            segment_weights = {low_key: 1.0 - blend}
            segment_weights[high_key] = segment_weights.get(high_key, 0.0) + blend
            break
    else:
        segment_weights = {SKIRT_SEGMENTS - 1: 1.0}
    weights = {}
    for key, segment_weight in segment_weights.items():
        if key == "hips":
            weights["hips"] = weights.get("hips", 0.0) + segment_weight
            continue
        for chain, chain_weight in ((first, 1.0 - chain_blend), (second, chain_blend)):
            name = chain_names(SKIRT_CHAINS[chain], SKIRT_SEGMENTS)[key]
            weights[name] = weights.get(name, 0.0) + segment_weight * chain_weight
    return {name: weight for name, weight in weights.items() if weight > 1e-4}


def _weight(skirt, armature, levels: SkirtLevels) -> None:
    skirt.vertex_groups.clear()
    groups = {}
    for vertex in skirt.data.vertices:
        for name, weight in _skirt_bones(vertex.co, levels).items():
            if name not in groups:
                groups[name] = skirt.vertex_groups.new(name=name)
            groups[name].add([vertex.index], weight, "REPLACE")
