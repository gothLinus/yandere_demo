class_name SenseIcon
extends Control
## An eye while the target sees the player, an ear while he hears footsteps; blank otherwise.

enum Sense { NONE, SEEN, HEARD }

const LINE_WIDTH: float = 2.5
const ICON_COLOR: Color = Color("ff8fb8")

var sense: Sense = Sense.NONE:
	set(value):
		sense = value
		queue_redraw()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _draw() -> void:
	var center: Vector2 = size * 0.5
	var radius: float = minf(size.x, size.y) * 0.5 - LINE_WIDTH
	match sense:
		Sense.SEEN:
			draw_arc(center + Vector2(0.0, radius * 0.9), radius * 1.5, deg_to_rad(-135.0), deg_to_rad(-45.0), 16, ICON_COLOR, LINE_WIDTH)
			draw_arc(center - Vector2(0.0, radius * 0.9), radius * 1.5, deg_to_rad(45.0), deg_to_rad(135.0), 16, ICON_COLOR, LINE_WIDTH)
			draw_circle(center, radius * 0.38, ICON_COLOR)
		Sense.HEARD:
			draw_arc(center + Vector2(radius * 0.1, 0.0), radius, deg_to_rad(-200.0), deg_to_rad(20.0), 24, ICON_COLOR, LINE_WIDTH)
			draw_arc(center + Vector2(radius * 0.1, radius * 0.2), radius * 0.5, deg_to_rad(-180.0), deg_to_rad(10.0), 16, ICON_COLOR, LINE_WIDTH)
