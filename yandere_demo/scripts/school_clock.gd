extends Node
## Autoload: the day's clock (spec §4.3). Wraps a SchoolClockModel, advances it while running, re-emits its signals,
## rings the bell on entering every block after the first, and owns fast-forward.

signal block_changed(block: ScheduleBlock)
signal bell_rang(block: ScheduleBlock)
signal day_ended()
## Every GameTuning.daylight_tick_seconds while running, and once at start_day().
signal minute_ticked(minute: float)

const PLAYER_GROUP: StringName = &"player"
const NORMAL_TIME_SCALE: float = 1.0

@export var schedule: ScheduleTable = preload("res://data/schedule_table.tres")
@export var tuning: GameTuning = preload("res://data/game_tuning.tres")

## Null until the first start_day(), so actors outside a running day keep their injected or permissive defaults.
var model: SchoolClockModel
var running: bool = false

var _is_fast_forwarding: bool = false
var _seconds_since_tick: float = 0.0


func _process(delta: float) -> void:
	_update_fast_forward()
	if not running:
		return
	model.advance(delta)
	_seconds_since_tick += delta
	if running and _seconds_since_tick >= tuning.daylight_tick_seconds:
		_seconds_since_tick = 0.0
		minute_ticked.emit(model.current_minute)


func _notification(what: int) -> void:
	if what == NOTIFICATION_PAUSED or what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		reset_time_scale()


## A fresh day at the first block's start; announces that block (without a bell) and the first minute.
func start_day() -> void:
	model = SchoolClockModel.new(schedule)
	model.block_changed.connect(_on_model_block_changed)
	model.day_ended.connect(_on_model_day_ended)
	_seconds_since_tick = 0.0
	running = true
	block_changed.emit(model.current_block())
	minute_ticked.emit(model.current_minute)


## Stops the clock where it is (game over, leaving the day).
func stop() -> void:
	running = false
	reset_time_scale()


func skip_class() -> void:
	if is_class_block():
		model.skip_to_block_end()


func is_class_block() -> bool:
	return model != null and not model.is_day_over() and model.current_block().kind == GameTypes.BlockKind.CLASS


func reset_time_scale() -> void:
	_is_fast_forwarding = false
	Engine.time_scale = NORMAL_TIME_SCALE


## Writes Engine.time_scale only when the wish changes, so a test's own time scale is never overwritten.
func _update_fast_forward() -> void:
	var wants_fast_forward: bool = running and Input.is_action_pressed(&"fast_forward") and not _is_player_in_camera_mode()
	if wants_fast_forward == _is_fast_forwarding:
		return
	_is_fast_forwarding = wants_fast_forward
	Engine.time_scale = tuning.fast_forward_time_scale if wants_fast_forward else NORMAL_TIME_SCALE


func _is_player_in_camera_mode() -> bool:
	var player: StealthPlayer = get_tree().get_first_node_in_group(PLAYER_GROUP) as StealthPlayer
	return player != null and player.mode == StealthPlayer.MODE_CAMERA


func _on_model_block_changed(block: ScheduleBlock) -> void:
	block_changed.emit(block)
	bell_rang.emit(block)


func _on_model_day_ended() -> void:
	running = false
	reset_time_scale()
	day_ended.emit()
