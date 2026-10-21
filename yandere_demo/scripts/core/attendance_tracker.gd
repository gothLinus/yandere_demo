class_name AttendanceTracker
extends RefCounted

signal penalty(reason: StringName)

var has_sat: bool = false

var _grace_real_seconds: float
var _current_block: ScheduleBlock


func _init(grace_real_seconds: float) -> void:
	_grace_real_seconds = grace_real_seconds


func on_block_started(block: ScheduleBlock) -> void:
	_current_block = block
	has_sat = false


func on_player_sat(seconds_into_block: float) -> void:
	if _current_block == null or _current_block.kind != GameTypes.BlockKind.CLASS or has_sat:
		return
	has_sat = true
	if seconds_into_block > _grace_real_seconds:
		penalty.emit(&"late")


func on_block_ended(block: ScheduleBlock) -> void:
	if block.kind == GameTypes.BlockKind.CLASS and not has_sat:
		penalty.emit(&"skipped_class")


func is_class_in_session(seconds_into_block: float) -> bool:
	return (
		_current_block != null
		and _current_block.kind == GameTypes.BlockKind.CLASS
		and seconds_into_block > _grace_real_seconds
	)
