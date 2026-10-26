class_name StealthPlayer
extends CharacterBody3D

signal stance_changed(stance: GameTypes.Stance)
signal mode_changed(mode: StringName)
signal interact_prompt_changed(text: String)
signal noise_made(position: Vector3, stance: GameTypes.Stance)
signal carried_item_changed(item_id: StringName)

const WALK_SPEED: float = 2.2
const RUN_SPEED: float = 4.5
const SNEAK_SPEED: float = 1.1
const VISION_SPEED_MULTIPLIER: float = 0.7
const STAND_HEIGHT: float = 1.6
const CROUCH_HEIGHT: float = 1.0
const CLEARANCE_LIFT: float = 0.05

const MODE_FREE: StringName = &"free"
const MODE_CAMERA: StringName = &"camera"
const MODE_HIDDEN: StringName = &"hidden"
const MODE_SEATED: StringName = &"seated"

const TURN_RATE: float = 10.0
const LOCOMOTION_BLEND_RATE: float = 8.0
const CROUCH_HEIGHT_RATIO: float = CROUCH_HEIGHT / STAND_HEIGHT
const ANIMATION_XFADE_SECONDS: float = 0.25
const CAMERA_HAND_BONE: StringName = &"hand.R"
const CAMERA_PROP_COLOR: Color = Color(0.08, 0.08, 0.1)
const CAMERA_PROP_BODY_SIZE: Vector3 = Vector3(0.12, 0.08, 0.06)
const CAMERA_PROP_LENS_RADIUS: float = 0.028
const CAMERA_PROP_LENS_LENGTH: float = 0.04
const CAMERA_PROP_OFFSET: Vector3 = Vector3(0.0, 0.05, 0.03)

const STATE_LOCOMOTION: StringName = &"locomotion"
const STATE_PHOTO: StringName = &"photo"
const STATE_HIDE: StringName = &"hide"
const STATE_SIT_DOWN: StringName = &"sit_down"
const STATE_SIT: StringName = &"sit"
const STATE_STAND_UP: StringName = &"stand_up"
const LOCOMOTION_POSITION_PARAMETER: StringName = &"parameters/locomotion/blend_position"
const PLAYBACK_PARAMETER: StringName = &"parameters/playback"

var tuning: StealthTuning = preload("res://data/stealth_tuning.tres")
var stance: GameTypes.Stance = GameTypes.Stance.WALK
var mode: StringName = MODE_FREE
var carried_item: StringName = &""
var hidden_spot: Node3D
var is_vision_active: bool = false
var low_sanity_slow: bool = false
var can_hide_callable: Callable = _default_can_hide

var _crouching: bool = false
var _crouch_blend: float = 0.0
var _locomotion_speed_blend: float = 0.0
var _prompt_text: String = ""
var _current_interactable: Interactable
var _playback: AnimationNodeStateMachinePlayback
var _camera_prop: Node3D

@onready var _body_shape: CharacterBodyShape = $CharacterBodyShape
@onready var _animation_tree: AnimationTree = $AnimationTree
@onready var _camera_rig: PlayerCameraRig = $CameraRig
@onready var _interaction_area: Area3D = $InteractionArea
@onready var _footstep_timer: Timer = $FootstepTimer
@onready var _model: Node3D = $Model


func _init() -> void:
	collision_layer = PhysicsLayers.PLAYER
	collision_mask = PhysicsLayers.WORLD


func _ready() -> void:
	_interaction_area.collision_layer = 0
	_interaction_area.collision_mask = PhysicsLayers.INTERACTABLE
	_build_animation_tree()
	_build_camera_prop()
	_footstep_timer.timeout.connect(_on_footstep_timer_timeout)


func _physics_process(delta: float) -> void:
	_poll_actions()
	var movement_input: Vector2 = Vector2.ZERO
	if mode == MODE_FREE or mode == MODE_CAMERA:
		movement_input = _step_body(delta)
	_update_crouch_blend(delta)
	_update_footsteps(movement_input)
	_update_interaction()
	_update_animation(movement_input, delta)


func current_activity() -> GameTypes.PlayerActivity:
	if mode == MODE_CAMERA:
		return GameTypes.PlayerActivity.CAMERA_RAISED
	if carried_item != &"":
		return GameTypes.PlayerActivity.CARRYING_ITEM
	return GameTypes.PlayerActivity.NONE


func move_speed() -> float:
	var speed: float = WALK_SPEED
	match stance:
		GameTypes.Stance.RUN:
			speed = RUN_SPEED
		GameTypes.Stance.SNEAK:
			speed = SNEAK_SPEED
			if low_sanity_slow:
				speed *= tuning.sneak_speed_low_sanity_multiplier
		GameTypes.Stance.HIDDEN:
			speed = 0.0
	if is_vision_active:
		speed *= VISION_SPEED_MULTIPLIER
	return speed


func enter_camera_mode() -> bool:
	if mode == MODE_HIDDEN or mode == MODE_SEATED:
		return false
	_crouching = false
	_crouch_blend = 0.0
	if is_node_ready():
		_body_shape.set_height_ratio(1.0)
	_set_stance(GameTypes.Stance.WALK)
	_set_mode(MODE_CAMERA)
	return true


func exit_camera_mode() -> void:
	if mode == MODE_CAMERA:
		_set_mode(MODE_FREE)


func enter_hidden(spot: Node3D) -> bool:
	if mode == MODE_HIDDEN or mode == MODE_SEATED or not can_hide_callable.call():
		return false
	exit_camera_mode()
	_snap_to(spot)
	hidden_spot = spot
	_set_stance(GameTypes.Stance.HIDDEN)
	_set_mode(MODE_HIDDEN)
	return true


func exit_hidden() -> void:
	if mode != MODE_HIDDEN:
		return
	hidden_spot = null
	if is_node_ready():
		_camera_rig.clear_peek_view()
	_set_stance(GameTypes.Stance.SNEAK if _crouching else GameTypes.Stance.WALK)
	_set_mode(MODE_FREE)


func show_peek_view(point: Node3D) -> void:
	_camera_rig.show_peek_view(point)


func is_position_clear(point: Vector3) -> bool:
	var shape_node: CollisionShape3D = _body_shape.collision_shape
	if shape_node == null:
		return true
	var query: PhysicsShapeQueryParameters3D = PhysicsShapeQueryParameters3D.new()
	query.shape = shape_node.shape
	query.transform = Transform3D(Basis.IDENTITY, point + shape_node.position + Vector3.UP * CLEARANCE_LIFT)
	query.collision_mask = PhysicsLayers.WORLD
	query.exclude = [get_rid()]
	return get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()


func sit(seat: Node3D) -> bool:
	if mode == MODE_HIDDEN or mode == MODE_SEATED:
		return false
	exit_camera_mode()
	_snap_to(seat)
	_set_mode(MODE_SEATED)
	return true


func stand_up() -> void:
	if mode == MODE_SEATED:
		_set_mode(MODE_FREE)


func pick_up(item_id: StringName) -> bool:
	if carried_item != &"":
		return false
	carried_item = item_id
	carried_item_changed.emit(carried_item)
	return true


func drop_carried() -> StringName:
	var dropped: StringName = carried_item
	if dropped != &"":
		carried_item = &""
		carried_item_changed.emit(carried_item)
	return dropped


func head_position() -> Vector3:
	var height: float = lerpf(STAND_HEIGHT, CROUCH_HEIGHT, _crouch_blend)
	return global_position + Vector3.UP * (height - tuning.eye_below_top)


func is_watching(target_head: Vector3, space: PhysicsDirectSpaceState3D, max_distance: float) -> bool:
	if not _camera_rig.current_camera().is_position_in_frustum(target_head):
		return false
	var origin: Vector3 = head_position()
	if origin.distance_to(target_head) > max_distance:
		return false
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(origin, target_head, PhysicsLayers.LINE_OF_SIGHT_MASK, [get_rid()])
	return space.intersect_ray(query).is_empty()


func _default_can_hide() -> bool:
	if not is_inside_tree():
		return true
	var sanity_system: Node = get_node_or_null("/root/SanitySystem")
	if sanity_system == null:
		return true
	return sanity_system.meters.can_hide()


func _snap_to(anchor: Node3D) -> void:
	var anchor_transform: Transform3D = anchor.global_transform if anchor.is_inside_tree() else anchor.transform
	if is_inside_tree():
		global_transform = anchor_transform
	else:
		transform = anchor_transform
	velocity = Vector3.ZERO


func _set_stance(new_stance: GameTypes.Stance) -> void:
	if new_stance == stance:
		return
	stance = new_stance
	stance_changed.emit(stance)


func _set_mode(new_mode: StringName) -> void:
	if new_mode == mode:
		return
	var previous_mode: StringName = mode
	mode = new_mode
	mode_changed.emit(mode)
	if not is_node_ready():
		return
	_camera_rig.set_viewfinder_active(mode == MODE_CAMERA)
	_camera_prop.visible = mode == MODE_CAMERA
	_body_shape.set_enabled(mode == MODE_FREE or mode == MODE_CAMERA)
	match mode:
		MODE_CAMERA:
			_playback.travel(STATE_PHOTO)
		MODE_HIDDEN:
			_playback.travel(STATE_HIDE)
		MODE_SEATED:
			_playback.travel(STATE_SIT_DOWN)
		_:
			_playback.travel(STATE_STAND_UP if previous_mode == MODE_SEATED else STATE_LOCOMOTION)


func _poll_actions() -> void:
	is_vision_active = Input.is_action_pressed(&"yandere_vision")
	if Input.is_action_just_pressed(&"camera_mode"):
		if mode == MODE_CAMERA:
			exit_camera_mode()
		else:
			enter_camera_mode()
	if Input.is_action_just_pressed(&"crouch") and mode == MODE_FREE:
		_crouching = not _crouching
	if Input.is_action_just_pressed(&"interact"):
		match mode:
			MODE_SEATED:
				stand_up()
			MODE_FREE, MODE_HIDDEN:
				if _current_interactable != null:
					_current_interactable.interact(self)


func _step_body(delta: float) -> Vector2:
	var input_vector: Vector2 = Vector2.ZERO
	if mode == MODE_FREE and not _is_standing_up():
		input_vector = Input.get_vector(&"move_left", &"move_right", &"move_forward", &"move_back")
		var wants_run: bool = Input.is_action_pressed(&"run") and not _crouching and input_vector != Vector2.ZERO
		if _crouching:
			_set_stance(GameTypes.Stance.SNEAK)
		else:
			_set_stance(GameTypes.Stance.RUN if wants_run else GameTypes.Stance.WALK)
	var direction: Vector3 = _camera_rig.yaw_basis() * Vector3(input_vector.x, 0.0, input_vector.y)
	var horizontal_velocity: Vector3 = direction * move_speed()
	velocity.x = horizontal_velocity.x
	velocity.z = horizontal_velocity.z
	if is_on_floor():
		velocity.y = 0.0
	else:
		velocity.y -= float(ProjectSettings.get_setting("physics/3d/default_gravity")) * delta
	var facing_yaw: float = _camera_rig.yaw
	if direction != Vector3.ZERO:
		facing_yaw = atan2(-direction.x, -direction.z)
	if direction != Vector3.ZERO or mode == MODE_CAMERA:
		rotation.y = lerp_angle(rotation.y, facing_yaw, minf(1.0, TURN_RATE * delta))
	move_and_slide()
	return input_vector


func _is_standing_up() -> bool:
	return _playback.get_current_node() == STATE_STAND_UP


func _update_crouch_blend(delta: float) -> void:
	var target: float = 1.0 if _crouching else 0.0
	_crouch_blend = move_toward(_crouch_blend, target, tuning.crouch_blend_rate * delta)
	_body_shape.set_height_ratio(lerpf(1.0, CROUCH_HEIGHT_RATIO, _crouch_blend))


func _update_footsteps(movement_input: Vector2) -> void:
	var is_stepping: bool = mode == MODE_FREE and movement_input != Vector2.ZERO and is_on_floor()
	if not is_stepping:
		_footstep_timer.stop()
	elif _footstep_timer.is_stopped():
		_start_footstep_timer()


func _start_footstep_timer() -> void:
	_footstep_timer.start(tuning.footstep_stride_meters / maxf(move_speed(), 0.1))


func _on_footstep_timer_timeout() -> void:
	noise_made.emit(global_position, stance)
	_start_footstep_timer()


func _update_interaction() -> void:
	var nearest: Interactable = null
	if mode == MODE_HIDDEN:
		nearest = hidden_spot as Interactable
	elif mode == MODE_FREE:
		var nearest_distance: float = INF
		for area: Area3D in _interaction_area.get_overlapping_areas():
			var interactable: Interactable = area as Interactable
			if interactable == null or not interactable.can_interact(self):
				continue
			var distance: float = global_position.distance_squared_to(interactable.global_position)
			if distance < nearest_distance:
				nearest = interactable
				nearest_distance = distance
	_current_interactable = nearest
	var text: String = nearest.prompt_text(self) if nearest != null else ""
	if text != _prompt_text:
		_prompt_text = text
		interact_prompt_changed.emit(_prompt_text)


func _update_animation(movement_input: Vector2, delta: float) -> void:
	var target_speed: float = 0.0
	if movement_input != Vector2.ZERO:
		target_speed = 2.0 if stance == GameTypes.Stance.RUN else 1.0
	_locomotion_speed_blend = move_toward(_locomotion_speed_blend, target_speed, LOCOMOTION_BLEND_RATE * delta)
	_animation_tree.set(LOCOMOTION_POSITION_PARAMETER, Vector2(_locomotion_speed_blend, _crouch_blend))


func _build_animation_tree() -> void:
	var locomotion: AnimationNodeBlendSpace2D = AnimationNodeBlendSpace2D.new()
	locomotion.min_space = Vector2(0.0, 0.0)
	locomotion.max_space = Vector2(2.0, 1.0)
	locomotion.add_blend_point(_animation_node(&"player_idle"), Vector2(0.0, 0.0), -1, &"idle")
	locomotion.add_blend_point(_animation_node(&"player_walk"), Vector2(1.0, 0.0), -1, &"walk")
	locomotion.add_blend_point(_animation_node(&"player_run"), Vector2(2.0, 0.0), -1, &"run")
	locomotion.add_blend_point(_animation_node(&"player_crouch_idle"), Vector2(0.0, 1.0), -1, &"crouch_idle")
	locomotion.add_blend_point(_animation_node(&"player_sneak"), Vector2(1.0, 1.0), -1, &"sneak")
	var machine: AnimationNodeStateMachine = AnimationNodeStateMachine.new()
	machine.add_node(STATE_LOCOMOTION, locomotion, Vector2(0.0, 0.0))
	machine.add_node(STATE_PHOTO, _animation_node(&"player_take_photo"), Vector2(250.0, -100.0))
	machine.add_node(STATE_HIDE, _animation_node(&"player_hide"), Vector2(250.0, 0.0))
	machine.add_node(STATE_SIT_DOWN, _animation_node(&"player_sit_down"), Vector2(250.0, 100.0))
	machine.add_node(STATE_SIT, _animation_node(&"player_sit"), Vector2(500.0, 100.0))
	machine.add_node(STATE_STAND_UP, _animation_node(&"player_stand_up"), Vector2(250.0, 200.0))
	machine.add_transition(&"Start", STATE_LOCOMOTION, AnimationNodeStateMachineTransition.new())
	for state: StringName in [STATE_PHOTO, STATE_HIDE, STATE_SIT_DOWN]:
		machine.add_transition(STATE_LOCOMOTION, state, _transition())
		machine.add_transition(state, STATE_LOCOMOTION, _transition())
	machine.add_transition(STATE_PHOTO, STATE_HIDE, _transition())
	machine.add_transition(STATE_PHOTO, STATE_SIT_DOWN, _transition())
	machine.add_transition(STATE_SIT_DOWN, STATE_SIT, _transition(true))
	machine.add_transition(STATE_SIT, STATE_STAND_UP, _transition())
	machine.add_transition(STATE_SIT_DOWN, STATE_STAND_UP, _transition())
	machine.add_transition(STATE_STAND_UP, STATE_LOCOMOTION, _transition(true))
	_animation_tree.tree_root = machine
	_animation_tree.active = true
	_playback = _animation_tree.get(PLAYBACK_PARAMETER) as AnimationNodeStateMachinePlayback


func _animation_node(animation_name: StringName) -> AnimationNodeAnimation:
	var node: AnimationNodeAnimation = AnimationNodeAnimation.new()
	node.animation = animation_name
	return node


func _transition(automatic: bool = false) -> AnimationNodeStateMachineTransition:
	var transition: AnimationNodeStateMachineTransition = AnimationNodeStateMachineTransition.new()
	transition.xfade_time = ANIMATION_XFADE_SECONDS
	if automatic:
		transition.advance_mode = AnimationNodeStateMachineTransition.ADVANCE_MODE_AUTO
		transition.switch_mode = AnimationNodeStateMachineTransition.SWITCH_MODE_AT_END
	return transition


func _build_camera_prop() -> void:
	var skeleton: Skeleton3D = _model.find_child("Skeleton3D", true, false) as Skeleton3D
	if skeleton == null:
		push_error("StealthPlayer: model has no Skeleton3D for the camera prop")
		return
	var attachment: BoneAttachment3D = BoneAttachment3D.new()
	attachment.name = "CameraPropAttachment"
	attachment.bone_name = CAMERA_HAND_BONE
	skeleton.add_child(attachment)
	_camera_prop = _make_camera_prop()
	_camera_prop.visible = false
	attachment.add_child(_camera_prop)


## Bone axes (checked against player_take_photo): +Y along the fingers, +Z toward the way the character faces.
func _make_camera_prop() -> Node3D:
	var source: StandardMaterial3D = StandardMaterial3D.new()
	source.resource_name = "M_CameraProp"
	source.albedo_color = CAMERA_PROP_COLOR
	var material: ShaderMaterial = ToonConverter.make_toon_material(source)
	var body_mesh: BoxMesh = BoxMesh.new()
	body_mesh.size = CAMERA_PROP_BODY_SIZE
	body_mesh.material = material
	var lens_mesh: CylinderMesh = CylinderMesh.new()
	lens_mesh.top_radius = CAMERA_PROP_LENS_RADIUS
	lens_mesh.bottom_radius = CAMERA_PROP_LENS_RADIUS
	lens_mesh.height = CAMERA_PROP_LENS_LENGTH
	lens_mesh.material = material
	var prop: Node3D = Node3D.new()
	prop.name = "CameraProp"
	prop.position = CAMERA_PROP_OFFSET
	var body: MeshInstance3D = MeshInstance3D.new()
	body.name = "Body"
	body.mesh = body_mesh
	prop.add_child(body)
	var lens: MeshInstance3D = MeshInstance3D.new()
	lens.name = "Lens"
	lens.mesh = lens_mesh
	lens.rotation.x = PI * 0.5
	lens.position.z = (CAMERA_PROP_BODY_SIZE.z + CAMERA_PROP_LENS_LENGTH) * 0.5
	prop.add_child(lens)
	return prop
