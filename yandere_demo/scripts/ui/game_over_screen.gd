class_name GameOverScreen
extends CanvasLayer
## Shown on game over: why it ended, then retry the day or leave.

const REASON_TEXTS: Dictionary = {
	&"target_report": "He told a teacher about you.",
	&"school_alert": "You've been called to the principal's office.",
}
const UNKNOWN_REASON_TEXT: String = "Your week is over."

@onready var _root: Control = $Root
@onready var _reason_label: Label = %ReasonLabel
@onready var _retry_button: Button = %RetryButton
@onready var _menu_button: Button = %MenuButton


func _ready() -> void:
	_root.visible = false
	GameManager.game_over.connect(_on_game_over)
	GameManager.day_started.connect(_on_day_started)
	_retry_button.pressed.connect(_on_retry_pressed)
	_menu_button.pressed.connect(_on_menu_pressed)


func _on_game_over(reason: StringName) -> void:
	_reason_label.text = REASON_TEXTS.get(reason, UNKNOWN_REASON_TEXT)
	ScreenSupport.show_cursor()
	_root.visible = true
	_retry_button.grab_focus()


func _on_day_started(_day_index: int) -> void:
	_root.visible = false


func _on_retry_pressed() -> void:
	_root.visible = false
	ScreenSupport.capture_cursor()
	GameManager.retry_day()


func _on_menu_pressed() -> void:
	ScreenSupport.go_to_main_menu(get_tree())
