extends IntegrationTest

## A seated anchor sits between desk and chair, so the navmesh (agent radius 0.3 m) cannot get as close as for a standing one.
const STANDING_TOLERANCE: float = 0.5
const SEATED_TOLERANCE: float = 0.8

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"

var _routes: Array[Dictionary] = [
	{"from": "PlayerSpawn", "to": "PlayerSeat", "tolerance": SEATED_TOLERANCE},
	{"from": "TargetSpawn", "to": "TargetSeat", "tolerance": SEATED_TOLERANCE},
	{"from": "TargetSeat", "to": "Anchor_rooftop_visit_00", "tolerance": STANDING_TOLERANCE},
	{"from": "Gate", "to": "Anchor_library_browse_00", "tolerance": SEATED_TOLERANCE},
	{"from": "StashLocker", "to": "HideLocker_06", "tolerance": STANDING_TOLERANCE},
]


func _ready() -> void:
	var school_scene: PackedScene = load(SCHOOL_ENV_PATH) as PackedScene
	if school_scene == null:
		fail_test("missing %s" % SCHOOL_ENV_PATH)
		return
	var school_env: SchoolEnv = school_scene.instantiate() as SchoolEnv
	add_child(school_env)
	await school_env.navigation_ready
	var morning_sun: DirectionalLight3D = school_env.get_node("Sun") as DirectionalLight3D
	if not is_equal_approx(morning_sun.light_energy, 1.2):
		fail_test("morning daylight not applied before navigation_ready")
		return
	var map: RID = school_env.navigation_map()
	for route: Dictionary in _routes:
		var origin: Vector3 = school_env.marker(route["from"]).global_position
		var target: Vector3 = school_env.marker(route["to"]).global_position
		var path: PackedVector3Array = NavigationServer3D.map_get_path(map, origin, target, true)
		if path.is_empty():
			fail_test("no path %s -> %s" % [route["from"], route["to"]])
			return
		var gap: float = path[path.size() - 1].distance_to(target)
		if gap > route["tolerance"]:
			fail_test("path %s -> %s ends %.2f m from target (limit %.1f)" % [route["from"], route["to"], gap, route["tolerance"]])
			return
	var counts: Dictionary = school_env.anchor_counts()
	var library_anchors: Array[Node3D] = school_env.anchors_for(&"library_browse")
	if int(counts.get(&"library_browse", 0)) != library_anchors.size() or library_anchors.size() < 2:
		fail_test("anchor lookup inconsistent: %s" % [counts])
		return
	if school_env.item_spawn_for(&"library_browse", 0) == null:
		fail_test("missing item spawn for library_browse 0")
		return
	var inside: bool = school_env.volume_contains("Volume_Class1A", school_env.marker("PlayerSeat").global_position)
	if not inside or school_env.volume_contains("Volume_Class1A", school_env.marker("Gate").global_position):
		fail_test("Volume_Class1A containment wrong")
		return
	school_env.set_daylight(1050.0)
	var sun: DirectionalLight3D = school_env.get_node("Sun") as DirectionalLight3D
	if not sun.light_color.is_equal_approx(Color("ffb070")) or not is_equal_approx(sun.light_energy, 0.8):
		fail_test("evening daylight wrong")
		return
	pass_test()
