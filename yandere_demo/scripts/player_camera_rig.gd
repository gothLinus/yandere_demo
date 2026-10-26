class_name PlayerCameraRig
extends Node3D

const MOUSE_SENSITIVITY: float = 0.0025
const PITCH_LIMIT: float = deg_to_rad(70.0)
const VIEWFINDER_FOV_WIDE: float = 50.0
const VIEWFINDER_FOV_TELE: float = 20.0
const ZOOM_STEP: float = 3.0
const SHAKE_FREQUENCY: float = 40.0
const SHAKE_OFFSET_SCALE: float = 0.05

var yaw: float = 0.0
var pitch: float = deg_to_rad(-10.0)
var shake_strength: float = 0.0

var _viewfinder_active: bool = false
var _shake_noise: FastNoiseLite = FastNoiseLite.new()

@onready var _spring_arm: SpringArm3D = $SpringArm3D
@onready var _third_person_camera: Camera3D = $SpringArm3D/ThirdPersonCamera
@onready var _viewfinder_camera: Camera3D = $ViewfinderCamera
@onready var _follow_target: Node3D = get_parent() as Node3D


func _ready() -> void:
	_viewfinder_camera.fov = VIEWFINDER_FOV_WIDE
	_third_person_camera.make_current()
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(event: InputEvent) -> void:
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	var motion: InputEventMouseMotion = event as InputEventMouseMotion
	if motion != null:
		yaw -= motion.relative.x * MOUSE_SENSITIVITY
		pitch = clampf(pitch - motion.relative.y * MOUSE_SENSITIVITY, -PITCH_LIMIT, PITCH_LIMIT)
		return
	var button: InputEventMouseButton = event as InputEventMouseButton
	if button != null and button.pressed and _viewfinder_active:
		if button.button_index == MOUSE_BUTTON_WHEEL_UP:
			_zoom(-ZOOM_STEP)
		elif button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_zoom(ZOOM_STEP)


func _process(_delta: float) -> void:
	global_position = _follow_target.global_position
	rotation = Vector3(0.0, yaw, 0.0)
	_spring_arm.rotation.x = pitch
	_viewfinder_camera.rotation.x = pitch
	var time_seconds: float = Time.get_ticks_msec() / 1000.0 * SHAKE_FREQUENCY
	var shake_offset: Vector2 = Vector2(
		_shake_noise.get_noise_2d(time_seconds, 0.0),
		_shake_noise.get_noise_2d(0.0, time_seconds),
	) * shake_strength * SHAKE_OFFSET_SCALE
	for camera: Camera3D in [_third_person_camera, _viewfinder_camera]:
		camera.h_offset = shake_offset.x
		camera.v_offset = shake_offset.y


func yaw_basis() -> Basis:
	return Basis(Vector3.UP, yaw)


func current_camera() -> Camera3D:
	return _viewfinder_camera if _viewfinder_active else _third_person_camera


func set_viewfinder_active(active: bool) -> void:
	_viewfinder_active = active
	if active:
		_viewfinder_camera.fov = VIEWFINDER_FOV_WIDE
		_viewfinder_camera.make_current()
	else:
		_third_person_camera.make_current()


func _zoom(fov_delta: float) -> void:
	_viewfinder_camera.fov = clampf(_viewfinder_camera.fov + fov_delta, VIEWFINDER_FOV_TELE, VIEWFINDER_FOV_WIDE)
