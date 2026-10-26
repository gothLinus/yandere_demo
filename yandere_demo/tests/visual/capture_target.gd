extends VisualCapture
## Windowed: frames the target against a neutral background and saves front, 3/4 and back views, a face close-up per
## expression and the walk at four phases (Task 22). Compare with docs/references/ against the Task 8 Step 4 list.

const TARGET_SCENE: PackedScene = preload("res://scenes/target.tscn")
const EXPRESSIONS: Array[StringName] = [&"neutral", &"startled", &"suspicious", &"happy"]
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
	for expression_name: StringName in EXPRESSIONS:
		expression.set_expression(expression_name, 0.0)
		_aim(head + Vector3(0.0, 0.0, -FACE_DISTANCE), head)
		await wait_seconds(EXPRESSION_SETTLE_SECONDS)
		await save_capture("target_expression_%s" % expression_name)
	expression.set_expression(&"neutral", 0.0)
	await _capture_walk_phases()
	finish()


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
