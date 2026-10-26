class_name ErrorCollector
extends Logger
## Collects every engine and script error (warnings excluded), so a test fails on any error it raised.

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
