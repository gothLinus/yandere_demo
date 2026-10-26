class_name PhotoMode
extends Node
## Camera mode's shutter: scores the frame (PhotoScorer), saves the image, owns the flash (ruling R21: the Suspicion
## spike and the "he can see it" check live here, the on_flash callbacks only react) and banks good photos.

signal photo_taken(result: PhotoScorer.PhotoResult, image_path: String)
signal flash_toggled(enabled: bool)
signal focus_quality_changed(preview_score: int)

const PHOTO_DIRECTORY: String = "user://photos"
const STUDENTS_GROUP: StringName = &"students"

var tuning: StealthTuning = preload("res://data/stealth_tuning.tres")
var flash_enabled: bool = false
var target: TargetAI
var meters: StealthMeters
var day_run: DayRun
## Cards already banked in the week, so a repeat unlock is refused by DayRun.
var banked_intel: Array[StringName] = []
var day_index: int = 0

var _preview_seconds: float = 0.0
var _is_snapping: bool = false

@onready var _player: StealthPlayer = get_parent() as StealthPlayer


func _process(_delta: float) -> void:
	if _player.mode != StealthPlayer.MODE_CAMERA:
		return
	if Input.is_action_just_pressed(&"toggle_flash"):
		set_flash_enabled(not flash_enabled)
	if Input.is_action_just_pressed(&"snap_photo"):
		snap()


func _physics_process(delta: float) -> void:
	if _player.mode != StealthPlayer.MODE_CAMERA or target == null:
		_preview_seconds = 0.0
		return
	_preview_seconds += delta
	if _preview_seconds < tuning.photo_preview_interval:
		return
	_preview_seconds = 0.0
	var camera: Camera3D = _player.current_camera()
	var shot: PhotoShot = build_shot(camera, target, camera.get_world_3d().direct_space_state)
	focus_quality_changed.emit(PhotoScorer.score(shot).score)


func bind(new_target: TargetAI, new_meters: StealthMeters, new_day_run: DayRun, new_banked_intel: Array[StringName], new_day_index: int) -> void:
	target = new_target
	meters = new_meters
	day_run = new_day_run
	banked_intel = new_banked_intel
	day_index = new_day_index


func set_flash_enabled(enabled: bool) -> void:
	if enabled == flash_enabled:
		return
	flash_enabled = enabled
	flash_toggled.emit(flash_enabled)


func build_shot(camera: Camera3D, photographed: TargetAI, space: PhysicsDirectSpaceState3D) -> PhotoShot:
	var shot: PhotoShot = PhotoShot.new()
	var head: Vector3 = photographed.head_position()
	shot.target_in_frame = camera.is_position_in_frustum(head)
	shot.flash_used = flash_enabled
	shot.distance = camera.global_position.distance_to(head)
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(camera.global_position, head, PhysicsLayers.LINE_OF_SIGHT_MASK)
	shot.is_obstructed = not space.intersect_ray(query).is_empty()
	if shot.target_in_frame:
		var viewport_size: Vector2 = camera.get_viewport().get_visible_rect().size
		var from_center: Vector2 = (camera.unproject_position(head) - viewport_size * 0.5) / (viewport_size * 0.5)
		shot.center_offset = clampf(from_center.length(), 0.0, 1.0)
	var facing: float = photographed.eye_forward().dot((camera.global_position - head).normalized())
	shot.target_looking_at_camera = facing > cos(deg_to_rad(tuning.photo_looking_angle_degrees))
	shot.face_visible = facing > tuning.photo_face_visible_dot
	var activity: ActivityDefinition = photographed.current_activity()
	shot.activity_is_rare = activity != null and activity.is_rare
	return shot


func snap() -> void:
	if _is_snapping or target == null or _player.mode != StealthPlayer.MODE_CAMERA:
		return
	_is_snapping = true
	var camera: Camera3D = _player.current_camera()
	var result: PhotoScorer.PhotoResult = PhotoScorer.score(build_shot(camera, target, camera.get_world_3d().direct_space_state))
	var activity: ActivityDefinition = target.current_activity()
	if flash_enabled:
		_fire_flash(camera.global_position)
	var image_path: String = await _save_image()
	if result.is_good:
		day_run.add_photo(image_path, result.score, day_index)
		meters.reward_photo()
		if activity != null and activity.is_rare:
			day_run.unlock_intel(activity.intel_card_id, banked_intel)
	_is_snapping = false
	photo_taken.emit(result, image_path)


func _fire_flash(flash_position: Vector3) -> void:
	if target.perception.can_see(flash_position):
		meters.add_suspicion_spike(tuning.flash_spike)
		target.on_flash(flash_position)
	get_tree().call_group(STUDENTS_GROUP, &"on_flash", flash_position)


func _save_image() -> String:
	if DisplayServer.get_name() == "headless":
		return ""
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(PHOTO_DIRECTORY)
	var path: String = "%s/day%d_%d.png" % [PHOTO_DIRECTORY, day_index, int(Time.get_unix_time_from_system() * 1000.0)]
	var error: Error = get_viewport().get_texture().get_image().save_png(path)
	if error != OK:
		push_error("PhotoMode: could not save %s (%s)" % [path, error_string(error)])
		return ""
	return path
