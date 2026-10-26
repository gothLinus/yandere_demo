class_name SchoolClockModel
extends RefCounted

signal block_changed(block: ScheduleBlock)
signal day_ended()

var current_minute: float
var _table: ScheduleTable
var _block_index: int = 0
var _day_over: bool = false


func _init(table: ScheduleTable) -> void:
	_table = table
	current_minute = float(table.blocks[0].start_minute)


func advance(real_delta: float) -> void:
	var remaining_seconds: float = real_delta
	while remaining_seconds > 0.0 and not _day_over:
		var block: ScheduleBlock = current_block()
		var rate: float = block.game_minutes_per_second()
		var seconds_to_block_end: float = (float(block.end_minute) - current_minute) / rate
		if remaining_seconds < seconds_to_block_end:
			current_minute += remaining_seconds * rate
			return
		remaining_seconds -= seconds_to_block_end
		_enter_next_block()


func current_block() -> ScheduleBlock:
	return _table.blocks[_block_index]


func skip_to_block_end() -> void:
	if _day_over:
		return
	_enter_next_block()


func seconds_into_block() -> float:
	var block: ScheduleBlock = current_block()
	return (current_minute - float(block.start_minute)) / block.game_minutes_per_second()


func is_day_over() -> bool:
	return _day_over


func clock_text(day_index: int) -> String:
	var total_minutes: int = floori(current_minute)
	return "%s %02d:%02d" % [GameTypes.WEEKDAY_NAMES[clampi(day_index, 0, GameTypes.WEEKDAY_NAMES.size() - 1)], floori(total_minutes / 60.0), total_minutes % 60]


func _enter_next_block() -> void:
	current_minute = float(current_block().end_minute)
	if _block_index + 1 >= _table.blocks.size():
		_day_over = true
		day_ended.emit()
		return
	_block_index += 1
	block_changed.emit(current_block())
