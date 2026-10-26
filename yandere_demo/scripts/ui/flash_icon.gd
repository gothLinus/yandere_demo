class_name FlashIcon
extends Control
## A lightning bolt: pink while the flash is on, dimmed while it is off.

const LIT_COLOR: Color = Color("ff8fb8")
const DIMMED_COLOR: Color = Color(1.0, 1.0, 1.0, 0.3)
## Bolt outline in a unit box.
const BOLT_POINTS: PackedVector2Array = [
	Vector2(0.62, 0.0), Vector2(0.1, 0.56), Vector2(0.46, 0.56),
	Vector2(0.32, 1.0), Vector2(0.9, 0.38), Vector2(0.54, 0.38),
]

var is_lit: bool = false:
	set(value):
		is_lit = value
		queue_redraw()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _draw() -> void:
	var points: PackedVector2Array = PackedVector2Array()
	for point: Vector2 in BOLT_POINTS:
		points.append(point * size)
	draw_colored_polygon(points, LIT_COLOR if is_lit else DIMMED_COLOR)
