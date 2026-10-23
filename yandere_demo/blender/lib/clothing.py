"""Uniforms fitted to a generated body: sailor top and collar, neckerchief, pleated skirt, shoes, proxy."""

import math
from dataclasses import dataclass

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import mesh_utils
from .materials import principled
from . import hair, pleats
from .rig import SLEEVE_BONES, add_bone, add_chain, bone_world_points

UNIFORM_COLORS = {
    "sailor_red": {"main": "#f7f5f8", "accent": "#c9505c", "accent_material": "M_UniformRed", "neckerchief": "#f39fae",
                   "shoe": "#6b4332"},
    "sailor_navy": {"main": "#f4f4f6", "accent": "#26304f", "accent_material": "M_UniformNavy", "neckerchief": "#b8243a",
                    "shoe": "#6b4332"},
    # Background students: Godot recolours M_UniformTint per instance, so its own colour is only the default.
    "sailor_tint": {"main": "#f4f4f6", "accent": "#34405e", "accent_material": "M_UniformTint", "neckerchief": "#c7454f",
                    "shoe": "#6b4332"},
}
# Tailored outfits as (material name, sRGB hex) per part.
TAILORED_UNIFORMS = {
    "gakuran": {"cloth": ("M_UniformTint", "#1f2433"), "trim": ("M_UniformButton", "#d9b45a"), "shoe": "#2a211d"},
    "suit": {"cloth": ("M_Suit", "#3b4048"), "trim": ("M_SuitButton", "#22252b"), "shirt": ("M_Shirt", "#f2f3f5"),
             "tie": ("M_Tie", "#7a2433"), "shoe": "#1d1a19"},
}

REFERENCE_HEIGHT = 1.58
SLEEVE_FRACTION = 0.52
PLEAT_COUNT = 20
PLEAT_DEPTH = pleats.PLEAT_DEPTH
HEM_FLARE = pleats.HEM_FLARE
# The femboy top sits slightly loose on the narrow frame.
TOP_EASE = 0.011
SLEEVE_PUFF = 0.012
# The top's hem rings stand this far outside the skirt's outer pleat faces.
TOP_HEM_EASE = 0.024
# Sleeve hems follow their spring bone this much at the cuff, fading out toward the shoulder.
SLEEVE_BONE_SHARE = 0.8
SLEEVE_BONE_START = 0.22

WHITE = 0
ACCENT = 1
NECKERCHIEF = 2
SHOE = 0
SOLE = 1


def _uniform_colors(uniform: str) -> dict:
    if uniform not in UNIFORM_COLORS:
        raise ValueError(f"unknown sailor uniform {uniform!r}; supported: {sorted(UNIFORM_COLORS)}")
    return UNIFORM_COLORS[uniform]


def _shoe_materials(params) -> list:
    colors = TAILORED_UNIFORMS.get(params.uniform) or _uniform_colors(params.uniform)
    return [principled("M_Shoe", colors["shoe"], 0.4), principled("M_ShoeSole", "#3a2620", 0.6)]


def _uniform_materials(params) -> list:
    colors = _uniform_colors(params.uniform)
    return [
        principled("M_UniformWhite", colors["main"], 0.7),
        principled(colors["accent_material"], colors["accent"], 0.65),
        principled("M_Neckerchief", colors["neckerchief"], 0.6),
    ]


@dataclass(frozen=True)
class UniformLevels:
    """Garment heights derived from the rig, so one uniform fits any character height."""

    waist_z: float
    hem_z: float
    top_hem_z: float
    top_cut_z: float
    scale: float

    @classmethod
    def from_armature(cls, armature) -> "UniformLevels":
        hips_head, _ = bone_world_points(armature, "hips")
        spine_head, _ = bone_world_points(armature, "spine")
        _, knee = bone_world_points(armature, "thigh.L")
        _, head_top = bone_world_points(armature, "head")
        scale = head_top.z / REFERENCE_HEIGHT
        return cls(
            waist_z=spine_head.z - 0.015 * scale,
            hem_z=knee.z + 0.036 * scale,
            top_hem_z=hips_head.z - 0.016 * scale,
            top_cut_z=spine_head.z + 0.060 * scale,
            scale=scale,
        )

    def skirt_fraction(self, z: float) -> float:
        return (self.waist_z - z) / (self.waist_z - self.hem_z)


class HemFit:
    """Where the top's hem rings may sit: just outside the pleated skirt (its drape profile plus pleat depth)."""

    def __init__(self, armature, params, pleat_depth: float, hem_flare: float):
        self.levels = UniformLevels.from_armature(armature)
        self.skirt = pleats.SkirtSurface(armature, params, pleat_depth, hem_flare)

    def radius(self, angle: float, z: float) -> float:
        return self.skirt.radius(angle, z)


def _ensure_outward(mesh_object, axis_point: Vector) -> None:
    outward = 0.0
    for polygon in mesh_object.data.polygons:
        radial = polygon.center - Vector((axis_point.x, axis_point.y, polygon.center.z))
        outward += polygon.normal.dot(radial)
    if outward < 0:
        mesh_object.data.flip_normals()


def build_top(body, params, armature, shape: HemFit) -> bpy.types.Object:
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
            return point.z < shape.levels.top_cut_z or point.z > neck_cut or front_neckline
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
            puff = SLEEVE_PUFF + 0.005 * math.sin(math.pi * min(1.0, fraction / SLEEVE_FRACTION))
            if vertex.is_boundary and fraction > SLEEVE_FRACTION * 0.7:
                vertex.co = start + axis * (end - start).length * SLEEVE_FRACTION + radial.normalized() * (radial.length + puff)
            else:
                vertex.co += vertex.normal * puff
            continue
        vertex.co += vertex.normal * TOP_EASE
    _extrude_hem(bm, shape)
    # bmesh element order after delete and extrude varies between runs; a canonical order keeps exports stable.
    bm.faces.index_update()
    ranked = sorted(bm.faces, key=lambda face: tuple(round(value, 5) for value in face.calc_center_median()))
    rank_by_index = {face.index: rank for rank, face in enumerate(ranked)}
    bm.faces.sort(key=lambda face: rank_by_index[face.index])
    bm.to_mesh(top.data)
    bm.free()
    top.data.update()
    _smooth_vertices(top, iterations=2)
    top.data.polygons.foreach_set("material_index", [WHITE] * len(top.data.polygons))
    return top


def _extrude_hem(bm, shape: HemFit) -> None:
    """Extend the torso's lower cut into clean horizontal rings that drape over the skirt waistband."""
    levels = shape.levels
    hem_edges = [edge for edge in bm.edges
                 if edge.is_boundary and all(vertex.co.z < levels.top_cut_z + 0.04 * levels.scale for vertex in edge.verts)]
    loop = {vertex for edge in hem_edges for vertex in edge.verts}
    radii = {}
    for vertex in loop:
        radii[vertex] = (math.atan2(vertex.co.y - 0.004, vertex.co.x), math.hypot(vertex.co.x, vertex.co.y - 0.004))
    ring_heights = [levels.top_cut_z - 0.025 * levels.scale, levels.waist_z,
                    (levels.waist_z + levels.top_hem_z) * 0.5, levels.top_hem_z]
    edges = hem_edges
    for z in ring_heights:
        result = bmesh.ops.extrude_edge_only(bm, edges=edges)
        new_vertices = [element for element in result["geom"] if isinstance(element, bmesh.types.BMVert)]
        edges = [element for element in result["geom"] if isinstance(element, bmesh.types.BMEdge)
                 and all(vertex in new_vertices for vertex in element.verts)]
        loosen = 1.0 + 0.16 * (levels.top_cut_z - z) / (levels.top_cut_z - levels.top_hem_z)
        sources = {vertex: next(edge.other_vert(vertex) for edge in vertex.link_edges if edge.other_vert(vertex) in radii)
                   for vertex in new_vertices}
        for vertex in new_vertices:
            angle, base_radius = radii[sources[vertex]]
            radius = max(base_radius * loosen, shape.radius(angle, z) + TOP_HEM_EASE * levels.scale)
            vertex.co = Vector((math.cos(angle) * radius, math.sin(angle) * radius + 0.004, z))
            radii[vertex] = (angle, base_radius)
    # recalc_face_normals is not reliable on an open shell (it can flip the whole top between runs);
    # orient each face away from the body's core instead.
    for face in bm.faces:
        center = face.calc_center_median()
        if face.normal.dot(_outward_from_core(center)) < 0:
            face.normal_flip()


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
    bands = [(0.0, 0.28, ACCENT), (0.28, 0.40, WHITE), (0.40, 0.56, ACCENT), (0.56, 0.68, WHITE), (0.68, 1.0, ACCENT)]
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
    vertices, faces, material_indices = mesh_utils.weld_geometry(vertices, faces, material_indices)
    cuffs = mesh_utils.mesh_from_geometry(f"{params.prefix}Cuffs", vertices, faces, _uniform_materials(params), material_indices)
    _ensure_outward_from_points(cuffs, [ring[0] for ring in _sleeve_rings(top, armature)])
    mesh_utils.add_modifier(cuffs, "SOLIDIFY", thickness=0.003, offset=0.0)
    mesh_utils.apply_modifiers(cuffs)
    return cuffs


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


def _outward_from_core(point: Vector) -> Vector:
    """Direction from a vertical core line (lowered a little, so shoulder tops count as outward) to `point`."""
    return point - Vector((0.0, 0.004, point.z - 0.1))


class _Surface:
    def __init__(self, mesh_object):
        bm = bmesh.new()
        bm.from_mesh(mesh_object.data)
        bm.transform(mesh_object.matrix_world)
        self.tree = BVHTree.FromBMesh(bm)
        bm.free()

    def place(self, point: Vector, offset: float) -> tuple:
        location, normal, _, distance = self.tree.find_nearest(point)
        if location is None:
            return point, Vector((0, -1, 0))
        # The BVH build is threaded, so equidistant faces (the mirror seam) can win in either order between
        # runs. Re-query the near band and break ties by position to keep exports reproducible.
        candidates = self.tree.find_nearest_range(point, distance + 1e-6)
        if candidates:
            location, normal, _, _ = min(candidates, key=lambda hit: (round(hit[3], 6), tuple(round(value, 6) for value in hit[0])))
        if normal.dot(_outward_from_core(location)) < 0:
            normal = -normal
        return location + normal * offset, normal

    def front(self, x: float, z: float, offset: float) -> tuple:
        """The first surface point seen from straight in front at (x, z), pushed out along its normal."""
        location, normal, _, _ = self.tree.ray_cast(Vector((x, -1.0, z)), Vector((0.0, 1.0, 0.0)))
        if location is None:
            return self.place(Vector((x, -0.3, z)), offset)
        if normal.y > 0.0:
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
    row_materials = [ACCENT, ACCENT, ACCENT, WHITE, ACCENT, WHITE, ACCENT, ACCENT]
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
    vertices, faces, material_indices = mesh_utils.weld_geometry(vertices, faces, material_indices)
    collar = mesh_utils.mesh_from_geometry(f"{params.prefix}Collar", vertices, faces, _uniform_materials(params), material_indices)
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


NECKERCHIEF_TAIL_ROOT_SHARE = 0.2


def build_neckerchief(top, collar, params, armature, tail_chains: bool = True) -> bpy.types.Object:
    """The knot, the V fill inside the collar and two tails; with `tail_chains` each tail hangs on its
    `neckerchief_<side>` chain, otherwise the tails ride on the chest."""
    surface = _Surface(top)
    v_point = Vector(collar["v_point"])
    knot_center, knot_normal = surface.place(v_point + Vector((0, 0, -0.012)), 0.012)
    parts = []
    vertex_bones = []
    vertices, faces = mesh_utils.ellipsoid(knot_center, Vector((0.019, 0.010, 0.012)), 14, 8)
    parts.append((vertices, faces, NECKERCHIEF))
    vertex_bones += [[(["chest"], 1.0)]] * len(vertices)
    for sign, length, spread in ((1.0, 0.115, 0.030), (-1.0, 0.100, 0.036)):
        points = []
        normals = []
        for step in range(7):
            fraction = step / 6
            guess = knot_center + Vector((sign * spread * fraction ** 1.2 + sign * 0.006, 0, -length * fraction - 0.008))
            placed, normal = surface.place(guess, 0.010 + 0.004 * (1 - fraction))
            points.append(placed)
            normals.append(normal)
        chain = (add_chain(armature, f"neckerchief_{'L' if sign > 0 else 'R'}", "chest", [points[0], points[3], points[6]])
                 if tail_chains else ["chest"])
        widths = [0.020, 0.030, 0.034, 0.036, 0.036, 0.032, 0.026]
        ribbon_vertices, ribbon_faces = _flat_ribbon(points, widths, normals, notch=0.012)
        parts.append((ribbon_vertices, ribbon_faces, NECKERCHIEF))
        for index in range(len(ribbon_vertices)):
            along = (index // 2) / (len(points) - 1)
            share = min(1.0, along / NECKERCHIEF_TAIL_ROOT_SHARE)
            vertex_bones.append([(["chest"], 1.0 - share), (chain, share)])
    fill = _v_fill(surface, collar, v_point)
    parts.append(fill)
    vertex_bones += [[(["chest"], 1.0)]] * len(fill[0])
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    neckerchief = mesh_utils.mesh_from_geometry(f"{params.prefix}Neckerchief", vertices, faces, _uniform_materials(params), material_indices)
    mesh_utils.weight_by_segments(neckerchief, armature, vertex_bones)
    _orient_away_from_body(neckerchief, armature)
    mesh_utils.add_modifier(neckerchief, "SOLIDIFY", thickness=0.002, offset=-1.0)
    mesh_utils.apply_modifiers(neckerchief)
    mesh_utils.parent_to_armature(neckerchief, armature)
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
    vertices, faces, material_indices = mesh_utils.weld_geometry(vertices, faces, material_indices)
    shoes = mesh_utils.mesh_from_geometry(f"{params.prefix}Shoes", vertices, faces, _shoe_materials(params), material_indices)
    mesh_utils.recalculate_normals(shoes)
    mesh_utils.add_modifier(shoes, "SUBSURF", levels=1, render_levels=1)
    mesh_utils.apply_modifiers(shoes)
    mesh_utils.assign_nearest_bone_weights(shoes, armature, ["foot.L", "toe.L", "foot.R", "toe.R", "shin.L", "shin.R"], blend=0.02)
    return shoes


def add_sleeve_bones(armature) -> list:
    """One bone per sleeve along the upper arm, from near the shoulder to the sleeve hem."""
    names = []
    for side, bone_name in zip((".L", ".R"), SLEEVE_BONES):
        start, end = bone_world_points(armature, f"upper_arm{side}")
        names.append(add_bone(armature, bone_name, start.lerp(end, 0.12), start.lerp(end, SLEEVE_FRACTION), f"upper_arm{side}"))
    return names


def _rebalance_top_weights(top, armature, levels: UniformLevels) -> None:
    """The hem rings move with the hips like the skirt waistband (so a forward lean does not push the top into
    the skirt), and the sleeves hand part of the upper arm's weight to their spring bones."""
    sleeves = [(side, sleeve) for side, sleeve in zip((".L", ".R"), SLEEVE_BONES) if sleeve in armature.data.bones]
    groups = {group.name: group for group in top.vertex_groups}
    for name in ["hips"] + [sleeve for _, sleeve in sleeves]:
        if name not in groups:
            groups[name] = top.vertex_groups.new(name=name)
    names = {group.index: group.name for group in top.vertex_groups}
    arms = {side: bone_world_points(armature, f"upper_arm{side}") for side in (".L", ".R")}
    hem_top = levels.top_cut_z + 0.03 * levels.scale
    for vertex in top.data.vertices:
        point = top.matrix_world @ vertex.co
        weights = {names[element.group]: element.weight for element in vertex.groups if element.weight > 1e-5}
        total = sum(weights.values())
        if total <= 0.0:
            continue
        weights = {name: weight / total for name, weight in weights.items()}
        hips_share = _smoothstep(hem_top, levels.waist_z, point.z)
        if hips_share > 0.0:
            weights = {name: weight * (1.0 - hips_share) for name, weight in weights.items()}
            weights["hips"] = weights.get("hips", 0.0) + hips_share
        for side, sleeve in sleeves:
            arm = f"upper_arm{side}"
            if weights.get(arm, 0.0) <= 0.0:
                continue
            start, end = arms[side]
            along = (point - start).dot(end - start) / (end - start).length_squared
            share = SLEEVE_BONE_SHARE * _smoothstep(SLEEVE_BONE_START, SLEEVE_FRACTION, along)
            moved = weights[arm] * share
            weights[arm] -= moved
            weights[sleeve] = weights.get(sleeve, 0.0) + moved
        for group in top.vertex_groups:
            group.remove([vertex.index])
        for name, weight in weights.items():
            if weight > 1e-5:
                groups[name].add([vertex.index], weight, "REPLACE")


def _smoothstep(edge_start: float, edge_end: float, value: float) -> float:
    fraction = min(1.0, max(0.0, (value - edge_start) / (edge_end - edge_start)))
    return fraction * fraction * (3.0 - 2.0 * fraction)


def build_sailor_uniform(body, params, armature, pleat_count: int = PLEAT_COUNT, neckerchief_chains: bool = True) -> dict:
    """Build `<prefix>Top` (top, collar, cuffs), `<prefix>Neckerchief`, `<prefix>Skirt` and `<prefix>Shoes`.

    The sleeves hand weight to `sleeve_*` bones when the rig has them.
    """
    _uniform_colors(params.uniform)
    shape = HemFit(armature, params, PLEAT_DEPTH, HEM_FLARE)
    skirt = pleats.build_pleated_skirt(armature, params, pleat_count, PLEAT_DEPTH, HEM_FLARE)
    top = build_top(body, params, armature, shape)
    collar = build_collar(top, params, armature)
    neckerchief = build_neckerchief(top, collar, params, armature, neckerchief_chains)
    cuffs = build_cuffs(top, params, armature)
    mesh_utils.add_modifier(top, "SOLIDIFY", thickness=0.0025, offset=-1.0)
    mesh_utils.apply_modifiers(top)
    # The feet now belong to the socks mesh, so the shoes are sized from it.
    shoes = build_shoes(bpy.data.objects[f"{params.prefix}Socks"], params, armature)
    for piece in (collar, cuffs):
        mesh_utils.transfer_weights(body, piece, armature)
    mesh_utils.parent_to_armature(top, armature)
    pin_point = _collar_pin_point(top, collar)
    top = mesh_utils.join_objects(f"{params.prefix}Top", [top, collar, cuffs])
    if "v_point" in top:
        del top["v_point"]
    _rebalance_top_weights(top, armature, shape.levels)
    for piece in (top, neckerchief, shoes):
        mesh_utils.shade_smooth(piece)
    return {"top": top, "neckerchief": neckerchief, "skirt": skirt, "shoes": shoes, "collar_pin": pin_point}


def _collar_pin_point(top, collar) -> tuple:
    """A spot on the left lapel, above the knot, for the collar pin (point and outward normal)."""
    surface = _Surface(top)
    v_point = Vector(collar["v_point"])
    return surface.place(v_point + Vector((0.040, 0.0, 0.050)), 0.0125)


ACCESSORY_BOW = 0
ACCESSORY_METAL = 1


def build_accessories(params, armature, collar_pin: tuple) -> bpy.types.Object:
    """`<prefix>Accessories`: the head and braid bows, a crossed hair clip under each head bow and a collar pin."""
    head_parts, braid_parts = hair.bow_parts(params, armature)
    clip_parts = []
    for origin, facing, up_hint in hair.head_bow_frames(armature):
        normal = facing.normalized()
        up = (up_hint - normal * normal.dot(up_hint)).normalized()
        across = up.cross(normal).normalized()
        center = origin - up * 0.020 + normal * 0.0015
        for tilt in (-32.0, 32.0):
            angle = math.radians(tilt)
            bar = (across * math.cos(angle) + up * math.sin(angle)).normalized()
            basis = Matrix((bar, normal.cross(bar).normalized(), normal)).transposed()
            vertices, faces = mesh_utils.ellipsoid(center, Vector((0.012, 0.0017, 0.0013)), 10, 6, basis)
            clip_parts.append((vertices, faces, ACCESSORY_METAL))
    pin_point, pin_normal = collar_pin
    pin_basis = _basis_facing(pin_normal)
    pin_vertices, pin_faces = mesh_utils.ellipsoid(Vector(pin_point), Vector((0.0062, 0.0062, 0.0018)), 16, 8, pin_basis)
    pin_parts = [(pin_vertices, pin_faces, ACCESSORY_METAL)]
    stone_vertices, stone_faces = mesh_utils.ellipsoid(Vector(pin_point) + Vector(pin_normal) * 0.0017,
                                                       Vector((0.0034, 0.0034, 0.0014)), 12, 6, pin_basis)
    pin_parts.append((stone_vertices, stone_faces, ACCESSORY_BOW))
    groups = [("head", head_parts + clip_parts), (hair.BRAID_BOW_BONE, braid_parts), ("chest", pin_parts)]
    parts = [part for _, group_parts in groups for part in group_parts]
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    materials = [principled("M_Bow", "#1d151b", 0.35), principled("M_HairClip", "#e8c372", 0.3)]
    accessories = mesh_utils.mesh_from_geometry(f"{params.prefix}Accessories", vertices, faces, materials, material_indices)
    mesh_utils.recalculate_normals(accessories)
    start = 0
    for bone_name, group_parts in groups:
        count = sum(len(part[0]) for part in group_parts)
        accessories.vertex_groups.new(name=bone_name).add(range(start, start + count), 1.0, "REPLACE")
        start += count
    mesh_utils.parent_to_armature(accessories, armature)
    return accessories


def _basis_facing(normal) -> Matrix:
    normal = Vector(normal).normalized()
    reference = Vector((0, 0, 1)) if abs(normal.z) < 0.9 else Vector((1, 0, 0))
    across = reference.cross(normal).normalized()
    return Matrix((across, normal.cross(across).normalized(), normal)).transposed()


def build_collision_proxy(armature, params, radius: float = 0.22, name: str | None = None) -> bpy.types.Object:
    """Capsule proxy (default name `<prefix>-col`) at an identity transform under the armature; Godot ignores proxy
    object transforms."""
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
    vertices, faces, _ = mesh_utils.weld_geometry(vertices, faces, [0] * len(faces))
    proxy = mesh_utils.mesh_from_geometry(name or f"{params.prefix}-col", vertices, faces,
                                          [principled("M_CollisionProxy", (0.5, 0.5, 0.5), 1.0)])
    mesh_utils.recalculate_normals(proxy)
    proxy.parent = armature
    proxy.matrix_parent_inverse.identity()
    proxy.matrix_basis.identity()
    proxy.hide_render = True
    return proxy


# ---------------------------------------------------------------------------------------------------
# Tailored outfits (gakuran, suit): shells cut from the skinned body, so they deform with the skin under them.

JACKET_EASE = 0.016
# The jacket hem stands this much further out than the waist, so it hangs over the trousers.
JACKET_HEM_FLARE = 0.012
TROUSER_EASE = 0.010
# Straight trouser legs: from the knee down the leg is at least this round.
TROUSER_LEG_RADIUS = 0.056
SLEEVE_END = 0.93
# The suit's V opening at the collar (half width) and how far above the waist it closes.
V_OPENING_HALF_WIDTH = 0.05
V_OPENING_BOTTOM = 0.075
SHELL_BONES = ("hips", "spine", "chest", "neck", "head", "shoulder.L", "shoulder.R", "upper_arm.L", "upper_arm.R",
               "forearm.L", "forearm.R", "hand.L", "hand.R", "thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R")
JACKET_BONES = ("hips", "spine", "chest", "shoulder.L", "shoulder.R", "upper_arm.L", "upper_arm.R", "forearm.L",
                "forearm.R", "thigh.L", "thigh.R")
TORSO_BONES = ("hips", "spine", "chest", "shoulder.L", "shoulder.R", "thigh.L", "thigh.R")
LEG_BONES = ("hips", "spine", "thigh.L", "thigh.R", "shin.L", "shin.R")


@dataclass(frozen=True)
class TailoredLevels:
    """Garment cut heights of a tailored outfit, derived from the rig."""

    neck_z: float
    waist_z: float
    jacket_hem_z: float
    trouser_hem_z: float
    scale: float

    @classmethod
    def from_armature(cls, armature) -> "TailoredLevels":
        levels = UniformLevels.from_armature(armature)
        neck, _ = bone_world_points(armature, "neck")
        hip_joint, _ = bone_world_points(armature, "thigh.L")
        ankle, _ = bone_world_points(armature, "foot.L")
        return cls(neck_z=neck.z, waist_z=levels.waist_z, jacket_hem_z=hip_joint.z - 0.01 * levels.scale,
                   trouser_hem_z=ankle.z + 0.035 * levels.scale, scale=levels.scale)


class _BoneSegments:
    def __init__(self, armature):
        self.segments = {name: bone_world_points(armature, name) for name in SHELL_BONES}

    def nearest(self, point: Vector) -> str:
        return min(self.segments, key=lambda name: mesh_utils.point_segment_distance(point, *self.segments[name]))

    def along(self, point: Vector, name: str) -> float:
        start, end = self.segments[name]
        return (point - start).dot(end - start) / (end - start).length_squared


def _tailored_materials(params, *parts: str) -> list:
    materials = []
    for part in parts:
        name, color = TAILORED_UNIFORMS[params.uniform][part]
        materials.append(principled(name, color, 0.35 if part == "trim" else 0.75))
    return materials


def _body_shell(body, armature, name: str, materials: list, keep, ease) -> bpy.types.Object:
    """A garment cut from the body: the vertices `keep(point, bone)` accepts (`bone` is the nearest body bone),
    pushed out along their normals by `ease(point, bone)` metres. It keeps the body's skin weights."""
    bones = _BoneSegments(armature)
    shell = body.copy()
    shell.data = body.data.copy()
    shell.name = name
    shell.data.name = name
    bpy.context.scene.collection.objects.link(shell)
    for modifier in list(shell.modifiers):
        shell.modifiers.remove(modifier)
    shell.data.materials.clear()
    for material in materials:
        shell.data.materials.append(material)
    mesh_utils.remove_vertices(shell, lambda point: not keep(point, bones.nearest(point)))
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    bm.normal_update()
    offsets = [vertex.normal * ease(vertex.co, bones.nearest(vertex.co)) for vertex in bm.verts]
    for vertex, offset in zip(bm.verts, offsets):
        vertex.co += offset
    bm.to_mesh(shell.data)
    bm.free()
    shell.data.polygons.foreach_set("material_index", [0] * len(shell.data.polygons))
    shell.data.update()
    return shell


def _snap_open_edges(shell, wanted, plane_point, plane_normal: Vector) -> None:
    """Flatten the jagged cut along the shell's open edges: boundary vertices `wanted(point)` accepts move onto the
    plane through `plane_point` with `plane_normal`."""
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    for vertex in bm.verts:
        if vertex.is_boundary and wanted(vertex.co):
            vertex.co -= plane_normal * (vertex.co - plane_point).dot(plane_normal)
    bm.to_mesh(shell.data)
    bm.free()
    shell.data.update()


def _finish_shell(shell, armature) -> None:
    mesh_utils.add_modifier(shell, "SOLIDIFY", thickness=0.0025, offset=-1.0)
    mesh_utils.apply_modifiers(shell)
    mesh_utils.shade_smooth(shell)
    mesh_utils.parent_to_armature(shell, armature)


def _build_jacket(body, params, armature, levels: TailoredLevels) -> bpy.types.Object:
    """A closed, long-sleeved jacket down to the hips, flaring a little over the trousers."""
    bones = _BoneSegments(armature)

    def keep(point: Vector, bone: str) -> bool:
        if bone not in JACKET_BONES or point.z < levels.jacket_hem_z:
            return False
        return not (bone.startswith("forearm") and bones.along(point, bone) > SLEEVE_END)

    def ease(point: Vector, bone: str) -> float:
        if bone not in TORSO_BONES:
            return JACKET_EASE * 0.8
        return JACKET_EASE + JACKET_HEM_FLARE * _smoothstep(levels.waist_z, levels.jacket_hem_z, point.z)

    materials = _tailored_materials(params, "cloth", "trim")
    jacket = _body_shell(body, armature, f"{params.prefix}Jacket", materials, keep, ease)
    _snap_open_edges(jacket, lambda point: point.z < levels.jacket_hem_z + 0.05 * levels.scale,
                     Vector((0.0, 0.0, levels.jacket_hem_z)), Vector((0.0, 0.0, 1.0)))
    _snap_open_edges(jacket, lambda point: point.z > levels.neck_z - 0.05 * levels.scale and abs(point.x) < 0.1,
                     Vector((0.0, 0.0, levels.neck_z - 0.01 * levels.scale)), Vector((0.0, 0.0, 1.0)))
    for side in (".L", ".R"):
        start, end = bones.segments[f"forearm{side}"]
        _snap_open_edges(jacket, lambda point, side=side: bones.nearest(point) in (f"forearm{side}", f"hand{side}"),
                         start.lerp(end, SLEEVE_END), (end - start).normalized())
    _finish_shell(jacket, armature)
    return jacket


def _build_trousers(body, params, armature, levels: TailoredLevels) -> bpy.types.Object:
    bones = _BoneSegments(armature)

    def keep(point: Vector, bone: str) -> bool:
        return bone in LEG_BONES and levels.trouser_hem_z <= point.z <= levels.waist_z

    trousers = _body_shell(body, armature, f"{params.prefix}Trousers", _tailored_materials(params, "cloth"), keep,
                           lambda point, bone: TROUSER_EASE)
    for vertex in trousers.data.vertices:
        bone = bones.nearest(vertex.co)
        if not bone.startswith("shin"):
            continue
        start, end = bones.segments[bone]
        axis = (end - start).normalized()
        center = start + axis * (vertex.co - start).dot(axis)
        radial = vertex.co - center
        straight = TROUSER_LEG_RADIUS * levels.scale * _smoothstep(0.0, 0.35, bones.along(vertex.co, bone))
        if 1e-6 < radial.length < straight:
            vertex.co = center + radial.normalized() * straight
    _snap_open_edges(trousers, lambda point: point.z < levels.trouser_hem_z + 0.05 * levels.scale,
                     Vector((0.0, 0.0, levels.trouser_hem_z)), Vector((0.0, 0.0, 1.0)))
    _snap_open_edges(trousers, lambda point: point.z > levels.waist_z - 0.05 * levels.scale,
                     Vector((0.0, 0.0, levels.waist_z)), Vector((0.0, 0.0, 1.0)))
    _finish_shell(trousers, armature)
    return trousers


def _stand_collar(body, armature, name: str, materials: list, height: float, ease: float,
                  front_gap_degrees: float = 0.0) -> bpy.types.Object:
    """A band collar standing around the base of the neck, open `front_gap_degrees` wide at the front."""
    neck, _ = bone_world_points(armature, "neck")
    base_z = neck.z + 0.004
    radii = [math.hypot(vertex.co.x, vertex.co.y - neck.y) for vertex in body.data.vertices
             if abs(vertex.co.z - base_z) < 0.012 and math.hypot(vertex.co.x, vertex.co.y - neck.y) < 0.07]
    radius = (sum(radii) / len(radii) if radii else 0.04) + ease
    gap = math.radians(front_gap_degrees)
    # Angles run round the back from one side of the front gap to the other (the front is at -90 degrees).
    angles = [-math.pi / 2 + gap / 2 + (2 * math.pi - gap) * index / 24 for index in range(25 if gap else 24)]
    rings = []
    for z, ring_radius in ((base_z - 0.015, radius + 0.006), (base_z, radius), (base_z + height, radius - 0.003)):
        rings.append([Vector((math.cos(angle) * ring_radius, neck.y + math.sin(angle) * ring_radius, z))
                      for angle in angles])
    vertices, faces = mesh_utils.loft(rings, closed=not gap)
    collar = mesh_utils.mesh_from_geometry(name, vertices, faces, materials, [0] * len(faces))
    _ensure_outward(collar, Vector((0.0, neck.y, 0.0)))
    mesh_utils.add_modifier(collar, "SOLIDIFY", thickness=0.003, offset=-1.0)
    mesh_utils.apply_modifiers(collar)
    mesh_utils.transfer_weights(body, collar, armature)
    return collar


def _buttons(surface: "_Surface", body, armature, name: str, materials: list, heights: list) -> bpy.types.Object:
    """Small round buttons down the centre front (material slot 1)."""
    parts = []
    for z in heights:
        point, normal = surface.front(0.0, z, 0.002)
        vertices, faces = mesh_utils.ellipsoid(point, Vector((0.0065, 0.0065, 0.0028)), 10, 6, _basis_facing(normal))
        parts.append((vertices, faces, 1))
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    buttons = mesh_utils.mesh_from_geometry(name, vertices, faces, materials, material_indices)
    mesh_utils.recalculate_normals(buttons)
    mesh_utils.transfer_weights(body, buttons, armature)
    return buttons


def _on_surface(surface: "_Surface", body, armature, name: str, materials: list, parts: list) -> bpy.types.Object:
    """A thin skinned mesh from (vertices, faces, material index) parts laid on a garment, facing away from the body."""
    vertices, faces, material_indices = mesh_utils.merge_geometry(parts)
    piece = mesh_utils.mesh_from_geometry(name, vertices, faces, materials, material_indices)
    _orient_away_from_body(piece, armature)
    mesh_utils.add_modifier(piece, "SOLIDIFY", thickness=0.0015, offset=-1.0)
    mesh_utils.apply_modifiers(piece)
    mesh_utils.transfer_weights(body, piece, armature)
    return piece


def _shirt_front(surface: "_Surface", levels: TailoredLevels) -> tuple:
    """The shirt seen through the jacket's V: a panel from the collar down to where the jacket closes."""
    bottom_z = levels.waist_z + V_OPENING_BOTTOM * levels.scale
    top_z = levels.neck_z + 0.004
    rows, columns = 8, 6
    vertices = []
    for row in range(rows + 1):
        fraction = row / rows
        z = bottom_z + (top_z - bottom_z) * fraction
        half_width = max(0.002, V_OPENING_HALF_WIDTH * levels.scale * fraction)
        for column in range(columns + 1):
            vertices.append(surface.front(-half_width + 2 * half_width * column / columns, z, 0.0025)[0])
    faces = [(row * (columns + 1) + column, row * (columns + 1) + column + 1, (row + 1) * (columns + 1) + column + 1,
              (row + 1) * (columns + 1) + column) for row in range(rows) for column in range(columns)]
    return vertices, faces, 0


def _tie(surface: "_Surface", levels: TailoredLevels) -> list:
    """A knot at the collar and a blade widening down the shirt front to a point, on top of the shirt panel."""
    knot_point, knot_normal = surface.front(0.0, levels.neck_z - 0.004, 0.011)
    knot_vertices, knot_faces = mesh_utils.ellipsoid(knot_point, Vector((0.011, 0.009, 0.006)), 10, 6,
                                                     _basis_facing(knot_normal))
    bottom_z = levels.waist_z + (V_OPENING_BOTTOM - 0.01) * levels.scale
    points, normals = [], []
    for step in range(9):
        z = knot_point.z - 0.004 - (knot_point.z - 0.004 - bottom_z) * step / 8
        point, normal = surface.front(0.0, z, 0.0065)
        points.append(point)
        normals.append(normal)
    widths = [0.022 + 0.03 * step / 8 for step in range(9)]
    blade_vertices, blade_faces = _flat_ribbon(points, widths, normals, notch=0.0)
    blade_vertices.append(points[-1] + Vector((0.0, -0.001, -0.02)))
    last = len(points) - 1
    blade_faces.append((last * 2, last * 2 + 1, len(blade_vertices) - 1))
    return [(knot_vertices, knot_faces, 1), (blade_vertices, blade_faces, 1)]


def build_gakuran(body, params, armature) -> dict:
    """Build `<prefix>Jacket` (with its stand collar and five gold buttons), `<prefix>Trousers` and `<prefix>Shoes`."""
    levels = TailoredLevels.from_armature(armature)
    materials = _tailored_materials(params, "cloth", "trim")
    jacket = _build_jacket(body, params, armature, levels)
    collar = _stand_collar(body, armature, f"{params.prefix}JacketCollar", materials, 0.032 * levels.scale, JACKET_EASE)
    top_button = levels.neck_z - 0.05 * levels.scale
    step = (top_button - levels.jacket_hem_z - 0.04 * levels.scale) / 4
    buttons = _buttons(_Surface(jacket), body, armature, f"{params.prefix}Buttons", materials,
                       [top_button - step * index for index in range(5)])
    jacket = mesh_utils.join_objects(f"{params.prefix}Jacket", [jacket, collar, buttons])
    return {"jacket": jacket} | _trousers_and_shoes(body, params, armature, levels)


def build_suit(body, params, armature) -> dict:
    """Build `<prefix>Jacket` (two buttons, a collar open at the front), `<prefix>Shirt` (the V of shirt front, its
    collar and the tie, laid over the jacket front), `<prefix>Trousers` and `<prefix>Shoes`."""
    levels = TailoredLevels.from_armature(armature)
    jacket_materials = _tailored_materials(params, "cloth", "trim")
    jacket = _build_jacket(body, params, armature, levels)
    surface = _Surface(jacket)
    button_z = levels.waist_z + V_OPENING_BOTTOM * levels.scale
    buttons = _buttons(surface, body, armature, f"{params.prefix}Buttons", jacket_materials,
                       [button_z - 0.012 * levels.scale, button_z - 0.09 * levels.scale])
    jacket_collar = _stand_collar(body, armature, f"{params.prefix}JacketCollar", jacket_materials, 0.03 * levels.scale,
                                  JACKET_EASE + 0.006, front_gap_degrees=80.0)
    shirt_materials = _tailored_materials(params, "shirt", "tie")
    shirt = _on_surface(surface, body, armature, f"{params.prefix}Shirt", shirt_materials,
                        [_shirt_front(surface, levels)] + _tie(surface, levels))
    shirt_collar = _stand_collar(body, armature, f"{params.prefix}ShirtCollar", shirt_materials, 0.026 * levels.scale,
                                 JACKET_EASE)
    jacket = mesh_utils.join_objects(f"{params.prefix}Jacket", [jacket, buttons, jacket_collar])
    shirt = mesh_utils.join_objects(f"{params.prefix}Shirt", [shirt, shirt_collar])
    return {"jacket": jacket, "shirt": shirt} | _trousers_and_shoes(body, params, armature, levels)


def _trousers_and_shoes(body, params, armature, levels: TailoredLevels) -> dict:
    trousers = _build_trousers(body, params, armature, levels)
    shoes = build_shoes(bpy.data.objects[f"{params.prefix}Socks"], params, armature)
    mesh_utils.shade_smooth(shoes)
    return {"trousers": trousers, "shoes": shoes}
