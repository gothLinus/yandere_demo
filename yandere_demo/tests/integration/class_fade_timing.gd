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
	return await _run_interruption(fade)


## A second fade_around starts while the first is fading out.
func _run_interruption(fade: ClassFade) -> String:
	var first_runs: Array[int] = [0]
	var second_runs: Array[int] = [0]
	var max_running_tweens: int = 0
	fade.fade_around(func() -> void: first_runs[0] += 1)
	await get_tree().create_timer(0.2).timeout
	fade.fade_around(func() -> void: second_runs[0] += 1)
	var elapsed_seconds: float = 0.0
	while elapsed_seconds < EXPECTED_SECONDS * 3.0:
		await get_tree().process_frame
		elapsed_seconds += get_process_delta_time()
		max_running_tweens = maxi(max_running_tweens, _running_tween_count())
	if first_runs[0] != 1 or second_runs[0] != 1:
		return "callbacks ran first %d, second %d times" % [first_runs[0], second_runs[0]]
	if max_running_tweens > 1:
		return "%d tweens ran at once" % max_running_tweens
	var curtain: ColorRect = fade.get_node("%Curtain")
	if curtain.modulate.a != 0.0 or curtain.mouse_filter != Control.MOUSE_FILTER_IGNORE:
		return "curtain ended at alpha %.2f, mouse_filter %d" % [curtain.modulate.a, curtain.mouse_filter]
	return ""


func _running_tween_count() -> int:
	var count: int = 0
	for tween: Tween in get_tree().get_processed_tweens():
		if tween.is_running():
			count += 1
	return count
