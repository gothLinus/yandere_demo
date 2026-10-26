extends IntegrationTest
## Photo mode against the real target: a clear shot from 8 m scores good and lands in the DayRun, a box in between
## scores 0, the flash raises Suspicion by exactly flash_spike (ruling R21: PhotoMode owns the spike), a good photo of
## a rare activity unlocks its intel card, watching an activity for its length unlocks the card too, and Yandere Vision
## puts the overlay on the target and takes it off again with the original materials back.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TARGET_SCENE_PATH: String = "res://scenes/target.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const POOL_PATH: String = "res://data/activity_pool.tres"
const STEALTH_TUNING: StealthTuning = preload("res://data/stealth_tuning.tres")
const BENCH_ID: StringName = &"read_bench"
const ROOFTOP_ID: StringName = &"rooftop_visit"
const ROOFTOP_CARD: StringName = &"intel_rooftop_visit"
const BENCH_CARD: StringName = &"intel_read_bench"
const PLANNED_MINUTES: float = 60.0
const DAY_SEED: int = 17
const DAY_INDEX: int = 1
const SHOT_DISTANCE: float = 8.0
const START_DEADLINE_SECONDS: float = 10.0
const POSE_SETTLE_SECONDS: float = 0.8
const AIM_SETTLE_FRAMES: int = 3
const WATCH_SECONDS: float = 1.0
const SPIKE_TOLERANCE: float = 1.0
const VIEWPOINT_ANGLES_DEGREES: Array[float] = [0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0, 90.0, -90.0, 135.0, -135.0, 180.0]
const BLOCKER_SIZE: Vector3 = Vector3(2.0, 3.0, 0.2)

var _school_env: SchoolEnv
var _target: TargetAI
var _player: StealthPlayer
var _photo_mode: PhotoMode
var _yandere_vision: YandereVision
var _meters: StealthMeters
var _day_run: DayRun
var _anchor: Node3D
var _forward: Vector3
var _clock_seconds: float = 0.0
var _taken_results: Array[PhotoScorer.PhotoResult] = []
var _taken_paths: Array[String] = []


func _ready() -> void:
	timeout_seconds = 60.0
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_target = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(_target)
	_target.setup(_school_env, DAY_SEED, ActivityHistory.new())
	_player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(_player)
	_meters = StealthMeters.new(STEALTH_TUNING)
	_day_run = DayRun.new()
	_photo_mode = _player.get_node("PhotoMode") as PhotoMode
	_yandere_vision = _player.get_node("YandereVision") as YandereVision
	var banked: Array[StringName] = []
	_photo_mode.bind(_target, _meters, _day_run, banked, DAY_INDEX)
	_yandere_vision.bind(_target, _meters, _day_run, banked)
	_photo_mode.photo_taken.connect(_on_photo_taken)
	var failure: String = await _run_scenario()
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _physics_process(delta: float) -> void:
	_clock_seconds += delta


func _run_scenario() -> String:
	for step: Callable in [_clear_shot, _blocked_shot, _flash_spike, _rare_activity_intel, _observed_activity_intel, _rebind_after_target_freed, _vision_overlay, _vision_rebind]:
		var failure: String = await step.call()
		if not failure.is_empty():
			return failure
	return ""


func _clear_shot() -> String:
	var failure: String = await _start_activity(BENCH_ID)
	if not failure.is_empty():
		return failure
	await _frame_up_target()
	_taken_results.clear()
	await _photo_mode.snap()
	if _taken_results.size() != 1:
		return "photo_taken fired %d times" % _taken_results.size()
	if not _taken_results[0].is_good:
		return "a clear shot from %.0f m scored %d (%s)" % [SHOT_DISTANCE, _taken_results[0].score, _taken_results[0].notes]
	if _day_run.photos.size() != 1:
		return "DayRun holds %d photos instead of 1" % _day_run.photos.size()
	if DisplayServer.get_name() == "headless" and not _taken_paths[0].is_empty():
		return "headless image_path should be empty, got %s" % _taken_paths[0]
	return ""


func _blocked_shot() -> String:
	var blocker: StaticBody3D = _body_between(_target.head_position(), _player.global_position)
	await get_tree().physics_frame
	await get_tree().physics_frame
	_taken_results.clear()
	await _photo_mode.snap()
	blocker.queue_free()
	if _taken_results.size() != 1 or _taken_results[0].score != 0:
		return "an obstructed shot did not score 0"
	if _day_run.photos.size() != 1:
		return "an obstructed shot was banked"
	return ""


func _flash_spike() -> String:
	await get_tree().physics_frame
	await get_tree().physics_frame
	_photo_mode.set_flash_enabled(true)
	_meters.reset()
	var before: float = _meters.suspicion
	await _photo_mode.snap()
	_photo_mode.set_flash_enabled(false)
	var gained: float = _meters.suspicion - before
	if absf(gained - STEALTH_TUNING.flash_spike) > SPIKE_TOLERANCE:
		return "flash raised Suspicion by %.1f, expected %.1f" % [gained, STEALTH_TUNING.flash_spike]
	return ""


func _rare_activity_intel() -> String:
	_meters.reset()
	await _wait_until(func() -> bool: return _target.state == TargetAI.State.ACTIVITY, 12.0)
	var failure: String = await _start_activity(ROOFTOP_ID)
	if not failure.is_empty():
		return failure
	await _frame_up_target()
	_taken_results.clear()
	await _photo_mode.snap()
	if _taken_results.size() != 1 or not _taken_results[0].is_good:
		return "the rooftop shot did not score good (%s)" % [_taken_results[0].score if not _taken_results.is_empty() else "no photo"]
	if not _day_run.intel.has(ROOFTOP_CARD):
		return "a good photo of rooftop_visit did not unlock %s" % ROOFTOP_CARD
	return ""


func _observed_activity_intel() -> String:
	var activity: ActivityDefinition = (load(POOL_PATH) as ActivityPool).find(BENCH_ID)
	_target.activity_started.emit(activity)
	await _wait_seconds(WATCH_SECONDS)
	_target.activity_completed.emit(activity)
	if not _day_run.intel.has(BENCH_CARD):
		return "watching %s for its whole length did not unlock %s" % [BENCH_ID, BENCH_CARD]
	return ""


func _vision_overlay() -> String:
	var meshes: Array[Node] = _target.find_children("*", "MeshInstance3D", true, false)
	if meshes.is_empty():
		return "the target has no meshes"
	var overlays_before: Array[Material] = []
	for node: Node in meshes:
		overlays_before.append((node as MeshInstance3D).material_overlay)
	var surface_before: Material = (meshes[0] as MeshInstance3D).get_active_material(0)
	var toggles: Array[bool] = []
	_yandere_vision.vision_toggled.connect(func(active: bool) -> void: toggles.append(active))
	_yandere_vision.set_vision(true)
	for frame: int in AIM_SETTLE_FRAMES:
		await get_tree().physics_frame
	if not _player.is_vision_active:
		return "is_vision_active was cleared again after set_vision(true)"
	for node: Node in meshes:
		if (node as MeshInstance3D).material_overlay == null:
			return "%s got no vision overlay" % node.name
	_yandere_vision.set_vision(false)
	await get_tree().physics_frame
	if _player.is_vision_active:
		return "is_vision_active stayed set after set_vision(false)"
	for index: int in meshes.size():
		if (meshes[index] as MeshInstance3D).material_overlay != overlays_before[index]:
			return "%s overlay was not restored" % meshes[index].name
	if (meshes[0] as MeshInstance3D).get_active_material(0) != surface_before:
		return "the surface material changed"
	if toggles != [true, false]:
		return "vision_toggled gave %s" % [toggles]
	return ""


func _rebind_after_target_freed() -> String:
	var old_target: TargetAI = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(old_target)
	await get_tree().process_frame
	var banked: Array[StringName] = []
	_yandere_vision.bind(old_target, _meters, _day_run, banked)
	old_target.free()
	_yandere_vision.bind(_target, _meters, _day_run, banked)
	var tracker: ObservationTracker = _yandere_vision.observation_tracker
	var activity: ActivityDefinition = (load(POOL_PATH) as ActivityPool).find(ROOFTOP_ID)
	_day_run.intel.erase(ROOFTOP_CARD)
	_target.activity_started.emit(activity)
	await _wait_seconds(WATCH_SECONDS)
	_target.activity_completed.emit(activity)
	if not _day_run.intel.has(ROOFTOP_CARD):
		return "tracking did not work on the new target after rebinding"
	if tracker.watched_seconds <= 0.0:
		return "no watched seconds on the new target"
	return ""


func _vision_rebind() -> String:
	var other: TargetAI = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(other)
	await get_tree().process_frame
	var banked: Array[StringName] = []
	var old_meshes: Array[Node] = _target.find_children("*", "MeshInstance3D", true, false)
	var new_meshes: Array[Node] = other.find_children("*", "MeshInstance3D", true, false)
	var old_overlay: Material = (old_meshes[0] as MeshInstance3D).material_overlay
	_yandere_vision.set_vision(true)
	_yandere_vision.bind(other, _meters, _day_run, banked)
	var failure: String = ""
	if (old_meshes[0] as MeshInstance3D).material_overlay != old_overlay:
		failure = "the old target kept the overlay after rebind"
	elif (new_meshes[0] as MeshInstance3D).material_overlay == null:
		failure = "the new target got no overlay while vision was active"
	_yandere_vision.set_vision(false)
	_yandere_vision.bind(_target, _meters, _day_run, banked)
	other.free()
	return failure


func _start_activity(activity_id: StringName) -> String:
	_anchor = _school_env.anchors_for(activity_id)[0]
	_forward = -_anchor.global_basis.z
	_forward.y = 0.0
	_forward = _forward.normalized()
	_target.global_position = _anchor.global_position
	_target.rotation.y = _anchor.global_rotation.y
	await get_tree().physics_frame
	var planned: PlannedActivity = PlannedActivity.new()
	planned.activity = (load(POOL_PATH) as ActivityPool).find(activity_id)
	planned.duration_minutes = PLANNED_MINUTES
	_target.start_plan([planned] as Array[PlannedActivity])
	await _wait_until(func() -> bool: return _target.current_activity() != null, START_DEADLINE_SECONDS)
	if _target.current_activity() == null or _target.current_activity().id != activity_id:
		return "he did not start %s (state %s)" % [activity_id, TargetAI.State.keys()[_target.state]]
	await _wait_seconds(POSE_SETTLE_SECONDS)
	return ""


func _frame_up_target() -> void:
	_player.global_position = _clear_viewpoint()
	_player.velocity = Vector3.ZERO
	_player.enter_camera_mode()
	var rig: PlayerCameraRig = _player.get_node("CameraRig") as PlayerCameraRig
	for frame: int in AIM_SETTLE_FRAMES:
		await get_tree().physics_frame
		await get_tree().process_frame
		var direction: Vector3 = (_target.head_position() - _player.current_camera().global_position).normalized()
		rig.yaw = atan2(-direction.x, -direction.z)
		rig.pitch = asin(direction.y)
	await get_tree().process_frame


## 8 m from his head with nothing in between, as near to straight ahead of him as the school allows.
func _clear_viewpoint() -> Vector3:
	var space: PhysicsDirectSpaceState3D = _target.get_world_3d().direct_space_state
	for degrees: float in VIEWPOINT_ANGLES_DEGREES:
		var spot: Vector3 = _anchor.global_position + _forward.rotated(Vector3.UP, deg_to_rad(degrees)) * SHOT_DISTANCE
		var eye_height: Vector3 = Vector3.UP * (_target.head_position().y - _anchor.global_position.y)
		if Detection.has_line_of_sight(space, _target.head_position(), spot + eye_height, []):
			return spot
	push_error("no clear viewpoint around %s" % _anchor.name)
	return _anchor.global_position + _forward * SHOT_DISTANCE


func _body_between(from: Vector3, to: Vector3) -> StaticBody3D:
	var body: StaticBody3D = StaticBody3D.new()
	body.collision_layer = PhysicsLayers.WORLD
	var box: CollisionShape3D = CollisionShape3D.new()
	var shape: BoxShape3D = BoxShape3D.new()
	shape.size = BLOCKER_SIZE
	box.shape = shape
	body.add_child(box)
	add_child(body)
	body.global_position = from.lerp(to, 0.5)
	body.look_at(to)
	return body


func _on_photo_taken(result: PhotoScorer.PhotoResult, image_path: String) -> void:
	_taken_results.append(result)
	_taken_paths.append(image_path)


func _wait_seconds(seconds: float) -> void:
	var end_seconds: float = _clock_seconds + seconds
	while _clock_seconds < end_seconds - 0.0001:
		await get_tree().physics_frame


func _wait_until(condition: Callable, limit: float) -> void:
	var end_seconds: float = _clock_seconds + limit
	while not condition.call() and _clock_seconds < end_seconds:
		await get_tree().physics_frame
