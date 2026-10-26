extends IntegrationTest
## Day 0 through GameManager on main.tscn: a forced Suspicion spike of 100 makes the target report, which fires
## game_over(&"target_report") once and stops the clock. retry_day() then restarts day 0 with a new seed, reset
## meters, an empty run and the clock back at 07:00.

const MAIN_SCENE: PackedScene = preload("res://scenes/main.tscn")
const TEST_SAVE_PATH: String = "user://test_save.json"
const SETTLE_FRAMES: int = 10
const FIRST_DAY_TEXT: String = "Mon 07:00"

var _game_over_reasons: Array[StringName] = []
var _days_started: int = 0


func _ready() -> void:
	SaveStore.erase(TEST_SAVE_PATH)
	add_child(MAIN_SCENE.instantiate())
	GameManager.test_mode = true
	GameManager.game_over.connect(func(reason: StringName) -> void: _game_over_reasons.append(reason))
	GameManager.day_started.connect(func(_day_index: int) -> void: _days_started += 1)
	GameManager.new_week()
	await _wait_for_days_started(1)
	var failure: String = await _run_scenario()
	SaveStore.erase(TEST_SAVE_PATH)
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _run_scenario() -> String:
	var first_seed: int = GameManager.progress.day_seed
	GameManager.day_run.add_photo("", 50, 0)
	await _settle()
	SanitySystem.meters.add_suspicion_spike(100.0)
	await _settle()
	if _game_over_reasons.size() != 1 or _game_over_reasons[0] != &"target_report":
		return "game_over fired %s, not once with target_report" % [_game_over_reasons]
	if SchoolClock.running:
		return "the clock still runs after game over"
	var stopped_minute: float = SchoolClock.model.current_minute
	await _settle()
	if SchoolClock.model.current_minute != stopped_minute:
		return "the clock advanced after game over (%.3f -> %.3f)" % [stopped_minute, SchoolClock.model.current_minute]
	if Engine.time_scale != 1.0:
		return "time_scale is %.1f after game over" % Engine.time_scale
	GameManager.retry_day()
	await _wait_for_days_started(2)
	var meters: StealthMeters = SanitySystem.meters
	var target: TargetAI = get_tree().get_first_node_in_group(&"target") as TargetAI
	if GameManager.progress.day_index != 0:
		return "retry moved to day %d" % GameManager.progress.day_index
	if GameManager.progress.day_seed == first_seed:
		return "retry kept the seed %d" % first_seed
	if meters.suspicion != 0.0 or meters.school_alert != 0.0 or meters.sanity != 100.0:
		return "meters not reset: suspicion %.1f, alert %.1f, sanity %.1f" % [meters.suspicion, meters.school_alert, meters.sanity]
	if not GameManager.day_run.photos.is_empty():
		return "the failed attempt's photos survived the retry"
	if not SchoolClock.running or SchoolClock.model.clock_text(0) != FIRST_DAY_TEXT:
		return "the clock is not running from 07:00 (running %s, %s)" % [SchoolClock.running, SchoolClock.model.clock_text(0)]
	if target.state == TargetAI.State.REPORTING:
		return "the target is still reporting after the retry"
	if _game_over_reasons.size() != 1:
		return "game_over fired again after the retry: %s" % [_game_over_reasons]
	return ""


func _wait_for_days_started(count: int) -> void:
	while _days_started < count:
		await get_tree().process_frame


func _settle() -> void:
	for frame: int in SETTLE_FRAMES:
		await get_tree().physics_frame


func _exit_tree() -> void:
	SaveStore.erase(TEST_SAVE_PATH)
