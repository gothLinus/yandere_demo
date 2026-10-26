class_name PauseMenu
extends CanvasLayer
## Esc during a day: resume, open the album, or leave for the main menu.

@onready var _root: Control = $Root
@onready var _resume_button: Button = %ResumeButton
@onready var _album_button: Button = %AlbumButton
@onready var _menu_button: Button = %MenuButton


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root.visible = false
	_resume_button.pressed.connect(resume)
	_album_button.pressed.connect(_on_album_pressed)
	_menu_button.pressed.connect(_on_menu_pressed)


func _unhandled_input(event: InputEvent) -> void:
	if not event.is_action_pressed(&"pause"):
		return
	if _root.visible:
		resume()
	elif SchoolClock.running and not get_tree().paused:
		_open()
	else:
		return
	get_viewport().set_input_as_handled()


func resume() -> void:
	_root.visible = false
	get_tree().paused = false
	ScreenSupport.capture_cursor()


func _open() -> void:
	get_tree().paused = true
	ScreenSupport.show_cursor()
	_root.visible = true
	_resume_button.grab_focus()


func _on_album_pressed() -> void:
	var album: Album = get_tree().get_first_node_in_group(Album.GROUP) as Album
	if album == null:
		return
	_root.visible = false
	album.open()
	await album.closed
	_root.visible = true
	_resume_button.grab_focus()


func _on_menu_pressed() -> void:
	ScreenSupport.go_to_main_menu(get_tree())
