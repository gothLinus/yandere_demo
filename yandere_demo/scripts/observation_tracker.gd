class_name ObservationTracker
extends Node
## Intel from watching (spec §4.7): an activity watched for most of its real length without ever alarming him unlocks
## its card.

var tuning: StealthTuning = preload("res://data/stealth_tuning.tres")
var player: StealthPlayer
var target: TargetAI
var meters: StealthMeters
var day_run: DayRun
var banked_intel: Array[StringName] = []
var watched_seconds: float = 0.0

var _activity_seconds: float = 0.0
var _is_tracking: bool = false
var _was_noticed: bool = false


func bind(watching_player: StealthPlayer, new_target: TargetAI, new_meters: StealthMeters, new_day_run: DayRun, new_banked_intel: Array[StringName]) -> void:
	_disconnect_previous()
	_is_tracking = false
	watched_seconds = 0.0
	_activity_seconds = 0.0
	_was_noticed = false
	player = watching_player
	target = new_target
	meters = new_meters
	day_run = new_day_run
	banked_intel = new_banked_intel
	target.activity_started.connect(_on_activity_started)
	target.activity_completed.connect(_on_activity_completed)
	meters.noticed.connect(_on_noticed)


func _disconnect_previous() -> void:
	if is_instance_valid(target):
		if target.activity_started.is_connected(_on_activity_started):
			target.activity_started.disconnect(_on_activity_started)
		if target.activity_completed.is_connected(_on_activity_completed):
			target.activity_completed.disconnect(_on_activity_completed)
	if meters != null and meters.noticed.is_connected(_on_noticed):
		meters.noticed.disconnect(_on_noticed)


func _physics_process(delta: float) -> void:
	if not _is_tracking:
		return
	_activity_seconds += delta
	var head: Vector3 = target.head_position()
	var within_range: bool = player.head_position().distance_to(head) <= tuning.observation_watch_distance
	var is_watching: bool = player.is_watching(head, player.get_world_3d().direct_space_state, tuning.observation_watch_distance)
	if is_watching or (player.is_vision_active and within_range):
		watched_seconds += delta


func _on_activity_started(_activity: ActivityDefinition) -> void:
	_is_tracking = true
	watched_seconds = 0.0
	_activity_seconds = 0.0
	_was_noticed = meters.is_noticed()


func _on_activity_completed(activity: ActivityDefinition) -> void:
	if not _is_tracking:
		return
	_is_tracking = false
	if _was_noticed or watched_seconds < tuning.observation_watched_fraction * _activity_seconds:
		return
	day_run.unlock_intel(activity.intel_card_id, banked_intel)


func _on_noticed() -> void:
	_was_noticed = true
