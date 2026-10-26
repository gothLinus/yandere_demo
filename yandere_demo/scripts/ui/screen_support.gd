class_name ScreenSupport
extends RefCounted
## Cursor and navigation helpers shared by the full-screen UI.

const MAIN_MENU_PATH: String = "res://scenes/ui/main_menu.tscn"


static func show_cursor() -> void:
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


## The camera rig only captures the mouse when it enters the tree, so every screen that gives play back does it.
static func capture_cursor() -> void:
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


static func go_to_main_menu(tree: SceneTree) -> void:
	tree.paused = false
	SchoolClock.stop()
	tree.change_scene_to_file.call_deferred(MAIN_MENU_PATH)
