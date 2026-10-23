"""Mesh construction, modifier and skinning helpers shared by the character builders."""

import math

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def link_object(name: str, data) -> bpy.types.Object:
    mesh_object = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(mesh_object)
    return mesh_object


def mesh_from_geometry(
    name: str,
    vertices: list,
    faces: list,
    materials: list | None = None,
    material_indices: list | None = None,
    uvs: list | None = None,
    smooth: bool = True,
) -> bpy.types.Object:
    """Build an object from raw geometry. `uvs` holds one (u, v) per face corner, in face order."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(vertex) for vertex in vertices], [], [tuple(face) for face in faces])
    if uvs is not None:
        layer = mesh.uv_layers.new(name="UVMap")
        for loop_index, uv in enumerate(uvs):
            layer.data[loop_index].uv = uv
    for material in materials or []:
        mesh.materials.append(material)
    if material_indices is not None:
        mesh.polygons.foreach_set("material_index", material_indices)
    mesh.polygons.foreach_set("use_smooth", [smooth] * len(mesh.polygons))
    mesh.validate()
    mesh.update()
    return link_object(name, mesh)


def add_modifier(mesh_object, modifier_type: str, **settings):
    modifier = mesh_object.modifiers.new(modifier_type.title(), modifier_type)
    for key, value in settings.items():
        setattr(modifier, key, value)
    return modifier


def apply_modifiers(mesh_object) -> None:
    with ActiveSelection(mesh_object):
        for modifier in list(mesh_object.modifiers):
            if modifier.type == "ARMATURE":
                continue
            bpy.ops.object.modifier_apply(modifier=modifier.name)


class ActiveSelection:
    """Make one object active and solely selected for operators."""

    def __init__(self, *objects):
        self.objects = objects

    def __enter__(self):
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        for mesh_object in self.objects:
            mesh_object.select_set(True)
        bpy.context.view_layer.objects.active = self.objects[0]
        return self.objects[0]

    def __exit__(self, *exception):
        return False


def join_objects(name: str, objects: list) -> bpy.types.Object:
    with ActiveSelection(*objects):
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    joined.data.name = name
    return joined


def recalculate_normals(mesh_object) -> None:
    bm = bmesh.new()
    bm.from_mesh(mesh_object.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh_object.data)
    bm.free()
    mesh_object.data.update()


def mark_sharp_edges(mesh_object, flags: list) -> None:
    """Flag edges as sharp so toon shading shows crisp folds while the rest stays smooth."""
    mesh = mesh_object.data
    attribute = mesh.attributes.get("sharp_edge")
    if attribute is None:
        attribute_types = [item.identifier for item in bpy.types.Attribute.bl_rna.properties["data_type"].enum_items]
        domains = [item.identifier for item in bpy.types.Attribute.bl_rna.properties["domain"].enum_items]
        attribute = mesh.attributes.new("sharp_edge", next(item for item in attribute_types if item == "BOOLEAN"),
                                        next(item for item in domains if item == "EDGE"))
    attribute.data.foreach_set("value", flags)
    mesh.update()


def shade_smooth(mesh_object, smooth: bool = True) -> None:
    mesh_object.data.polygons.foreach_set("use_smooth", [smooth] * len(mesh_object.data.polygons))
    mesh_object.data.update()


def transform_vertices(mesh_object, function) -> None:
    for vertex in mesh_object.data.vertices:
        vertex.co = function(vertex.co.copy())
    mesh_object.data.update()


def loft(rings: list, closed: bool = True, cap_start: bool = False, cap_end: bool = False):
    """Return (vertices, faces) for consecutive rings of equal vertex count."""
    vertices = [point for ring in rings for point in ring]
    count = len(rings[0])
    faces = []
    columns = count if closed else count - 1
    for ring_index in range(len(rings) - 1):
        start = ring_index * count
        following = start + count
        for column in range(columns):
            next_column = (column + 1) % count
            faces.append((start + column, start + next_column, following + next_column, following + column))
    if cap_start and closed:
        faces.append(tuple(reversed(range(count))))
    if cap_end and closed:
        last = (len(rings) - 1) * count
        faces.append(tuple(range(last, last + count)))
    return vertices, faces


def ellipsoid(center: Vector, radii: Vector, segments: int = 16, rings: int = 10, rotation: Matrix | None = None):
    """Return (vertices, faces) of a UV ellipsoid."""
    rotation = rotation or Matrix.Identity(3)
    vertices = [center + rotation @ Vector((0, 0, radii.z))]
    for ring in range(1, rings):
        polar = math.pi * ring / rings
        for segment in range(segments):
            azimuth = 2 * math.pi * segment / segments
            local = Vector((
                radii.x * math.sin(polar) * math.cos(azimuth),
                radii.y * math.sin(polar) * math.sin(azimuth),
                radii.z * math.cos(polar),
            ))
            vertices.append(center + rotation @ local)
    vertices.append(center + rotation @ Vector((0, 0, -radii.z)))
    faces = []
    for segment in range(segments):
        faces.append((0, 1 + segment, 1 + (segment + 1) % segments))
    for ring in range(rings - 2):
        start = 1 + ring * segments
        for segment in range(segments):
            following = (segment + 1) % segments
            faces.append((start + segment, start + segments + segment, start + segments + following, start + following))
    bottom = len(vertices) - 1
    start = 1 + (rings - 2) * segments
    for segment in range(segments):
        faces.append((start + (segment + 1) % segments, start + segment, bottom))
    return vertices, faces


def weld_geometry(vertices: list, faces: list, material_indices: list, precision: int = 6):
    """Merge coincident vertices in a fixed order (bmesh remove_doubles is not order-stable) and drop
    faces that collapse to fewer than three corners."""
    welded: list = []
    index_by_key: dict = {}
    remap = []
    for vertex in vertices:
        key = tuple(round(coordinate, precision) for coordinate in vertex)
        if key not in index_by_key:
            index_by_key[key] = len(welded)
            welded.append(vertex)
        remap.append(index_by_key[key])
    kept_faces, kept_materials = [], []
    for face, material_index in zip(faces, material_indices):
        corners = []
        for index in face:
            mapped = remap[index]
            if mapped not in corners:
                corners.append(mapped)
        if len(corners) >= 3:
            kept_faces.append(tuple(corners))
            kept_materials.append(material_index)
    return welded, kept_faces, kept_materials


def merge_geometry(parts: list):
    """Concatenate (vertices, faces, material_index) parts into one vertex/face/material list."""
    vertices, faces, material_indices = [], [], []
    for part_vertices, part_faces, material_index in parts:
        offset = len(vertices)
        vertices.extend(part_vertices)
        for face in part_faces:
            faces.append(tuple(index + offset for index in face))
            material_indices.append(material_index)
    return vertices, faces, material_indices


def frame_along(points: list) -> list:
    """Parallel-transport frames (tangent, normal, binormal) along a polyline."""
    tangents = []
    for index in range(len(points)):
        previous = points[max(index - 1, 0)]
        following = points[min(index + 1, len(points) - 1)]
        tangents.append((following - previous).normalized())
    reference = Vector((0, 0, 1)) if abs(tangents[0].z) < 0.9 else Vector((1, 0, 0))
    normal = tangents[0].cross(reference).normalized()
    frames = []
    for tangent in tangents:
        normal = (normal - tangent * normal.dot(tangent)).normalized()
        frames.append((tangent, normal, tangent.cross(normal).normalized()))
    return frames


def build_bvh(mesh_object) -> BVHTree:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh_object.evaluated_get(depsgraph)
    bm = bmesh.new()
    bm.from_mesh(evaluated.to_mesh())
    bm.transform(mesh_object.matrix_world)
    evaluated.to_mesh_clear()
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def point_segment_distance(point: Vector, start: Vector, end: Vector) -> float:
    segment = end - start
    length_squared = segment.length_squared
    if length_squared < 1e-12:
        return (point - start).length
    fraction = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    return (point - (start + segment * fraction)).length


def parent_to_armature(mesh_object, armature) -> None:
    world = mesh_object.matrix_world.copy()
    mesh_object.parent = armature
    mesh_object.parent_type = "OBJECT"
    mesh_object.matrix_parent_inverse = armature.matrix_world.inverted()
    mesh_object.matrix_world = world
    if not any(modifier.type == "ARMATURE" for modifier in mesh_object.modifiers):
        modifier = mesh_object.modifiers.new("Armature", "ARMATURE")
        modifier.object = armature


def deform_bone_names(armature) -> list:
    return [bone.name for bone in armature.data.bones if bone.use_deform]


def assign_single_bone(mesh_object, armature, bone_name: str) -> None:
    mesh_object.vertex_groups.clear()
    group = mesh_object.vertex_groups.new(name=bone_name)
    group.add(range(len(mesh_object.data.vertices)), 1.0, "REPLACE")
    parent_to_armature(mesh_object, armature)


def assign_nearest_bone_weights(mesh_object, armature, bone_names: list | None = None, blend: float = 0.035) -> None:
    """Weight each vertex to its nearest bones by segment distance, blending bones within `blend` metres."""
    names = bone_names or deform_bone_names(armature)
    segments = {}
    for name in names:
        bone = armature.data.bones[name]
        segments[name] = (armature.matrix_world @ bone.head_local, armature.matrix_world @ bone.tail_local)
    mesh_object.vertex_groups.clear()
    groups = {name: mesh_object.vertex_groups.new(name=name) for name in names}
    matrix = mesh_object.matrix_world
    for vertex in mesh_object.data.vertices:
        point = matrix @ vertex.co
        distances = sorted((point_segment_distance(point, *segments[name]), name) for name in names)
        nearest = distances[0][0]
        weights = {}
        for distance, name in distances[:3]:
            excess = distance - nearest
            if excess > blend:
                break
            weights[name] = 1.0 - excess / blend if blend > 0 else 1.0
        total = sum(weights.values())
        for name, weight in weights.items():
            groups[name].add([vertex.index], weight / total, "REPLACE")
    parent_to_armature(mesh_object, armature)


def parent_with_automatic_weights(mesh_object, armature, fallback_bones: list | None = None) -> bool:
    """Heat-weight `mesh_object`; fall back to nearest-bone weights if any vertex is left unweighted."""
    parent_types = [item.identifier for item in bpy.ops.object.parent_set.get_rna_type().properties["type"].enum_items]
    automatic = next(identifier for identifier in parent_types if identifier.endswith("_AUTO"))
    mesh_object.vertex_groups.clear()
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    mesh_object.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.parent_set(type=automatic)
    if _all_vertices_weighted(mesh_object):
        return True
    for modifier in list(mesh_object.modifiers):
        if modifier.type == "ARMATURE":
            mesh_object.modifiers.remove(modifier)
    assign_nearest_bone_weights(mesh_object, armature, fallback_bones)
    return False


def _all_vertices_weighted(mesh_object) -> bool:
    if not mesh_object.vertex_groups:
        return False
    for vertex in mesh_object.data.vertices:
        if not any(group.weight > 1e-4 for group in vertex.groups):
            return False
    return True


def transfer_weights(source, target, armature) -> None:
    """Copy skin weights from the nearest `source` vertex onto each `target` vertex, then skin `target`."""
    tree = KDTree(len(source.data.vertices))
    for vertex in source.data.vertices:
        tree.insert(source.matrix_world @ vertex.co, vertex.index)
    tree.balance()
    names = {group.index: group.name for group in source.vertex_groups}
    target.vertex_groups.clear()
    groups = {}
    for vertex in target.data.vertices:
        _, nearest_index, _ = tree.find(target.matrix_world @ vertex.co)
        for element in source.data.vertices[nearest_index].groups:
            if element.weight <= 1e-4:
                continue
            name = names[element.group]
            if name not in groups:
                groups[name] = target.vertex_groups.new(name=name)
            groups[name].add([vertex.index], element.weight, "REPLACE")
    parent_to_armature(target, armature)


def limit_influences(mesh_object, limit: int = 4) -> None:
    """Keep the strongest `limit` bone weights per vertex (the glTF skin limit) and renormalise them."""
    groups = mesh_object.vertex_groups
    for vertex in mesh_object.data.vertices:
        elements = sorted(((element.weight, element.group) for element in vertex.groups if element.weight > 0), reverse=True)
        if len(elements) <= limit and abs(sum(weight for weight, _ in elements) - 1.0) < 1e-4:
            continue
        kept = elements[:limit]
        total = sum(weight for weight, _ in kept) or 1.0
        for weight, group_index in elements[limit:]:
            groups[group_index].remove([vertex.index])
        for weight, group_index in kept:
            groups[group_index].add([vertex.index], weight / total, "REPLACE")


def closest_point_on_segment(point: Vector, start: Vector, end: Vector) -> Vector:
    segment = end - start
    if segment.length_squared < 1e-12:
        return start.copy()
    fraction = max(0.0, min(1.0, (point - start).dot(segment) / segment.length_squared))
    return start + segment * fraction


def remove_vertices(mesh_object, predicate) -> None:
    bm = bmesh.new()
    bm.from_mesh(mesh_object.data)
    doomed = [vertex for vertex in bm.verts if predicate(vertex.co)]
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    bm.to_mesh(mesh_object.data)
    bm.free()
    mesh_object.data.update()


def merge_geometry_with_uvs(parts: list):
    """Like `merge_geometry`, for (vertices, faces, material_index, vertex_uvs) parts; returns per-corner UVs."""
    vertices, faces, material_indices, corner_uvs = [], [], [], []
    for part_vertices, part_faces, material_index, vertex_uvs in parts:
        offset = len(vertices)
        vertices.extend(part_vertices)
        for face in part_faces:
            faces.append(tuple(index + offset for index in face))
            material_indices.append(material_index)
            corner_uvs.extend(vertex_uvs[index] for index in face)
    return vertices, faces, material_indices, corner_uvs


def weight_by_segments(mesh_object, armature, vertex_bones: list, blend: float = 0.02) -> None:
    """Skin each vertex to its own candidate bones: `vertex_bones[i]` is a list of (bone names, share) pairs.

    Within each pair the share is split over the nearest of those bones by segment distance (blended over
    `blend` metres). Shares of a vertex are normalised.
    """
    segments = {}
    groups = {}
    matrix = mesh_object.matrix_world
    for vertex, candidates in zip(mesh_object.data.vertices, vertex_bones):
        point = matrix @ vertex.co
        weights: dict = {}
        for names, share in candidates:
            if share <= 1e-5:
                continue
            for name in names:
                if name not in segments:
                    bone = armature.data.bones[name]
                    segments[name] = (armature.matrix_world @ bone.head_local, armature.matrix_world @ bone.tail_local)
            distances = sorted((point_segment_distance(point, *segments[name]), name) for name in names)
            nearest = distances[0][0]
            local = {}
            for distance, name in distances[:3]:
                if distance - nearest > blend:
                    break
                local[name] = 1.0 - (distance - nearest) / blend if blend > 0 else 1.0
            local_total = sum(local.values())
            for name, weight in local.items():
                weights[name] = weights.get(name, 0.0) + share * weight / local_total
        total = sum(weights.values())
        for name, weight in weights.items():
            if name not in groups:
                groups[name] = mesh_object.vertex_groups.get(name) or mesh_object.vertex_groups.new(name=name)
            groups[name].add([vertex.index], weight / total, "REPLACE")


def material_center(mesh_object, material_name: str, keep=None) -> Vector:
    """Mean world position of the rest-pose polygon centres using `material_name` (and accepted by `keep(point)`)."""
    index = mesh_object.data.materials.find(material_name)
    centers = [mesh_object.matrix_world @ polygon.center for polygon in mesh_object.data.polygons
               if index >= 0 and polygon.material_index == index]
    centers = [point for point in centers if keep is None or keep(point)]
    if not centers:
        raise ValueError(f"{mesh_object.name} has no polygons using {material_name}")
    return sum(centers, Vector()) / len(centers)
