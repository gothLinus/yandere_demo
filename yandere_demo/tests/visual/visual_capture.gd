class_name VisualCapture
extends Node
## Base of the windowed capture scenes (Task 22): saves the rendered frame as a PNG under user://captures/ and quits
## when the scenario is done. These scenes need a window, so tests/run_all.sh never discovers them.

const CAPTURE_DIRECTORY: String = "user://captures"

var saved_paths: Array[String] = []


func _enter_tree() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	DirAccess.make_dir_recursive_absolute(CAPTURE_DIRECTORY)
	# The window opens on someone's desktop: keystrokes meant for other apps must not press its buttons, and it stays
	# on top because macOS stops drawing a covered window, which stalls every capture.
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, true)


func save_capture(capture_name: String) -> void:
	await RenderingServer.frame_post_draw
	var image: Image = get_viewport().get_texture().get_image()
	var path: String = "%s/%s.png" % [CAPTURE_DIRECTORY, capture_name]
	var error: Error = image.save_png(path)
	if error != OK:
		push_error("VisualCapture: could not save %s (%s)" % [path, error_string(error)])
		return
	saved_paths.append(ProjectSettings.globalize_path(path))
	print("CAPTURE %s" % ProjectSettings.globalize_path(path))


## Game time, so the waits stay in step with the scene's own timers even when a throttled window drops frames.
func wait_seconds(seconds: float) -> void:
	await get_tree().create_timer(seconds, true).timeout


func wait_frames(frame_count: int) -> void:
	for frame: int in frame_count:
		await get_tree().process_frame


func finish() -> void:
	print("CAPTURES DONE %d in %s" % [saved_paths.size(), ProjectSettings.globalize_path(CAPTURE_DIRECTORY)])
	get_tree().quit(0)
