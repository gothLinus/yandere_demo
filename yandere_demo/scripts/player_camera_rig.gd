class_name PlayerCameraRig
extends Node3D

signal zoom_changed(factor: float)

const PITCH_LIMIT: float = deg_to_rad(70.0)
const VIEWFINDER_FOV_WIDE: float = 50.0
const VIEWFINDER_FOV_TELE: float = 20.0
const SHAKE_FREQUENCY: float = 40.0
const SHAKE_OFFSET_SCALE: float = 0.05

var tuning: StealthTuning = preload("res://data/stealth_tuning.tres")
var yaw: float = 0.0
var pitch: float = deg_to_rad(-10.0)
var shake_strength: float = 0.0

var _viewfinder_active: bool = false
var _peek_point: Node3D
var _viewfinder_rest_transform: Transform3D
var _shake_noise: FastNoiseLite = FastNoiseLite.new()

@onready var _spring_arm: SpringArm3D = $SpringArm3D
@onready var _third_person_camera: Camera3D = $SpringArm3D/ThirdPersonCamera
@onready var _viewfinder_camera: Camera3D = $ViewfinderCamera
@onready var _follow_target: Node3D = get_parent() as Node3D


func _ready() -> void:
	_spring_arm.collision_mask = PhysicsLayers.WORLD
	_viewfinder_camera.fov = VIEWFINDER_FOV_WIDE
	_viewfinder_rest_transform = _viewfinder_camera.transform
	_third_person_camera.make_current()
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(event: InputEvent) -> void:
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	var motion: InputEventMouseMotion = event as InputEventMouseMotion
	if motion != null:
		yaw -= motion.relative.x * tuning.mouse_sensitivity
		pitch = clampf(pitch - motion.relative.y * tuning.mouse_sensitivity, -PITCH_LIMIT, PITCH_LIMIT)
		return
	var button: InputEventMouseButton = event as InputEventMouseButton
	if button != null and button.pressed and _viewfinder_active:
		if button.button_index == MOUSE_BUTTON_WHEEL_UP:
			_zoom(-tuning.zoom_step)
		elif button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_zoom(tuning.zoom_step)


func _process(_delta: float) -> void:
	global_position = _follow_target.global_position
	rotation = Vector3(0.0, yaw, 0.0)
	_spring_arm.rotation.x = pitch
	if _peek_point != null:
		_viewfinder_camera.global_transform = _peek_point.global_transform
	else:
		_viewfinder_camera.rotation.x = pitch
	var time_seconds: float = Time.get_ticks_msec() / 1000.0 * SHAKE_FREQUENCY
	var shake_offset: Vector2 = Vector2(
		_shake_noise.get_noise_2d(time_seconds, 0.0),
		_shake_noise.get_noise_2d(0.0, time_seconds),
	) * shake_strength * SHAKE_OFFSET_SCALE
	for camera: Camera3D in [_third_person_camera, _viewfinder_camera]:
		camera.h_offset = shake_offset.x
		camera.v_offset = shake_offset.y


## The viewfinder camera, which also serves the peek views, stops rendering these render layers.
func hide_in_first_person(render_layers: int) -> void:
	_viewfinder_camera.cull_mask &= ~render_layers


func yaw_basis() -> Basis:
	return Basis(Vector3.UP, yaw)


func current_camera() -> Camera3D:
	return _viewfinder_camera if _viewfinder_active or _peek_point != null else _third_person_camera


func set_viewfinder_active(active: bool) -> void:
	_viewfinder_active = active
	if active:
		_viewfinder_camera.fov = VIEWFINDER_FOV_WIDE
		_viewfinder_camera.make_current()
		zoom_changed.emit(1.0)
	else:
		_third_person_camera.make_current()


## Looks through a fixed point (locker slit, under-desk) and keeps the orbit yaw aligned so leaving continues in that direction.
func show_peek_view(point: Node3D) -> void:
	_peek_point = point
	yaw = point.global_rotation.y
	_viewfinder_camera.fov = VIEWFINDER_FOV_WIDE
	_viewfinder_camera.global_transform = point.global_transform
	_viewfinder_camera.make_current()


func clear_peek_view() -> void:
	if _peek_point == null:
		return
	_peek_point = null
	_viewfinder_camera.transform = _viewfinder_rest_transform
	if not _viewfinder_active:
		_third_person_camera.make_current()


func _zoom(fov_delta: float) -> void:
	_viewfinder_camera.fov = clampf(_viewfinder_camera.fov + fov_delta, VIEWFINDER_FOV_TELE, VIEWFINDER_FOV_WIDE)
	zoom_changed.emit(VIEWFINDER_FOV_WIDE / _viewfinder_camera.fov)
