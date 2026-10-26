class_name ClassFade
extends CanvasLayer
## The fade over a class period (ruling R23). The clock face spins while the day jumps from the start of the class
## to its end: out holds the start time, in animates from the start time to wherever the clock now is.

## Fires when a fade ends, including when a newer fade or leaving the tree cuts it short, so no awaiter hangs.
signal fade_finished()

const FADE_SECONDS: float = 0.6

var _start_minute: float = 0.0
var _fade_tween: Tween

@onready var _curtain: ColorRect = %Curtain
@onready var _clock_label: Label = %ClockLabel
@onready var _clock_face: ClockFace = %ClockFace


func _ready() -> void:
	_curtain.modulate.a = 0.0
	_curtain.mouse_filter = Control.MOUSE_FILTER_IGNORE
	GameManager.fade_callable = fade_around


func _exit_tree() -> void:
	fade_finished.emit()
	if GameManager.fade_callable == fade_around:
		GameManager.fade_callable = func(callback: Callable) -> void: callback.call()


## The shape GameManager expects: fade out, run the callback, fade in.
func fade_around(callback: Callable) -> void:
	await fade_out()
	callback.call()
	await fade_in()


func fade_out() -> Signal:
	_start_minute = SchoolClock.model.current_minute if SchoolClock.model != null else 0.0
	_show_minute(_start_minute)
	_curtain.mouse_filter = Control.MOUSE_FILTER_STOP
	_restart_tween().tween_property(_curtain, "modulate:a", 1.0, FADE_SECONDS)
	return fade_finished


func fade_in() -> Signal:
	var end_minute: float = SchoolClock.model.current_minute if SchoolClock.model != null else _start_minute
	var tween: Tween = _restart_tween()
	tween.set_parallel()
	tween.tween_method(_show_minute, _start_minute, end_minute, FADE_SECONDS)
	tween.tween_property(_curtain, "modulate:a", 0.0, FADE_SECONDS)
	tween.finished.connect(func() -> void: _curtain.mouse_filter = Control.MOUSE_FILTER_IGNORE)
	return fade_finished


func _restart_tween() -> Tween:
	if _fade_tween != null and _fade_tween.is_running():
		_fade_tween.kill()
		fade_finished.emit()
	_fade_tween = create_tween()
	_fade_tween.finished.connect(fade_finished.emit)
	return _fade_tween


func _show_minute(minute: float) -> void:
	_clock_face.minute_of_day = minute
	var total_minutes: int = floori(minute)
	_clock_label.text = "%02d:%02d" % [total_minutes / 60, total_minutes % 60]
