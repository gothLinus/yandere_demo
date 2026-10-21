class_name DayRun
extends RefCounted

var photos: Array[Dictionary] = []
var stashed_items: Array[StringName] = []
var carried_item: StringName = &""
var intel: Array[StringName] = []


func add_photo(path: String, score: int, day_index: int) -> void:
	photos.append({"path": path, "score": score, "day": day_index})


func unlock_intel(card_id: StringName, banked: Array[StringName]) -> bool:
	if card_id == &"" or intel.has(card_id) or banked.has(card_id):
		return false
	intel.append(card_id)
	return true
