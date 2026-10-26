class_name CharacterBodyShape
extends Node

const FALLBACK_RADIUS: float = 0.22
const FALLBACK_HEIGHT: float = 1.6

@export var model_path: NodePath

var collision_shape: CollisionShape3D

var _standing_height: float = FALLBACK_HEIGHT


func _ready() -> void:
	var body: CharacterBody3D = get_parent() as CharacterBody3D
	if body == null:
		push_error("CharacterBodyShape must be a child of a CharacterBody3D")
		return
	var model: Node = get_node_or_null(model_path)
	var shape: Shape3D = model.get_meta("body_shape", null) as Shape3D if model != null else null
	collision_shape = CollisionShape3D.new()
	collision_shape.name = "CollisionShape3D"
	if shape == null:
		var capsule: CapsuleShape3D = CapsuleShape3D.new()
		capsule.radius = FALLBACK_RADIUS
		capsule.height = FALLBACK_HEIGHT
		collision_shape.shape = capsule
		collision_shape.position.y = FALLBACK_HEIGHT * 0.5
	else:
		collision_shape.shape = shape
	_standing_height = _measure_height(collision_shape.shape)
	body.add_child.call_deferred(collision_shape)


## Scaling the shape node keeps its feet on the body origin; both the convex import and the capsule fallback accept it.
func set_height_ratio(ratio: float) -> void:
	if collision_shape != null:
		collision_shape.scale.y = ratio


func set_enabled(enabled: bool) -> void:
	if collision_shape != null:
		collision_shape.disabled = not enabled


func height() -> float:
	if collision_shape == null:
		return 0.0
	return _standing_height * collision_shape.scale.y


func _measure_height(shape: Shape3D) -> float:
	if shape is ConvexPolygonShape3D:
		var points: PackedVector3Array = (shape as ConvexPolygonShape3D).points
		if points.is_empty():
			return FALLBACK_HEIGHT
		var lowest: float = points[0].y
		var highest: float = points[0].y
		for point: Vector3 in points:
			lowest = minf(lowest, point.y)
			highest = maxf(highest, point.y)
		return highest - lowest
	return (shape as CapsuleShape3D).height
