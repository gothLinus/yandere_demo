class_name ClockFace
extends Control
## An analogue clock face drawn from a game minute, so a tween over the minute spins the hands.

const FACE_COLOR: Color = Color("ff8fb8")
const HOUR_HAND_RATIO: float = 0.5
const MINUTE_HAND_RATIO: float = 0.8

var minute_of_day: float = 0.0:
	set(value):
		minute_of_day = value
		queue_redraw()


func _draw() -> void:
	var center: Vector2 = size * 0.5
	var radius: float = minf(size.x, size.y) * 0.5 - 4.0
	draw_arc(center, radius, 0.0, TAU, 48, FACE_COLOR, 4.0)
	var hour_angle: float = TAU * fposmod(minute_of_day / 60.0, 12.0) / 12.0
	var minute_angle: float = TAU * fposmod(minute_of_day, 60.0) / 60.0
	draw_line(center, center + Vector2.UP.rotated(hour_angle) * radius * HOUR_HAND_RATIO, FACE_COLOR, 5.0)
	draw_line(center, center + Vector2.UP.rotated(minute_angle) * radius * MINUTE_HAND_RATIO, Color.WHITE, 3.0)
