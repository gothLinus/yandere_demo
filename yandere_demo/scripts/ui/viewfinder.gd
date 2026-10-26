extends Control
## Camera mode overlay: corner brackets, a focus reticle that turns green on a good frame, zoom, flash and shot count.
## A shot flashes white for a moment and then desaturates the frame.

const PLAYER_GROUP: StringName = &"player"
const PHOTO_MODE_PATH: NodePath = ^"PhotoMode"
const CAMERA_RIG_PATH: NodePath = ^"CameraRig"
const GOOD_FOCUS_SCORE: int = 60
const FLASH_SECONDS: float = 0.12
const DESATURATE_SECONDS: float = 0.4
const BRACKET_MARGIN: float = 56.0
const BRACKET_LENGTH: float = 64.0
const BRACKET_WIDTH: float = 4.0
const RETICLE_RADIUS: float = 26.0
const RETICLE_GAP: float = 8.0
const IDLE_COLOR: Color = Color("ffffff")
const GOOD_COLOR: Color = Color("7dffb0")
const BRACKET_COLOR: Color = Color("ff8fb8")

var focus_score: int = 0
var shot_count: int = 0

var _player: StealthPlayer
var _desaturate_material: ShaderMaterial = ShaderMaterial.new()

@onready var _zoom_label: Label = %ZoomLabel
@onready var _flash_label: Label = %FlashLabel
@onready var _shot_label: Label = %ShotLabel
@onready var _flash_rect: ColorRect = %FlashRect
@onready var _desaturate_rect: ColorRect = %DesaturateRect


func _ready() -> void:
	visible = false
	_desaturate_material.shader = preload("res://assets/shaders/photo_desaturate.gdshader")
	_desaturate_rect.material = _desaturate_material
	_flash_rect.modulate.a = 0.0
	_desaturate_rect.visible = false
	GameManager.day_started.connect(_on_day_started)
	_on_flash_toggled(false)
	_on_zoom_changed(1.0)
	_update_shot_label()
	_bind_player()


func _draw() -> void:
	var corner_directions: Array[Vector2] = [Vector2(1, 1), Vector2(-1, 1), Vector2(1, -1), Vector2(-1, -1)]
	for direction: Vector2 in corner_directions:
		var corner: Vector2 = Vector2(
			BRACKET_MARGIN if direction.x > 0.0 else size.x - BRACKET_MARGIN,
			BRACKET_MARGIN if direction.y > 0.0 else size.y - BRACKET_MARGIN,
		)
		draw_line(corner, corner + Vector2(BRACKET_LENGTH * direction.x, 0.0), BRACKET_COLOR, BRACKET_WIDTH)
		draw_line(corner, corner + Vector2(0.0, BRACKET_LENGTH * direction.y), BRACKET_COLOR, BRACKET_WIDTH)
	var center: Vector2 = size * 0.5
	var reticle_color: Color = GOOD_COLOR if is_focus_good() else IDLE_COLOR
	draw_arc(center, RETICLE_RADIUS, 0.0, TAU, 40, reticle_color, 3.0)
	for direction: Vector2 in [Vector2.LEFT, Vector2.RIGHT, Vector2.UP, Vector2.DOWN]:
		draw_line(center + direction * RETICLE_GAP, center + direction * (RETICLE_RADIUS + RETICLE_GAP), reticle_color, 3.0)


func is_focus_good() -> bool:
	return focus_score >= GOOD_FOCUS_SCORE


func _bind_player() -> void:
	var player: StealthPlayer = get_tree().get_first_node_in_group(PLAYER_GROUP) as StealthPlayer
	if player == null or player == _player:
		return
	_player = player
	_player.mode_changed.connect(_on_mode_changed)
	var photo_mode: PhotoMode = _player.get_node(PHOTO_MODE_PATH) as PhotoMode
	photo_mode.focus_quality_changed.connect(_on_focus_quality_changed)
	photo_mode.flash_toggled.connect(_on_flash_toggled)
	photo_mode.photo_taken.connect(_on_photo_taken)
	(_player.get_node(CAMERA_RIG_PATH) as PlayerCameraRig).zoom_changed.connect(_on_zoom_changed)


func _on_day_started(_day_index: int) -> void:
	_bind_player()
	shot_count = 0
	_update_shot_label()


func _on_mode_changed(mode: StringName) -> void:
	visible = mode == StealthPlayer.MODE_CAMERA
	_on_focus_quality_changed(0)


func _on_focus_quality_changed(preview_score: int) -> void:
	focus_score = preview_score
	queue_redraw()


func _on_flash_toggled(enabled: bool) -> void:
	_flash_label.text = "Flash on" if enabled else "Flash off"


func _on_zoom_changed(factor: float) -> void:
	_zoom_label.text = "%.1fx" % factor


func _on_photo_taken(_result: PhotoScorer.PhotoResult, _image_path: String) -> void:
	shot_count += 1
	_update_shot_label()
	var tween: Tween = create_tween()
	_flash_rect.modulate.a = 1.0
	tween.tween_property(_flash_rect, "modulate:a", 0.0, FLASH_SECONDS)
	_desaturate_rect.visible = true
	_desaturate_material.set_shader_parameter(&"amount", 1.0)
	tween.tween_method(_set_desaturation, 1.0, 0.0, DESATURATE_SECONDS)
	tween.tween_callback(_desaturate_rect.hide)


func _set_desaturation(amount: float) -> void:
	_desaturate_material.set_shader_parameter(&"amount", amount)


func _update_shot_label() -> void:
	_shot_label.text = "Shots %d" % shot_count
