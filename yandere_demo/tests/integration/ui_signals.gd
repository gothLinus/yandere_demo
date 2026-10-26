extends IntegrationTest
## The HUD, viewfinder, game over screen and main menu react to the autoload signals alone.

const HUD_SCENE: PackedScene = preload("res://scenes/ui/hud.tscn")
const VIEWFINDER_SCENE: PackedScene = preload("res://scenes/ui/viewfinder.tscn")
const GAME_OVER_SCENE: PackedScene = preload("res://scenes/ui/game_over.tscn")
const MAIN_MENU_SCENE: PackedScene = preload("res://scenes/ui/main_menu.tscn")
const TEST_SAVE_PATH: String = "user://test_save.json"


func _ready() -> void:
	GameManager.test_mode = true
	SaveStore.erase(TEST_SAVE_PATH)
	var failure: String = await _run_scenario()
	SaveStore.erase(TEST_SAVE_PATH)
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _run_scenario() -> String:
	var hud: Control = HUD_SCENE.instantiate()
	var viewfinder: Control = VIEWFINDER_SCENE.instantiate()
	var game_over: CanvasLayer = GAME_OVER_SCENE.instantiate()
	add_child(hud)
	add_child(viewfinder)
	add_child(game_over)
	await get_tree().process_frame

	SanitySystem.suspicion_changed.emit(57.0)
	var suspicion_bar: ProgressBar = hud.get_node("%SuspicionBar")
	var suspicion_label: Label = hud.get_node("%SuspicionLabel")
	if not is_equal_approx(suspicion_bar.value, 57.0) or suspicion_label.text != "57%":
		return "suspicion bar shows %s / '%s'" % [suspicion_bar.value, suspicion_label.text]

	SanitySystem.school_alert_changed.emit(30.0)
	var alert_label: Label = hud.get_node("%AlertLabel")
	if alert_label.text != "30%":
		return "alert label shows '%s'" % alert_label.text

	SanitySystem.sanity_changed.emit(20.0)
	var vignette: Vignette = hud.get_node("%Vignette")
	if vignette.intensity <= 0.4:
		return "vignette intensity %.2f at sanity 20" % vignette.intensity

	GameManager.game_over.emit(&"school_alert")
	var reason_label: Label = game_over.get_node("%ReasonLabel")
	if not reason_label.text.contains("principal"):
		return "game over text '%s' lacks 'principal'" % reason_label.text
	GameManager.game_over.emit(&"target_report")
	if not reason_label.text.contains("He told a teacher"):
		return "game over text '%s' lacks the report text" % reason_label.text

	var main_menu: Node = MAIN_MENU_SCENE.instantiate()
	add_child(main_menu)
	await get_tree().process_frame
	var continue_button: Button = main_menu.get_node("%ContinueButton")
	if not continue_button.disabled:
		return "Continue is enabled without a save"
	return ""
