extends Node
## Autoload: runs the week (spec §4.3, §4.3a). Starts each day on main.tscn, wires that day's actors to the clock and
## the meters, handles class attendance, game over and the end of the day, and saves the week's progress.

signal day_started(day_index: int)
## Keys: photos (Array[Dictionary]), photo_score (int), items (Array[StringName]), intel_new (Array[StringName]),
## school_alert (float).
signal day_completed(summary: Dictionary)
signal game_over(reason: StringName)
signal week_completed(ending_id: StringName)
signal intel_unlocked(card: IntelCard)

const MAIN_SCENE_PATH: String = "res://scenes/main.tscn"
const ENDING_SCENE_PATH: String = "res://scenes/ending.tscn"
const TEST_SAVE_PATH: String = "user://test_save.json"
const PLAYER_GROUP: StringName = &"player"
const TARGET_GROUP: StringName = &"target"
const TEACHER_GROUP: StringName = &"teacher"
const CROWD_GROUP: StringName = &"crowd"
const SCHOOL_ENV_GROUP: StringName = &"school_env"
const PLAYER_SPAWN_MARKER: String = "PlayerSpawn"
const TEACHER_PATROL_PREFIX: String = "TeacherPatrol_"
const PHOTO_MODE_PATH: NodePath = ^"PhotoMode"
const YANDERE_VISION_PATH: NodePath = ^"YandereVision"
const CAMERA_RIG_PATH: NodePath = ^"CameraRig"

@export var stealth_tuning: StealthTuning = preload("res://data/stealth_tuning.tres")
@export var game_tuning: GameTuning = preload("res://data/game_tuning.tres")
@export var ending_tuning: EndingTuning = preload("res://data/ending_tuning.tres")
@export var intel_catalog: IntelCatalog = preload("res://data/intel_cards.tres")

## Skips the scene change in start_day(), saves to TEST_SAVE_PATH and makes the class fade instant.
var test_mode: bool = false
var progress: WeekProgress
var day_run: DayRun
var attendance: AttendanceTracker
## Called with one Callable: fade out, run it, fade in. Task 19's ClassFade replaces the instant default (ruling R23).
var fade_callable: Callable = _instant_fade

var _player: StealthPlayer
var _target: TargetAI
var _teacher: TeacherAI
var _crowd: CrowdSpawner
var _school_env: SchoolEnv
var _is_day_active: bool = false
var _is_starting_day: bool = false
var _current_block: ScheduleBlock
var _seconds_since_target_seen: float = 0.0


func _ready() -> void:
	SchoolClock.block_changed.connect(_on_block_changed)
	SchoolClock.day_ended.connect(complete_day)
	SchoolClock.minute_ticked.connect(_on_minute_ticked)
	SanitySystem.caught.connect(_on_caught)
	SanitySystem.sanity_changed.connect(_on_sanity_changed)
	get_tree().node_added.connect(_on_node_added)


func _physics_process(delta: float) -> void:
	# While he is gone home there is nothing to watch, so Sanity holds instead of draining.
	if not _is_day_active or _target.state == TargetAI.State.GONE:
		return
	var space: PhysicsDirectSpaceState3D = _player.get_world_3d().direct_space_state
	var is_watching: bool = _player.is_watching(_target.head_position(), space, stealth_tuning.sanity_watch_range)
	_seconds_since_target_seen = 0.0 if is_watching else _seconds_since_target_seen + delta
	SanitySystem.meters.update_sanity(delta, _seconds_since_target_seen, is_watching, _player.is_vision_active)


func save_path() -> String:
	return TEST_SAVE_PATH if test_mode else SaveStore.DEFAULT_PATH


## A saved week that still has days left.
func has_save() -> bool:
	var saved: WeekProgress = SaveStore.load_progress(save_path())
	return saved != null and not saved.is_week_complete()


func new_week() -> void:
	SaveStore.erase(save_path())
	progress = WeekProgress.new()
	start_day()


func continue_week() -> void:
	var saved: WeekProgress = SaveStore.load_progress(save_path())
	if saved == null or saved.is_week_complete():
		new_week()
		return
	progress = saved
	start_day()


func start_day() -> void:
	if _is_starting_day:
		return
	_is_starting_day = true
	_is_day_active = false
	SchoolClock.running = false
	if not test_mode and not _is_main_scene_current():
		get_tree().change_scene_to_file(MAIN_SCENE_PATH)
		await get_tree().scene_changed
	if not _find_actors():
		push_error("GameManager: main scene lacks a node in group player, target, teacher, crowd or school_env")
		_is_starting_day = false
		return
	if not _school_env.is_navigation_ready:
		await _school_env.navigation_ready
	_begin_day()
	_is_starting_day = false


func retry_day() -> void:
	progress.retry_seed()
	start_day()


func on_player_sat() -> void:
	if not _is_day_active or not SchoolClock.is_class_block() or attendance.has_sat:
		return
	attendance.on_player_sat(SchoolClock.model.seconds_into_block())
	# Deferred: sitting can happen inside a clock signal (a bell), and skipping the block from there would re-enter it.
	_fade.call_deferred(_sit_through_class)


func complete_day() -> void:
	if not _is_day_active:
		return
	_is_day_active = false
	if _current_block != null:
		attendance.on_block_ended(_current_block)
		_current_block = null
	var photo_score: int = 0
	for photo: Dictionary in day_run.photos:
		photo_score += int(photo["score"])
	var summary: Dictionary = {
		"photos": day_run.photos.duplicate(true),
		"photo_score": photo_score,
		"items": day_run.stashed_items.duplicate(),
		"intel_new": day_run.intel.duplicate(),
		"school_alert": SanitySystem.meters.school_alert,
	}
	progress.bank(day_run)
	var error: Error = SaveStore.save(progress, save_path())
	if error != OK:
		push_error("GameManager: could not save to %s (%s)" % [save_path(), error_string(error)])
	day_completed.emit(summary)
	if progress.is_week_complete():
		week_completed.emit(EndingResolver.resolve(progress.photo_score_total(), progress.banked_intel.size(), ending_tuning))


func _begin_day() -> void:
	_clear_items()
	SanitySystem.reset()
	day_run = DayRun.new()
	day_run.intel_unlocked.connect(_on_intel_unlocked)
	attendance = AttendanceTracker.new(SchoolClock.schedule.class_grace_real_seconds)
	attendance.penalty.connect(_on_attendance_penalty)
	_current_block = null
	_seconds_since_target_seen = 0.0
	_is_day_active = true
	SchoolClock.start_day()
	var model: SchoolClockModel = SchoolClock.model
	var meters: StealthMeters = SanitySystem.meters
	_target.clock = model
	_target.setup(_school_env, progress.day_seed, progress.history)
	_target.perception.watch(_player, meters)
	_crowd.meters = meters
	_crowd.clock = model
	_crowd.spawn(_school_env, progress.day_seed)
	var patrol_points: Array[Node3D] = _school_env.markers_with_prefix(TEACHER_PATROL_PREFIX)
	if not patrol_points.is_empty():
		_teacher.global_transform = patrol_points[0].global_transform
	_teacher.clock = model
	_teacher.target = _target
	_teacher.watch(_player, meters)
	_teacher.set_attendance(attendance)
	_teacher.setup(_school_env)
	_place_player()
	(_player.get_node(PHOTO_MODE_PATH) as PhotoMode).bind(_target, meters, day_run, progress.banked_intel, progress.day_index)
	(_player.get_node(YANDERE_VISION_PATH) as YandereVision).bind(_target, meters, day_run, progress.banked_intel)
	_on_sanity_changed(meters.sanity)
	day_started.emit(progress.day_index)


func _find_actors() -> bool:
	var tree: SceneTree = get_tree()
	_player = tree.get_first_node_in_group(PLAYER_GROUP) as StealthPlayer
	_target = tree.get_first_node_in_group(TARGET_GROUP) as TargetAI
	_teacher = tree.get_first_node_in_group(TEACHER_GROUP) as TeacherAI
	_crowd = tree.get_first_node_in_group(CROWD_GROUP) as CrowdSpawner
	_school_env = tree.get_first_node_in_group(SCHOOL_ENV_GROUP) as SchoolEnv
	if _player == null or _target == null or _teacher == null or _crowd == null or _school_env == null:
		return false
	for node: Node in _school_env.get_children():
		var stash_locker: StashLocker = node as StashLocker
		if stash_locker != null and not stash_locker.item_stashed.is_connected(_on_item_stashed):
			stash_locker.item_stashed.connect(_on_item_stashed)
		var seat: ClassSeat = node as ClassSeat
		if seat != null and seat.is_player_seat and not seat.player_sat.is_connected(on_player_sat):
			seat.player_sat.connect(on_player_sat)
	if not _player.tree_exiting.is_connected(_on_main_scene_left):
		_player.tree_exiting.connect(_on_main_scene_left)
	return true


func _is_main_scene_current() -> bool:
	var scene: Node = get_tree().current_scene
	return scene != null and scene.scene_file_path == MAIN_SCENE_PATH


## Items of a failed or finished attempt never carry over.
func _clear_items() -> void:
	for node: Node in get_tree().get_nodes_in_group(ItemPickup.YANDERE_ITEMS_GROUP):
		node.queue_free()


func _place_player() -> void:
	_player.exit_hidden()
	_player.exit_camera_mode()
	_player.stand_up()
	_player.drop_carried()
	_player.global_transform = _school_env.marker(PLAYER_SPAWN_MARKER).global_transform
	_player.velocity = Vector3.ZERO


func _fade(callback: Callable) -> void:
	if test_mode:
		callback.call()
	else:
		fade_callable.call(callback)


func _instant_fade(callback: Callable) -> void:
	callback.call()


func _sit_through_class() -> void:
	if not _is_day_active or not SchoolClock.is_class_block():
		return
	_target.snap_to_class_seat()
	_crowd.snap_all_to_seats()
	SchoolClock.skip_class()
	_player.stand_up()


func _on_block_changed(block: ScheduleBlock) -> void:
	if attendance == null:
		return
	if _current_block != null:
		attendance.on_block_ended(_current_block)
	_current_block = block
	attendance.on_block_started(block)


func _on_caught(reason: StringName) -> void:
	if not _is_day_active:
		return
	_is_day_active = false
	SchoolClock.stop()
	game_over.emit(reason)


func _on_main_scene_left() -> void:
	_is_day_active = false
	SchoolClock.stop()


func _on_attendance_penalty(reason: StringName) -> void:
	SanitySystem.meters.add_alert_spike(reason)


func _on_sanity_changed(value: float) -> void:
	if not is_instance_valid(_player):
		return
	_player.low_sanity_slow = value < stealth_tuning.low_sanity_threshold
	var shake: float = game_tuning.low_sanity_shake_strength if value < stealth_tuning.no_hide_sanity_threshold else 0.0
	(_player.get_node(CAMERA_RIG_PATH) as PlayerCameraRig).shake_strength = shake


func _on_minute_ticked(minute: float) -> void:
	if is_instance_valid(_school_env):
		_school_env.set_daylight(minute)


func _on_node_added(node: Node) -> void:
	var day_summary: DaySummary = node as DaySummary
	if day_summary != null:
		day_summary.ending_requested.connect(_on_ending_requested)
	var pickup: ItemPickup = node as ItemPickup
	if pickup != null:
		pickup.picked.connect(_on_item_picked)


## The final DaySummary hands over here (ruling R26): week_completed itself never changes the scene.
func _on_ending_requested(ending_id: StringName) -> void:
	get_tree().change_scene_to_file(ENDING_SCENE_PATH)
	await get_tree().scene_changed
	(get_tree().current_scene as EndingDirector).play(ending_id, progress)


func _on_item_picked(item_id: StringName) -> void:
	if not _is_day_active:
		return
	day_run.carried_item = item_id
	var definition: ItemDefinition = ItemPickup.definition_for(item_id)
	if definition != null:
		day_run.unlock_intel(definition.intel_card_id, progress.banked_intel)


func _on_item_stashed(item_id: StringName) -> void:
	if not _is_day_active:
		return
	day_run.stashed_items.append(item_id)
	day_run.carried_item = &""


func _on_intel_unlocked(card_id: StringName) -> void:
	var card: IntelCard = intel_catalog.find(card_id)
	if card != null:
		intel_unlocked.emit(card)
