class_name SaveStore
extends RefCounted

const DEFAULT_PATH: String = "user://save.json"


static func save(progress: WeekProgress, path: String = DEFAULT_PATH) -> Error:
	var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return FileAccess.get_open_error()
	file.store_string(JSON.stringify(progress.to_dictionary()))
	file.close()
	return OK


static func load_progress(path: String = DEFAULT_PATH) -> WeekProgress:
	if not FileAccess.file_exists(path):
		return null
	var file: FileAccess = FileAccess.open(path, FileAccess.READ)
	if file == null:
		return null
	var text: String = file.get_as_text()
	file.close()
	var parser: JSON = JSON.new()
	if parser.parse(text) != OK:
		return null
	if not parser.data is Dictionary:
		return null
	var data: Dictionary = parser.data
	return WeekProgress.from_dictionary(data)


static func erase(path: String = DEFAULT_PATH) -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
