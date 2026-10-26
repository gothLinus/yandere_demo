extends IntegrationTest
## Each of the four endings plays on ending.tscn at time scale 8, finishes within 30 s with the right title card, and
## the shrine hangs one photo quad per banked photo. DaySummary's ending_requested reaches GameManager.

const ENDING_SCENE_PATH: String = "res://scenes/ending.tscn"
const DAY_SUMMARY_SCENE: PackedScene = preload("res://scenes/ui/day_summary.tscn")
const TEST_SAVE_PATH: String = "user://test_save.json"
const TIME_SCALE: float = 8.0
const MINIMUM_PHYSICS_STEPS: int = 64
const FINISH_TIMEOUT_MILLISECONDS: int = 30000
const GATE_REACHED_DISTANCE: float = 1.5
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


func _ready() -> void:
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
	director.play(ending_id, progress)
	var started_at: int = Time.get_ticks_msec()
	while _finished_ids.is_empty() and Time.get_ticks_msec() - started_at < FINISH_TIMEOUT_MILLISECONDS:
		await get_tree().process_frame
	var failure: String = _verify(director, ending_id)
	director.queue_free()
	await get_tree().process_frame
	return failure


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
	if ending_id == &"stranger":
		var target: Node3D = director.get_node("%Target")
		var gate: Node3D = director.get_node("%SchoolEnv").marker("Gate")
		var distance: float = target.global_position.distance_to(gate.global_position)
		if distance > GATE_REACHED_DISTANCE:
			return "the target stopped %.1f m from the Gate" % distance
	return ""
