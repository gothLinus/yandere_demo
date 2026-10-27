extends VisualCapture
## Windowed (Task 23b): the target's motion. With `-- --sheets` it saves a contact sheet per clip (eight moments, from
## the front three-quarter view above the side view). With `-- --sequence=sit` or `-- --sequence=startle` it plays
## walk -> sit_down -> sit_read, or idle -> notice_player -> startled, through the AnimationTree with the springs active;
## run those under Movie Maker (`--write-movie <dir>/frame.png --fixed-fps 30`) for a frame-exact 30 fps PNG sequence.

const TARGET_SCENE: PackedScene = preload("res://scenes/target.tscn")
const SKELETON_PATH: NodePath = ^"Model/TargetChar/Skeleton3D"
const PLAYBACK_PARAMETER: StringName = &"parameters/playback"
const LOCOMOTION_STATE: StringName = &"locomotion"
const IDLE_STATE: StringName = &"target_idle"
const SHEET_TILES: int = 8
const SHEET_VIEWS: Array[float] = [25.0, 90.0]
const TILE_SIZE: Vector2i = Vector2i(300, 460)
const SHEET_DISTANCE: float = 2.9
const SHEET_CAMERA_HEIGHT: float = 1.05
const SHEET_LOOK_HEIGHT: float = 0.85
const SPRING_SETTLE_FRAMES: int = 12
const FIELD_OF_VIEW: float = 40.0
const FRAMES_PER_SECOND: float = 30.0
const WALK_SPEED: float = 1.3
const WALK_FRAMES: int = 48
const STOP_FRAMES: int = 9
const SEAT_HEIGHT: float = 0.45
const SEAT_SIZE: Vector3 = Vector3(0.42, 0.45, 0.38)
## The seat's centre lies this far behind the seated hip joints, under the buttocks.
const SEAT_BEHIND_HIPS: float = 0.06
const FLOOR_STRIPE_SPACING: float = 0.25
const FLOOR_STRIPE_COUNT: int = 24
const FLOOR_STRIPE_SIZE: Vector3 = Vector3(0.04, 0.002, 1.6)
const STARTLE_IDLE_FRAMES: int = 15
const SEQUENCE_TAIL_FRAMES: int = 20

@onready var _camera: Camera3D = $Camera3D

var _target: TargetAI
var _tree: AnimationTree
var _player: AnimationPlayer
var _playback: AnimationNodeStateMachinePlayback


func _ready() -> void:
	_target = TARGET_SCENE.instantiate() as TargetAI
	add_child(_target)
	_target.set_physics_process(false)
	_camera.fov = FIELD_OF_VIEW
	var expression: ExpressionController = _target.get_node(^"ExpressionController") as ExpressionController
	expression.set_process(false)
	expression.set_expression(&"neutral", 0.0)
	_tree = _target.get_node(^"AnimationTree") as AnimationTree
	_player = _target.get_node(^"Model/AnimationPlayer") as AnimationPlayer
	_playback = _tree.get(PLAYBACK_PARAMETER)
	var arguments: PackedStringArray = OS.get_cmdline_user_args()
	if arguments.has("--sheets"):
		await _capture_sheets()
	elif arguments.has("--sequence=sit"):
		await _play_sit_sequence()
	elif arguments.has("--sequence=startle"):
		await _play_startle_sequence()
	finish()


func _capture_sheets() -> void:
	_tree.active = false
	var props: TargetProps = _target.get_node(^"TargetProps") as TargetProps
	for animation_name: StringName in _player.get_animation_list():
		if not String(animation_name).begins_with("target_"):
			continue
		_player.play(animation_name)
		props.show_for(animation_name)
		var length: float = _player.current_animation_length
		var sheet: Image = Image.create_empty(TILE_SIZE.x * SHEET_TILES, TILE_SIZE.y * SHEET_VIEWS.size(), false,
				Image.FORMAT_RGBA8)
		for tile: int in SHEET_TILES:
			_player.seek(length * tile / (SHEET_TILES - 1), true)
			_player.pause()
			await wait_frames(SPRING_SETTLE_FRAMES)
			for row: int in SHEET_VIEWS.size():
				_aim_around(deg_to_rad(SHEET_VIEWS[row]))
				await RenderingServer.frame_post_draw
				var image: Image = get_viewport().get_texture().get_image()
				image.convert(Image.FORMAT_RGBA8)
				var height: int = image.get_height()
				var width: int = height * TILE_SIZE.x / TILE_SIZE.y
				image = image.get_region(Rect2i((image.get_width() - width) / 2, 0, width, height))
				image.resize(TILE_SIZE.x, TILE_SIZE.y, Image.INTERPOLATE_LANCZOS)
				sheet.blit_rect(image, Rect2i(Vector2i.ZERO, TILE_SIZE), Vector2i(tile * TILE_SIZE.x, row * TILE_SIZE.y))
		_save_image(sheet, "sheet_%s" % animation_name)
	props.show_for(&"")


## He walks in along +X at 1.3 m/s over a striped floor (so any slide shows), past the front of a 0.45 m seat that waits
## under where his hips will land, turns to face away from it as he slows to a stop over 0.3 s, sits down and reads.
func _play_sit_sequence() -> void:
	var seat_offset: Vector3 = await _seated_hips_offset()
	var walk_distance: float = WALK_SPEED * WALK_FRAMES / FRAMES_PER_SECOND
	var stop_distance: float = WALK_SPEED * 0.5 * STOP_FRAMES / FRAMES_PER_SECOND
	_target.global_position = Vector3(-walk_distance - stop_distance, 0.0, 0.0)
	_target.rotation.y = -PI * 0.5
	_add_floor_stripes()
	_add_seat(seat_offset + Vector3(0.0, 0.0, SEAT_BEHIND_HIPS))
	_aim(Vector3(1.2, 1.2, -2.4), Vector3(-0.5, 0.75, 0.0))
	_tree.set(TargetAI.LOCOMOTION_BLEND_PARAMETER, 1.0)
	_tree.set(TargetAI.WALK_TIME_SCALE_PARAMETER, 1.0)
	_playback.start(LOCOMOTION_STATE)
	for frame: int in WALK_FRAMES:
		await get_tree().process_frame
		_target.global_position.x += WALK_SPEED / FRAMES_PER_SECOND
	for frame: int in STOP_FRAMES:
		var share: float = 1.0 - float(frame + 1) / STOP_FRAMES
		_tree.set(TargetAI.LOCOMOTION_BLEND_PARAMETER, share)
		_tree.set(TargetAI.WALK_TIME_SCALE_PARAMETER, share)
		await get_tree().process_frame
		_target.global_position.x += WALK_SPEED * share / FRAMES_PER_SECOND
		_target.rotation.y = -PI * 0.5 * share
	_target.global_position.x = 0.0
	_playback.travel(TargetAI.ANIMATION_SIT_DOWN)
	await wait_frames(roundi(_animation_length(TargetAI.ANIMATION_SIT_DOWN) * FRAMES_PER_SECOND))
	_playback.travel(&"target_sit_read")
	(_target.get_node(^"TargetProps") as TargetProps).show_for(&"target_sit_read")
	await wait_frames(roundi(_animation_length(&"target_sit_read") * FRAMES_PER_SECOND))


func _play_startle_sequence() -> void:
	_aim(Vector3(0.7, 1.4, -1.6), Vector3(0.0, 1.05, 0.0))
	_playback.start(IDLE_STATE)
	await wait_frames(STARTLE_IDLE_FRAMES)
	_playback.travel(TargetAI.ANIMATION_NOTICE)
	await wait_frames(roundi(_animation_length(TargetAI.ANIMATION_NOTICE) * FRAMES_PER_SECOND))
	_playback.travel(TargetAI.ANIMATION_STARTLED)
	await wait_frames(roundi(_animation_length(TargetAI.ANIMATION_STARTLED) * FRAMES_PER_SECOND) + SEQUENCE_TAIL_FRAMES)


## Where the hip joints sit in target_sit, relative to his root.
func _seated_hips_offset() -> Vector3:
	_tree.active = false
	_player.play(TargetAI.ANIMATION_SIT)
	_player.seek(0.0, true)
	await get_tree().process_frame
	var skeleton: Skeleton3D = _target.get_node(SKELETON_PATH) as Skeleton3D
	var hips: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("hips")).origin
	_player.stop()
	_tree.active = true
	return hips - _target.global_position


func _add_seat(hips: Vector3) -> void:
	var seat: MeshInstance3D = MeshInstance3D.new()
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = Vector3(SEAT_SIZE.x, SEAT_HEIGHT, SEAT_SIZE.z)
	seat.mesh = mesh
	seat.position = Vector3(hips.x, SEAT_HEIGHT * 0.5, hips.z)
	add_child(seat)


func _add_floor_stripes() -> void:
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = FLOOR_STRIPE_SIZE
	for index: int in FLOOR_STRIPE_COUNT:
		var stripe: MeshInstance3D = MeshInstance3D.new()
		stripe.mesh = mesh
		stripe.position = Vector3(-index * FLOOR_STRIPE_SPACING + 0.5, 0.0, -0.4)
		add_child(stripe)


func _animation_length(animation_name: StringName) -> float:
	return _player.get_animation(animation_name).length


func _save_image(image: Image, capture_name: String) -> void:
	var path: String = "%s/%s.png" % [CAPTURE_DIRECTORY, capture_name]
	var error: Error = image.save_png(path)
	if error != OK:
		push_error("CaptureTargetMotion: could not save %s (%s)" % [path, error_string(error)])
		return
	saved_paths.append(ProjectSettings.globalize_path(path))
	print("CAPTURE %s" % ProjectSettings.globalize_path(path))


## Orbits the camera around the target; angle 0 looks at his face (the model faces -Z).
func _aim_around(angle: float) -> void:
	var offset: Vector3 = Vector3(sin(angle), 0.0, -cos(angle)) * SHEET_DISTANCE
	_aim(Vector3(offset.x, SHEET_CAMERA_HEIGHT, offset.z), Vector3(0.0, SHEET_LOOK_HEIGHT, 0.0))


func _aim(from: Vector3, at: Vector3) -> void:
	_camera.global_position = from
	_camera.look_at(at)
