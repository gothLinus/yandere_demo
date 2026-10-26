class_name SchoolEnv
extends Node3D

signal navigation_ready()

const MORNING_MINUTE: float = 420.0
const NOON_MINUTE: float = 720.0
const EVENING_MINUTE: float = 1050.0
const MORNING_COLOR: Color = Color(1.0, 0.95, 0.86)
const NOON_COLOR: Color = Color(1.0, 1.0, 1.0)
const EVENING_COLOR: Color = Color("ffb070")
const MORNING_ENERGY: float = 1.2
const NOON_ENERGY: float = 1.0
const EVENING_ENERGY: float = 0.8
const MORNING_PITCH_DEGREES: float = -35.0
const NOON_PITCH_DEGREES: float = -65.0
const EVENING_PITCH_DEGREES: float = -18.0
const SUN_YAW_DEGREES: float = -30.0
const MAP_SYNC_TOLERANCE: float = 0.5
const VOLUME_HALF_EXTENT_LIMIT: float = 1.0

var _markers: Dictionary = {}

@onready var _school: Node3D = $School
@onready var _navigation_region: NavigationRegion3D = $NavigationRegion3D
@onready var _sun: DirectionalLight3D = $Sun


func _ready() -> void:
	_school.reparent(_navigation_region, false)
	_index_markers()
	var navigation_mesh: NavigationMesh = _navigation_region.navigation_mesh
	var map: RID = _navigation_region.get_navigation_map()
	NavigationServer3D.map_set_cell_size(map, navigation_mesh.cell_size)
	NavigationServer3D.map_set_cell_height(map, navigation_mesh.cell_height)
	_navigation_region.bake_navigation_mesh(false)
	await get_tree().physics_frame
	var baked_vertex: Vector3 = navigation_mesh.get_vertices()[0]
	while not _map_contains(map, baked_vertex):
		await get_tree().physics_frame
	navigation_ready.emit()
	set_daylight(MORNING_MINUTE)


func marker(marker_name: String) -> Node3D:
	var found: Node3D = _markers.get(marker_name) as Node3D
	if found == null:
		push_error("SchoolEnv: missing marker '%s'" % marker_name)
	return found


func anchors_for(activity_id: StringName) -> Array[Node3D]:
	return _numbered_markers("Anchor_%s_" % activity_id)


func anchor_counts() -> Dictionary:
	var counts: Dictionary = {}
	for marker_name: String in _markers:
		if not marker_name.begins_with("Anchor_"):
			continue
		var activity_id: StringName = StringName(marker_name.trim_prefix("Anchor_").rsplit("_", true, 1)[0])
		counts[activity_id] = int(counts.get(activity_id, 0)) + 1
	return counts


func item_spawn_for(activity_id: StringName, anchor_index: int) -> Node3D:
	return _markers.get("ItemSpawn_%s_%02d" % [activity_id, anchor_index]) as Node3D


func markers_with_prefix(prefix: String) -> Array[Node3D]:
	var matches: Array[Node3D] = []
	for marker_name: String in _markers:
		if marker_name.begins_with(prefix):
			matches.append(_markers[marker_name] as Node3D)
	matches.sort_custom(func(first: Node3D, second: Node3D) -> bool: return first.name < second.name)
	return matches


func volume_contains(volume_name: String, point: Vector3) -> bool:
	var volume: Node3D = marker(volume_name)
	if volume == null:
		return false
	var local_point: Vector3 = volume.global_transform.affine_inverse() * point
	return absf(local_point.x) <= VOLUME_HALF_EXTENT_LIMIT \
		and absf(local_point.y) <= VOLUME_HALF_EXTENT_LIMIT \
		and absf(local_point.z) <= VOLUME_HALF_EXTENT_LIMIT


func navigation_map() -> RID:
	return _navigation_region.get_navigation_map()


func set_daylight(minute: float) -> void:
	var morning_to_noon: bool = minute < NOON_MINUTE
	var from_minute: float = MORNING_MINUTE if morning_to_noon else NOON_MINUTE
	var to_minute: float = NOON_MINUTE if morning_to_noon else EVENING_MINUTE
	var weight: float = clampf(inverse_lerp(from_minute, to_minute, minute), 0.0, 1.0)
	var from_color: Color = MORNING_COLOR if morning_to_noon else NOON_COLOR
	var to_color: Color = NOON_COLOR if morning_to_noon else EVENING_COLOR
	var from_energy: float = MORNING_ENERGY if morning_to_noon else NOON_ENERGY
	var to_energy: float = NOON_ENERGY if morning_to_noon else EVENING_ENERGY
	var from_pitch: float = MORNING_PITCH_DEGREES if morning_to_noon else NOON_PITCH_DEGREES
	var to_pitch: float = NOON_PITCH_DEGREES if morning_to_noon else EVENING_PITCH_DEGREES
	_sun.light_color = from_color.lerp(to_color, weight)
	_sun.light_energy = lerpf(from_energy, to_energy, weight)
	_sun.rotation_degrees = Vector3(lerpf(from_pitch, to_pitch, weight), SUN_YAW_DEGREES, 0.0)


func _map_contains(map: RID, point: Vector3) -> bool:
	if NavigationServer3D.map_get_iteration_id(map) == 0:
		return false
	return NavigationServer3D.map_get_closest_point(map, point).distance_to(point) <= MAP_SYNC_TOLERANCE


func _index_markers() -> void:
	_markers.clear()
	for node: Node in _school.find_children("*", "Node3D", true, false):
		if not _markers.has(String(node.name)):
			_markers[String(node.name)] = node


func _numbered_markers(prefix: String) -> Array[Node3D]:
	var matches: Array[Node3D] = []
	for index: int in range(0, _markers.size()):
		var found: Node3D = _markers.get("%s%02d" % [prefix, index]) as Node3D
		if found == null:
			break
		matches.append(found)
	return matches
