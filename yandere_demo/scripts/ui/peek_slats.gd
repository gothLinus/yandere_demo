class_name PeekSlats
extends Control
## The view from inside a locker: dark door metal with a few horizontal vent slits across the middle of the screen.

const SLIT_COUNT: int = 3
const SLIT_HEIGHT_RATIO: float = 0.1
const BAR_HEIGHT_RATIO: float = 0.05
const METAL_COLOR: Color = Color(0.06, 0.07, 0.09, 0.94)


func _ready() -> void:
	resized.connect(queue_redraw)


func _draw() -> void:
	var slit_height: float = size.y * SLIT_HEIGHT_RATIO
	var bar_height: float = size.y * BAR_HEIGHT_RATIO
	var band_height: float = SLIT_COUNT * slit_height + (SLIT_COUNT - 1) * bar_height
	var band_top: float = (size.y - band_height) * 0.5
	draw_rect(Rect2(0.0, 0.0, size.x, band_top), METAL_COLOR)
	for bar_index: int in SLIT_COUNT - 1:
		var bar_top: float = band_top + (bar_index + 1) * slit_height + bar_index * bar_height
		draw_rect(Rect2(0.0, bar_top, size.x, bar_height), METAL_COLOR)
	var band_bottom: float = band_top + band_height
	draw_rect(Rect2(0.0, band_bottom, size.x, size.y - band_bottom), METAL_COLOR)
