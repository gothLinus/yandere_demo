extends SceneTree
## Geometry check for Ruling R12, run by hand (a navmesh bake is too heavy for the unit suite):
##   godot --headless --path yandere_demo --script res://tests/tools/seated_anchor_probe.gd
## Bakes the school with the Task 12 navigation settings, then for every seated marker checks that the nearest
## navmesh point is within MAX_REACH and that the straight approach from it, at knee and hip height, hits no collider.

const SCHOOL_SCENE_PATH: String = "res://assets/models/school.glb"
const ACTIVITY_POOL_PATH: String = "res://data/activity_pool.tres"
const MAX_REACH: float = 0.8
const PROBE_HEIGHTS: Array[float] = [0.3, 0.9]
const SETTLE_FRAMES: int = 30

var _region: NavigationRegion3D
var _school: Node3D
var _frame: int = 0


func _initialize() -> void:
	_region = NavigationRegion3D.new()
	var navigation_mesh: NavigationMesh = NavigationMesh.new()
	navigation_mesh.agent_radius = 0.3
	navigation_mesh.agent_height = 1.6
	navigation_mesh.agent_max_climb = 0.25
	navigation_mesh.agent_max_slope = 40.0
	navigation_mesh.cell_size = 0.1
	navigation_mesh.cell_height = 0.05
	navigation_mesh.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	navigation_mesh.geometry_source_geometry_mode = NavigationMesh.SOURCE_GEOMETRY_ROOT_NODE_CHILDREN
	_region.navigation_mesh = navigation_mesh
	get_root().add_child(_region)
	_school = (load(SCHOOL_SCENE_PATH) as PackedScene).instantiate() as Node3D
	_region.add_child(_school)
	var map: RID = get_root().get_world_3d().navigation_map
	NavigationServer3D.map_set_cell_size(map, navigation_mesh.cell_size)
	NavigationServer3D.map_set_cell_height(map, navigation_mesh.cell_height)


func _physics_process(_delta: float) -> bool:
	_frame += 1
	if _frame == 1:
		_region.bake_navigation_mesh(false)
	if _frame < SETTLE_FRAMES:
		return false
	var failures: int = 0
	print("| Marker | Nearest navmesh (m) | Approach clear |")
	print("|---|---|---|")
	for marker_name: String in _seated_marker_names():
		var marker: Node3D = _school.find_child(marker_name, true, false) as Node3D
		if marker == null:
			print("| %s | missing | - |" % marker_name)
			failures += 1
			continue
		var anchor: Vector3 = marker.global_position
		var nearest: Vector3 = NavigationServer3D.map_get_closest_point(_region.get_navigation_map(), anchor)
		var reach: float = Vector2(nearest.x - anchor.x, nearest.z - anchor.z).length()
		var blocker: String = _first_blocker(nearest, anchor)
		var passed: bool = reach <= MAX_REACH and absf(nearest.y - anchor.y) < 0.3 and blocker.is_empty()
		if not passed:
			failures += 1
		print("| %s | %.2f | %s |" % [marker_name, reach, "yes" if blocker.is_empty() else "no (%s)" % blocker])
	print("%s: %d seated markers failed" % ["FAIL" if failures > 0 else "PASS", failures])
	quit(1 if failures > 0 else 0)
	return true


func _seated_marker_names() -> Array[String]:
	var names: Array[String] = ["PlayerSeat", "TargetSeat"]
	for number: int in range(1, 13):
		names.append("StudentSeat_%02d" % number)
	var pool: ActivityPool = load(ACTIVITY_POOL_PATH) as ActivityPool
	for activity: ActivityDefinition in pool.activities:
		if activity.posture != GameTypes.Posture.SITTING:
			continue
		var index: int = 0
		while _school.find_child("Anchor_%s_%02d" % [activity.id, index], true, false) != null:
			names.append("Anchor_%s_%02d" % [activity.id, index])
			index += 1
	return names


func _first_blocker(nearest: Vector3, anchor: Vector3) -> String:
	var space: PhysicsDirectSpaceState3D = get_root().get_world_3d().direct_space_state
	for height: float in PROBE_HEIGHTS:
		var start: Vector3 = Vector3(nearest.x, anchor.y + height, nearest.z)
		var end: Vector3 = Vector3(anchor.x, anchor.y + height, anchor.z)
		var blocker: String = _ray_blocker(space, start, end)
		if blocker.is_empty():
			blocker = _ray_blocker(space, end, start)
		if not blocker.is_empty():
			return "%s at %.1f m" % [blocker, height]
	return ""


func _ray_blocker(space: PhysicsDirectSpaceState3D, from: Vector3, to: Vector3) -> String:
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(from, to)
	query.hit_back_faces = true
	var hit: Dictionary = space.intersect_ray(query)
	return "" if hit.is_empty() else String((hit["collider"] as Node).get_parent().name)
