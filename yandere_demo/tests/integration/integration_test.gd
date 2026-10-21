class_name IntegrationTest
extends Node

@export var timeout_seconds: float = 60.0

var _elapsed_seconds: float = 0.0
var _finished: bool = false


func _process(delta: float) -> void:
	if _finished:
		return
	_elapsed_seconds += delta / maxf(Engine.time_scale, 0.001)
	if _elapsed_seconds >= timeout_seconds:
		fail_test("timeout")


func pass_test() -> void:
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
