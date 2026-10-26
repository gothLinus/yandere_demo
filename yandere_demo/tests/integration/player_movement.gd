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
	player.noise_made.connect(func(_position: Vector3, stance: GameTypes.Stance) -> void: _noise_stances.append(stance))
	player.interact_prompt_changed.connect(func(text: String) -> void: _prompts.append(text))
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

	if not player.enter_camera_mode():
		fail_test("camera mode refused")
		return
	await get_tree().create_timer(0.5).timeout
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
