extends IntegrationTest
## ClassFade's fade_out() and fade_in() each take 0.6 s, and fade_around() always runs its callback.

const CLASS_FADE_SCENE: PackedScene = preload("res://scenes/ui/class_fade.tscn")
const EXPECTED_SECONDS: float = 0.6
const TOLERANCE_SECONDS: float = 0.05
const WARMUP_SECONDS: float = 0.7


func _ready() -> void:
	var fade: ClassFade = CLASS_FADE_SCENE.instantiate()
	add_child(fade)
	var failure: String = await _run_scenario(fade)
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _run_scenario(fade: ClassFade) -> String:
	# Startup frames carry large deltas that a tween would swallow, so let the loop settle first.
	await get_tree().create_timer(WARMUP_SECONDS).timeout
	var started_milliseconds: int = Time.get_ticks_msec()
	await fade.fade_out()
	var out_seconds: float = (Time.get_ticks_msec() - started_milliseconds) / 1000.0
	if absf(out_seconds - EXPECTED_SECONDS) > TOLERANCE_SECONDS:
		return "fade_out took %.3f s" % out_seconds
	started_milliseconds = Time.get_ticks_msec()
	await fade.fade_in()
	var in_seconds: float = (Time.get_ticks_msec() - started_milliseconds) / 1000.0
	if absf(in_seconds - EXPECTED_SECONDS) > TOLERANCE_SECONDS:
		return "fade_in took %.3f s" % in_seconds
	var ran: Array[bool] = [false]
	fade.fade_around(func() -> void: ran[0] = true)
	await get_tree().create_timer(0.2).timeout
	fade.fade_out()
	await get_tree().create_timer(EXPECTED_SECONDS * 2.0 + 0.2).timeout
	if not ran[0]:
		return "fade_around skipped its callback after an interrupting fade"
	return ""

