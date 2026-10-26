extends IntegrationTest
## Each of the four endings plays on ending.tscn at time scale 8, finishes within 30 s with the right title card, and
## the shrine hangs one photo quad per banked photo. DaySummary's ending_requested reaches GameManager.

const ENDING_SCENE_PATH: String = "res://scenes/ending.tscn"
const DAY_SUMMARY_SCENE: PackedScene = preload("res://scenes/ui/day_summary.tscn")
const TEST_SAVE_PATH: String = "user://test_save.json"
const TIME_SCALE: float = 8.0
const MINIMUM_PHYSICS_STEPS: int = 64
const FINISH_TIMEOUT_MILLISECONDS: int = 30000
const MINIMUM_TRAVEL_DISTANCE: float = 10.0
const SAMPLING_PRIORITY: int = 100
const PASS_DISTANCE: float = 3.0
const MAXIMUM_WALK_SPEED: float = 1.5
const MINIMUM_SEQUENCE_SECONDS: float = 10.0
const MAXIMUM_SEQUENCE_SECONDS: float = 15.0
## Ruling R31: the stranger's static camera keeps his head in frame for most of the walk, and the player too.
const MINIMUM_FRAMED_WALK_FRACTION: float = 0.8
const PLAYER_HEAD_HEIGHT: float = 1.5
const BANKED_PHOTO_COUNT: int = 3
const TITLES: Dictionary = {
	&"cherry_tree": "Under the Cherry Tree",
	&"friends": "Friends First",
	&"stranger": "Just a Stranger",
	&"shrine": "The Shrine",
}

var _finished_ids: Array[StringName] = []
var _previous_time_scale: float = 1.0
var _previous_physics_steps: int = 8
var _sequence_seconds: float = 0.0
var _observed_target: TargetAI
var _observed_player: Node3D
var _last_position: Vector3 = Vector3.ZERO
var _travelled: float = 0.0
var _fastest_speed: float = 0.0
var _closest_distance: float = INF
var _final_distance: float = 0.0
var _max_look_influence: float = 0.0
var _walking_frames: int = 0
var _framed_walking_frames: int = 0
var _player_framed_frames: int = 0
var _observed_camera: Camera3D


func _ready() -> void:
	# Sampling must follow the director's own _process in the same frame, or each step is divided by the wrong delta.
	process_priority = SAMPLING_PRIORITY
	GameManager.test_mode = true
	SaveStore.erase(TEST_SAVE_PATH)
	_previous_time_scale = Engine.time_scale
	_previous_physics_steps = Engine.max_physics_steps_per_frame
	Engine.max_physics_steps_per_frame = maxi(_previous_physics_steps, MINIMUM_PHYSICS_STEPS)
	Engine.time_scale = TIME_SCALE
	var failure: String = await _run_scenario()
	_restore_engine()
	SaveStore.erase(TEST_SAVE_PATH)
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _process(delta: float) -> void:
	super._process(delta)
	if _observed_target == null or delta <= 0.0:
		return
	_sequence_seconds += delta
	_sample(delta)


func _sample(delta: float) -> void:
	var position: Vector3 = _observed_target.global_position
	var step: float = Vector2(position.x - _last_position.x, position.z - _last_position.z).length()
	_travelled += step
	_fastest_speed = maxf(_fastest_speed, step / delta)
	_last_position = position
	_final_distance = position.distance_to(_observed_player.global_position)
	_closest_distance = minf(_closest_distance, _final_distance)
	var look_at: LookAtModifier3D = _observed_target.get_node(^"Model/TargetChar/Skeleton3D/LookAtModifier3D")
	_max_look_influence = maxf(_max_look_influence, look_at.influence)
	if step > 0.0:
		_walking_frames += 1
		if _observed_camera.is_position_in_frustum(_observed_target.head_position()):
			_framed_walking_frames += 1
		if _observed_camera.is_position_in_frustum(_observed_player.global_position + Vector3.UP * PLAYER_HEAD_HEIGHT):
			_player_framed_frames += 1


func _exit_tree() -> void:
	_restore_engine()
	SaveStore.erase(TEST_SAVE_PATH)


func _restore_engine() -> void:
	Engine.time_scale = _previous_time_scale
	Engine.max_physics_steps_per_frame = _previous_physics_steps


func _run_scenario() -> String:
	var wiring_failure: String = await _check_ending_requested_wiring()
	if not wiring_failure.is_empty():
		return wiring_failure
	var progress: WeekProgress = WeekProgress.new()
	for photo_index: int in BANKED_PHOTO_COUNT:
		progress.banked_photos.append({"path": "", "score": 100, "day": photo_index})
	for ending_id: StringName in TITLES:
		var failure: String = await _play_ending(ending_id, progress)
		if not failure.is_empty():
			return "%s: %s" % [ending_id, failure]
	return ""


func _check_ending_requested_wiring() -> String:
	var summary: DaySummary = DAY_SUMMARY_SCENE.instantiate()
	add_child(summary)
	await get_tree().process_frame
	var is_wired: bool = false
	for connection: Dictionary in summary.ending_requested.get_connections():
		var callable: Callable = connection["callable"]
		is_wired = is_wired or callable.get_object() == GameManager
	summary.queue_free()
	return "" if is_wired else "GameManager does not listen to DaySummary.ending_requested"


func _play_ending(ending_id: StringName, progress: WeekProgress) -> String:
	var director: EndingDirector = (load(ENDING_SCENE_PATH) as PackedScene).instantiate() as EndingDirector
	add_child(director)
	_finished_ids.clear()
	director.ending_finished.connect(func(finished_id: StringName) -> void: _finished_ids.append(finished_id))
	var school_env: SchoolEnv = director.get_node("%SchoolEnv")
	if not school_env.is_navigation_ready:
		await school_env.navigation_ready
	director.play(ending_id, progress)
	_begin_observing(director)
	var started_at: int = Time.get_ticks_msec()
	while _finished_ids.is_empty() and Time.get_ticks_msec() - started_at < FINISH_TIMEOUT_MILLISECONDS:
		await get_tree().process_frame
	_observed_target = null
	var failure: String = _verify(director, ending_id)
	director.queue_free()
	await get_tree().process_frame
	return failure


func _begin_observing(director: EndingDirector) -> void:
	_sequence_seconds = 0.0
	_travelled = 0.0
	_fastest_speed = 0.0
	_closest_distance = INF
	_max_look_influence = 0.0
	_walking_frames = 0
	_framed_walking_frames = 0
	_player_framed_frames = 0
	_observed_camera = director.get_node("%EndingCamera")
	_observed_player = director.get_node("%Player")
	_last_position = director.get_node("%Target").global_position
	_observed_target = director.get_node("%Target")


func _verify(director: EndingDirector, ending_id: StringName) -> String:
	if _finished_ids != [ending_id]:
		return "ending_finished fired %s within 30 s" % [_finished_ids]
	var title_label: Label = director.get_node("%TitleLabel")
	if title_label.text != TITLES[ending_id]:
		return "title card reads '%s'" % title_label.text
	var new_week_button: Button = director.get_node("%NewWeekButton")
	if not new_week_button.is_visible_in_tree() or new_week_button.text != "New Week":
		return "the New Week button is missing or hidden"
	if not new_week_button.pressed.get_connections().any(func(connection: Dictionary) -> bool: return connection["callable"].get_object() == GameManager):
		return "the New Week button is not wired to GameManager.new_week"
	if not director.get_viewport().get_camera_3d().is_inside_tree():
		return "no ending camera is current"
	var photo_quads: Array[Node] = director.get_tree().get_nodes_in_group(EndingDirector.SHRINE_PHOTO_GROUP)
	var expected_quads: int = BANKED_PHOTO_COUNT if ending_id == &"shrine" else 0
	if photo_quads.size() != expected_quads:
		return "%d shrine photo quads, expected %d" % [photo_quads.size(), expected_quads]
	if _sequence_seconds < MINIMUM_SEQUENCE_SECONDS or _sequence_seconds > MAXIMUM_SEQUENCE_SECONDS:
		return "the sequence took %.1f s, outside 10-15 s" % _sequence_seconds
	if ending_id == &"stranger":
		if _travelled < MINIMUM_TRAVEL_DISTANCE:
			return "he walked only %.1f m" % _travelled
		if _fastest_speed > MAXIMUM_WALK_SPEED:
			return "he moved at %.2f m/s on one frame" % _fastest_speed
		if _closest_distance >= _final_distance or _closest_distance > PASS_DISTANCE:
			return "he did not pass the player (closest %.1f m, final %.1f m)" % [_closest_distance, _final_distance]
		if _max_look_influence > 0.0:
			return "his LookAt influence rose to %.2f" % _max_look_influence
		var framed_fraction: float = float(_framed_walking_frames) / maxi(_walking_frames, 1)
		if framed_fraction < MINIMUM_FRAMED_WALK_FRACTION:
			return "his head was in frame for only %.0f%% of the walk" % (framed_fraction * 100.0)
		if _player_framed_frames < _walking_frames:
			return "the player left the frame during the walk (%d of %d frames)" % [_player_framed_frames, _walking_frames]
	return ""
