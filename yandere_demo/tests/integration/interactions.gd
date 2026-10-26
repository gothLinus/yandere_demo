extends IntegrationTest

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const SETTLE_FRAMES: int = 3
const DOOR_SETTLE_SECONDS: float = 0.5
const SIT_SETTLE_SECONDS: float = 1.5
const PICKUP_OFFSET: Vector3 = Vector3(0.0, 0.1, -0.4)
const HIDDEN_DRIFT_TOLERANCE: float = 0.02
const PEEK_TOLERANCE: float = 0.01

var _school_env: SchoolEnv
var _player: StealthPlayer
var _prompts: Array[String] = []
var _picked_ids: Array[StringName] = []
var _stashed_ids: Array[StringName] = []
var _sat_count: int = 0


func _ready() -> void:
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(_player)
	_player.global_transform = _school_env.marker("PlayerSpawn").global_transform
	_player.interact_prompt_changed.connect(func(text: String) -> void: _prompts.append(text))
	await _settle()
	var failure: String = await _run_scenario()
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _run_scenario() -> String:
	for step: Callable in [_hide_in_first_locker, _pick_up_pen, _stash_pen, _sit_in_class, _every_hide_spot_exits_clear]:
		var failure: String = await step.call()
		if not failure.is_empty():
			return failure
	return ""


func _hide_in_first_locker() -> String:
	var locker_marker: Node3D = _school_env.marker("HideLocker_01")
	await _teleport(locker_marker.global_position)
	await _press_interact()
	if _player.mode != StealthPlayer.MODE_HIDDEN:
		return "interact at HideLocker_01 did not hide the player (mode %s)" % _player.mode
	await get_tree().create_timer(DOOR_SETTLE_SECONDS).timeout
	await _settle()
	var drift_failure: String = _hidden_drift_failure(_hide_spots()[0])
	if not drift_failure.is_empty():
		return drift_failure
	if not _prompts.has("E – Leave"):
		return "no 'E – Leave' prompt while hidden: %s" % [_prompts]
	var spot: HideSpot = _hide_spots()[0]
	var rig: PlayerCameraRig = _player.get_node("CameraRig") as PlayerCameraRig
	var peek_point: Node3D = spot.view_point.get_node("PeekPoint") as Node3D
	if rig.current_camera().global_position.distance_to(peek_point.global_position) > PEEK_TOLERANCE:
		return "camera is not at the locker slit"
	await _press_interact()
	if _player.mode != StealthPlayer.MODE_FREE:
		return "second interact did not leave the locker (mode %s)" % _player.mode
	if not _player.is_position_clear(_player.global_position):
		return "player left the locker inside a collider"
	if _player.is_position_clear(spot.view_point.global_position):
		return "the locker interior reads as clear, so the exit check proves nothing"
	if rig.current_camera() == rig.get_node("ViewfinderCamera"):
		return "camera stayed at the slit after leaving"
	return ""


func _pick_up_pen() -> String:
	var spawn: Node3D = _school_env.marker("PlayerSpawn")
	await _teleport(spawn.global_position)
	var pickup: ItemPickup = ItemPickup.spawn(_school_env, &"pen", spawn.global_position + spawn.global_basis * PICKUP_OFFSET)
	if not pickup.is_in_group(&"yandere_items"):
		return "pickup is not in the yandere_items group"
	pickup.picked.connect(func(item_id: StringName) -> void: _picked_ids.append(item_id))
	await _settle()
	await _press_interact()
	if _player.carried_item != &"pen" or _picked_ids != [&"pen"]:
		return "pen not picked up: carried %s, picked %s" % [_player.carried_item, _picked_ids]
	return ""


func _stash_pen() -> String:
	var stash: StashLocker = _school_env.find_children("*", "StashLocker", true, false)[0] as StashLocker
	stash.item_stashed.connect(func(item_id: StringName) -> void: _stashed_ids.append(item_id))
	await _teleport(_school_env.marker("StashLocker").global_position)
	if not _prompts.has("E – Stash Pen"):
		return "no stash prompt: %s" % [_prompts]
	await _press_interact()
	if _stashed_ids != [&"pen"] or _player.carried_item != &"":
		return "pen not stashed: stashed %s, carried %s" % [_stashed_ids, _player.carried_item]
	return ""


func _sit_in_class() -> String:
	var seat: ClassSeat = _school_env.find_children("*", "ClassSeat", true, false)[0] as ClassSeat
	if not seat.is_player_seat:
		return "class seat is not the player seat"
	seat.player_sat.connect(func() -> void: _sat_count += 1)
	var seat_marker: Node3D = _school_env.marker("PlayerSeat")
	var approach: Vector3 = NavigationServer3D.map_get_closest_point(_school_env.navigation_map(), seat_marker.global_position)
	await _teleport(approach)
	await _press_interact()
	if _sat_count != 0:
		return "sat outside a class block"
	seat.is_class_block_callable = func() -> bool: return true
	await _settle()
	await _press_interact()
	if _sat_count != 1 or _player.mode != StealthPlayer.MODE_SEATED:
		return "did not sit in class (sat %d, mode %s)" % [_sat_count, _player.mode]
	await get_tree().create_timer(SIT_SETTLE_SECONDS).timeout
	await _press_interact()
	if _player.mode != StealthPlayer.MODE_FREE:
		return "interact while seated did not stand up (mode %s)" % _player.mode
	return ""


func _every_hide_spot_exits_clear() -> String:
	var spots: Array[HideSpot] = _hide_spots()
	if spots.size() != 10:
		return "expected 10 hide spots, found %d" % spots.size()
	for spot: HideSpot in spots:
		await _teleport(spot.global_position)
		spot.interact(_player)
		await _settle()
		if _player.mode != StealthPlayer.MODE_HIDDEN:
			return "%s did not hide the player" % spot.get_path()
		if spot.kind == &"desk":
			await get_tree().create_timer(DOOR_SETTLE_SECONDS).timeout
			await _settle()
			var drift_failure: String = _hidden_drift_failure(spot)
			if not drift_failure.is_empty():
				return drift_failure
		var view_failure: String = await _hidden_view_failure(spot)
		if not view_failure.is_empty():
			return view_failure
		spot.interact(_player)
		await _settle()
		if _player.mode != StealthPlayer.MODE_FREE:
			return "%s did not release the player" % spot.get_path()
		if not _player.is_position_clear(_player.global_position):
			return "%s released the player inside a collider at %s" % [spot.get_path(), _player.global_position]
	return ""


## The peek camera sits inside the crouched hide pose, so it must not render the player's own body.
func _hidden_view_failure(spot: HideSpot) -> String:
	await get_tree().process_frame
	var own_body_failure: String = _own_body_rendered_failure(_player.current_camera())
	if not own_body_failure.is_empty():
		return "%s: %s" % [spot.get_path(), own_body_failure]
	return ""


func _own_body_rendered_failure(camera: Camera3D) -> String:
	for node: Node in _player.get_node(^"Model").find_children("*", "VisualInstance3D", true, false):
		var visual: VisualInstance3D = node as VisualInstance3D
		if visual.is_visible_in_tree() and camera.cull_mask & visual.layers != 0:
			return "the peek camera renders the player's own %s" % visual.name
	return ""


func _hidden_drift_failure(spot: HideSpot) -> String:
	var drift: float = _player.global_position.distance_to(spot.view_point.global_position)
	if drift > HIDDEN_DRIFT_TOLERANCE:
		return "%s: hidden body drifted %.3f m from the ViewPoint" % [spot.get_path(), drift]
	return ""


func _hide_spots() -> Array[HideSpot]:
	var spots: Array[HideSpot] = []
	for prefix: String in ["HideLocker_", "HideDesk_"]:
		for marker_node: Node3D in _school_env.markers_with_prefix(prefix):
			for node: Node in _school_env.find_children("*", "HideSpot", true, false):
				var spot: HideSpot = node as HideSpot
				if spot.global_position.is_equal_approx(marker_node.global_position):
					spots.append(spot)
	return spots


func _teleport(position: Vector3) -> void:
	_player.global_position = position
	_player.velocity = Vector3.ZERO
	await _settle()


func _settle() -> void:
	for frame: int in SETTLE_FRAMES:
		await get_tree().physics_frame


func _press_interact() -> void:
	Input.action_press(&"interact")
	await get_tree().physics_frame
	await get_tree().physics_frame
	Input.action_release(&"interact")
	await _settle()
