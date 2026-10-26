extends IntegrationTest
## Spec §4.5: Sanity recovers while watching him. While hidden, "watching" must mean what the peek view shows: for
## every hide spot, a head on a grid in front of the peek camera counts as watched exactly when the peek camera has a
## clear line of sight to it. Under a desk the standing head height would see over the desks the peek view looks
## through.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const SETTLE_FRAMES: int = 3
const PROBE_DISTANCES: Array[float] = [1.5, 2.0, 3.0, 4.0, 6.0]
const PROBE_LATERAL_OFFSETS: Array[float] = [-1.0, 0.0, 1.0]
const TARGET_HEAD_HEIGHT: float = 1.45
const WATCH_RANGE: float = 15.0
const APPROACH_DISTANCE: float = 0.5

var _school_env: SchoolEnv
var _player: StealthPlayer


func _ready() -> void:
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(_player)
	_player.can_hide_callable = func() -> bool: return true
	await _settle()
	var failure: String = await _watching_matches_the_peek_view()
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _watching_matches_the_peek_view() -> String:
	var visible_heads_by_kind: Dictionary = {}
	for node: Node in _school_env.get_children():
		var spot: HideSpot = node as HideSpot
		if spot == null:
			continue
		_player.global_position = spot.global_position + spot.global_basis.z * APPROACH_DISTANCE
		await _settle()
		spot.interact(_player)
		if _player.mode != StealthPlayer.MODE_HIDDEN:
			return "%s did not hide the player" % spot.name
		await _settle()
		var failure: String = _compare_probe_grid(spot, visible_heads_by_kind)
		spot.interact(_player)
		await _settle()
		if not failure.is_empty():
			return failure
	for kind: StringName in [&"locker", &"desk"]:
		if not visible_heads_by_kind.has(kind):
			return "no %s peek view saw any probe head, so the check proves nothing (%s)" % [kind, visible_heads_by_kind]
	return ""


func _compare_probe_grid(spot: HideSpot, visible_heads_by_kind: Dictionary) -> String:
	var camera: Camera3D = _player.current_camera()
	var forward: Vector3 = -camera.global_basis.z
	forward.y = 0.0
	forward = forward.normalized()
	var side: Vector3 = forward.cross(Vector3.UP)
	var space: PhysicsDirectSpaceState3D = _player.get_world_3d().direct_space_state
	for distance: float in PROBE_DISTANCES:
		for lateral: float in PROBE_LATERAL_OFFSETS:
			var head: Vector3 = camera.global_position + forward * distance + side * lateral
			head.y = spot.global_position.y + TARGET_HEAD_HEIGHT
			var ray: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(camera.global_position, head, PhysicsLayers.LINE_OF_SIGHT_MASK)
			var camera_sees: bool = camera.is_position_in_frustum(head) and space.intersect_ray(ray).is_empty()
			var is_watching: bool = _player.is_watching(head, space, WATCH_RANGE)
			if camera_sees != is_watching:
				return "%s: head %.1f m ahead, %.1f m aside: peek camera sees %s but is_watching %s" % [
						spot.name, distance, lateral, camera_sees, is_watching]
			if camera_sees:
				visible_heads_by_kind[spot.kind] = int(visible_heads_by_kind.get(spot.kind, 0)) + 1
	return ""


func _settle() -> void:
	for frame: int in SETTLE_FRAMES:
		await get_tree().physics_frame
	await get_tree().process_frame
