class_name SchoolEnv
extends Node3D

signal navigation_ready()

const MAX_SYNC_FRAMES: int = 300
const MAP_SYNC_TOLERANCE: float = 0.5
const VOLUME_HALF_EXTENT_LIMIT: float = 1.0
const HIDE_LOCKER_SCENE: PackedScene = preload("res://scenes/props/hide_locker.tscn")
const HIDE_DESK_SCENE: PackedScene = preload("res://scenes/props/hide_desk.tscn")
const CLASS_SEAT_SCENE: PackedScene = preload("res://scenes/props/class_seat.tscn")
const STASH_LOCKER_SCENE: PackedScene = preload("res://scenes/props/stash_locker.tscn")

@export var daylight_profile: DaylightProfile = preload("res://data/daylight_profile.tres")

var is_navigation_ready: bool = false

var _markers: Dictionary = {}

@onready var _school: Node3D = $School
@onready var _navigation_region: NavigationRegion3D = $NavigationRegion3D
@onready var _sun: DirectionalLight3D = $Sun


func _ready() -> void:
	_school.reparent(_navigation_region, false)
	_index_markers()
	_spawn_interactables()
	var navigation_mesh: NavigationMesh = _navigation_region.navigation_mesh
	var map: RID = _navigation_region.get_navigation_map()
	NavigationServer3D.map_set_cell_size(map, navigation_mesh.cell_size)
	NavigationServer3D.map_set_cell_height(map, navigation_mesh.cell_height)
	set_daylight(daylight_profile.morning_minute)
	_navigation_region.bake_navigation_mesh(false)
	await get_tree().physics_frame
	var vertices: PackedVector3Array = navigation_mesh.get_vertices()
	if vertices.is_empty():
		push_error("SchoolEnv: navigation bake produced no vertices")
	else:
		var waited_frames: int = 0
		while not _map_contains(map, vertices[0]) and waited_frames < MAX_SYNC_FRAMES:
			await get_tree().physics_frame
			waited_frames += 1
		if waited_frames >= MAX_SYNC_FRAMES:
			push_error("SchoolEnv: navigation map did not sync within %d frames" % MAX_SYNC_FRAMES)
	is_navigation_ready = true
	navigation_ready.emit()


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
	matches.sort_custom(func(first: Node3D, second: Node3D) -> bool: return String(first.name) < String(second.name))
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
	daylight_profile.apply_to(_sun, minute)


func _map_contains(map: RID, point: Vector3) -> bool:
	if NavigationServer3D.map_get_iteration_id(map) == 0:
		return false
	return NavigationServer3D.map_get_closest_point(map, point).distance_to(point) <= MAP_SYNC_TOLERANCE


func _index_markers() -> void:
	_markers.clear()
	for node: Node in _school.find_children("*", "Node3D", true, false):
		if not _markers.has(String(node.name)):
			_markers[String(node.name)] = node


func _spawn_interactables() -> void:
	for locker_marker: Node3D in markers_with_prefix("HideLocker_"):
		_place(HIDE_LOCKER_SCENE, locker_marker)
	for desk_marker: Node3D in markers_with_prefix("HideDesk_"):
		_place(HIDE_DESK_SCENE, desk_marker)
	var seat: ClassSeat = _place(CLASS_SEAT_SCENE, marker("PlayerSeat")) as ClassSeat
	seat.is_player_seat = true
	_place(STASH_LOCKER_SCENE, marker("StashLocker"))


func _place(scene: PackedScene, anchor: Node3D) -> Node3D:
	var instance: Node3D = scene.instantiate() as Node3D
	instance.name = "Interactable_%s" % anchor.name
	add_child(instance)
	instance.global_transform = anchor.global_transform
	return instance


func _numbered_markers(prefix: String) -> Array[Node3D]:
	var matches: Array[Node3D] = []
	for index: int in range(0, _markers.size()):
		var found: Node3D = _markers.get("%s%02d" % [prefix, index]) as Node3D
		if found == null:
			break
		matches.append(found)
	return matches
