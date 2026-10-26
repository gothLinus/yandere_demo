extends IntegrationTest

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const WALK_SECONDS: float = 1.0
const MINIMUM_DISTANCE: float = 1.5
const CROUCH_SETTLE_SECONDS: float = 0.6
const MAXIMUM_CROUCH_HEIGHT: float = 1.05
const PROMPT_TEXT: String = "Open the door"

var _noise_stances: Array[GameTypes.Stance] = []
var _prompts: Array[String] = []


class PromptingInteractable:
	extends Interactable

	func prompt_text(_player: StealthPlayer) -> String:
		return PROMPT_TEXT


func _ready() -> void:
	var school_env: SchoolEnv = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(school_env)
	await school_env.navigation_ready
	var player: StealthPlayer = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(player)
	player.global_transform = school_env.marker("PlayerSpawn").global_transform
	await get_tree().physics_frame
	await get_tree().physics_frame
	var start_playback: AnimationNodeStateMachinePlayback = (player.get_node("AnimationTree") as AnimationTree).get("parameters/playback")
	if start_playback.get_current_node() != StealthPlayer.STATE_LOCOMOTION:
		fail_test("a fresh player is not in locomotion but %s, so the model stands in its rest pose" % start_playback.get_current_node())
		return
	player.noise_made.connect(func(_position: Vector3, stance: GameTypes.Stance) -> void: _noise_stances.append(stance))
	player.interact_prompt_changed.connect(func(text: String) -> void: _prompts.append(text))
	if not await _line_of_sight_ignores_characters(player):
		return
	var start: Vector3 = player.global_position

	Input.action_press("move_forward")
	await get_tree().create_timer(WALK_SECONDS).timeout
	Input.action_release("move_forward")
	var travelled: float = start.distance_to(player.global_position)
	if travelled <= MINIMUM_DISTANCE:
		fail_test("moved only %.2f m in %.1f s" % [travelled, WALK_SECONDS])
		return
	if _noise_stances.is_empty() or _noise_stances[0] != GameTypes.Stance.WALK:
		fail_test("walking emitted no WALK footstep noise: %s" % [_noise_stances])
		return
	if player.stance != GameTypes.Stance.WALK:
		fail_test("expected WALK while moving, got %d" % player.stance)
		return

	Input.action_press("crouch")
	await get_tree().physics_frame
	await get_tree().physics_frame
	Input.action_release("crouch")
	await get_tree().create_timer(CROUCH_SETTLE_SECONDS).timeout
	if player.stance != GameTypes.Stance.SNEAK:
		fail_test("crouch did not select SNEAK, got %d" % player.stance)
		return
	var shape_node: CharacterBodyShape = player.get_node("CharacterBodyShape") as CharacterBodyShape
	if shape_node.collision_shape == null or not shape_node.collision_shape.is_inside_tree():
		fail_test("body collision shape missing")
		return
	var height: float = shape_node.height()
	if height > MAXIMUM_CROUCH_HEIGHT:
		fail_test("crouched collision height %.2f > %.2f" % [height, MAXIMUM_CROUCH_HEIGHT])
		return

	var interactable: PromptingInteractable = PromptingInteractable.new()
	var interactable_shape: CollisionShape3D = CollisionShape3D.new()
	interactable_shape.shape = SphereShape3D.new()
	interactable.add_child(interactable_shape)
	add_child(interactable)
	interactable.global_position = player.global_position + Vector3(0.0, 0.8, 0.5)
	await get_tree().create_timer(0.3).timeout
	if _prompts != [PROMPT_TEXT]:
		fail_test("interact prompt not announced exactly once: %s" % [_prompts])
		return

	var camera_failure: String = await _camera_mode_failure(player)
	if not camera_failure.is_empty():
		fail_test(camera_failure)
		return
	var playback: AnimationNodeStateMachinePlayback = (player.get_node("AnimationTree") as AnimationTree).get("parameters/playback")
	var prop: Node3D = player.find_child("CameraProp", true, false) as Node3D
	if playback.get_current_node() != &"photo" or prop == null or not prop.is_visible_in_tree():
		fail_test("camera mode did not raise the camera (state %s)" % playback.get_current_node())
		return
	player.exit_camera_mode()
	if prop.visible:
		fail_test("camera prop still visible outside camera mode")
		return
	pass_test()


func _line_of_sight_ignores_characters(player: StealthPlayer) -> bool:
	var target_head: Vector3 = player.head_position() + Vector3(0.0, 0.0, -1.5)
	var character_body: StaticBody3D = _body_at(target_head, PhysicsLayers.CHARACTERS, Vector3.ONE * 0.5)
	await get_tree().physics_frame
	await get_tree().physics_frame
	var space: PhysicsDirectSpaceState3D = player.get_world_3d().direct_space_state
	if not player.is_watching(target_head, space, 10.0):
		fail_test("a character-layer body around the target head blocked the line of sight")
		return false
	var wall: StaticBody3D = _body_at(target_head + Vector3(0.0, 0.0, 0.75), PhysicsLayers.WORLD, Vector3(2.0, 2.0, 0.1))
	await get_tree().physics_frame
	await get_tree().physics_frame
	if player.is_watching(target_head, space, 10.0):
		fail_test("a world wall did not block the line of sight")
		return false
	character_body.queue_free()
	wall.queue_free()
	return true


func _body_at(position: Vector3, layer: int, size: Vector3) -> StaticBody3D:
	var body: StaticBody3D = StaticBody3D.new()
	body.collision_layer = layer
	var box: CollisionShape3D = CollisionShape3D.new()
	var shape: BoxShape3D = BoxShape3D.new()
	shape.size = size
	box.shape = shape
	body.add_child(box)
	add_child(body)
	body.global_position = position
	return body


func _camera_mode_failure(player: StealthPlayer) -> String:
	if player.stance != GameTypes.Stance.SNEAK:
		return "player should still be crouched before the camera test"
	if not player.enter_camera_mode():
		return "camera mode refused"
	await get_tree().create_timer(0.5).timeout
	if player.stance != GameTypes.Stance.WALK:
		return "camera mode kept stance %d" % player.stance
	var shape_node: CharacterBodyShape = player.get_node("CharacterBodyShape") as CharacterBodyShape
	if shape_node.height() < 1.5:
		return "camera mode kept the crouched collision (%.2f m)" % shape_node.height()
	var viewfinder: Camera3D = player.get_node("CameraRig/ViewfinderCamera") as Camera3D
	var head_height: float = player.head_position().y - player.global_position.y
	if absf(head_height - viewfinder.position.y) > 0.001:
		return "head %.2f m and viewfinder %.2f m disagree" % [head_height, viewfinder.position.y]
	var lens: MeshInstance3D = player.find_child("Lens", true, false) as MeshInstance3D
	if lens == null or not lens.mesh.surface_get_material(0) is ShaderMaterial:
		return "camera prop is not toon shaded"
	return ""
