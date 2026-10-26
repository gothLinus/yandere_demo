extends IntegrationTest
## Runs the target through the whole before_school block at 8x and checks that his motion stays seamless: no
## teleports, no snapping turns, and every activity starting on its anchor with its expression. Then, at 1x, the
## class-fade snap into his seat and a notice that turns his head toward a point and back.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TARGET_SCENE_PATH: String = "res://scenes/target.tscn"
const SCHEDULE_PATH: String = "res://data/schedule_table.tres"
const TUNING_PATH: String = "res://data/target_tuning.tres"
const DAY_SEED: int = 1234
const TIME_SCALE: float = 8.0
const PHYSICS_STEPS_PER_TIME_SCALE: int = 8
const ANCHOR_TOLERANCE: float = 0.35
const MAX_HORIZONTAL_SPEED: float = 1.3 * 1.1 * 1.05
const YAW_RATE: float = 8.0
const YAW_TOLERANCE: float = 0.05
const SEAT_TOLERANCE: float = 0.01
const LOOK_SETTLE_SECONDS: float = 0.6
const NOTICE_OFFSET: Vector3 = Vector3(3.0, 0.0, 0.0)
const MIN_FACING_DOT: float = 0.5
const MIN_LOOK_DOT: float = 0.8

var _school_env: SchoolEnv
var _target: TargetAI
var _clock: SchoolClockModel
var _tuning: TargetTuning
var _started_ids: Array[StringName] = []
var _failures: PackedStringArray = PackedStringArray()
var _previous_position: Vector3
var _previous_yaw: float
var _entering_seconds: float = 0.0
var _running: bool = false
var _previous_time_scale: float
var _previous_max_steps: int


func _ready() -> void:
	timeout_seconds = 150.0
	_tuning = load(TUNING_PATH) as TargetTuning
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_clock = SchoolClockModel.new(load(SCHEDULE_PATH) as ScheduleTable)
	_target = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(_target)
	_target.clock = _clock
	_target.activity_started.connect(_on_activity_started)
	_target.state_changed.connect(_on_state_changed)
	_clock.block_changed.connect(_on_block_changed)
	_target.setup(_school_env, DAY_SEED, ActivityHistory.new())
	_previous_position = _target.global_position
	_previous_yaw = _target.rotation.y
	_previous_time_scale = Engine.time_scale
	_previous_max_steps = Engine.max_physics_steps_per_frame
	Engine.time_scale = TIME_SCALE
	Engine.max_physics_steps_per_frame = maxi(_previous_max_steps, int(PHYSICS_STEPS_PER_TIME_SCALE * TIME_SCALE))
	_running = true


func _physics_process(delta: float) -> void:
	if not _running:
		return
	_check_motion(delta)
	_clock.advance(delta)


func _check_motion(delta: float) -> void:
	var position: Vector3 = _target.global_position
	var horizontal_speed: float = Vector2(position.x - _previous_position.x, position.z - _previous_position.z).length() / delta
	if horizontal_speed > MAX_HORIZONTAL_SPEED:
		_fail_once("horizontal speed %.2f m/s in state %s at %s" % [horizontal_speed, _state_name(), position])
	var yaw_change: float = absf(angle_difference(_previous_yaw, _target.rotation.y))
	var yaw_limit: float = YAW_RATE * delta + YAW_TOLERANCE
	if _target.state == TargetAI.State.ENTERING:
		yaw_limit = PI * delta / _entering_seconds + YAW_TOLERANCE
	if yaw_change > yaw_limit:
		_fail_once("yaw changed %.3f rad in one frame (limit %.3f) in state %s" % [yaw_change, yaw_limit, _state_name()])
	_previous_position = position
	_previous_yaw = _target.rotation.y


func _on_state_changed(state: TargetAI.State) -> void:
	if state != TargetAI.State.ENTERING:
		return
	# The ENTERING tween runs max(0.4 s, distance / 1.2 m/s) toward the nearest anchor of his activity (ruling R12).
	var distance: float = 0.0
	var activity: ActivityDefinition = _target.current_activity()
	if activity != null:
		distance = INF
		for anchor: Node3D in _school_env.anchors_for(activity.id):
			distance = minf(distance, anchor.global_position.distance_to(_target.global_position))
	_entering_seconds = maxf(_tuning.entering_min_seconds, distance / _tuning.entering_max_speed)


func _on_activity_started(activity: ActivityDefinition) -> void:
	_started_ids.append(activity.id)
	var nearest: float = INF
	for planned: PlannedActivity in _target.plan:
		if planned.activity.id != activity.id:
			continue
		var anchors: Array[Node3D] = _school_env.anchors_for(activity.id)
		if planned.anchor_index < anchors.size():
			nearest = minf(nearest, anchors[planned.anchor_index].global_position.distance_to(_target.global_position))
	if nearest > ANCHOR_TOLERANCE:
		_fail_once("%s started %.2f m from its anchor" % [activity.id, nearest])
	var expression: StringName = (_target.get_node("ExpressionController") as ExpressionController).expression
	if expression != activity.expression:
		_fail_once("%s started with expression %s, not %s" % [activity.id, expression, activity.expression])


func _on_block_changed(block: ScheduleBlock) -> void:
	if not _running or block.id == &"before_school":
		return
	_running = false
	_clock.block_changed.disconnect(_on_block_changed)
	if _started_ids.is_empty() or _started_ids[0] != &"arrive_locker":
		_failures.append("the first activity was not arrive_locker: %s" % [_started_ids])
	if _started_ids.size() < 2:
		_failures.append("only %s started before school ended" % [_started_ids])
	print("activities started: %s" % [_started_ids])
	Engine.time_scale = _previous_time_scale
	Engine.max_physics_steps_per_frame = _previous_max_steps
	await _check_class_seat_and_notice()
	_finish()


func _check_class_seat_and_notice() -> void:
	# The target's own block_changed handler runs after this one and plans attend_class.
	await get_tree().physics_frame
	_target.snap_to_class_seat()
	await get_tree().physics_frame
	var seat: Node3D = _school_env.marker("TargetSeat")
	if _target.global_position.distance_to(seat.global_position) > SEAT_TOLERANCE:
		_failures.append("snap_to_class_seat left him %.2f m from TargetSeat" % _target.global_position.distance_to(seat.global_position))
	if _target.current_activity() == null or _target.current_activity().id != &"attend_class" or _started_ids[-1] != &"attend_class":
		_failures.append("snap_to_class_seat did not start attend_class (started %s)" % [_started_ids])
	await get_tree().create_timer(LOOK_SETTLE_SECONDS).timeout
	var body_forward: Vector3 = -_target.global_basis.z
	if _target.eye_forward().dot(body_forward) < MIN_FACING_DOT:
		_failures.append("eye_forward %s does not face his body's forward %s" % [_target.eye_forward(), body_forward])
	var point: Vector3 = _target.head_position() + _target.global_basis * NOTICE_OFFSET
	_target.notice(point)
	await get_tree().create_timer(LOOK_SETTLE_SECONDS).timeout
	var toward: Vector3 = (point - _target.head_position()).normalized()
	if _target.state != TargetAI.State.NOTICE or _target.eye_forward().dot(toward) < MIN_LOOK_DOT:
		_failures.append("notice did not turn his head (state %s, eye·target %.2f)" % [_state_name(), _target.eye_forward().dot(toward)])
	_target.calm_down()
	await get_tree().create_timer(LOOK_SETTLE_SECONDS).timeout
	if _target.state != TargetAI.State.ACTIVITY or _target.eye_forward().dot(body_forward) < MIN_FACING_DOT:
		_failures.append("calm_down did not resume (state %s)" % _state_name())


func _fail_once(message: String) -> void:
	if _failures.size() < 5:
		_failures.append(message)


func _state_name() -> String:
	return TargetAI.State.keys()[_target.state]


func _finish() -> void:
	Engine.time_scale = _previous_time_scale
	Engine.max_physics_steps_per_frame = _previous_max_steps
	if _failures.is_empty():
		pass_test()
	else:
		fail_test("; ".join(_failures))


func _exit_tree() -> void:
	if _running:
		Engine.time_scale = _previous_time_scale
		Engine.max_physics_steps_per_frame = _previous_max_steps
