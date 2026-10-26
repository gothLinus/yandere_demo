class_name ExpressionController
extends Node
## Drives a model's face shape keys: one expression at a time, plus a blink on a random timer.

const BLINK_SHAPE: StringName = &"blink"

@export var model_path: NodePath
@export var tuning: TargetTuning = preload("res://data/target_tuning.tres")

var expression: StringName = &""

var _meshes: Array[MeshInstance3D] = []
var _expression_tween: Tween
var _blink_tween: Tween
var _seconds_to_blink: float = 0.0
var _random: RandomNumberGenerator = RandomNumberGenerator.new()


func _ready() -> void:
	var model: Node = get_node_or_null(model_path)
	if model == null:
		push_error("ExpressionController: no model at %s" % model_path)
		return
	for node: Node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance: MeshInstance3D = node as MeshInstance3D
		if mesh_instance.mesh != null and mesh_instance.mesh.get_blend_shape_count() > 0:
			_meshes.append(mesh_instance)
	_random.randomize()
	_seconds_to_blink = _next_blink_delay()


func _process(delta: float) -> void:
	_seconds_to_blink -= delta
	if _seconds_to_blink <= 0.0:
		_blink()
		_seconds_to_blink = _next_blink_delay()


func set_expression(new_expression: StringName, blend_seconds: float = 0.25) -> void:
	expression = new_expression
	if _expression_tween != null:
		_expression_tween.kill()
	_expression_tween = null
	for mesh_instance: MeshInstance3D in _meshes:
		if _shape_index(mesh_instance, new_expression) < 0:
			continue
		for index: int in mesh_instance.mesh.get_blend_shape_count():
			var shape_name: StringName = mesh_instance.mesh.get_blend_shape_name(index)
			if shape_name == BLINK_SHAPE:
				continue
			var value: float = 1.0 if shape_name == new_expression else 0.0
			if blend_seconds <= 0.0:
				mesh_instance.set_blend_shape_value(index, value)
				continue
			if _expression_tween == null:
				_expression_tween = create_tween().set_parallel(true)
			_expression_tween.tween_property(mesh_instance, "blend_shapes/%s" % shape_name, value, blend_seconds)


func _blink() -> void:
	if _blink_tween != null:
		_blink_tween.kill()
	_blink_tween = null
	var half: float = tuning.blink_seconds * 0.5
	for mesh_instance: MeshInstance3D in _meshes:
		if _shape_index(mesh_instance, BLINK_SHAPE) < 0:
			continue
		if _blink_tween == null:
			_blink_tween = create_tween().set_parallel(true)
		var property: String = "blend_shapes/%s" % BLINK_SHAPE
		_blink_tween.tween_property(mesh_instance, property, 1.0, half)
		_blink_tween.tween_property(mesh_instance, property, 0.0, half).set_delay(half)


func _next_blink_delay() -> float:
	return _random.randf_range(tuning.blink_min_seconds, tuning.blink_max_seconds)


func _shape_index(mesh_instance: MeshInstance3D, shape_name: StringName) -> int:
	return mesh_instance.find_blend_shape_by_name(shape_name)
