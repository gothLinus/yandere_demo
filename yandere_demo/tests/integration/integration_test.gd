class_name IntegrationTest
extends Node
## Base of every integration scene. pass_test() turns into a FAIL when any engine or script error was raised while
## the scene ran: a script error aborts the scenario coroutine, which then returns its default value to the caller and
## would otherwise read as success.

@export var timeout_seconds: float = 60.0

var _elapsed_seconds: float = 0.0
var _finished: bool = false
var _error_collector: ErrorCollector = ErrorCollector.new()


## _notification runs in every class of the hierarchy, so scenes that override _ready or _exit_tree keep the collector.
func _notification(what: int) -> void:
	if what == NOTIFICATION_ENTER_TREE:
		OS.add_logger(_error_collector)
	elif what == NOTIFICATION_EXIT_TREE:
		OS.remove_logger(_error_collector)


func _process(delta: float) -> void:
	if _finished:
		return
	_elapsed_seconds += delta / maxf(Engine.time_scale, 0.001)
	if _elapsed_seconds >= timeout_seconds:
		fail_test("timeout")


func pass_test() -> void:
	var errors: Array[String] = _error_collector.take_errors()
	if not errors.is_empty():
		fail_test("%d error(s) raised during the scenario: %s" % [errors.size(), " | ".join(errors)])
		return
	if _finished:
		return
	_finished = true
	print("INTEGRATION PASS %s" % _scene_name())
	get_tree().quit(0)


func fail_test(message: String) -> void:
	if _finished:
		return
	_finished = true
	print("INTEGRATION FAIL %s: %s" % [_scene_name(), message])
	get_tree().quit(1)


func _scene_name() -> String:
	var scene: Node = get_tree().current_scene
	return scene.scene_file_path if scene != null else str(name)
