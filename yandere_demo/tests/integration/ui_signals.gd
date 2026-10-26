extends IntegrationTest
## The HUD, viewfinder, game over screen and main menu react to the autoload signals alone.

const HUD_SCENE: PackedScene = preload("res://scenes/ui/hud.tscn")
const VIEWFINDER_SCENE: PackedScene = preload("res://scenes/ui/viewfinder.tscn")
const GAME_OVER_SCENE: PackedScene = preload("res://scenes/ui/game_over.tscn")
const MAIN_MENU_SCENE: PackedScene = preload("res://scenes/ui/main_menu.tscn")
const TEST_SAVE_PATH: String = "user://test_save.json"
const LAYOUT_WINDOW_SIZES: Array[Vector2i] = [Vector2i(1152, 648), Vector2i(1280, 720), Vector2i(1920, 1080)]


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

	var layout_failure: String = await _layout_failure(hud, viewfinder)
	if not layout_failure.is_empty():
		return layout_failure

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


## Seen in the Task 22 captures: the shown bell banner and the viewfinder corner brackets must clear the HUD's meters,
## clock and item slot, at the default window size and at common larger ones (the UI does not scale).
func _layout_failure(hud: Control, viewfinder: Control) -> String:
	var window: Window = get_tree().root
	var previous_size: Vector2i = window.size
	var item_slot: Control = hud.get_node("%ItemSlot")
	item_slot.visible = true
	var failure: String = ""
	for window_size: Vector2i in LAYOUT_WINDOW_SIZES:
		window.size = window_size
		await get_tree().process_frame
		await get_tree().process_frame
		failure = _overlap_failure(hud, viewfinder, item_slot)
		if not failure.is_empty():
			failure = "at %s: %s" % [window_size, failure]
			break
	item_slot.visible = false
	window.size = previous_size
	return failure


func _overlap_failure(hud: Control, viewfinder: Control, item_slot: Control) -> String:
	var panels: Dictionary = {
		"meters": (hud.get_node("TopLeft") as Control).get_global_rect(),
		"clock": (hud.get_node("ClockPanel") as Control).get_global_rect(),
		"item slot": item_slot.get_global_rect(),
	}
	var banner: Control = hud.get_node("BellBanner")
	var banner_rect: Rect2 = Rect2(Vector2(banner.global_position.x, banner.get(&"SHOWN_Y")), banner.size)
	for panel_name: String in panels:
		if banner_rect.intersects(panels[panel_name]):
			return "the shown bell banner %s overlaps the %s %s" % [banner_rect, panel_name, panels[panel_name]]
	panels["viewfinder readout"] = (viewfinder.get_node("Readout") as Control).get_global_rect()
	for leg: PackedVector2Array in viewfinder.call(&"bracket_legs"):
		var leg_rect: Rect2 = Rect2(leg[0], Vector2.ZERO).expand(leg[1]).grow(viewfinder.get(&"BRACKET_WIDTH"))
		for panel_name: String in panels:
			if leg_rect.intersects(panels[panel_name]):
				return "a viewfinder bracket %s overlaps the %s %s" % [leg_rect, panel_name, panels[panel_name]]
	return ""
