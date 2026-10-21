class_name WeekProgress
extends RefCounted

const SAVE_VERSION: int = 1
const DAYS_IN_WEEK: int = 5

var day_index: int = 0
var banked_photos: Array[Dictionary] = []
var banked_items: Array[StringName] = []
var banked_intel: Array[StringName] = []
var history: ActivityHistory
var day_seed: int = 0


func _init() -> void:
	history = ActivityHistory.new()
	_roll_new_seed()


func bank(run: DayRun) -> void:
	banked_photos.append_array(run.photos)
	banked_items.append_array(run.stashed_items)
	for card_id: StringName in run.intel:
		if not banked_intel.has(card_id):
			banked_intel.append(card_id)
	run.carried_item = &""
	history.roll_over()
	day_index += 1
	_roll_new_seed()


func retry_seed() -> void:
	_roll_new_seed()
	history.clear_today()


func is_week_complete() -> bool:
	return day_index >= DAYS_IN_WEEK


func photo_score_total() -> int:
	var total: int = 0
	for photo: Dictionary in banked_photos:
		total += int(photo["score"])
	return total


func to_dictionary() -> Dictionary:
	return {
		"version": SAVE_VERSION,
		"day_index": day_index,
		"banked_photos": banked_photos.duplicate(true),
		"banked_items": _to_strings(banked_items),
		"banked_intel": _to_strings(banked_intel),
		"history": history.to_dictionary(),
		"day_seed": day_seed,
	}


static func from_dictionary(data: Dictionary) -> WeekProgress:
	var required_types: Dictionary = {
		"version": [TYPE_INT, TYPE_FLOAT],
		"day_index": [TYPE_INT, TYPE_FLOAT],
		"banked_photos": [TYPE_ARRAY],
		"banked_items": [TYPE_ARRAY],
		"banked_intel": [TYPE_ARRAY],
		"history": [TYPE_DICTIONARY],
		"day_seed": [TYPE_INT, TYPE_FLOAT],
	}
	for key: String in required_types:
		if not data.has(key):
			return null
		var allowed_types: Array = required_types[key]
		if not allowed_types.has(typeof(data[key])):
			return null
	if int(data["version"]) != SAVE_VERSION:
		return null
	var progress: WeekProgress = WeekProgress.new()
	progress.day_index = int(data["day_index"])
	progress.day_seed = int(data["day_seed"])
	var photos: Array = data["banked_photos"]
	for entry: Variant in photos:
		if not entry is Dictionary:
			return null
		var photo: Dictionary = entry
		if not (photo.has("path") and photo.has("score") and photo.has("day")):
			return null
		progress.banked_photos.append({
			"path": String(photo["path"]),
			"score": int(photo["score"]),
			"day": int(photo["day"]),
		})
	progress.banked_items = _to_string_names(data["banked_items"])
	progress.banked_intel = _to_string_names(data["banked_intel"])
	progress.history = ActivityHistory.from_dictionary(data["history"])
	return progress


func _roll_new_seed() -> void:
	var previous_seed: int = day_seed
	while day_seed == previous_seed or day_seed == 0:
		day_seed = randi()


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
