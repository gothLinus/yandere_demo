class_name SanityHeart
extends TextureProgressBar
## Sanity as a ring with a beating heart inside. Everything is drawn here, so no texture asset is needed.

const BASE_BPM: float = 60.0
const BPM_PER_LOST_SANITY: float = 0.8
const RING_WIDTH: float = 7.0
const HEART_POINT_COUNT: int = 48
const HEART_RADIUS_RATIO: float = 0.36
const PULSE_SCALE: float = 0.16
const CALM_COLOR: Color = Color("ff8fb8")
const PANIC_COLOR: Color = Color("ff3b5c")
const RING_BACKGROUND_COLOR: Color = Color("1a1020cc")

var _beat_phase: float = 0.0
var _heart_outline: PackedVector2Array = _build_heart_outline()


static func beats_per_minute(sanity: float) -> float:
	return BASE_BPM + (100.0 - sanity) * BPM_PER_LOST_SANITY


## The classic parametric heart, normalised to a unit box.
static func _build_heart_outline() -> PackedVector2Array:
	var outline: PackedVector2Array = PackedVector2Array()
	for index: int in HEART_POINT_COUNT:
		var angle: float = TAU * index / HEART_POINT_COUNT
		outline.append(Vector2(
			16.0 * pow(sin(angle), 3.0),
			-(13.0 * cos(angle) - 5.0 * cos(2.0 * angle) - 2.0 * cos(3.0 * angle) - cos(4.0 * angle)),
		) / 17.0)
	return outline


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	fill_mode = TextureProgressBar.FILL_CLOCKWISE
	max_value = 100.0
	SanitySystem.sanity_changed.connect(_on_sanity_changed)
	value = SanitySystem.meters.sanity


func _process(delta: float) -> void:
	_beat_phase = fposmod(_beat_phase + delta * beats_per_minute(value) / 60.0, 1.0)
	queue_redraw()


func _draw() -> void:
	var center: Vector2 = size * 0.5
	var ring_radius: float = minf(size.x, size.y) * 0.5 - RING_WIDTH
	var color: Color = PANIC_COLOR.lerp(CALM_COLOR, value / max_value)
	draw_arc(center, ring_radius, 0.0, TAU, 64, RING_BACKGROUND_COLOR, RING_WIDTH)
	if value > 0.0:
		draw_arc(center, ring_radius, -PI * 0.5, -PI * 0.5 + TAU * value / max_value, 64, color, RING_WIDTH)
	# A sharp beat that decays: the heart is big at the start of each cycle.
	var beat: float = pow(1.0 - _beat_phase, 3.0)
	var heart_radius: float = ring_radius * HEART_RADIUS_RATIO * 2.0 * (1.0 + PULSE_SCALE * beat)
	var heart_points: PackedVector2Array = PackedVector2Array()
	for point: Vector2 in _heart_outline:
		heart_points.append(center + point * heart_radius * 0.5 + Vector2(0.0, ring_radius * 0.04))
	draw_colored_polygon(heart_points, color)


func _on_sanity_changed(new_value: float) -> void:
	value = new_value
