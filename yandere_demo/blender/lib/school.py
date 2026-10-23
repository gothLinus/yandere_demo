"""The school environment: building, courtyard, props, colliders and the gameplay marker empties.

Blender coordinates: the gate is the origin, +Y runs from the gate into the school (Godot -Z) and Z is up.
Objects named `<Name>-col` become trimesh static colliders on Godot import; every other mesh is decoration.
Markers are empties facing +Y (Godot -Z), the facing a character takes at them.
"""

import math
import os
import random

import bmesh
import bpy
import numpy
from mathutils import Matrix, Vector

from . import materials, mesh_utils

FLOOR_ONE = 0.0
FLOOR_TWO = 3.6
ROOF = 7.2
SLAB = 0.25
WALL = 0.2
DOOR_WIDTH = 1.2
DOOR_HEIGHT = 2.1
WINDOW_WIDTH = 2.0
WINDOW_SILL = 0.9
WINDOW_TOP = 2.4
SEAT_HEIGHT = 0.45
DESK_HEIGHT = 0.73

BUILDING_WEST = -10.5
BUILDING_EAST = 2.0
HALL_WALL_X = -2.0
BUILDING_SOUTH = 12.0
BUILDING_NORTH = 61.0
ROOM_INTERIOR_WEST = BUILDING_WEST + WALL / 2
ROOM_INTERIOR_EAST = HALL_WALL_X - WALL / 2
HALL_INTERIOR_WEST = HALL_WALL_X + WALL / 2
HALL_INTERIOR_EAST = BUILDING_EAST - WALL / 2

# Room bands along Y.
ENTRANCE = (12.0, 19.0)
CLASS_BAND = (19.0, 28.0)
SECOND_BAND = (28.0, 37.0)
CAFETERIA = (37.0, 47.0)
RESTROOM = (47.0, 52.0)
LIBRARY = (37.0, 52.0)
STAIRWELL = (52.0, 61.0)

# Two stacked flights in side-by-side lanes: A climbs north to floor 2, B climbs back south to the roof.
STEP_COUNT = 24
STEP_RISE = (FLOOR_TWO - FLOOR_ONE) / STEP_COUNT
STEP_RUN = 0.27
STAIR_LOW_Y = 53.0
STAIR_HIGH_Y = STAIR_LOW_Y + STEP_COUNT * STEP_RUN
STAIR_WIDTH = 2.0
LANE_A_X = -3.1
LANE_B_X = -5.3
STAIR_HOLE_A = (LANE_A_X - STAIR_WIDTH / 2, STAIR_LOW_Y, HALL_WALL_X, STAIR_HIGH_Y)
STAIR_HOLE_B = (LANE_B_X - STAIR_WIDTH / 2, STAIR_LOW_Y, LANE_B_X + STAIR_WIDTH / 2, STAIR_HIGH_Y)
DIVIDER_X = (LANE_A_X + LANE_B_X) / 2
PENTHOUSE = (LANE_B_X - STAIR_WIDTH / 2 - WALL, 50.8, DIVIDER_X + WALL / 2, STAIR_HIGH_Y + WALL)
PENTHOUSE_HEIGHT = 2.6

GROUNDS = (-14.0, 0.0, 28.0, 66.0)
GROUND_EXTENT = (-20.0, -10.0, 34.0, 72.0)
GATE_HALF_WIDTH = 2.0
FOUNTAIN_CENTER = Vector((12.0, 30.0, 0.0))
COURTYARD_DOOR_Y = 30.0
SHRINE_ROOM_CENTER = Vector((-70.0, -30.0, 0.0))

NORTH = 0.0
SOUTH = math.pi
EAST = -math.pi / 2
WEST = math.pi / 2

CHAIN_LINK_TILE = 0.3
BEVEL_WIDTH = 0.02

PALETTE = {
    "M_Wall": {"color": "#f3ecdc", "roughness": 0.9},
    "M_Floor_Wood": {"color": "#b5865a", "roughness": 0.7},
    "M_Floor_Tile": {"color": "#d8d5cb", "roughness": 0.6},
    "M_Locker": {"color": "#8ea7ba", "roughness": 0.45},
    "M_PropWood": {"color": "#c99c68", "roughness": 0.7},
    "M_PropMetal": {"color": "#a3abb3", "roughness": 0.4},
    "M_PropBoard": {"color": "#2f4b3d", "roughness": 0.8},
    "M_PropBooks": {"color": "#a2525b", "roughness": 0.8},
    "M_PropStone": {"color": "#c4beb3", "roughness": 0.85},
    "M_PropBark": {"color": "#6d4b3c", "roughness": 0.9},
    "M_PropVending": {"color": "#eaf6ff", "roughness": 0.3, "emission_strength": 2.0},
    "M_Grass": {"color": "#86b85e", "roughness": 0.95},
    "M_Path": {"color": "#cfc1a6", "roughness": 0.9},
    "M_Foliage": {"color": "#f5b7cd", "roughness": 0.8},
    "M_Water": {"color": "#79c3e3", "roughness": 0.1},
    "M_Glass": {"color": "#d4ecf7", "roughness": 0.05, "alpha": 0.25},
    "M_Sky": {"color": "#9ed4f3", "roughness": 1.0},
}
FENCE_MATERIAL = "M_Fence"


def build_school(chain_link_texture_path: str) -> bpy.types.Object:
    """Build every school object under one `School` root empty and return the root."""
    palette = {name: materials.principled(name, **settings) for name, settings in PALETTE.items()}
    write_chain_link_texture(chain_link_texture_path)
    palette[FENCE_MATERIAL] = materials.principled(FENCE_MATERIAL, "#ffffff", 0.5, chain_link_texture_path)
    root = bpy.data.objects.new("School", None)
    root.empty_display_type = _enum_identifier(bpy.types.Object, "empty_display_type", "PLAIN_AXES")
    bpy.context.scene.collection.objects.link(root)
    layout = Layout()
    builders = (
        _build_grounds, _build_floors, _build_walls, _build_stairs, _build_roof, _build_classrooms, _build_cafeteria,
        _build_restroom, _build_library, _build_club_room, _build_lockers, _build_courtyard, _build_rooftop_props,
        _build_shrine_room,
    )
    for builder in builders:
        for built in builder(palette, layout):
            built.parent = root
    for marker in _build_markers(layout):
        marker.parent = root
    return root


class Layout:
    """Placements shared between the props and the markers that stand at them."""

    def __init__(self):
        self.desk_anchors: dict = {}
        self.bench_anchors: dict = {}
        self.table_anchors: dict = {}
        self.table_centers: dict = {}
        self.hide_lockers: list = []
        self.shoe_lockers: dict = {}
        self.hall_windows: list = []


# Geometry ---------------------------------------------------------------------------------------------------------

class Assembly:
    """Geometry for one object, gathered part by part with a material name per face."""

    def __init__(self, name: str):
        self.name = name
        self.vertices: list = []
        self.faces: list = []
        self.face_materials: list = []
        self.material_names: list = []

    def add(self, vertices, faces, material_name: str, matrix: Matrix | None = None, face_material_names=None) -> None:
        offset = len(self.vertices)
        for vertex in vertices:
            point = Vector(vertex)
            self.vertices.append(matrix @ point if matrix is not None else point)
        for face_index, face in enumerate(faces):
            name = face_material_names[face_index] if face_material_names else material_name
            self.faces.append(tuple(corner + offset for corner in face))
            self.face_materials.append(self._material_index(name))

    def box(self, minimum, maximum, material_name: str, matrix: Matrix | None = None,
            top_material_name: str | None = None) -> None:
        vertices, faces = box_geometry(minimum, maximum)
        face_material_names = None
        if top_material_name is not None:
            face_material_names = [material_name] * len(faces)
            face_material_names[BOX_TOP_FACE] = top_material_name
        self.add(vertices, faces, material_name, matrix, face_material_names)

    def build(self, palette: dict, bevel_width: float = 0.0, closed: bool = True,
              uv_tile: float | None = None) -> bpy.types.Object:
        uvs = _planar_uvs(self.vertices, self.faces, uv_tile) if uv_tile else None
        built = mesh_utils.mesh_from_geometry(
            self.name, self.vertices, self.faces, [palette[name] for name in self.material_names],
            self.face_materials, uvs=uvs, smooth=False,
        )
        if closed:
            mesh_utils.recalculate_normals(built)
        if bevel_width > 0.0:
            _soften(built, bevel_width)
        return built

    def _material_index(self, name: str) -> int:
        if name not in self.material_names:
            self.material_names.append(name)
        return self.material_names.index(name)


BOX_TOP_FACE = 1


def box_geometry(minimum, maximum):
    x0, y0, z0 = minimum
    x1, y1, z1 = maximum
    vertices = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return vertices, faces


def cylinder_geometry(center, radius: float, bottom: float, top: float, segments: int = 24,
                      top_radius: float | None = None):
    top_radius = radius if top_radius is None else top_radius
    vertices = []
    for ring_radius, height in ((radius, bottom), (top_radius, top)):
        for segment in range(segments):
            angle = 2 * math.pi * segment / segments
            vertices.append((center[0] + ring_radius * math.cos(angle), center[1] + ring_radius * math.sin(angle), height))
    faces = [(segment, (segment + 1) % segments, segments + (segment + 1) % segments, segments + segment)
             for segment in range(segments)]
    faces.append(tuple(reversed(range(segments))))
    faces.append(tuple(range(segments, 2 * segments)))
    return vertices, faces


def ring_geometry(center, inner_radius: float, outer_radius: float, bottom: float, top: float, segments: int = 32):
    vertices = []
    for ring_radius, height in ((outer_radius, bottom), (outer_radius, top), (inner_radius, top), (inner_radius, bottom)):
        for segment in range(segments):
            angle = 2 * math.pi * segment / segments
            vertices.append((center[0] + ring_radius * math.cos(angle), center[1] + ring_radius * math.sin(angle), height))
    faces = []
    for band in range(4):
        start, following = band * segments, ((band + 1) % 4) * segments
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            faces.append((start + segment, start + next_segment, following + next_segment, following + segment))
    return vertices, faces


def ramp_geometry(half_width: float, length: float, rise: float):
    """A wedge climbing local +Y from height 0 at y = 0 to `rise` at y = `length`."""
    vertices = [(-half_width, 0, 0), (half_width, 0, 0), (-half_width, length, 0), (half_width, length, 0),
                (-half_width, length, rise), (half_width, length, rise)]
    faces = [(0, 1, 5, 4), (0, 2, 3, 1), (2, 4, 5, 3), (0, 4, 2), (1, 3, 5)]
    return vertices, faces


def tube_geometry(points: list, radii: list, segments: int = 10):
    rings = []
    for point, (_tangent, normal, binormal), radius in zip(points, mesh_utils.frame_along(points), radii):
        rings.append([point + (normal * math.cos(2 * math.pi * segment / segments)
                               + binormal * math.sin(2 * math.pi * segment / segments)) * radius
                      for segment in range(segments)])
    return mesh_utils.loft(rings, closed=True, cap_start=True, cap_end=True)


def placement(origin, yaw: float) -> Matrix:
    return Matrix.Translation(Vector(origin)) @ Matrix.Rotation(yaw, 4, "Z")


def facing(yaw: float) -> Vector:
    return Vector((-math.sin(yaw), math.cos(yaw), 0.0))


def side_of(yaw: float) -> Vector:
    return Vector((math.cos(yaw), math.sin(yaw), 0.0))


def subtract_rectangle(rectangles: list, hole: tuple) -> list:
    """Cut the axis-aligned `hole` (x0, y0, x1, y1) out of (x0, y0, x1, y1, *rest) rectangles."""
    hole_x0, hole_y0, hole_x1, hole_y1 = hole
    remaining = []
    for rectangle in rectangles:
        x0, y0, x1, y1, *rest = rectangle
        if hole_x1 <= x0 or hole_x0 >= x1 or hole_y1 <= y0 or hole_y0 >= y1:
            remaining.append(rectangle)
            continue
        cut_x0, cut_x1 = max(x0, hole_x0), min(x1, hole_x1)
        cut_y0, cut_y1 = max(y0, hole_y0), min(y1, hole_y1)
        pieces = [(x0, y0, x1, cut_y0), (x0, cut_y1, x1, y1), (x0, cut_y0, cut_x0, cut_y1), (cut_x1, cut_y0, x1, cut_y1)]
        remaining.extend((*piece, *rest) for piece in pieces if piece[2] - piece[0] > 1e-6 and piece[3] - piece[1] > 1e-6)
    return remaining


def _planar_uvs(vertices: list, faces: list, tile: float) -> list:
    """World-space planar UVs per face corner, projected along each face's dominant normal axis."""
    uvs = []
    for face in faces:
        corners = [vertices[index] for index in face]
        normal = (corners[1] - corners[0]).cross(corners[2] - corners[1])
        dominant = max(range(3), key=lambda axis: abs(normal[axis]))
        axes = [axis for axis in range(3) if axis != dominant]
        uvs.extend((corner[axes[0]] / tile, corner[axes[1]] / tile) for corner in corners)
    return uvs


def _soften(mesh_object, width: float) -> None:
    """Round the edges with a small bevel and shade the bevels smooth, keeping the flat faces crisp."""
    limit_method = _enum_identifier(bpy.types.BevelModifier, "limit_method", "ANGLE")
    mesh_utils.add_modifier(mesh_object, "BEVEL", width=width, segments=2, limit_method=limit_method,
                            angle_limit=math.radians(40))
    mesh_utils.apply_modifiers(mesh_object)
    mesh = bmesh.new()
    mesh.from_mesh(mesh_object.data)
    mesh.edges.ensure_lookup_table()
    flags = []
    for edge in mesh.edges:
        angle = edge.calc_face_angle(None)
        flags.append(angle is None or angle > math.radians(50))
    mesh.free()
    mesh_utils.mark_sharp_edges(mesh_object, flags)
    mesh_utils.shade_smooth(mesh_object)


def _enum_identifier(rna_type, property_name: str, wanted: str) -> str:
    identifiers = [item.identifier for item in rna_type.bl_rna.properties[property_name].enum_items]
    if wanted not in identifiers:
        raise ValueError(f"{property_name} has no {wanted}; available: {identifiers}")
    return wanted


def write_chain_link_texture(path: str, size: int = 128) -> None:
    """A tileable diamond wire mesh: grey wires on full alpha, transparent holes."""
    coordinates = (numpy.arange(size) + 0.5) / size
    u_grid, v_grid = numpy.meshgrid(coordinates, coordinates)
    diamonds_per_tile = 4
    wire_half_width = 0.07

    def wire(values):
        distance = numpy.abs((values * diamonds_per_tile) % 1.0 - 0.5)
        return numpy.clip((wire_half_width - distance) / 0.03 + 0.5, 0.0, 1.0)

    alpha = numpy.maximum(wire(u_grid + v_grid), wire(u_grid - v_grid))
    color = numpy.array(materials.hex_to_srgb("#8d969c"))
    pixels = numpy.concatenate([numpy.broadcast_to(color, (size, size, 3)), alpha[..., None]], axis=-1)
    name = os.path.basename(path)
    image = bpy.data.images.get(name) or bpy.data.images.new(name, size, size, alpha=True)
    image.pixels.foreach_set(pixels.astype(numpy.float32).ravel())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.filepath_raw = path
    formats = [item.identifier for item in bpy.types.Image.bl_rna.properties["file_format"].enum_items]
    image.file_format = next(identifier for identifier in formats if identifier.startswith("PNG"))
    image.save()


# Walls ------------------------------------------------------------------------------------------------------------

def wall(assembly: Assembly, axis: str, line: float, start: float, end: float, bottom: float, top: float,
         openings=(), material_name: str = "M_Wall") -> None:
    """An axis-aligned wall centred on `line`, running along `axis` ("x" or "y") from `start` to `end`.

    `openings` are (center, width, opening bottom, opening top) in absolute coordinates.
    """
    def segment(low: float, high: float, segment_bottom: float, segment_top: float) -> None:
        if high - low <= 1e-6 or segment_top - segment_bottom <= 1e-6:
            return
        if axis == "x":
            assembly.box((low, line - WALL / 2, segment_bottom), (high, line + WALL / 2, segment_top), material_name)
        else:
            assembly.box((line - WALL / 2, low, segment_bottom), (line + WALL / 2, high, segment_top), material_name)

    cursor = start
    for center, width, opening_bottom, opening_top in sorted(openings):
        segment(cursor, center - width / 2, bottom, top)
        segment(center - width / 2, center + width / 2, bottom, opening_bottom)
        segment(center - width / 2, center + width / 2, opening_top, top)
        cursor = center + width / 2
    segment(cursor, end, bottom, top)


def window_pane(windows: Assembly, axis: str, line: float, center: float, width: float, bottom: float,
                top: float) -> None:
    """Glass and a slim frame filling a wall opening."""
    frame = 0.05
    depth = 0.06

    def piece(low: float, high: float, piece_bottom: float, piece_top: float, half_depth: float, material: str):
        if axis == "x":
            windows.box((low, line - half_depth, piece_bottom), (high, line + half_depth, piece_top), material)
        else:
            windows.box((line - half_depth, low, piece_bottom), (line + half_depth, high, piece_top), material)

    low, high = center - width / 2, center + width / 2
    piece(low, high, bottom, bottom + frame, depth, "M_PropMetal")
    piece(low, high, top - frame, top, depth, "M_PropMetal")
    piece(low, low + frame, bottom, top, depth, "M_PropMetal")
    piece(high - frame, high, bottom, top, depth, "M_PropMetal")
    piece(center - frame / 2, center + frame / 2, bottom, top, depth, "M_PropMetal")
    piece(low + frame, high - frame, bottom + frame, top - frame, 0.005, "M_Glass")


def window_centers(start: float, end: float) -> list:
    count = max(1, int((end - start - 0.6) // (WINDOW_WIDTH + 0.6)))
    spacing = (end - start) / count
    return [start + spacing * (index + 0.5) for index in range(count)]


def door_leaf(walls: Assembly, windows: Assembly, x_center: float, y_start: float, floor: float) -> None:
    """A sliding classroom door with a window, standing across the hall wall line (x) from `y_start`."""
    thickness = 0.04
    window_low, window_high = 0.3, DOOR_WIDTH - 0.3
    window_bottom, window_top = 1.0, 1.75
    x0, x1 = x_center - thickness / 2, x_center + thickness / 2
    y0 = y_start
    walls.box((x0, y0, floor), (x1, y0 + DOOR_WIDTH, floor + window_bottom), "M_PropWood")
    walls.box((x0, y0, floor + window_top), (x1, y0 + DOOR_WIDTH, floor + DOOR_HEIGHT), "M_PropWood")
    walls.box((x0, y0, floor + window_bottom), (x1, y0 + window_low, floor + window_top), "M_PropWood")
    walls.box((x0, y0 + window_high, floor + window_bottom), (x1, y0 + DOOR_WIDTH, floor + window_top), "M_PropWood")
    windows.box((x_center - 0.005, y0 + window_low, floor + window_bottom),
                (x_center + 0.005, y0 + window_high, floor + window_top), "M_Glass")


def _build_walls(palette: dict, layout: Layout) -> list:
    built = []
    windows = Assembly("Windows")
    for floor_index, floor in enumerate((FLOOR_ONE, FLOOR_TWO)):
        walls = Assembly(f"Walls{floor_index + 1}-col")
        exterior_bottom = floor - 0.2 if floor_index == 0 else floor
        exterior_top = floor + (FLOOR_TWO - FLOOR_ONE)
        interior_top = exterior_top - SLAB
        sill, window_top = floor + WINDOW_SILL, floor + WINDOW_TOP

        def windows_on(axis: str, line: float, centers: list, record: bool = False) -> list:
            openings = []
            for center in centers:
                openings.append((center, WINDOW_WIDTH, sill, window_top))
                window_pane(windows, axis, line, center, WINDOW_WIDTH, sill, window_top)
                if record:
                    layout.hall_windows.append(Vector((line, center, floor)))
            return openings

        west_centers = []
        bands = [ENTRANCE, CLASS_BAND, SECOND_BAND]
        bands += [CAFETERIA, RESTROOM] if floor_index == 0 else [LIBRARY]
        bands.append(STAIRWELL)
        for band in bands:
            west_centers += window_centers(*band)
        wall(walls, "y", BUILDING_WEST, BUILDING_SOUTH - WALL / 2, BUILDING_NORTH + WALL / 2, exterior_bottom,
             exterior_top, windows_on("y", BUILDING_WEST, west_centers))

        east_centers = [14.5 + 3.0 * index for index in range(16)]
        east_openings = []
        if floor_index == 0:
            east_centers = [center for center in east_centers if abs(center - COURTYARD_DOOR_Y) > DOOR_WIDTH + WINDOW_WIDTH / 2 + 0.3]
            east_openings.append((COURTYARD_DOOR_Y, 2 * DOOR_WIDTH, floor, floor + 2.4))
        east_openings += windows_on("y", BUILDING_EAST, east_centers, record=True)
        wall(walls, "y", BUILDING_EAST, BUILDING_SOUTH - WALL / 2, BUILDING_NORTH + WALL / 2, exterior_bottom,
             exterior_top, east_openings)

        south_openings = windows_on("x", BUILDING_SOUTH, [-8.0, -4.5] + ([] if floor_index == 0 else [0.0]))
        if floor_index == 0:
            south_openings.append((0.0, 2 * DOOR_WIDTH, floor, floor + 2.4))
        wall(walls, "x", BUILDING_SOUTH, BUILDING_WEST, BUILDING_EAST, exterior_bottom, exterior_top, south_openings)
        wall(walls, "x", BUILDING_NORTH, BUILDING_WEST, BUILDING_EAST, exterior_bottom, exterior_top,
             windows_on("x", BUILDING_NORTH, [-8.5, 0.0]))

        cross_lines = [CLASS_BAND[0], SECOND_BAND[0], CAFETERIA[0], RESTROOM[0], STAIRWELL[0]]
        if floor_index == 1:
            cross_lines.remove(RESTROOM[0])
        for line in cross_lines:
            wall(walls, "x", line, BUILDING_WEST, HALL_WALL_X + WALL / 2, floor, interior_top)

        def door(center: float) -> tuple:
            return center, DOOR_WIDTH, floor, floor + DOOR_HEIGHT

        classroom_bands = [CLASS_BAND, SECOND_BAND]
        hall_openings = []
        for band in classroom_bands:
            back_center, front_center = band[0] + 1.2, band[1] - 1.2
            hall_openings += [door(back_center), door(front_center)]
            door_leaf(walls, windows, HALL_WALL_X, back_center - DOOR_WIDTH / 2, floor)
            door_leaf(walls, windows, HALL_WALL_X + WALL / 2 + 0.03, front_center + DOOR_WIDTH / 2 - 0.02, floor)
        if floor_index == 0:
            hall_openings += [door(38.5), door(45.5), door(48.2)]
        else:
            hall_openings += [door(38.6), door(50.6)]
        wall(walls, "y", HALL_WALL_X, CLASS_BAND[0], STAIRWELL[0] + WALL / 2, floor, interior_top, hall_openings)

        if floor_index == 1:
            hole_x0, hole_y0, hole_x1, hole_y1 = STAIR_HOLE_A
            walls.box((hole_x1, hole_y0, floor), (hole_x1 + 0.08, hole_y1, floor + 1.0), "M_Wall")
            walls.box((hole_x0, hole_y0 - 0.08, floor), (hole_x1 + 0.08, hole_y0, floor + 1.0), "M_Wall")
            walls.box((hole_x1 - 0.01, hole_y0 - 0.1, floor + 1.0), (hole_x1 + 0.09, hole_y1, floor + 1.06),
                      "M_PropMetal")
            walls.box((DIVIDER_X - WALL / 2, hole_y0, floor), (DIVIDER_X + WALL / 2, hole_y1, ROOF), "M_Wall")
        built.append(walls.build(palette))
    built.append(windows.build(palette))
    return built


# Floors, stairs and roof ------------------------------------------------------------------------------------------

def _floor_rectangles(floor_index: int) -> list:
    hall = (HALL_WALL_X, CLASS_BAND[0], BUILDING_EAST, BUILDING_NORTH, "M_Floor_Tile")
    entrance = (BUILDING_WEST, ENTRANCE[0], BUILDING_EAST, ENTRANCE[1], "M_Floor_Tile")
    rooms = [(BUILDING_WEST, CLASS_BAND[0], HALL_WALL_X, CLASS_BAND[1], "M_Floor_Wood"),
             (BUILDING_WEST, SECOND_BAND[0], HALL_WALL_X, SECOND_BAND[1], "M_Floor_Wood"),
             (BUILDING_WEST, STAIRWELL[0], HALL_WALL_X, STAIRWELL[1], "M_Floor_Tile")]
    if floor_index == 0:
        rooms += [(BUILDING_WEST, CAFETERIA[0], HALL_WALL_X, CAFETERIA[1], "M_Floor_Tile"),
                  (BUILDING_WEST, RESTROOM[0], HALL_WALL_X, RESTROOM[1], "M_Floor_Tile")]
    else:
        rooms.append((BUILDING_WEST, LIBRARY[0], HALL_WALL_X, LIBRARY[1], "M_Floor_Wood"))
    return [entrance, hall] + rooms


def _slab(assembly: Assembly, rectangles: list, top: float, thickness: float) -> None:
    for x0, y0, x1, y1, material_name in rectangles:
        assembly.box((x0, y0, top - thickness), (x1, y1, top), "M_Wall", top_material_name=material_name)


def _build_floors(palette: dict, layout: Layout) -> list:
    floor_one = Assembly("Floor1-col")
    _slab(floor_one, _floor_rectangles(0), FLOOR_ONE, 0.2)
    floor_two = Assembly("Floor2-col")
    _slab(floor_two, subtract_rectangle(_floor_rectangles(1), STAIR_HOLE_A), FLOOR_TWO, SLAB)
    return [floor_one.build(palette), floor_two.build(palette)]


def _build_stairs(palette: dict, layout: Layout) -> list:
    """Walkable ramps (the colliders) hidden inside solid decorative steps: the ramp runs through the inner
    corners, so agents and the player climb a smooth slope while the steps read as stairs."""
    ramps = Assembly("Stairs-col")
    steps = Assembly("StairSteps")
    flights = [placement((LANE_A_X, STAIR_LOW_Y, FLOOR_ONE), NORTH), placement((LANE_B_X, STAIR_HIGH_Y, FLOOR_TWO), SOUTH)]
    length = STEP_COUNT * STEP_RUN
    for matrix in flights:
        vertices, faces = ramp_geometry(STAIR_WIDTH / 2 - 0.02, length, FLOOR_TWO - FLOOR_ONE)
        ramps.add(vertices, faces, "M_Floor_Tile", matrix)
        for step in range(STEP_COUNT):
            steps.box((-STAIR_WIDTH / 2, step * STEP_RUN, 0.0), (STAIR_WIDTH / 2, (step + 1) * STEP_RUN, (step + 1) * STEP_RISE),
                      "M_Wall", matrix, top_material_name="M_Floor_Tile")
            steps.box((-STAIR_WIDTH / 2, step * STEP_RUN - 0.02, (step + 1) * STEP_RISE - 0.03),
                      (STAIR_WIDTH / 2, step * STEP_RUN + 0.03, (step + 1) * STEP_RISE + 0.005), "M_PropMetal", matrix)
    return [ramps.build(palette), steps.build(palette)]


def _build_roof(palette: dict, layout: Layout) -> list:
    roof = Assembly("Roof-col")
    footprint = [(BUILDING_WEST, BUILDING_SOUTH, BUILDING_EAST, BUILDING_NORTH, "M_Floor_Tile")]
    _slab(roof, subtract_rectangle(footprint, STAIR_HOLE_B), ROOF, SLAB)
    parapet = ROOF + 0.3
    roof.box((BUILDING_WEST - 0.1, BUILDING_SOUTH - 0.1, ROOF), (BUILDING_EAST + 0.1, BUILDING_SOUTH + 0.1, parapet), "M_Wall")
    roof.box((BUILDING_WEST - 0.1, BUILDING_NORTH - 0.1, ROOF), (BUILDING_EAST + 0.1, BUILDING_NORTH + 0.1, parapet), "M_Wall")
    roof.box((BUILDING_WEST - 0.1, BUILDING_SOUTH, ROOF), (BUILDING_WEST + 0.1, BUILDING_NORTH, parapet), "M_Wall")
    roof.box((BUILDING_EAST - 0.1, BUILDING_SOUTH, ROOF), (BUILDING_EAST + 0.1, BUILDING_NORTH, parapet), "M_Wall")
    x0, y0, x1, y1 = PENTHOUSE
    top = ROOF + PENTHOUSE_HEIGHT
    door_center = LANE_B_X
    wall(roof, "y", x0 + WALL / 2, y0, y1, ROOF, top)
    wall(roof, "y", x1 - WALL / 2, y0, y1, ROOF, top)
    wall(roof, "x", y1 - WALL / 2, x0, x1, ROOF, top)
    wall(roof, "x", y0 + WALL / 2, x0, x1, ROOF, top, [(door_center, DOOR_WIDTH, ROOF, ROOF + DOOR_HEIGHT)])
    roof.box((x0 - 0.1, y0 - 0.1, top), (x1 + 0.1, y1 + 0.1, top + 0.2), "M_Wall")
    return [roof.build(palette)]


# Grounds and courtyard --------------------------------------------------------------------------------------------

def _build_grounds(palette: dict, layout: Layout) -> list:
    ground = Assembly("Courtyard-col")
    footprint = (BUILDING_WEST, BUILDING_SOUTH, BUILDING_EAST, BUILDING_NORTH)
    for x0, y0, x1, y1 in subtract_rectangle([GROUND_EXTENT], footprint):
        ground.add([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)], [(0, 1, 2, 3)], "M_Grass")
    path_top = 0.01
    paths = [(-1.5, GROUND_EXTENT[1], 1.5, BUILDING_SOUTH), (1.5, 5.0, 13.0, 7.0), (11.0, 7.0, 13.0, 26.0),
             (BUILDING_EAST, COURTYARD_DOOR_Y - 1.2, 8.0, COURTYARD_DOOR_Y + 1.2), (16.0, 31.5, 18.0, 38.8)]
    for x0, y0, x1, y1 in paths:
        ground.box((x0, y0, -0.05), (x1, y1, path_top), "M_Path")
    vertices, faces = cylinder_geometry(FOUNTAIN_CENTER, 4.5, -0.05, path_top, segments=40)
    ground.add(vertices, faces, "M_Path")

    perimeter = Assembly("SchoolWall-col")
    west, south, east, north = GROUNDS
    height = 1.6
    wall(perimeter, "x", south, west, east, 0.0, height, [(0.0, 2 * GATE_HALF_WIDTH + 0.6, 0.0, height)], "M_Wall")
    wall(perimeter, "x", north, west, east, 0.0, height, (), "M_Wall")
    wall(perimeter, "y", west, south, north, 0.0, height, (), "M_Wall")
    wall(perimeter, "y", east, south, north, 0.0, height, (), "M_Wall")
    for side in (-1, 1):
        pillar_x = side * (GATE_HALF_WIDTH + 0.3)
        perimeter.box((pillar_x - 0.3, south - 0.3, 0.0), (pillar_x + 0.3, south + 0.3, 2.3), "M_PropStone")
        perimeter.box((pillar_x - 0.36, south - 0.36, 2.3), (pillar_x + 0.36, south + 0.36, 2.42), "M_PropStone")
    return [ground.build(palette, closed=False), perimeter.build(palette, BEVEL_WIDTH)]


def _bench(assembly: Assembly, matrix: Matrix) -> None:
    """A slatted park bench whose seat (0.4 deep, 1.6 long) is centred on the local origin, facing local +Y."""
    for slat in range(3):
        y0 = -0.2 + slat * 0.135
        assembly.box((-0.8, y0, SEAT_HEIGHT - 0.04), (0.8, y0 + 0.125, SEAT_HEIGHT), "M_PropWood", matrix)
    for slat in range(2):
        z0 = 0.6 + slat * 0.17
        assembly.box((-0.8, -0.27, z0), (0.8, -0.23, z0 + 0.12), "M_PropWood", matrix)
    for leg_x in (-0.68, 0.68):
        assembly.box((leg_x - 0.03, -0.18, 0.0), (leg_x + 0.03, 0.18, SEAT_HEIGHT - 0.04), "M_PropMetal", matrix)
        assembly.box((leg_x - 0.03, -0.29, 0.0), (leg_x + 0.03, -0.21, 0.95), "M_PropMetal", matrix)


def _bench_object(palette: dict, layout: Layout, name: str, seat_center, yaw: float) -> bpy.types.Object:
    assembly = Assembly(f"{name}-col")
    _bench(assembly, placement(seat_center, yaw))
    layout.bench_anchors[name] = (Vector(seat_center) + facing(yaw) * 0.4, yaw)
    return assembly.build(palette, BEVEL_WIDTH)


def _fountain(assembly: Assembly, center: Vector) -> None:
    for vertices, faces, material in (
        (*ring_geometry(center, 1.75, 2.0, 0.0, 0.5, 40), "M_PropStone"),
        (*ring_geometry(center, 1.95, 2.15, 0.0, 0.12, 40), "M_PropStone"),
        (*cylinder_geometry(center, 1.76, 0.0, 0.08, 40), "M_PropStone"),
        (*cylinder_geometry(center, 1.76, 0.08, 0.38, 40), "M_Water"),
        (*cylinder_geometry(center, 0.28, 0.0, 1.15, 16, top_radius=0.2), "M_PropStone"),
        (*ring_geometry(center, 0.58, 0.72, 1.1, 1.3, 24), "M_PropStone"),
        (*cylinder_geometry(center, 0.6, 1.1, 1.16, 24), "M_PropStone"),
        (*cylinder_geometry(center, 0.59, 1.16, 1.26, 24), "M_Water"),
        (*cylinder_geometry(center, 0.08, 1.26, 1.55, 12, top_radius=0.04), "M_PropStone"),
    ):
        assembly.add(vertices, faces, material)


def _cherry_tree(trunk: Assembly, foliage: Assembly, base: Vector, seed: int) -> None:
    generator = random.Random(seed)
    lean = Vector((generator.uniform(-0.25, 0.25), generator.uniform(-0.25, 0.25), 0.0))
    trunk_points = [base + Vector((0, 0, height)) + lean * (height / 2.4) ** 2 for height in (0.0, 0.8, 1.6, 2.4)]
    vertices, faces = tube_geometry(trunk_points, [0.3, 0.24, 0.2, 0.16])
    trunk.add(vertices, faces, "M_PropBark")
    canopy_center = trunk_points[-1] + Vector((0, 0, 1.1))
    for branch in range(4):
        angle = branch * math.pi / 2 + generator.uniform(-0.4, 0.4)
        direction = Vector((math.cos(angle), math.sin(angle), 0.0))
        start = trunk_points[-2].lerp(trunk_points[-1], 0.5)
        middle = start + direction * 0.7 + Vector((0, 0, 0.6))
        end = start + direction * 1.4 + Vector((0, 0, 1.0))
        vertices, faces = tube_geometry([start, middle, end], [0.12, 0.08, 0.04], segments=8)
        trunk.add(vertices, faces, "M_PropBark")
    for blob in range(9):
        angle = blob * 2 * math.pi / 8 + generator.uniform(-0.3, 0.3)
        reach = 0.0 if blob == 8 else generator.uniform(1.2, 1.7)
        blob_center = canopy_center + Vector((math.cos(angle) * reach, math.sin(angle) * reach,
                                              generator.uniform(-0.3, 0.4) + (0.5 if blob == 8 else 0.0)))
        radius = generator.uniform(1.0, 1.35)
        vertices, faces = mesh_utils.ellipsoid(blob_center, Vector((radius, radius, radius * 0.78)), 20, 12)
        bumped = []
        for vertex in vertices:
            offset = vertex - blob_center
            wobble = 1.0 + 0.08 * math.sin(offset.x * 5.1 + seed) * math.sin(offset.y * 4.3) + 0.05 * math.sin(offset.z * 6.7)
            bumped.append(blob_center + offset * wobble)
        foliage.add(bumped, faces, "M_Foliage")


def _vending_machine(assembly: Assembly, matrix: Matrix) -> None:
    """Front face at local y = 0 looking along local +Y, centred on x."""
    assembly.box((-0.475, -0.8, 0.0), (0.475, 0.0, 1.85), "M_PropMetal", matrix)
    assembly.box((-0.4, 0.0, 0.95), (0.4, 0.025, 1.72), "M_PropVending", matrix)
    assembly.box((-0.4, 0.0, 0.82), (0.4, 0.02, 0.9), "M_PropBoard", matrix)
    assembly.box((-0.34, 0.0, 0.14), (0.34, 0.03, 0.34), "M_PropBoard", matrix)
    assembly.box((0.18, 0.0, 0.48), (0.34, 0.03, 0.72), "M_PropBoard", matrix)


VENDING_COURTYARD = (Vector((BUILDING_EAST + WALL / 2 + 0.82, 37.0, 0.0)), EAST)
VENDING_CAFETERIA = (Vector((-9.72, CAFETERIA[0] + WALL / 2 + 0.82, 0.0)), NORTH)
CHERRY_TREES = [Vector((17.0, 42.0, 0.0)), Vector((5.5, 18.0, 0.0)), Vector((20.0, 15.0, 0.0)), Vector((6.5, 47.0, 0.0))]
COURTYARD_BENCHES = {
    "Bench_01": (Vector((12.0, 35.4, 0.0)), SOUTH),
    "Bench_02": (Vector((6.6, 26.0, 0.0)), EAST),
    "Bench_03": (Vector((19.5, 22.5, 0.0)), WEST),
}
ROOFTOP_BENCH = ("Bench_04", Vector((-1.4, 42.0, ROOF)), EAST)


def _build_courtyard(palette: dict, layout: Layout) -> list:
    built = []
    fountain = Assembly("Fountain-col")
    _fountain(fountain, FOUNTAIN_CENTER)
    built.append(fountain.build(palette, 0.015))
    for name, (seat_center, yaw) in COURTYARD_BENCHES.items():
        built.append(_bench_object(palette, layout, name, seat_center, yaw))
    for index, base in enumerate(CHERRY_TREES, start=1):
        trunk = Assembly(f"CherryTrunk_{index:02d}-col")
        foliage = Assembly(f"CherryFoliage_{index:02d}")
        _cherry_tree(trunk, foliage, base, seed=index * 7)
        for part in (trunk.build(palette), foliage.build(palette)):
            mesh_utils.shade_smooth(part)
            built.append(part)
    for index, (origin, yaw) in enumerate((VENDING_COURTYARD, VENDING_CAFETERIA), start=1):
        machine = Assembly(f"VendingMachine_{index:02d}-col")
        _vending_machine(machine, placement(origin, yaw))
        built.append(machine.build(palette, BEVEL_WIDTH))
    return built


def _build_rooftop_props(palette: dict, layout: Layout) -> list:
    name, seat_center, yaw = ROOFTOP_BENCH
    built = [_bench_object(palette, layout, name, seat_center, yaw)]
    tank = Assembly("WaterTank-col")
    tank_center = Vector((-8.6, 57.0, ROOF))
    for leg_x in (-0.7, 0.7):
        for leg_y in (-0.7, 0.7):
            tank.box((tank_center.x + leg_x - 0.06, tank_center.y + leg_y - 0.06, ROOF),
                     (tank_center.x + leg_x + 0.06, tank_center.y + leg_y + 0.06, ROOF + 0.8), "M_PropMetal")
    tank.box((tank_center.x - 0.9, tank_center.y - 0.9, ROOF + 0.8), (tank_center.x + 0.9, tank_center.y + 0.9, ROOF + 0.9),
             "M_PropMetal")
    for vertices, faces in (cylinder_geometry(tank_center, 1.0, ROOF + 0.9, ROOF + 2.7, 28),
                            cylinder_geometry(tank_center, 1.0, ROOF + 2.7, ROOF + 3.0, 28, top_radius=0.25)):
        tank.add(vertices, faces, "M_PropMetal")
    built.append(tank.build(palette, BEVEL_WIDTH))

    fence = Assembly("RoofFence-col")
    posts = Assembly("RoofFencePosts")
    bottom, top = ROOF + 0.3, ROOF + 2.3
    sides = [("x", BUILDING_SOUTH, BUILDING_WEST, BUILDING_EAST), ("x", BUILDING_NORTH, BUILDING_WEST, BUILDING_EAST),
             ("y", BUILDING_WEST, BUILDING_SOUTH, BUILDING_NORTH), ("y", BUILDING_EAST, BUILDING_SOUTH, BUILDING_NORTH)]
    for axis, line, start, end in sides:
        if axis == "x":
            fence.box((start, line - 0.01, bottom), (end, line + 0.01, top), FENCE_MATERIAL)
        else:
            fence.box((line - 0.01, start, bottom), (line + 0.01, end, top), FENCE_MATERIAL)
        count = int(round((end - start) / 2.5))
        for index in range(count + 1):
            along = start + (end - start) * index / count
            center = (along, line) if axis == "x" else (line, along)
            vertices, faces = cylinder_geometry(center, 0.04, bottom, top + 0.05, 10)
            posts.add(vertices, faces, "M_PropMetal")
        if axis == "x":
            posts.box((start, line - 0.03, top - 0.03), (end, line + 0.03, top + 0.03), "M_PropMetal")
        else:
            posts.box((line - 0.03, start, top - 0.03), (line + 0.03, end, top + 0.03), "M_PropMetal")
    built.append(fence.build(palette, uv_tile=CHAIN_LINK_TILE))
    built.append(posts.build(palette))
    return built


# Rooms ------------------------------------------------------------------------------------------------------------

DESK_COLUMNS_X = (-7.85, -6.25, -4.65)
DESK_ROW_OFFSETS = (2.6, 4.2, 5.8)


def _desk_and_chair(assembly: Assembly, anchor: Vector, yaw: float) -> None:
    """A school desk ahead of the anchor and a chair whose seat front edge is 0.2 m behind it."""
    matrix = placement(anchor, yaw)
    assembly.box((-0.325, 0.2, DESK_HEIGHT - 0.03), (0.325, 0.65, DESK_HEIGHT), "M_PropWood", matrix)
    assembly.box((-0.3, 0.25, DESK_HEIGHT - 0.14), (0.3, 0.62, DESK_HEIGHT - 0.12), "M_PropMetal", matrix)
    for leg_x in (-0.3, 0.3):
        for leg_y in (0.23, 0.62):
            assembly.box((leg_x - 0.02, leg_y - 0.02, 0.0), (leg_x + 0.02, leg_y + 0.02, DESK_HEIGHT - 0.03), "M_PropMetal", matrix)
    _chair(assembly, matrix)


def _chair(assembly: Assembly, matrix: Matrix) -> None:
    """Seat surface at 0.45 m spanning 0.2-0.6 m behind the local origin."""
    assembly.box((-0.2, -0.6, SEAT_HEIGHT - 0.03), (0.2, -0.2, SEAT_HEIGHT), "M_PropWood", matrix)
    assembly.box((-0.2, -0.64, 0.62), (0.2, -0.6, 0.86), "M_PropWood", matrix)
    for leg_x in (-0.18, 0.18):
        for leg_y in (-0.58, -0.22):
            assembly.box((leg_x - 0.015, leg_y - 0.015, 0.0), (leg_x + 0.015, leg_y + 0.015, SEAT_HEIGHT - 0.03),
                         "M_PropMetal", matrix)
        assembly.box((leg_x - 0.015, -0.635, SEAT_HEIGHT), (leg_x + 0.015, -0.605, 0.86), "M_PropMetal", matrix)


def _classroom(assembly: Assembly, band: tuple, floor: float) -> list:
    anchors = []
    for row_offset in DESK_ROW_OFFSETS:
        for column_x in DESK_COLUMNS_X:
            anchor = Vector((column_x, band[0] + row_offset, floor))
            _desk_and_chair(assembly, anchor, NORTH)
            anchors.append(anchor)
    center_x = (ROOM_INTERIOR_WEST + ROOM_INTERIOR_EAST) / 2
    front = band[1] - WALL / 2
    assembly.box((center_x - 2.5, front - 0.03, floor + 0.9), (center_x + 2.5, front, floor + 2.1), "M_PropBoard")
    assembly.box((center_x - 2.5, front - 0.09, floor + 0.86), (center_x + 2.5, front, floor + 0.9), "M_PropWood")
    assembly.box((center_x - 0.4, front - 1.25, floor), (center_x + 0.4, front - 0.75, floor + 1.05), "M_PropWood")
    return anchors


def _build_classrooms(palette: dict, layout: Layout) -> list:
    built = []
    for name, band, floor in (("Desks_1A", CLASS_BAND, FLOOR_ONE), ("Desks_1B", SECOND_BAND, FLOOR_ONE),
                              ("Desks_2B", CLASS_BAND, FLOOR_TWO)):
        assembly = Assembly(f"{name}-col")
        layout.desk_anchors[name] = _classroom(assembly, band, floor)
        built.append(assembly.build(palette, 0.01))
    return built


def _table(assembly: Assembly, center: Vector, size_x: float, size_y: float, height: float = DESK_HEIGHT) -> None:
    x0, x1 = center.x - size_x / 2, center.x + size_x / 2
    y0, y1 = center.y - size_y / 2, center.y + size_y / 2
    assembly.box((x0, y0, center.z + height - 0.04), (x1, y1, center.z + height), "M_PropWood")
    for leg_x in (x0 + 0.08, x1 - 0.08):
        for leg_y in (y0 + 0.08, y1 - 0.08):
            assembly.box((leg_x - 0.03, leg_y - 0.03, center.z), (leg_x + 0.03, leg_y + 0.03, center.z + height - 0.04),
                         "M_PropMetal")


def _seated_table(assembly: Assembly, layout: Layout, key: str, center: Vector, size_x: float, size_y: float,
                  chairs: list) -> None:
    """A table with chairs. `chairs` holds (offset along the table edge, yaw) per chair: each chair faces the table and
    its anchor sits 0.2 m off the table edge."""
    _table(assembly, center, size_x, size_y)
    anchors = []
    for along, yaw in chairs:
        toward = facing(yaw)
        half_depth = size_y / 2 if abs(toward.y) > 0.5 else size_x / 2
        anchor = center - toward * (half_depth + 0.2) + side_of(yaw) * along
        anchor.z = center.z
        _chair(assembly, placement(anchor, yaw))
        anchors.append((anchor, yaw))
    layout.table_anchors[key] = anchors
    layout.table_centers[key] = center


def _build_cafeteria(palette: dict, layout: Layout) -> list:
    assembly = Assembly("Cafeteria-col")
    for table_x in (-7.6, -4.5):
        for table_y in (40.2, 43.2):
            _table(assembly, Vector((table_x, table_y, FLOOR_ONE)), 1.8, 0.8)
            for side in (-1, 1):
                for along in (-0.6, 0.0, 0.6):
                    vertices, faces = cylinder_geometry((table_x + along, table_y + side * 0.65), 0.17, 0.0, SEAT_HEIGHT, 16)
                    assembly.add(vertices, faces, "M_PropWood")
    counter_y0 = CAFETERIA[1] - WALL / 2 - 0.7
    assembly.box((-10.0, counter_y0, 0.0), (-5.0, CAFETERIA[1] - WALL / 2, 0.86), "M_PropMetal")
    assembly.box((-10.05, counter_y0 - 0.05, 0.86), (-4.95, CAFETERIA[1] - WALL / 2, 0.9), "M_PropWood")
    return [assembly.build(palette, 0.015)]


MIRROR_CENTERS_X = (-6.8, -5.3, -3.8)


def _build_restroom(palette: dict, layout: Layout) -> list:
    assembly = Assembly("Restroom-col")
    back = RESTROOM[1] - WALL / 2
    assembly.box((-7.6, back - 0.55, 0.0), (-3.0, back, 0.85), "M_PropStone")
    for mirror_x in MIRROR_CENTERS_X:
        assembly.box((mirror_x - 0.22, back - 0.45, 0.8), (mirror_x + 0.22, back - 0.12, 0.86), "M_PropMetal")
        assembly.box((mirror_x - 0.5, back - 0.03, 1.1), (mirror_x + 0.5, back, 1.9), "M_PropMetal")
        assembly.box((mirror_x - 0.45, back - 0.035, 1.15), (mirror_x + 0.45, back - 0.03, 1.85), "M_Sky")
    stall_front = ROOM_INTERIOR_WEST + 1.9
    for partition_y in (48.7, 50.3):
        assembly.box((ROOM_INTERIOR_WEST, partition_y - 0.03, 0.1), (stall_front, partition_y + 0.03, 2.0), "M_Wall")
    wall(assembly, "y", stall_front, RESTROOM[0] + WALL / 2, back, 0.1, 2.0,
         [(47.9, 0.7, 0.1, 2.0), (49.5, 0.7, 0.1, 2.0), (51.1, 0.7, 0.1, 2.0)])
    return [assembly.build(palette, 0.01)]


def _bookshelf(assembly: Assembly, x0: float, y0: float, x1: float, y1: float, floor: float, height: float,
               generator: random.Random) -> None:
    """An open shelf unit filled with books; it may face both sides of its long axis."""
    along_x = (x1 - x0) > (y1 - y0)
    assembly.box((x0, y0, floor), (x1, y1, floor + 0.08), "M_PropWood")
    shelf_count = 4
    for shelf in range(1, shelf_count + 1):
        level = floor + 0.08 + shelf * (height - 0.08) / shelf_count
        assembly.box((x0, y0, level - 0.025), (x1, y1, level), "M_PropWood")
    if along_x:
        end_panels = [(x0, y0, x0 + 0.03, y1), (x1 - 0.03, y0, x1, y1)]
    else:
        end_panels = [(x0, y0, x1, y0 + 0.03), (x0, y1 - 0.03, x1, y1)]
    for panel_x0, panel_y0, panel_x1, panel_y1 in end_panels:
        assembly.box((panel_x0, panel_y0, floor), (panel_x1, panel_y1, floor + height), "M_PropWood")
    length = (x1 - x0) if along_x else (y1 - y0)
    for shelf in range(shelf_count):
        base = floor + 0.08 + shelf * (height - 0.08) / shelf_count
        cursor = 0.05
        while cursor < length - 0.1:
            thickness = generator.uniform(0.03, 0.06)
            book_height = generator.uniform(0.18, 0.28)
            material = "M_PropBooks" if generator.random() < 0.6 else "M_PropBoard"
            if along_x:
                assembly.box((x0 + cursor, y0 + 0.04, base), (x0 + cursor + thickness, y1 - 0.04, base + book_height), material)
            else:
                assembly.box((x0 + 0.04, y0 + cursor, base), (x1 - 0.04, y0 + cursor + thickness, base + book_height), material)
            cursor += thickness + 0.004
            if generator.random() < 0.06:
                cursor += 0.12


LIBRARY_TABLES = {"LibraryTable_1": Vector((-4.4, 46.5, FLOOR_TWO)), "LibraryTable_2": Vector((-4.4, 49.6, FLOOR_TWO))}
CLUB_TABLE = Vector((-6.25, 32.5, FLOOR_TWO))


def _build_library(palette: dict, layout: Layout) -> list:
    assembly = Assembly("Library-col")
    generator = random.Random(11)
    _bookshelf(assembly, ROOM_INTERIOR_WEST, LIBRARY[0] + 0.6, ROOM_INTERIOR_WEST + 0.4, LIBRARY[1] - 0.6, FLOOR_TWO, 2.0, generator)
    for shelf_y in (40.0, 43.0):
        _bookshelf(assembly, -9.2, shelf_y - 0.25, -5.8, shelf_y + 0.25, FLOOR_TWO, 1.8, generator)
    for key, center in LIBRARY_TABLES.items():
        _seated_table(assembly, layout, key, center, 0.9, 1.6, [(-0.4, EAST), (0.4, EAST), (-0.4, WEST), (0.4, WEST)])
    return [assembly.build(palette)]


def _build_club_room(palette: dict, layout: Layout) -> list:
    assembly = Assembly("ClubRoom-col")
    _seated_table(assembly, layout, "ClubTable", CLUB_TABLE, 3.0, 1.4,
                  [(-0.75, NORTH), (0.75, NORTH), (-0.75, SOUTH), (0.75, SOUTH)])
    assembly.box((ROOM_INTERIOR_WEST, 29.0, FLOOR_TWO), (ROOM_INTERIOR_WEST + 0.5, 36.0, FLOOR_TWO + 1.8), "M_PropWood")
    front = SECOND_BAND[1] - WALL / 2
    assembly.box((-8.25, front - 0.03, FLOOR_TWO + 0.9), (-4.25, front, FLOOR_TWO + 2.0), "M_PropBoard")
    return [assembly.build(palette, 0.01)]


HALL_LOCKER_BANKS = [(23.5, FLOOR_ONE), (32.5, FLOOR_ONE), (42.0, FLOOR_ONE),
                     (23.5, FLOOR_TWO), (32.5, FLOOR_TWO), (44.6, FLOOR_TWO)]
HALL_LOCKER_DEPTH = 0.45
LOCKERS_PER_BANK = 6
HIDE_LOCKER_INDEX = 3
SHOE_ROWS_X = (-8.5, -5.5)
SHOE_ROW_Y = (13.6, 17.4)
SHOE_COLUMN_WIDTH = 0.38
SHOE_LEVELS = (0.1, 0.47, 0.84, 1.21, 1.58)
STASH_CUBBY = (1, 3)
TARGET_CUBBY = (0, 6)


def _build_lockers(palette: dict, layout: Layout) -> list:
    lockers = Assembly("Locker-col")
    face_x = HALL_INTERIOR_WEST + HALL_LOCKER_DEPTH
    for bank_center, floor in HALL_LOCKER_BANKS:
        start = bank_center - LOCKERS_PER_BANK * 0.5 / 2
        for index in range(LOCKERS_PER_BANK):
            y0 = start + index * 0.5
            lockers.box((HALL_INTERIOR_WEST, y0 + 0.005, floor), (face_x, y0 + 0.495, floor + 1.85), "M_Locker")
            lockers.box((face_x, y0 + 0.38, floor + 0.95), (face_x + 0.025, y0 + 0.42, floor + 1.1), "M_PropMetal")
            for slit in range(3):
                slit_z = floor + 1.55 + slit * 0.06
                lockers.box((face_x, y0 + 0.12, slit_z), (face_x + 0.006, y0 + 0.36, slit_z + 0.02), "M_PropBoard")
            if index == HIDE_LOCKER_INDEX:
                layout.hide_lockers.append(Vector((face_x + 0.45, y0 + 0.25, floor)))

    shoe = Assembly("ShoeLockers-col")
    y0, y1 = SHOE_ROW_Y
    depth = 0.4
    columns = int(round((y1 - y0) / SHOE_COLUMN_WIDTH))
    for row_index, center_x in enumerate(SHOE_ROWS_X):
        x0, x1 = center_x - depth, center_x + depth
        shoe.box((x0, y0, 0.0), (x1, y1, SHOE_LEVELS[0]), "M_PropWood")
        shoe.box((x0 - 0.02, y0 - 0.02, SHOE_LEVELS[-1]), (x1 + 0.02, y1 + 0.02, SHOE_LEVELS[-1] + 0.03), "M_PropWood")
        shoe.box((center_x - 0.01, y0, SHOE_LEVELS[0]), (center_x + 0.01, y1, SHOE_LEVELS[-1]), "M_PropWood")
        for level in SHOE_LEVELS[1:-1]:
            shoe.box((x0, y0, level - 0.02), (x1, y1, level), "M_PropWood")
        for column in range(columns + 1):
            divider_y = y0 + column * SHOE_COLUMN_WIDTH
            shoe.box((x0, divider_y - 0.01, SHOE_LEVELS[0]), (x1, divider_y + 0.01, SHOE_LEVELS[-1]), "M_PropWood")
        for key, (cubby_row, cubby_column) in (("stash", STASH_CUBBY), ("target", TARGET_CUBBY)):
            if cubby_row == row_index:
                layout.shoe_lockers[key] = (x1, y0 + (cubby_column + 0.5) * SHOE_COLUMN_WIDTH)
    return [lockers.build(palette, 0.012), shoe.build(palette, 0.006)]


def _build_shrine_room(palette: dict, layout: Layout) -> list:
    """The player's bedroom, far from the school, with the photo wall `ShrineWall` facing into the room."""
    room = Assembly("ShrineRoom")
    center = SHRINE_ROOM_CENTER
    half, height = 2.0, 2.6
    x0, y0, x1, y1 = center.x - half, center.y - half, center.x + half, center.y + half
    room.box((x0 - WALL, y0 - WALL, -0.2), (x1 + WALL, y1 + WALL, 0.0), "M_Wall", top_material_name="M_Floor_Wood")
    room.box((x0 - WALL, y0 - WALL, height), (x1 + WALL, y1 + WALL, height + 0.2), "M_Wall")
    wall(room, "x", y0 - WALL / 2, x0 - WALL, x1 + WALL, 0.0, height)
    wall(room, "x", y1 + WALL / 2, x0 - WALL, x1 + WALL, 0.0, height)
    wall(room, "y", x1 + WALL / 2, y0, y1, 0.0, height)
    wall(room, "y", x0 - WALL / 2, y0, y1, 0.0, height, [(center.y - 0.6, 1.2, 1.0, 2.0)])
    room.box((x1 - 0.9, y0, 0.0), (x1, y0 + 2.0, 0.45), "M_PropWood")
    shrine_room = room.build(palette)

    width, wall_height = 3.4, 1.9
    shrine_wall = mesh_utils.mesh_from_geometry(
        "ShrineWall",
        [(-width / 2, 0, -wall_height / 2), (width / 2, 0, -wall_height / 2), (width / 2, 0, wall_height / 2),
         (-width / 2, 0, wall_height / 2)],
        [(0, 1, 2, 3)], [palette["M_PropWood"]], smooth=False,
    )
    shrine_wall.location = (center.x, y1 - 0.02, 1.4)

    sky = mesh_utils.mesh_from_geometry(
        "SkyBackdrop",
        [(0, -1.5, -1.0), (0, 1.5, -1.0), (0, 1.5, 1.0), (0, -1.5, 1.0)],
        [(0, 1, 2, 3)], [palette["M_Sky"]], smooth=False,
    )
    sky.location = (x0 - 1.2, center.y - 0.6, 1.5)
    return [shrine_room, shrine_wall, sky]


# Markers ----------------------------------------------------------------------------------------------------------

def marker(name: str, location, yaw: float = 0.0) -> bpy.types.Object:
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = _enum_identifier(bpy.types.Object, "empty_display_type", "ARROWS")
    empty.empty_display_size = 0.35
    empty.location = Vector(location)
    empty.rotation_euler = (0.0, 0.0, yaw)
    bpy.context.scene.collection.objects.link(empty)
    return empty


def camera_marker(name: str, location, look_at) -> bpy.types.Object:
    empty = marker(name, location)
    empty.rotation_euler = (Vector(look_at) - Vector(location)).to_track_quat("Y", "Z").to_euler()
    return empty


def volume_marker(name: str, minimum, maximum) -> bpy.types.Object:
    minimum, maximum = Vector(minimum), Vector(maximum)
    empty = marker(name, (minimum + maximum) / 2)
    empty.empty_display_type = _enum_identifier(bpy.types.Object, "empty_display_type", "CUBE")
    empty.empty_display_size = 1.0
    empty.scale = (maximum - minimum) / 2
    return empty


def _on_floor_beside(anchor: Vector, yaw: float, distance: float = 0.45) -> Vector:
    return anchor + side_of(yaw) * distance


def _on_table(anchor: Vector, yaw: float, height: float = DESK_HEIGHT, reach: float = 0.42) -> Vector:
    return anchor + facing(yaw) * reach + Vector((0, 0, height + 0.005))


def _on_bench(anchor: Vector, yaw: float) -> Vector:
    return anchor - facing(yaw) * 0.4 + side_of(yaw) * 0.55 + Vector((0, 0, SEAT_HEIGHT + 0.005))


def _activity_anchors(layout: Layout) -> dict:
    """activity id -> [(anchor position, yaw, item spawn position)], in anchor index order."""
    target_seat = layout.desk_anchors["Desks_2B"][TARGET_DESK]
    spare_desk = layout.desk_anchors["Desks_2B"][SPARE_DESK_2B]
    bench_courtyard, bench_courtyard_yaw = layout.bench_anchors["Bench_01"]
    bench_roof, bench_roof_yaw = layout.bench_anchors["Bench_04"]
    vending_one = VENDING_COURTYARD[0] + facing(VENDING_COURTYARD[1]) * 0.5
    vending_two = VENDING_CAFETERIA[0] + facing(VENDING_CAFETERIA[1]) * 0.5
    library_one = layout.table_anchors["LibraryTable_1"][0]
    library_two = layout.table_anchors["LibraryTable_2"][3]
    club_one = layout.table_anchors["ClubTable"][0]
    club_two = layout.table_anchors["ClubTable"][3]
    mirror_y = RESTROOM[1] - WALL / 2 - 0.55 - 0.45
    gate, gate_yaw = GATE
    locker = _target_locker(layout)

    def standing(position, yaw):
        position = Vector(position)
        return position, yaw, _on_floor_beside(position, yaw)

    def seated_at_table(anchor_and_yaw):
        anchor, yaw = anchor_and_yaw
        return anchor, yaw, _on_table(anchor, yaw)

    return {
        "read_bench": [(bench_courtyard, bench_courtyard_yaw, _on_bench(bench_courtyard, bench_courtyard_yaw)),
                       (bench_roof, bench_roof_yaw, _on_bench(bench_roof, bench_roof_yaw))],
        "vending_drink": [standing(vending_one, VENDING_COURTYARD[1] + math.pi),
                          standing(vending_two, VENDING_CAFETERIA[1] + math.pi)],
        "chat_students": [standing((14.6, 30.0, 0.0), WEST), standing((0.8, 36.0, FLOOR_ONE), WEST)],
        "desk_phone": [(target_seat, NORTH, _on_table(target_seat, NORTH)), (spare_desk, NORTH, _on_table(spare_desk, NORTH))],
        "courtyard_stroll": [standing((9.0, 22.0, 0.0), NORTH), standing((16.0, 45.5, 0.0), WEST)],
        "restroom_braid": [(Vector((MIRROR_CENTERS_X[0], mirror_y, FLOOR_ONE)), NORTH,
                            Vector((MIRROR_CENTERS_X[0] + 0.5, mirror_y + 0.7, 0.865))),
                           (Vector((MIRROR_CENTERS_X[2], mirror_y, FLOOR_ONE)), NORTH,
                            Vector((MIRROR_CENTERS_X[2] + 0.5, mirror_y + 0.7, 0.865)))],
        "rooftop_visit": [standing((BUILDING_EAST - 0.6, 24.0, ROOF), EAST), standing((BUILDING_EAST - 0.6, 34.0, ROOF), EAST)],
        "library_browse": [seated_at_table(library_one), seated_at_table(library_two)],
        "club_activity": [seated_at_table(club_one), seated_at_table(club_two)],
        "attend_class": [(target_seat, NORTH, _on_table(target_seat, NORTH))],
        "cleaning_duty": [standing((-9.2, CLASS_BAND[1] - 1.4, FLOOR_TWO), NORTH), standing((0.6, 22.0, FLOOR_TWO), NORTH)],
        "go_home": [standing(gate, gate_yaw)],
        "arrive_locker": [standing(locker, WEST)],
    }


GATE = (Vector((0.0, 0.0, 0.0)), SOUTH)
TARGET_DESK = 2
SPARE_DESK_2B = 6
PLAYER_DESK = 0
STUDENT_DESKS_1A = (1, 2, 3, 4, 5, 7)
STUDENT_DESKS_2B = (0, 1, 3, 4, 5, 7)
HIDE_DESK_1A = 8
HIDE_DESK_1B = 4
TEACHER_PATROL = [
    (0.6, 16.0, FLOOR_ONE), (0.6, 30.0, FLOOR_ONE), (0.6, 46.0, FLOOR_ONE), (LANE_A_X, STAIR_LOW_Y - 0.6, FLOOR_ONE),
    (LANE_A_X + 0.4, 60.2, FLOOR_TWO), (0.6, 50.0, FLOOR_TWO), (0.6, 34.0, FLOOR_TWO), (0.6, 18.0, FLOOR_TWO),
]
STUDENT_SPOTS = [
    (8.5, 27.0, 0.0), (15.5, 33.0, 0.0), (15.0, 26.0, 0.0), (6.0, 36.0, 0.0), (18.0, 19.5, 0.0), (8.0, 44.0, 0.0),
    (-6.05, 41.7, FLOOR_ONE), (-2.85, 41.7, FLOOR_ONE), (-9.45, 41.7, FLOOR_ONE), (-6.05, 45.3, FLOOR_ONE),
    (0.9, 26.0, FLOOR_ONE), (0.9, 40.0, FLOOR_ONE), (0.9, 28.0, FLOOR_TWO), (0.9, 41.0, FLOOR_TWO),
    (-2.0, 30.0, ROOF), (-7.5, 40.0, ROOF),
]
HALL_WINDOW_PICKS = [(FLOOR_ONE, 20.5), (FLOOR_ONE, 44.5), (FLOOR_TWO, 26.5), (FLOOR_TWO, 41.5)]


def _target_locker(layout: Layout) -> Vector:
    face_x, cubby_y = layout.shoe_lockers["target"]
    return Vector((face_x + 0.45, cubby_y, FLOOR_ONE))


def _yaw_between(start, end) -> float:
    direction = Vector(end) - Vector(start)
    return math.atan2(-direction.x, direction.y)


def _build_markers(layout: Layout) -> list:
    markers = []
    gate, gate_yaw = GATE
    markers.append(marker("Gate", gate, gate_yaw))
    markers.append(marker("TargetSpawn", (0.8, -1.2, 0.0), NORTH))
    markers.append(marker("PlayerSpawn", (-0.8, 2.0, 0.0), NORTH))

    class_1a, class_1b, class_2b = (layout.desk_anchors[name] for name in ("Desks_1A", "Desks_1B", "Desks_2B"))
    markers.append(marker("PlayerSeat", class_1a[PLAYER_DESK], NORTH))
    markers.append(marker("TargetSeat", class_2b[TARGET_DESK], NORTH))
    student_seats = [class_1a[index] for index in STUDENT_DESKS_1A] + [class_2b[index] for index in STUDENT_DESKS_2B]
    for number, seat in enumerate(student_seats, start=1):
        markers.append(marker(f"StudentSeat_{number:02d}", seat, NORTH))

    stash_face_x, stash_y = layout.shoe_lockers["stash"]
    markers.append(marker("StashLocker", (stash_face_x + 0.45, stash_y, FLOOR_ONE), WEST))
    target_locker = _target_locker(layout)
    markers.append(marker("TargetLocker", target_locker, WEST))
    target_face_x, target_y = layout.shoe_lockers["target"]
    for index, level in enumerate((SHOE_LEVELS[2], SHOE_LEVELS[1])):
        markers.append(marker(f"ItemSpawn_target_locker_{index:02d}", (target_face_x - 0.2, target_y, level), WEST))

    for number, position in enumerate(layout.hide_lockers, start=1):
        markers.append(marker(f"HideLocker_{number:02d}", position, WEST))
    hide_desks = [class_1a[HIDE_DESK_1A] + facing(NORTH) * 0.42, class_1b[HIDE_DESK_1B] + facing(NORTH) * 0.42]
    hide_desks += [layout.table_centers[key] for key in LIBRARY_TABLES]
    for number, position in enumerate(hide_desks, start=1):
        markers.append(marker(f"HideDesk_{number:02d}", position, NORTH))

    for activity_id, anchors in _activity_anchors(layout).items():
        for index, (position, yaw, item_position) in enumerate(anchors):
            markers.append(marker(f"Anchor_{activity_id}_{index:02d}", position, yaw))
            markers.append(marker(f"ItemSpawn_{activity_id}_{index:02d}", item_position, yaw))

    for number, position in enumerate(TEACHER_PATROL, start=1):
        following = TEACHER_PATROL[number % len(TEACHER_PATROL)]
        markers.append(marker(f"TeacherPatrol_{number:02d}", position, _yaw_between(position, following)))
    for number, position in enumerate(STUDENT_SPOTS, start=1):
        markers.append(marker(f"StudentSpot_{number:02d}", position, (number * 2.3) % (2 * math.pi) - math.pi))
    for number, (floor, window_y) in enumerate(HALL_WINDOW_PICKS, start=1):
        if not any(abs(window.y - window_y) < 0.01 and abs(window.z - floor) < 0.01 for window in layout.hall_windows):
            raise ValueError(f"no hall window at y={window_y} on floor {floor}")
        markers.append(marker(f"Window_{number:02d}", (HALL_INTERIOR_EAST - 0.4, window_y, floor), EAST))

    tree = CHERRY_TREES[0]
    stand_target = tree + Vector((0.0, -1.6, 0.0))
    stand_player = tree + Vector((0.0, -3.7, 0.0))
    markers.append(marker("EndingStand_Target", stand_target, NORTH))
    markers.append(marker("EndingStand_Player", stand_player, NORTH))
    between = (stand_target + stand_player) / 2 + Vector((0, 0, 1.3))
    markers.append(camera_marker("EndingCamera_cherry_tree", tree + Vector((3.4, -4.0, 1.5)), between))
    markers.append(camera_marker("EndingCamera_friends", tree + Vector((4.6, -7.5, 2.1)), between + Vector((0, 0, -0.2))))
    markers.append(camera_marker("EndingCamera_stranger", tree + Vector((-4.0, -5.0, 1.6)), between))
    shrine = SHRINE_ROOM_CENTER
    markers.append(camera_marker("EndingCamera_shrine", shrine + Vector((0.0, -1.2, 1.45)), shrine + Vector((0.0, 2.0, 1.4))))

    room_x0, room_x1 = ROOM_INTERIOR_WEST, ROOM_INTERIOR_EAST
    markers.append(volume_marker("Volume_Class1A", (room_x0, CLASS_BAND[0] + WALL / 2, FLOOR_ONE),
                                 (room_x1, CLASS_BAND[1] - WALL / 2, FLOOR_TWO - SLAB)))
    markers.append(volume_marker("Volume_Halls", (HALL_INTERIOR_WEST, BUILDING_SOUTH + WALL / 2, FLOOR_ONE),
                                 (HALL_INTERIOR_EAST, BUILDING_NORTH - WALL / 2, ROOF)))
    return markers
