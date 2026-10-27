extends VisualCapture
## Windowed: frames the target against a neutral background and saves front, 3/4 and back views, a face close-up per
## expression, the walk at four phases and every hand-prop clip at its middle (Task 22, Task 23a).

const TARGET_SCENE: PackedScene = preload("res://scenes/target.tscn")
const EXPRESSIONS: Array[StringName] = [
	&"neutral", &"startled", &"suspicious", &"happy", &"blink", &"smile", &"sad", &"blush", &"wink_L", &"wink_R",
	&"mouth_A", &"mouth_I", &"mouth_U", &"mouth_E", &"mouth_O", &"pupil_small", &"pupil_large",
]
## Ruling R9: the clips that show a hand prop, captured at their middle frame.
const PROP_ANIMATIONS: Array[StringName] = [&"target_sit_read", &"target_phone", &"target_drink", &"target_sweep"]
const PROP_DISTANCE: float = 0.9
const PROP_CAMERA_RISE: float = 0.15
const SKELETON_PATH: NodePath = ^"Model/TargetChar/Skeleton3D"
const IDLE_STATE: StringName = &"target_idle"
const PLAYBACK_PARAMETER: StringName = &"parameters/playback"
const WALK_ANIMATION: StringName = &"target_walk_routine"
const WALK_PHASES: Array[float] = [0.0, 0.25, 0.5, 0.75]
const BODY_LOOK_HEIGHT: float = 0.82
const BODY_DISTANCE: float = 2.6
const BODY_CAMERA_HEIGHT: float = 1.0
const FACE_DISTANCE: float = 0.55
const FIELD_OF_VIEW: float = 40.0
const SETTLE_SECONDS: float = 1.0
const EXPRESSION_SETTLE_SECONDS: float = 0.4
const SPRING_SETTLE_FRAMES: int = 20

@onready var _camera: Camera3D = $Camera3D

var _target: TargetAI


func _ready() -> void:
	_target = TARGET_SCENE.instantiate() as TargetAI
	add_child(_target)
	_camera.fov = FIELD_OF_VIEW
	var expression: ExpressionController = _target.get_node(^"ExpressionController") as ExpressionController
	# No blink mid-capture.
	expression.set_process(false)
	expression.set_expression(&"neutral", 0.0)
	var playback: AnimationNodeStateMachinePlayback = _target.get_node(^"AnimationTree").get(PLAYBACK_PARAMETER)
	playback.start(IDLE_STATE)
	await wait_seconds(SETTLE_SECONDS)
	for view: Array in [["front", 0.0], ["three_quarter", 45.0], ["side", 90.0], ["back", 180.0]]:
		_aim_at_body(deg_to_rad(float(view[1])))
		await save_capture("target_%s" % view[0])
	var head: Vector3 = _target.head_position()
	var face: MeshInstance3D = _target.find_child("TargetFace", true, false) as MeshInstance3D
	for expression_name: StringName in EXPRESSIONS:
		expression.set_expression(expression_name, 0.0)
		# ExpressionController leaves the blink to its own timer, so the capture closes the eyes itself.
		face.set_blend_shape_value(face.find_blend_shape_by_name(ExpressionController.BLINK_SHAPE),
				1.0 if expression_name == ExpressionController.BLINK_SHAPE else 0.0)
		_aim(head + Vector3(0.0, 0.0, -FACE_DISTANCE), head)
		await wait_seconds(EXPRESSION_SETTLE_SECONDS)
		await save_capture("target_expression_%s" % expression_name)
	expression.set_expression(&"neutral", 0.0)
	await _capture_walk_phases()
	await _capture_props()
	finish()


func _capture_props() -> void:
	var animation_player: AnimationPlayer = _target.get_node(^"Model/AnimationPlayer") as AnimationPlayer
	var props: TargetProps = _target.get_node(^"TargetProps") as TargetProps
	for animation_name: StringName in PROP_ANIMATIONS:
		animation_player.play(animation_name)
		animation_player.seek(animation_player.current_animation_length * 0.5, true)
		animation_player.pause()
		props.show_for(animation_name)
		await wait_frames(SPRING_SETTLE_FRAMES)
		var skeleton: Skeleton3D = _target.get_node(SKELETON_PATH) as Skeleton3D
		var hand_bone: int = skeleton.find_bone(TargetProps.PROP_BONES[TargetProps.PROP_FOR_ANIMATION[animation_name]])
		var hand: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(hand_bone).origin
		for view: Array in [["front", 20.0], ["side", 70.0]]:
			var angle: float = deg_to_rad(float(view[1]))
			var offset: Vector3 = Vector3(sin(angle), 0.0, -cos(angle)) * PROP_DISTANCE
			_aim(hand + offset + Vector3.UP * PROP_CAMERA_RISE, hand)
			await save_capture("%s_prop_%s" % [animation_name, view[0]])
	props.show_for(&"")


func _capture_walk_phases() -> void:
	var animation_tree: AnimationTree = _target.get_node(^"AnimationTree") as AnimationTree
	var animation_player: AnimationPlayer = _target.get_node(^"Model/AnimationPlayer") as AnimationPlayer
	animation_tree.active = false
	animation_player.play(WALK_ANIMATION)
	var length: float = animation_player.current_animation_length
	for phase: float in WALK_PHASES:
		animation_player.seek(phase * length, true)
		animation_player.pause()
		await wait_frames(SPRING_SETTLE_FRAMES)
		_aim_at_body(deg_to_rad(90.0))
		await save_capture("target_walk_phase_%03d" % roundi(phase * 100.0))
		_aim_at_body(deg_to_rad(20.0))
		await save_capture("target_walk_phase_%03d_front" % roundi(phase * 100.0))


## Orbits the camera around the target; angle 0 looks at his face (the model faces -Z).
func _aim_at_body(angle: float) -> void:
	var offset: Vector3 = Vector3(sin(angle), 0.0, -cos(angle)) * BODY_DISTANCE
	_aim(Vector3(offset.x, BODY_CAMERA_HEIGHT, offset.z), Vector3(0.0, BODY_LOOK_HEIGHT, 0.0))


func _aim(from: Vector3, at: Vector3) -> void:
	_camera.global_position = from
	_camera.look_at(at)
