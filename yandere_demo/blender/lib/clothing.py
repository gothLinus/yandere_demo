"""Uniforms fitted to a generated body: sailor top and collar, neckerchief, pleated skirt, shoes, proxy."""

import math

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import mesh_utils
from .materials import principled
from .rig import SKIRT_BONES, SKIRT_SIDES, add_skirt_chains, bone_world_points

UNIFORM_COLORS = {
    "sailor_red": {"main": "#f7f5f8", "accent": "#c9505c", "neckerchief": "#f39fae", "trim": "#fbfbfc"},
    "sailor_navy": {"main": "#f4f4f6", "accent": "#26304f", "neckerchief": "#b8243a", "trim": "#fbfbfc"},
}

WAIST_Z = 0.995
HEM_Z = 0.505
TOP_HEM_Z = 0.915
TOP_CUT_Z = 1.07
SLEEVE_FRACTION = 0.52
PLEAT_COUNT = 24
LOWER_BODY_BONES = {"hips", "spine", "thigh.L", "thigh.R", "shin.L", "shin.R"}

WHITE = 0
RED = 1
NECKERCHIEF = 2
SHOE = 3
SOLE = 4


def _uniform_materials(params) -> list:
    colors = UNIFORM_COLORS.get(params.uniform, UNIFORM_COLORS["sailor_red"])
    return [
        principled("M_UniformWhite", colors["main"], 0.7),
        principled("M_UniformRed", colors["accent"], 0.65),
        principled("M_Neckerchief", colors["neckerchief"], 0.6),
        principled("M_Shoe", "#6b4332", 0.4),
        principled("M_ShoeSole", "#3a2620", 0.6),
    ]


def add_skirt_bones(armature, params) -> list:
    return add_skirt_chains(armature, WAIST_Z, HEM_Z, 0.11, 0.09)


class SkirtShape:
    """Radial skirt profile, fitted around the body's hips so no vertex pokes through."""

    def __init__(self, body):
        self.bands = {}
        names = {group.index: group.name for group in body.vertex_groups}
        for vertex in body.data.vertices:
            point = body.matrix_world @ vertex.co
            if point.z < HEM_Z - 0.05 or point.z > WAIST_Z + 0.05:
                continue
            dominant = max(vertex.groups, key=lambda element: element.weight, default=None)
            if dominant is None or names[dominant.group] not in LOWER_BODY_BONES:
                continue
            band = round(point.z / 0.02)
            sector = round(math.atan2(point.y - 0.004, point.x) / (2 * math.pi) * 36) % 36
            distance = math.hypot(point.x, point.y - 0.004)
            key = (band, sector)
            self.bands[key] = max(self.bands.get(key, 0.0), distance)

    def body_extent(self, angle: float, z: float) -> float:
        sector = round(angle / (2 * math.pi) * 36) % 36
        band = round(z / 0.02)
        extent = 0.0
        for band_offset in (-1, 0, 1):
            for sector_offset in (-1, 0, 1):
                extent = max(extent, self.bands.get((band + band_offset, (sector + sector_offset) % 36), 0.0))
        return extent

    def radius(self, angle: float, z: float) -> float:
        fraction = (WAIST_Z - z) / (WAIST_Z - HEM_Z)
        flare = max(0.0, fraction) ** 0.85
        radius_x = 0.090 + 0.125 * flare
        radius_y = 0.074 + 0.105 * flare
        profile = (radius_x * radius_y) / math.hypot(radius_y * math.cos(angle), radius_x * math.sin(angle))
        return max(profile, self.body_extent(angle, z) + 0.016)


def build_skirt(body, params, armature, shape: SkirtShape) -> bpy.types.Object:
    stripe_bands = [(0.032, 0.040), (0.050, 0.058)]
    heights = [WAIST_Z - (WAIST_Z - HEM_Z - 0.07) * index / 9 for index in range(10)]
    for low, high in stripe_bands:
        heights += [HEM_Z + high, HEM_Z + low]
    heights += [HEM_Z + 0.022, HEM_Z + 0.011, HEM_Z]
    heights = sorted(set(round(height, 4) for height in heights), reverse=True)

    samples_per_pleat = 4
    count = PLEAT_COUNT * samples_per_pleat
    rings = []
    for z in heights:
        fraction = (WAIST_Z - z) / (WAIST_Z - HEM_Z)
        amplitude = 0.002 + 0.010 * fraction
        ring = []
        for index in range(count):
            angle = 2 * math.pi * index / count
            phase = (index % samples_per_pleat) / samples_per_pleat
            sawtooth = phase * 2 - 1 if phase > 0 else 1.0
            radius = shape.radius(angle, z) + amplitude * (0.5 + 0.5 * sawtooth)
            ring.append(Vector((math.cos(angle) * radius, math.sin(angle) * radius + 0.004, z)))
        rings.append(ring)
    vertices, faces = mesh_utils.loft(rings)
    material_indices = []
    for ring_index in range(len(rings) - 1):
        middle = (heights[ring_index] + heights[ring_index + 1]) * 0.5 - HEM_Z
        is_stripe = any(low < middle < high for low, high in stripe_bands)
        material_indices += [WHITE if is_stripe else RED] * count
    skirt = mesh_utils.mesh_from_geometry(f"{params.prefix}Skirt", vertices, faces, _uniform_materials(params), material_indices)
    fold_edges = []
    for edge in skirt.data.edges:
        first, second = edge.vertices
        same_column = first % count == second % count
        fold_edges.append(same_column and (first % count) % samples_per_pleat in (0, 1))
    mesh_utils.mark_sharp_edges(skirt, fold_edges)
    mesh_utils.recalculate_normals(skirt)
    _ensure_outward(skirt, Vector((0, 0.004, 0)))
    mesh_utils.add_modifier(skirt, "SOLIDIFY", thickness=0.003, offset=-1.0, use_even_offset=True)
    mesh_utils.apply_modifiers(skirt)
    _skirt_weights(skirt, armature)
    return skirt


def _skirt_weights(skirt, armature) -> None:
    directions = {"front": -math.pi / 2, "back": math.pi / 2, "left": 0.0, "right": math.pi}
    skirt.vertex_groups.clear()
    groups = {name: skirt.vertex_groups.new(name=name) for name in ["hips", "thigh.L", "thigh.R"] + SKIRT_BONES}
    for vertex in skirt.data.vertices:
        point = vertex.co
        angle = math.atan2(point.y - 0.004, point.x)
        fraction = max(0.0, min(1.0, (WAIST_Z - point.z) / (WAIST_Z - HEM_Z)))
        hips_weight = max(0.0, 1.0 - fraction * 3.0)
        upper = max(0.0, 1.0 - abs(fraction - 0.4) / 0.4) if fraction < 0.8 else 0.0
        lower = max(0.0, (fraction - 0.4) / 0.6)
        side_weights = {}
        for side, direction in directions.items():
            difference = abs(math.atan2(math.sin(angle - direction), math.cos(angle - direction)))
            side_weights[side] = max(0.0, math.cos(difference)) ** 2
        side_total = sum(side_weights.values())
        weights = {"hips": hips_weight}
        # Part of the lower skirt follows the nearer thigh, so walking legs push the hem instead of piercing it.
        radius = math.hypot(point.x, point.y - 0.004)
        leg_share = min(1.0, abs(point.x) / max(radius * 0.6, 1e-6))
        weights["thigh.L" if point.x > 0 else "thigh.R"] = 0.35 * fraction ** 1.3 * leg_share
        for side in SKIRT_SIDES:
            share = side_weights[side] / side_total
            weights[f"skirt_{side}_01"] = upper * share
            weights[f"skirt_{side}_02"] = lower * share
        total = sum(weights.values())
        for name, weight in weights.items():
            if weight > 1e-4:
                groups[name].add([vertex.index], weight / total, "REPLACE")
    mesh_utils.parent_to_armature(skirt, armature)


def _ensure_outward(mesh_object, axis_point: Vector) -> None:
    outward = 0.0
    for polygon in mesh_object.data.polygons:
        radial = polygon.center - Vector((axis_point.x, axis_point.y, polygon.center.z))
        outward += polygon.normal.dot(radial)
    if outward < 0:
        mesh_object.data.flip_normals()


def build_top(body, params, armature, shape: SkirtShape) -> bpy.types.Object:
    top = body.copy()
    top.data = body.data.copy()
    top.name = f"{params.prefix}Top"
    top.data.name = top.name
    bpy.context.scene.collection.objects.link(top)
    top.data.materials.clear()
    for material in _uniform_materials(params):
        top.data.materials.append(material)

    segments = {
        name: bone_world_points(armature, name)
        for name in ("hips", "spine", "chest", "neck", "head", "shoulder.L", "shoulder.R", "upper_arm.L", "upper_arm.R",
                     "forearm.L", "forearm.R", "thigh.L", "thigh.R")
    }
    neck_cut = segments["neck"][0].z + 0.01

    def nearest(point: Vector) -> str:
        return min(segments, key=lambda name: mesh_utils.point_segment_distance(point, *segments[name]))

    def along(point: Vector, name: str) -> float:
        start, end = segments[name]
        axis = end - start
        return (point - start).dot(axis) / axis.length_squared

    def discard(point: Vector) -> bool:
        bone = nearest(point)
        if bone.startswith("upper_arm"):
            return along(point, bone) > SLEEVE_FRACTION
        if bone in ("hips", "spine", "chest") or bone.startswith("shoulder"):
            front_neckline = point.y < -0.02 and abs(point.x) < 0.055 and point.z > neck_cut - 0.03
            return point.z < TOP_CUT_Z or point.z > neck_cut or front_neckline
        return True

    mesh_utils.remove_vertices(top, discard)
    bm = bmesh.new()
    bm.from_mesh(top.data)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    for vertex in bm.verts:
        bone = nearest(vertex.co)
        if bone.startswith("upper_arm"):
            start, end = segments[bone]
            axis = (end - start).normalized()
            fraction = along(vertex.co, bone)
            radial = vertex.co - (start + axis * (vertex.co - start).dot(axis))
            puff = 0.010 + 0.006 * math.sin(math.pi * min(1.0, fraction / SLEEVE_FRACTION))
            if vertex.is_boundary and fraction > SLEEVE_FRACTION * 0.7:
                vertex.co = start + axis * (end - start).length * SLEEVE_FRACTION + radial.normalized() * (radial.length + puff)
            else:
                vertex.co += vertex.normal * puff
            continue
        vertex.co += vertex.normal * 0.008
    _extrude_hem(bm, shape)
    bm.to_mesh(top.data)
    bm.free()
    top.data.update()
    _smooth_vertices(top, iterations=2)
    top.data.polygons.foreach_set("material_index", [WHITE] * len(top.data.polygons))
    return top


def _extrude_hem(bm, shape: SkirtShape) -> None:
    """Extend the torso's lower cut into clean horizontal rings that drape over the skirt waistband."""
    hem_edges = [edge for edge in bm.edges if edge.is_boundary and all(vertex.co.z < TOP_CUT_Z + 0.04 for vertex in edge.verts)]
    loop = {vertex for edge in hem_edges for vertex in edge.verts}
    radii = {}
    for vertex in loop:
        radii[vertex] = (math.atan2(vertex.co.y - 0.004, vertex.co.x), math.hypot(vertex.co.x, vertex.co.y - 0.004))
    levels = [TOP_CUT_Z - 0.025, WAIST_Z, (WAIST_Z + TOP_HEM_Z) * 0.5, TOP_HEM_Z]
    edges = hem_edges
    for z in levels:
        result = bmesh.ops.extrude_edge_only(bm, edges=edges)
        new_vertices = [element for element in result["geom"] if isinstance(element, bmesh.types.BMVert)]
        edges = [element for element in result["geom"] if isinstance(element, bmesh.types.BMEdge)
                 and all(vertex in new_vertices for vertex in element.verts)]
        loosen = 1.0 + 0.16 * (TOP_CUT_Z - z) / (TOP_CUT_Z - TOP_HEM_Z)
        sources = {vertex: next(edge.other_vert(vertex) for edge in vertex.link_edges if edge.other_vert(vertex) in radii)
                   for vertex in new_vertices}
        for vertex in new_vertices:
            angle, base_radius = radii[sources[vertex]]
            radius = max(base_radius * loosen, shape.radius(angle, z) + 0.018)
            vertex.co = Vector((math.cos(angle) * radius, math.sin(angle) * radius + 0.004, z))
            radii[vertex] = (angle, base_radius)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def _smooth_vertices(mesh_object, iterations: int) -> None:
    modifier = mesh_utils.add_modifier(mesh_object, "SMOOTH", factor=0.5, iterations=iterations)
    modifier.name = "Smooth"
    for other in list(mesh_object.modifiers):
        if other.type == "ARMATURE":
            mesh_object.modifiers.remove(other)
    mesh_utils.apply_modifiers(mesh_object)


def _sleeve_rings(top, armature) -> list:
    rings = []
    for side in (".L", ".R"):
        start, end = bone_world_points(armature, f"upper_arm{side}")
        axis = (end - start).normalized()
        center = start + (end - start) * SLEEVE_FRACTION
        radii = []
        for vertex in top.data.vertices:
            offset = vertex.co - center
            if abs(offset.dot(axis)) < 0.012 and offset.length < 0.09:
                radii.append((offset - axis * offset.dot(axis)).length)
        radius = max(radii) if radii else 0.045
        rings.append((center, axis, radius, side))
    return rings


def build_cuffs(top, params, armature) -> list:
    bands = [(0.0, 0.28, RED), (0.28, 0.40, WHITE), (0.40, 0.56, RED), (0.56, 0.68, WHITE), (0.68, 1.0, RED)]
    cuff_width = 0.030
    parts = []
    for center, axis, radius, side in _sleeve_rings(top, armature):
        reference = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
        first = axis.cross(reference).normalized()
        second = axis.cross(first).normalized()
        rings = []
        heights = sorted({edge for band in bands for edge in band[:2]})
        for height in heights:
            ring_center = center - axis * cuff_width * (1.0 - height)
            ring = []
            for index in range(24):
                angle = 2 * math.pi * index / 24
                ring.append(ring_center + (first * math.cos(angle) + second * math.sin(angle)) * (radius + 0.004))
            rings.append(ring)
        vertices, faces = mesh_utils.loft(rings)
        material_indices = []
        for ring_index in range(len(rings) - 1):
            middle = (heights[ring_index] + heights[ring_index + 1]) * 0.5
            material = next(band[2] for band in bands if band[0] <= middle <= band[1])
            material_indices += [material] * 24
        for face, material in zip(faces, material_indices):
            parts.append(([vertices[index] for index in face], [(0, 1, 2, 3)], material))
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    cuffs = mesh_utils.mesh_from_geometry(f"{params.prefix}Cuffs", vertices, faces, _uniform_materials(params), material_indices)
    _weld(cuffs)
    _ensure_outward_from_points(cuffs, [ring[0] for ring in _sleeve_rings(top, armature)])
    mesh_utils.add_modifier(cuffs, "SOLIDIFY", thickness=0.003, offset=0.0)
    mesh_utils.apply_modifiers(cuffs)
    return cuffs


def _weld(mesh_object) -> None:
    bm = bmesh.new()
    bm.from_mesh(mesh_object.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(mesh_object.data)
    bm.free()
    mesh_object.data.update()


def _ensure_outward_from_points(mesh_object, centers: list) -> None:
    bm = bmesh.new()
    bm.from_mesh(mesh_object.data)
    for face in bm.faces:
        center = min(centers, key=lambda point: (point - face.calc_center_median()).length)
        if face.normal.dot(face.calc_center_median() - center) < 0:
            face.normal_flip()
    bm.to_mesh(mesh_object.data)
    bm.free()
    mesh_object.data.update()


class _Surface:
    def __init__(self, mesh_object):
        bm = bmesh.new()
        bm.from_mesh(mesh_object.data)
        bm.transform(mesh_object.matrix_world)
        self.tree = BVHTree.FromBMesh(bm)
        bm.free()

    def place(self, point: Vector, offset: float) -> tuple:
        location, normal, _, _ = self.tree.find_nearest(point)
        if location is None:
            return point, Vector((0, -1, 0))
        if normal.dot(point - location) < 0 and (point - location).length > 0.02:
            normal = -normal
        return location + normal * offset, normal


def _collar_keys(neck_base: Vector, v_point: Vector, shoulder: Vector, back_bottom_z: float) -> tuple:
    """Matching inner (neckline) and outer (collar edge) key points for the character's right half."""
    back_x = -0.09
    inner = [
        v_point,
        Vector((-0.030, neck_base.y - 0.050, neck_base.z - 0.040)),
        Vector((-0.050, neck_base.y - 0.004, neck_base.z + 0.004)),
        Vector((-0.045, neck_base.y + 0.025, neck_base.z + 0.006)),
        Vector((-0.030, neck_base.y + 0.045, neck_base.z + 0.006)),
        Vector((0.0, neck_base.y + 0.050, neck_base.z + 0.004)),
    ]
    outer = [
        v_point,
        Vector((-0.098, neck_base.y - 0.080, neck_base.z - 0.075)),
        Vector((shoulder.x + 0.004, shoulder.y, shoulder.z + 0.020)),
        Vector((back_x - 0.004, neck_base.y + 0.085, shoulder.z - 0.010)),
        Vector((back_x, neck_base.y + 0.085, back_bottom_z)),
        Vector((0.0, neck_base.y + 0.090, back_bottom_z)),
    ]
    return inner, outer


def _polyline(keys: list, counts: list) -> list:
    points = []
    for index in range(len(keys) - 1):
        for step in range(counts[index]):
            points.append(keys[index].lerp(keys[index + 1], step / counts[index]))
    points.append(keys[-1])
    return points


def build_collar(top, params, armature) -> bpy.types.Object:
    surface = _Surface(top)
    neck_base, _ = bone_world_points(armature, "neck")
    _, shoulder = bone_world_points(armature, "shoulder.R")
    chest_head, _ = bone_world_points(armature, "chest")
    v_point, _ = surface.place(Vector((0, -0.12, chest_head.z + 0.035)), 0.004)
    inner_keys, outer_keys = _collar_keys(neck_base, v_point, shoulder, chest_head.z - 0.075)
    counts = [8, 7, 6, 6, 7]
    inner_right = _polyline(inner_keys, counts)
    outer_right = _polyline(outer_keys, counts)
    mirror = Vector((-1, 1, 1))
    inner = inner_right + [point * mirror for point in reversed(inner_right[:-1])]
    outer = outer_right + [point * mirror for point in reversed(outer_right[:-1])]
    row_edges = [0.0, 0.22, 0.45, 0.64, 0.70, 0.78, 0.84, 0.92, 1.0]
    row_materials = [RED, RED, RED, WHITE, RED, WHITE, RED, RED]
    vertices = []
    for row in row_edges:
        for inner_point, outer_point in zip(inner, outer):
            guess = inner_point.lerp(outer_point, row)
            for _ in range(2):
                guess, _ = surface.place(guess, 0.0075)
            vertices.append(guess)
    columns = len(inner)
    faces = []
    material_indices = []
    for row in range(len(row_edges) - 1):
        for column in range(columns - 1):
            first = row * columns + column
            faces.append((first, first + 1, first + columns + 1, first + columns))
            material_indices.append(row_materials[row])
    collar = mesh_utils.mesh_from_geometry(f"{params.prefix}Collar", vertices, faces, _uniform_materials(params), material_indices)
    _weld(collar)
    _orient_away_from_body(collar, armature)
    mesh_utils.add_modifier(collar, "SOLIDIFY", thickness=0.0025, offset=1.0)
    mesh_utils.apply_modifiers(collar)
    collar["v_point"] = list(v_point)
    return collar


def _orient_away_from_body(mesh_object, armature) -> None:
    spine_points = [bone_world_points(armature, name) for name in ("hips", "spine", "chest", "neck")]
    bm = bmesh.new()
    bm.from_mesh(mesh_object.data)
    for face in bm.faces:
        center = face.calc_center_median()
        nearest_axis = min((mesh_utils.closest_point_on_segment(center, start, end) for start, end in spine_points),
                           key=lambda point: (point - center).length)
        if face.normal.dot(center - nearest_axis) < 0:
            face.normal_flip()
    bm.to_mesh(mesh_object.data)
    bm.free()
    mesh_object.data.update()


def build_neckerchief(top, collar, params, armature) -> bpy.types.Object:
    surface = _Surface(top)
    v_point = Vector(collar["v_point"])
    knot_center, knot_normal = surface.place(v_point + Vector((0, 0, -0.012)), 0.012)
    parts = []
    vertices, faces = mesh_utils.ellipsoid(knot_center, Vector((0.019, 0.010, 0.012)), 14, 8)
    parts.append((vertices, faces, NECKERCHIEF))
    for sign, length, spread in ((1.0, 0.115, 0.030), (-1.0, 0.100, 0.036)):
        points = []
        normals = []
        for step in range(7):
            fraction = step / 6
            guess = knot_center + Vector((sign * spread * fraction ** 1.2 + sign * 0.006, 0, -length * fraction - 0.008))
            placed, normal = surface.place(guess, 0.010 + 0.004 * (1 - fraction))
            points.append(placed)
            normals.append(normal)
        widths = [0.020, 0.030, 0.034, 0.036, 0.036, 0.032, 0.026]
        ribbon_vertices, ribbon_faces = _flat_ribbon(points, widths, normals, notch=0.012)
        parts.append((ribbon_vertices, ribbon_faces, NECKERCHIEF))
    fill = _v_fill(surface, collar, v_point)
    parts.append(fill)
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    neckerchief = mesh_utils.mesh_from_geometry(f"{params.prefix}Neckerchief", vertices, faces, _uniform_materials(params), material_indices)
    _orient_away_from_body(neckerchief, armature)
    mesh_utils.add_modifier(neckerchief, "SOLIDIFY", thickness=0.002, offset=-1.0)
    mesh_utils.apply_modifiers(neckerchief)
    return neckerchief


def _flat_ribbon(points: list, widths: list, normals: list, notch: float):
    vertices = []
    for index, point in enumerate(points):
        following = points[min(index + 1, len(points) - 1)]
        previous = points[max(index - 1, 0)]
        tangent = (following - previous).normalized()
        lateral = tangent.cross(normals[index]).normalized()
        left = point - lateral * widths[index] * 0.5
        right = point + lateral * widths[index] * 0.5
        if index == len(points) - 1:
            left += tangent * notch
            right += tangent * notch
        vertices += [left, right]
    faces = [(index * 2, index * 2 + 1, index * 2 + 3, index * 2 + 2) for index in range(len(points) - 1)]
    return vertices, faces


def _v_fill(surface: "_Surface", collar, v_point: Vector):
    """Neckerchief fabric visible inside the collar's V, from the knot up to the neckline."""
    top_z = v_point.z + 0.12
    rows = 6
    columns = 6
    vertices = []
    for row in range(rows + 1):
        fraction = row / rows
        z = v_point.z - 0.006 + (top_z - v_point.z) * fraction
        half_width = 0.006 + 0.05 * fraction
        for column in range(columns + 1):
            x = -half_width + 2 * half_width * column / columns
            placed, _ = surface.place(Vector((x, v_point.y - 0.02, z)), 0.0022)
            vertices.append(placed)
    faces = []
    for row in range(rows):
        for column in range(columns):
            first = row * (columns + 1) + column
            faces.append((first, first + 1, first + columns + 2, first + columns + 1))
    return vertices, faces, NECKERCHIEF


def build_shoes(body, params, armature) -> bpy.types.Object:
    parts = []
    for side, sign in ((".L", 1.0), (".R", -1.0)):
        foot_points = [body.matrix_world @ vertex.co for vertex in body.data.vertices
                       if (body.matrix_world @ vertex.co).z < 0.085 and (body.matrix_world @ vertex.co).x * sign > 0]
        minimum = Vector((min(point.x for point in foot_points), min(point.y for point in foot_points), 0.0))
        maximum = Vector((max(point.x for point in foot_points), max(point.y for point in foot_points), max(point.z for point in foot_points)))
        center_x = (minimum.x + maximum.x) * 0.5
        toe_y = minimum.y - 0.012
        heel_y = maximum.y + 0.010
        half_width = (maximum.x - minimum.x) * 0.5 + 0.010
        rings = []
        sections = 12
        for index in range(sections + 1):
            fraction = index / sections
            y = heel_y + (toe_y - heel_y) * fraction
            width_profile = 0.82 + 0.18 * math.sin(math.pi * min(1.0, fraction * 1.3)) if fraction < 0.85 else 0.95 - (fraction - 0.85) * 3.5
            height = 0.072 - 0.034 * fraction ** 0.9 if fraction > 0.2 else 0.072
            if fraction < 0.05 or fraction > 0.97:
                width_profile *= 0.75
                height *= 0.85
            ring = []
            for column in range(16):
                angle = 2 * math.pi * column / 16
                cosine, sine = math.cos(angle), math.sin(angle)
                x = center_x + half_width * width_profile * math.copysign(abs(cosine) ** 0.6, cosine)
                z = height * 0.5 + height * 0.5 * math.copysign(abs(sine) ** 0.75, sine)
                ring.append(Vector((x, y, max(0.0, z))))
            rings.append(ring)
        vertices, faces = mesh_utils.loft(rings, closed=True, cap_start=True, cap_end=True)
        material_indices = []
        for face in faces:
            lowest = max(vertices[index].z for index in face)
            material_indices.append(SOLE if lowest < 0.008 else SHOE)
        for face, material in zip(faces, material_indices):
            parts.append(([vertices[index] for index in face], [tuple(range(len(face)))], material))
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    shoes = mesh_utils.mesh_from_geometry(f"{params.prefix}Shoes", vertices, faces, _uniform_materials(params), material_indices)
    _weld(shoes)
    mesh_utils.recalculate_normals(shoes)
    mesh_utils.add_modifier(shoes, "SUBSURF", levels=1, render_levels=1)
    mesh_utils.apply_modifiers(shoes)
    mesh_utils.assign_nearest_bone_weights(shoes, armature, ["foot.L", "toe.L", "foot.R", "toe.R", "shin.L", "shin.R"], blend=0.02)
    return shoes


def build_sailor_uniform(body, params, armature) -> bpy.types.Object:
    shape = SkirtShape(body)
    skirt = build_skirt(body, params, armature, shape)
    top = build_top(body, params, armature, shape)
    collar = build_collar(top, params, armature)
    neckerchief = build_neckerchief(top, collar, params, armature)
    cuffs = build_cuffs(top, params, armature)
    mesh_utils.add_modifier(top, "SOLIDIFY", thickness=0.0025, offset=-1.0)
    mesh_utils.apply_modifiers(top)
    shoes = build_shoes(body, params, armature)
    for piece in (collar, neckerchief, cuffs):
        mesh_utils.transfer_weights(body, piece, armature)
    mesh_utils.parent_to_armature(top, armature)
    uniform = mesh_utils.join_objects(f"{params.prefix}Uniform", [top, skirt, collar, neckerchief, cuffs, shoes])
    if "v_point" in uniform:
        del uniform["v_point"]
    mesh_utils.shade_smooth(uniform)
    return uniform


def build_collision_proxy(armature, params, radius: float = 0.22) -> bpy.types.Object:
    """Capsule proxy at an identity transform under the armature; Godot ignores proxy object transforms."""
    height = params.height
    segments = 16
    rings = []
    for center_z, latitudes in ((radius, range(-4, 1)), (height - radius, range(0, 5))):
        for step in latitudes:
            latitude = math.pi / 2 * step / 4
            ring_radius = radius * math.cos(latitude)
            z = center_z + radius * math.sin(latitude)
            rings.append([Vector((ring_radius * math.cos(2 * math.pi * index / segments),
                                  ring_radius * math.sin(2 * math.pi * index / segments), z)) for index in range(segments)])
    vertices, faces = mesh_utils.loft(rings)
    proxy = mesh_utils.mesh_from_geometry(f"{params.prefix}-col", vertices, faces, [principled("M_CollisionProxy", (0.5, 0.5, 0.5), 1.0)])
    _weld(proxy)
    mesh_utils.recalculate_normals(proxy)
    proxy.parent = armature
    proxy.matrix_parent_inverse.identity()
    proxy.matrix_basis.identity()
    proxy.hide_render = True
    return proxy


def build_suit(*arguments, **keywords):
    raise NotImplementedError("build_suit is implemented for the teacher in Task 10")
