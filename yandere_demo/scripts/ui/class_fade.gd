class_name ClassFade
extends CanvasLayer
## The fade over a class period (ruling R23). The clock face spins while the day jumps from the start of the class
## to its end: out holds the start time, in animates from the start time to wherever the clock now is.

## One per fade, so an interrupted fade wakes only its own awaiters, exactly once, and never a newer fade's.
class FadeToken extends RefCounted:
	signal finished()

const FADE_SECONDS: float = 0.6

var _start_minute: float = 0.0
var _fade_tween: Tween
var _fade_token: FadeToken

@onready var _curtain: ColorRect = %Curtain
@onready var _clock_label: Label = %ClockLabel
@onready var _clock_face: ClockFace = %ClockFace


func _ready() -> void:
	_curtain.modulate.a = 0.0
	_curtain.mouse_filter = Control.MOUSE_FILTER_IGNORE
	GameManager.fade_callable = fade_around


func _exit_tree() -> void:
	if _fade_token != null:
		_fade_token.finished.emit()
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
	var token: FadeToken = _start_fade()
	_fade_tween.tween_property(_curtain, "modulate:a", 1.0, FADE_SECONDS)
	return token.finished


func fade_in() -> Signal:
	var end_minute: float = SchoolClock.model.current_minute if SchoolClock.model != null else _start_minute
	var token: FadeToken = _start_fade()
	_fade_tween.set_parallel()
	_fade_tween.tween_method(_show_minute, _start_minute, end_minute, FADE_SECONDS)
	_fade_tween.tween_property(_curtain, "modulate:a", 0.0, FADE_SECONDS)
	_fade_tween.finished.connect(func() -> void: _curtain.mouse_filter = Control.MOUSE_FILTER_IGNORE)
	return token.finished


## Replaces any running fade. The new tween and token are in place before the old token is woken (deferred, so its
## awaiter cannot start another fade from inside this call).
func _start_fade() -> FadeToken:
	var interrupted_token: FadeToken = _fade_token
	if _fade_tween != null and _fade_tween.is_running():
		_fade_tween.kill()
	else:
		interrupted_token = null
	var token: FadeToken = FadeToken.new()
	_fade_token = token
	_fade_tween = create_tween()
	_fade_tween.finished.connect(token.finished.emit)
	if interrupted_token != null:
		# The lambda keeps the token alive until its awaiter has been woken.
		(func() -> void: interrupted_token.finished.emit()).call_deferred()
	return token


func _show_minute(minute: float) -> void:
	_clock_face.minute_of_day = minute
	var total_minutes: int = floori(minute)
	_clock_label.text = "%02d:%02d" % [floori(total_minutes / 60.0), total_minutes % 60]
