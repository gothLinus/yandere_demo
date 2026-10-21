class_name ActivityHistory
extends RefCounted

var today_ids: Array[StringName] = []
var today_by_block: Dictionary = {}
var yesterday_by_block: Dictionary = {}


func record(block_id: StringName, activity_id: StringName) -> void:
	today_ids.append(activity_id)
	if not today_by_block.has(block_id):
		today_by_block[block_id] = [] as Array[StringName]
	var block_ids: Array[StringName] = today_by_block[block_id]
	block_ids.append(activity_id)


func roll_over() -> void:
	yesterday_by_block = today_by_block
	today_by_block = {}
	today_ids = [] as Array[StringName]


func clear_today() -> void:
	today_by_block = {}
	today_ids = [] as Array[StringName]


func to_dictionary() -> Dictionary:
	return {
		"today_ids": _to_strings(today_ids),
		"today_by_block": _block_map_to_strings(today_by_block),
		"yesterday_by_block": _block_map_to_strings(yesterday_by_block),
	}


static func from_dictionary(data: Dictionary) -> ActivityHistory:
	var history: ActivityHistory = ActivityHistory.new()
	history.today_ids = _to_string_names(data.get("today_ids", []))
	history.today_by_block = _block_map_to_string_names(data.get("today_by_block", {}))
	history.yesterday_by_block = _block_map_to_string_names(data.get("yesterday_by_block", {}))
	return history


static func _to_strings(source: Array) -> Array[String]:
	var result: Array[String] = []
	for entry: Variant in source:
		result.append(String(entry))
	return result


static func _to_string_names(source: Array) -> Array[StringName]:
	var result: Array[StringName] = []
	for entry: Variant in source:
		result.append(StringName(entry))
	return result


static func _block_map_to_strings(source: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for block_id: Variant in source:
		result[String(block_id)] = _to_strings(source[block_id])
	return result


static func _block_map_to_string_names(source: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for block_id: Variant in source:
		result[StringName(block_id)] = _to_string_names(source[block_id])
	return result
