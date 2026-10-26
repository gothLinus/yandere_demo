extends IntegrationTest
## A planned anchor sealed inside a solid box: the target walks into the box, stalls, skips that activity and starts
## the next one within 12 s.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TARGET_SCENE_PATH: String = "res://scenes/target.tscn"
const POOL_PATH: String = "res://data/activity_pool.tres"
const SEALED_ACTIVITY: StringName = &"vending_drink"
const NEXT_ACTIVITY: StringName = &"chat_students"
const BOX_OFFSET: Vector3 = Vector3(3.0, 0.0, 0.0)
const BOX_SIZE: Vector3 = Vector3(2.0, 2.0, 2.0)
const START_OFFSET: Vector3 = Vector3(1.0, 0.0, 0.0)
const DEADLINE_SECONDS: float = 12.0
const PLANNED_MINUTES: float = 5.0

var _started_ids: Array[StringName] = []
var _plan_seconds: float = 0.0
var _running: bool = false


func _ready() -> void:
	timeout_seconds = 60.0
	var school_env: SchoolEnv = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(school_env)
	await school_env.navigation_ready
	var next_anchor: Node3D = school_env.anchors_for(NEXT_ACTIVITY)[0]
	var sealed_anchor: Node3D = school_env.anchors_for(SEALED_ACTIVITY)[0]
	sealed_anchor.global_position = next_anchor.global_position + BOX_OFFSET
	_add_sealed_box(sealed_anchor.global_position)
	var target: TargetAI = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(target)
	target.activity_started.connect(func(activity: ActivityDefinition) -> void: _started_ids.append(activity.id))
	target.setup(school_env, 1, ActivityHistory.new())
	target.global_position = next_anchor.global_position + START_OFFSET
	await get_tree().physics_frame
	var pool: ActivityPool = load(POOL_PATH) as ActivityPool
	target.start_plan([_planned(pool.find(SEALED_ACTIVITY)), _planned(pool.find(NEXT_ACTIVITY))] as Array[PlannedActivity])
	_running = true


func _physics_process(delta: float) -> void:
	if not _running:
		return
	_plan_seconds += delta
	if _started_ids.has(SEALED_ACTIVITY):
		_running = false
		fail_test("the sealed activity started")
	elif _started_ids.has(NEXT_ACTIVITY):
		_running = false
		print("%s started after %.1f s" % [NEXT_ACTIVITY, _plan_seconds])
		pass_test()
	elif _plan_seconds > DEADLINE_SECONDS:
		_running = false
		fail_test("%s did not start within %.0f s (started %s)" % [NEXT_ACTIVITY, DEADLINE_SECONDS, _started_ids])


func _planned(activity: ActivityDefinition) -> PlannedActivity:
	var planned: PlannedActivity = PlannedActivity.new()
	planned.activity = activity
	planned.duration_minutes = PLANNED_MINUTES
	return planned


func _add_sealed_box(center: Vector3) -> void:
	var body: StaticBody3D = StaticBody3D.new()
	body.collision_layer = PhysicsLayers.WORLD
	var shape: CollisionShape3D = CollisionShape3D.new()
	var box: BoxShape3D = BoxShape3D.new()
	box.size = BOX_SIZE
	shape.shape = box
	body.add_child(shape)
	add_child(body)
	body.global_position = center + Vector3.UP * BOX_SIZE.y * 0.5
