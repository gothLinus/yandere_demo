class_name EndingDirector
extends Node3D
## Plays one of the four week endings (spec §4.3a): a scripted camera shot, the target's choreography and a title card
## with a New Week button. The target is driven directly (animation tree, expression, head turn, walk) and never gets
## `setup()`, so his schedule logic stays passive.

signal ending_finished(ending_id: StringName)

const SHRINE_PHOTO_GROUP: StringName = &"shrine_photo"
const AUDIO_DIRECTOR_PATH: NodePath = ^"/root/AudioDirector"
const HEARTBEAT_METHOD: StringName = &"swell_heartbeat"

const TITLES: Dictionary = {
	&"cherry_tree": "Under the Cherry Tree",
	&"friends": "Friends First",
	&"stranger": "Just a Stranger",
	&"shrine": "The Shrine",
}

const TARGET_STAND_MARKER: String = "EndingStand_Target"
const PLAYER_STAND_MARKER: String = "EndingStand_Player"
const CAMERA_MARKER_PREFIX: String = "EndingCamera_"
const SHRINE_WALL_MARKER: String = "ShrineWall"
const GATE_MARKER: String = "Gate"

const STATE_IDLE: StringName = &"target_idle"
const STATE_WAVE: StringName = &"target_wave"
const STATE_LOCOMOTION: StringName = &"locomotion"
const EXPRESSION_HAPPY: StringName = &"happy"
const EXPRESSION_NEUTRAL: StringName = &"neutral"
const PLAYBACK_PARAMETER: StringName = &"parameters/playback"

const SEQUENCE_SECONDS: float = 12.0
const TURN_SECONDS: float = 1.2
const WAVE_SECONDS: float = 3.5
const NOTICE_DELAY_SECONDS: float = 1.5
const WALK_SPEED: float = 1.3
const WALK_TURN_RATE: float = 8.0
const TITLE_FADE_SECONDS: float = 1.0
const LOOK_AT_HEIGHT: float = 1.5

const CHERRY_PUSH_IN_DISTANCE: float = 2.0
const CHERRY_FIELD_OF_VIEW: float = 45.0
const FRIENDS_FIELD_OF_VIEW: float = 70.0
const STRANGER_FIELD_OF_VIEW: float = 50.0
const SHRINE_FIELD_OF_VIEW: float = 60.0
const PETAL_HEIGHT: float = 3.5
const PETAL_AMOUNT: int = 120
const PETAL_PREPROCESS_SECONDS: float = 8.0

const SHRINE_AMBIENT_COLOR: Color = Color(0.5, 0.05, 0.08)
const SHRINE_AMBIENT_ENERGY: float = 0.15
const SHRINE_LIGHT_COLOR: Color = Color(0.95, 0.08, 0.1)
const SHRINE_LIGHT_ENERGY: float = 0.35
const SHRINE_LIGHT_RANGE: float = 9.0
const SHRINE_LIGHT_HEIGHT: float = 0.6
const SHRINE_PLACEHOLDER_COLOR: Color = Color(1.0, 0.45, 0.7)
const SHRINE_EMISSION_ENERGY: float = 0.35
const SHRINE_TILE_SIZE: Vector2 = Vector2(0.6, 0.45)
const SHRINE_TILE_GAP: float = 0.12
const SHRINE_WALL_OFFSET: float = 0.04
const SHRINE_GRID_COLUMNS: int = 4
const SHRINE_PAN_FRACTION: float = 0.3

var _progress: WeekProgress
var _target_playback: AnimationNodeStateMachinePlayback
var _walk_path: PackedVector3Array = PackedVector3Array()
var _walk_length: float = 0.0
var _walk_distance: float = 0.0

@onready var _school_env: SchoolEnv = %SchoolEnv
@onready var _target: TargetAI = %Target
@onready var _player: StealthPlayer = %Player
@onready var _camera: Camera3D = %EndingCamera
@onready var _title_card: Control = %TitleCard
@onready var _title_label: Label = %TitleLabel
@onready var _new_week_button: Button = %NewWeekButton


func _ready() -> void:
	_title_card.visible = false
	_new_week_button.pressed.connect(GameManager.new_week)
	var animation_tree: AnimationTree = _target.get_node(^"AnimationTree")
	_target_playback = animation_tree.get(PLAYBACK_PARAMETER)


func _process(delta: float) -> void:
	if _walk_distance < _walk_length:
		_walk_distance = minf(_walk_distance + WALK_SPEED * delta, _walk_length)
		_move_target_along(_walk_distance, _walk_path, _walk_length)


func play(ending_id: StringName, progress: WeekProgress) -> void:
	_progress = progress
	ScreenSupport.show_cursor()
	_player.set_physics_process(false)
	_player.set_process_unhandled_input(false)
	_title_label.text = TITLES.get(ending_id, "")
	_place_actors()
	_camera.global_transform = _school_env.marker(CAMERA_MARKER_PREFIX + String(ending_id)).global_transform
	_camera.make_current()
	match ending_id:
		&"cherry_tree":
			await _play_cherry_tree()
		&"friends":
			await _play_friends()
		&"stranger":
			await _play_stranger()
		&"shrine":
			await _play_shrine()
		_:
			push_error("EndingDirector: unknown ending '%s'" % ending_id)
			return
	_show_title_card()
	ending_finished.emit(ending_id)


func _play_cherry_tree() -> void:
	_camera.fov = CHERRY_FIELD_OF_VIEW
	_start_petals()
	var push_end: Vector3 = _camera.global_position - _camera.global_basis.z * CHERRY_PUSH_IN_DISTANCE
	create_tween().tween_property(_camera, "global_position", push_end, SEQUENCE_SECONDS)
	_set_expression(EXPRESSION_NEUTRAL, 0.0)
	_target_playback.travel(STATE_IDLE)
	await _wait(NOTICE_DELAY_SECONDS)
	_turn_target_toward_player()
	_set_expression(EXPRESSION_HAPPY)
	await _wait(TURN_SECONDS)
	_target_playback.travel(STATE_WAVE)
	await _wait(WAVE_SECONDS)
	_target_playback.travel(STATE_IDLE)
	await _wait(SEQUENCE_SECONDS - NOTICE_DELAY_SECONDS - TURN_SECONDS - WAVE_SECONDS)


func _play_friends() -> void:
	_camera.fov = FRIENDS_FIELD_OF_VIEW
	_set_expression(EXPRESSION_NEUTRAL, 0.0)
	_target_playback.travel(STATE_IDLE)
	await _wait(NOTICE_DELAY_SECONDS)
	_turn_target_toward_player()
	_set_expression(EXPRESSION_HAPPY)
	await _wait(TURN_SECONDS)
	_target_playback.travel(STATE_WAVE)
	await _wait(SEQUENCE_SECONDS - NOTICE_DELAY_SECONDS - TURN_SECONDS)


func _play_stranger() -> void:
	_camera.fov = STRANGER_FIELD_OF_VIEW
	_set_expression(EXPRESSION_NEUTRAL, 0.0)
	if not _school_env.is_navigation_ready:
		await _school_env.navigation_ready
	var path: PackedVector3Array = NavigationServer3D.map_get_path(
		_school_env.navigation_map(),
		_target.global_position,
		_school_env.marker(GATE_MARKER).global_position,
		true
	)
	# The stand can lie off the navmesh, so the walk starts at the stand itself instead of popping onto the path.
	path.insert(0, _target.global_position)
	# The Gate is far away, so the shot cuts to the title card before he gets there.
	var walked_length: float = minf(_path_length(path), WALK_SPEED * SEQUENCE_SECONDS)
	_target.get_node(^"AnimationTree").set(TargetAI.LOCOMOTION_BLEND_PARAMETER, 1.0)
	_target_playback.travel(STATE_LOCOMOTION)
	_walk_path = path
	_walk_length = walked_length
	_walk_distance = 0.0
	await _wait(SEQUENCE_SECONDS)


func _play_shrine() -> void:
	_camera.fov = SHRINE_FIELD_OF_VIEW
	_target.visible = false
	_player.visible = false
	var wall: Node3D = _school_env.marker(SHRINE_WALL_MARKER)
	var wall_normal: Vector3 = _wall_normal(wall)
	var wall_tangent: Vector3 = Vector3.UP.cross(wall_normal).normalized()
	_dim_to_red_light()
	var grid_width: float = _hang_photos(wall, wall_normal, wall_tangent)
	_swell_heartbeat()
	var pan_distance: float = grid_width * SHRINE_PAN_FRACTION
	var camera_rest: Vector3 = _camera.global_position
	_camera.global_position = camera_rest - wall_tangent * pan_distance
	create_tween().tween_property(_camera, "global_position", camera_rest + wall_tangent * pan_distance, SEQUENCE_SECONDS)
	await _wait(SEQUENCE_SECONDS)


func _place_actors() -> void:
	_target.global_transform = _school_env.marker(TARGET_STAND_MARKER).global_transform
	_player.global_transform = _school_env.marker(PLAYER_STAND_MARKER).global_transform
	_target.velocity = Vector3.ZERO
	_player.velocity = Vector3.ZERO


func _turn_target_toward_player() -> void:
	var offset: Vector3 = _player.global_position - _target.global_position
	var final_yaw: float = atan2(-offset.x, -offset.z)
	create_tween().tween_property(_target, "rotation:y", final_yaw, TURN_SECONDS)
	_target.look_toward(_player.global_position + Vector3.UP * LOOK_AT_HEIGHT)


func _set_expression(expression: StringName, blend_seconds: float = 0.25) -> void:
	var controller: ExpressionController = _target.get_node(^"ExpressionController")
	controller.set_expression(expression, blend_seconds)


func _start_petals() -> void:
	var petals: GPUParticles3D = _school_env.get_node(^"Petals")
	petals.global_position = _target.global_position + Vector3.UP * PETAL_HEIGHT
	petals.amount = PETAL_AMOUNT
	petals.preprocess = PETAL_PREPROCESS_SECONDS
	petals.restart()


func _path_length(path: PackedVector3Array) -> float:
	var total: float = 0.0
	for index: int in range(1, path.size()):
		total += path[index - 1].distance_to(path[index])
	return total


func _move_target_along(distance: float, path: PackedVector3Array, path_length: float) -> void:
	if path.size() < 2:
		return
	var remaining: float = clampf(distance, 0.0, path_length)
	for index: int in range(1, path.size()):
		var segment_length: float = path[index - 1].distance_to(path[index])
		if remaining > segment_length and index < path.size() - 1:
			remaining -= segment_length
			continue
		var direction: Vector3 = (path[index] - path[index - 1]).normalized()
		_target.global_position = path[index - 1] + direction * minf(remaining, segment_length)
		var wanted_yaw: float = atan2(-direction.x, -direction.z)
		_target.rotation.y = lerp_angle(_target.rotation.y, wanted_yaw, minf(1.0, WALK_TURN_RATE * get_process_delta_time()))
		return


## The wall's horizontal axis that points toward the shrine camera, so the photos hang on the room side.
func _wall_normal(wall: Node3D) -> Vector3:
	var to_camera: Vector3 = _camera.global_position - wall.global_position
	to_camera.y = 0.0
	var best: Vector3 = Vector3.ZERO
	var best_alignment: float = 0.0
	for axis: Vector3 in [wall.global_basis.x, wall.global_basis.z]:
		var flat_axis: Vector3 = Vector3(axis.x, 0.0, axis.z).normalized()
		var alignment: float = flat_axis.dot(to_camera)
		if absf(alignment) > absf(best_alignment):
			best = flat_axis * signf(alignment)
			best_alignment = alignment
	return best


## Hangs one textured quad per banked photo in front of the wall and returns the grid's width.
func _hang_photos(wall: Node3D, wall_normal: Vector3, wall_tangent: Vector3) -> float:
	var photos: Array[Dictionary] = _progress.banked_photos
	var columns: int = mini(SHRINE_GRID_COLUMNS, maxi(photos.size(), 1))
	var rows: int = ceili(float(photos.size()) / columns)
	var cell: Vector2 = SHRINE_TILE_SIZE + Vector2.ONE * SHRINE_TILE_GAP
	var orientation: Basis = Basis(wall_tangent, Vector3.UP, wall_normal)
	for index: int in photos.size():
		var column: int = index % columns
		var row: int = floori(float(index) / columns)
		var quad: MeshInstance3D = MeshInstance3D.new()
		var mesh: QuadMesh = QuadMesh.new()
		mesh.size = SHRINE_TILE_SIZE
		quad.mesh = mesh
		quad.material_override = _photo_material(String(photos[index]["path"]))
		quad.add_to_group(SHRINE_PHOTO_GROUP)
		add_child(quad)
		var offset: Vector3 = wall_tangent * (column - (columns - 1) * 0.5) * cell.x \
			+ Vector3.UP * ((rows - 1) * 0.5 - row) * cell.y \
			+ wall_normal * SHRINE_WALL_OFFSET
		quad.global_transform = Transform3D(orientation, wall.global_position + offset)
	return columns * cell.x


func _photo_material(path: String) -> StandardMaterial3D:
	var material: StandardMaterial3D = StandardMaterial3D.new()
	var texture: ImageTexture = _load_photo(path)
	if texture == null:
		material.albedo_color = SHRINE_PLACEHOLDER_COLOR
		material.emission_enabled = true
		material.emission = SHRINE_PLACEHOLDER_COLOR
	else:
		material.albedo_texture = texture
		material.emission_enabled = true
		material.emission_texture = texture
	material.emission_energy_multiplier = SHRINE_EMISSION_ENERGY
	return material


func _load_photo(path: String) -> ImageTexture:
	if path.is_empty() or not FileAccess.file_exists(path):
		return null
	var image: Image = Image.load_from_file(path)
	return ImageTexture.create_from_image(image) if image != null else null


func _dim_to_red_light() -> void:
	var sun: DirectionalLight3D = _school_env.get_node(^"Sun")
	sun.light_energy = 0.0
	var world_environment: WorldEnvironment = _school_env.get_node(^"WorldEnvironment")
	# The scene's Environment is a shared sub-resource, so changing it in place would leak into later runs.
	var environment: Environment = world_environment.environment.duplicate()
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = SHRINE_AMBIENT_COLOR
	environment.ambient_light_energy = SHRINE_AMBIENT_ENERGY
	world_environment.environment = environment
	var light: OmniLight3D = OmniLight3D.new()
	light.light_color = SHRINE_LIGHT_COLOR
	light.light_energy = SHRINE_LIGHT_ENERGY
	light.omni_range = SHRINE_LIGHT_RANGE
	add_child(light)
	light.global_position = _camera.global_position + Vector3.UP * SHRINE_LIGHT_HEIGHT


## Task 21's AudioDirector implements `swell_heartbeat(duration_seconds)`; without it the shrine stays silent.
func _swell_heartbeat() -> void:
	var audio_director: Node = get_node_or_null(AUDIO_DIRECTOR_PATH)
	if audio_director != null and audio_director.has_method(HEARTBEAT_METHOD):
		audio_director.call(HEARTBEAT_METHOD, SEQUENCE_SECONDS)


func _show_title_card() -> void:
	_title_card.modulate.a = 0.0
	_title_card.visible = true
	create_tween().tween_property(_title_card, "modulate:a", 1.0, TITLE_FADE_SECONDS)
	_new_week_button.grab_focus()


func _wait(seconds: float) -> void:
	await get_tree().create_timer(maxf(seconds, 0.0)).timeout
