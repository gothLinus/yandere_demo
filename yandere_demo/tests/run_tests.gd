extends SceneTree

const UNIT_DIRECTORY: String = "res://tests/unit"


class ErrorCollector:
	extends Logger

	var _mutex: Mutex = Mutex.new()
	var _errors: Array[String] = []

	func _log_error(
		function: String,
		file: String,
		line: int,
		code: String,
		rationale: String,
		_editor_notify: bool,
		error_type: int,
		_script_backtraces: Array[ScriptBacktrace]
	) -> void:
		if error_type == Logger.ERROR_TYPE_WARNING:
			return
		var text: String = rationale if not rationale.is_empty() else code
		_mutex.lock()
		_errors.append("%s (%s:%d in %s)" % [text, file, line, function])
		_mutex.unlock()

	func clear() -> void:
		_mutex.lock()
		_errors.clear()
		_mutex.unlock()

	func take_errors() -> Array[String]:
		_mutex.lock()
		var taken: Array[String] = _errors.duplicate()
		_errors.clear()
		_mutex.unlock()
		return taken


func _init() -> void:
	var collector: ErrorCollector = ErrorCollector.new()
	OS.add_logger(collector)
	var failed_count: int = 0
	var passed_count: int = 0
	var test_files: Array[String] = _list_test_files()
	for file_name: String in test_files:
		var path: String = "%s/%s" % [UNIT_DIRECTORY, file_name]
		var script: GDScript = load(path) as GDScript
		if script == null or not script.can_instantiate():
			print("FAIL %s: script failed to load" % path)
			failed_count += 1
			continue
		for method_name: String in _list_test_methods(script):
			collector.clear()
			var test_case: TestCase = script.new() as TestCase
			if test_case == null:
				print("FAIL %s::%s: script does not extend TestCase" % [path, method_name])
				failed_count += 1
				continue
			test_case.before_each()
			test_case.call(method_name)
			test_case.after_each()
			var messages: Array[String] = test_case.failures.duplicate()
			for error_text: String in collector.take_errors():
				messages.append("runtime error: %s" % error_text)
			if messages.is_empty():
				print("PASS %s::%s" % [path, method_name])
				passed_count += 1
			else:
				print("FAIL %s::%s: %s" % [path, method_name, " | ".join(messages)])
				failed_count += 1
	OS.remove_logger(collector)
	if passed_count + failed_count == 0:
		print("FAIL no tests found in %s" % UNIT_DIRECTORY)
		failed_count += 1
	print("%d passed, %d failed" % [passed_count, failed_count])
	quit(1 if failed_count > 0 else 0)


func _list_test_files() -> Array[String]:
	var files: Array[String] = []
	for file_name: String in DirAccess.get_files_at(UNIT_DIRECTORY):
		var clean_name: String = file_name.trim_suffix(".remap")
		if clean_name.begins_with("test_") and clean_name.ends_with(".gd"):
			files.append(clean_name)
	files.sort()
	return files


func _list_test_methods(script: GDScript) -> Array[String]:
	var methods: Array[String] = []
	for method_info: Dictionary in script.get_script_method_list():
		var method_name: String = method_info["name"]
		if method_name.begins_with("test_"):
			methods.append(method_name)
	methods.sort()
	return methods
