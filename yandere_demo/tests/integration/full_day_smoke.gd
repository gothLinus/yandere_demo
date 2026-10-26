extends IntegrationTest
## One full day through GameManager on main.tscn at 16x with a scripted bot player: it stays hidden in HideLocker_01
## during free blocks and sits at PlayerSeat at every class bell, so it is never caught. "No push_error logged" is
## enforced by the base class, whose ErrorCollector Logger (OS.add_logger) fails the scene on any engine or script
## error.

const MAIN_SCENE: PackedScene = preload("res://scenes/main.tscn")
const SCHEDULE: ScheduleTable = preload("res://data/schedule_table.tres")
const TEST_SAVE_PATH: String = "user://test_save.json"
const TIME_SCALE: float = 16.0
const PHYSICS_STEPS_PER_TIME_SCALE: int = 8
const RANDOM_SEED: int = 18
const LOAD_ALLOWANCE_SECONDS: float = 60.0
const MINIMUM_DISTINCT_ACTIVITIES: int = 6
const SUMMARY_KEYS: Array[String] = ["photos", "photo_score", "items", "intel_new", "school_alert"]
const HIDE_LOCKER_NODE: String = "Interactable_HideLocker_01"
const PLAYER_SEAT_MARKER: String = "PlayerSeat"

var _school_env: SchoolEnv
var _player: StealthPlayer
var _hide_spot: HideSpot
var _activity_ids: Array[StringName] = []
var _class_bells: int = 0
var _previous_time_scale: float
var _previous_max_steps: int


func _ready() -> void:
	timeout_seconds = _full_day_real_seconds() / TIME_SCALE + LOAD_ALLOWANCE_SECONDS
	SaveStore.erase(TEST_SAVE_PATH)
	add_child(MAIN_SCENE.instantiate())
	_school_env = get_tree().get_first_node_in_group(&"school_env") as SchoolEnv
	_player = get_tree().get_first_node_in_group(&"player") as StealthPlayer
	var target: TargetAI = get_tree().get_first_node_in_group(&"target") as TargetAI
	target.activity_started.connect(_on_activity_started)
	# The bot hides all day, so its Sanity drains below the no-hide threshold; hiding is its only safety.
	_player.can_hide_callable = func() -> bool: return true
	GameManager.test_mode = true
	GameManager.day_started.connect(_on_day_started, CONNECT_ONE_SHOT)
	GameManager.day_completed.connect(_on_day_completed)
	GameManager.game_over.connect(_on_game_over)
	SchoolClock.bell_rang.connect(_on_bell_rang)
	_previous_time_scale = Engine.time_scale
	_previous_max_steps = Engine.max_physics_steps_per_frame
	Engine.time_scale = TIME_SCALE
	Engine.max_physics_steps_per_frame = maxi(_previous_max_steps, int(PHYSICS_STEPS_PER_TIME_SCALE * TIME_SCALE))
	seed(RANDOM_SEED)
	GameManager.new_week()


func _on_day_started(_day_index: int) -> void:
	_hide_spot = _school_env.get_node(HIDE_LOCKER_NODE) as HideSpot
	_hide()


func _on_bell_rang(block: ScheduleBlock) -> void:
	if block.kind != GameTypes.BlockKind.CLASS:
		_hide()
		return
	_class_bells += 1
	if _player.mode == StealthPlayer.MODE_HIDDEN:
		_hide_spot.interact(_player)
	_player.global_transform = _school_env.marker(PLAYER_SEAT_MARKER).global_transform
	GameManager.on_player_sat()


func _hide() -> void:
	if _player.mode != StealthPlayer.MODE_HIDDEN:
		_hide_spot.interact(_player)
	if _player.mode != StealthPlayer.MODE_HIDDEN:
		fail_test("the bot could not hide in %s (mode %s)" % [HIDE_LOCKER_NODE, _player.mode])


func _on_activity_started(activity: ActivityDefinition) -> void:
	if not _activity_ids.has(activity.id):
		_activity_ids.append(activity.id)


func _on_game_over(reason: StringName) -> void:
	fail_test("the hidden bot was caught: %s" % reason)


func _on_day_completed(summary: Dictionary) -> void:
	_restore_time_scale()
	print("distinct activities: %s; class bells: %d; summary: %s" % [_activity_ids, _class_bells, summary])
	var failures: PackedStringArray = PackedStringArray()
	for key: String in SUMMARY_KEYS:
		if not summary.has(key):
			failures.append("the summary has no '%s'" % key)
	if GameManager.progress.day_index != 1:
		failures.append("day_index is %d after the first day, not 1" % GameManager.progress.day_index)
	if _activity_ids.size() < MINIMUM_DISTINCT_ACTIVITIES:
		failures.append("only %d distinct activities started: %s" % [_activity_ids.size(), _activity_ids])
	if _class_bells != 2:
		failures.append("%d class bells rang, not 2" % _class_bells)
	if SaveStore.load_progress(TEST_SAVE_PATH) == null:
		failures.append("no loadable save at %s" % TEST_SAVE_PATH)
	SaveStore.erase(TEST_SAVE_PATH)
	if failures.is_empty():
		pass_test()
	else:
		fail_test("; ".join(failures))


func _full_day_real_seconds() -> float:
	var total: float = 0.0
	for block: ScheduleBlock in SCHEDULE.blocks:
		total += block.real_seconds
	return total


func _restore_time_scale() -> void:
	Engine.time_scale = _previous_time_scale
	Engine.max_physics_steps_per_frame = _previous_max_steps


func _exit_tree() -> void:
	_restore_time_scale()
	SaveStore.erase(TEST_SAVE_PATH)
