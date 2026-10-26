extends Node3D
## Title screen over a slow camera orbit of the courtyard.

const ORBIT_RADIUS: float = 9.0
const ORBIT_HEIGHT: float = 4.5
const ORBIT_RADIANS_PER_SECOND: float = 0.07
const LOOK_HEIGHT: float = 1.5
const COURTYARD_ACTIVITY: StringName = &"courtyard_stroll"

var _orbit_center: Vector3 = Vector3.ZERO
var _orbit_angle: float = 0.0

@onready var _school_env: SchoolEnv = $SchoolEnv
@onready var _camera: Camera3D = $OrbitCamera
@onready var _continue_button: Button = %ContinueButton
@onready var _new_week_button: Button = %NewWeekButton
@onready var _quit_button: Button = %QuitButton


func _ready() -> void:
	get_tree().paused = false
	ScreenSupport.show_cursor()
	var anchors: Array[Node3D] = _school_env.anchors_for(COURTYARD_ACTIVITY)
	if not anchors.is_empty():
		_orbit_center = anchors[0].global_position
	_continue_button.disabled = not GameManager.has_save()
	_continue_button.pressed.connect(GameManager.continue_week)
	_new_week_button.pressed.connect(GameManager.new_week)
	_quit_button.pressed.connect(get_tree().quit)
	(_new_week_button if _continue_button.disabled else _continue_button).grab_focus()
	_place_camera()


func _process(delta: float) -> void:
	_orbit_angle += delta * ORBIT_RADIANS_PER_SECOND
	_place_camera()


func _place_camera() -> void:
	_camera.global_position = _orbit_center + Vector3(cos(_orbit_angle) * ORBIT_RADIUS, ORBIT_HEIGHT, sin(_orbit_angle) * ORBIT_RADIUS)
	_camera.look_at(_orbit_center + Vector3.UP * LOOK_HEIGHT)
