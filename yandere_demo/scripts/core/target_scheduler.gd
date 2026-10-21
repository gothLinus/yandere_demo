class_name TargetScheduler
extends RefCounted

const MICRO_STOP_IDS: Array[StringName] = [&"check_phone", &"look_window", &"glance_back"]
const FILL_FRACTION: float = 0.85
const TODAY_PENALTY: float = 0.25
const YESTERDAY_PENALTY: float = 0.4
const MAX_MICRO_STOPS: int = 2
const MIN_WALK_SPEED_SCALE: float = 0.9
const MAX_WALK_SPEED_SCALE: float = 1.1

var _pool: ActivityPool
var _anchor_counts: Dictionary


func _init(pool: ActivityPool, anchor_counts: Dictionary) -> void:
	_pool = pool
	_anchor_counts = anchor_counts


func plan_block(block: ScheduleBlock, rng_seed: int, history: ActivityHistory) -> Array[PlannedActivity]:
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = rng_seed
	var plan: Array[PlannedActivity] = []
	var block_minutes: float = float(block.end_minute - block.start_minute)
	var fixed_activity: ActivityDefinition = _find_fixed(block.id)

	if block.kind == GameTypes.BlockKind.CLASS or block.id == &"cleaning" or block.id == &"going_home":
		if fixed_activity == null:
			push_error("No fixed activity in the pool for block %s" % block.id)
			return plan
		plan.append(_make_planned(fixed_activity, block_minutes, rng))
		return plan

	var elapsed_minutes: float = 0.0
	var previous_id: StringName = &""
	if fixed_activity != null:
		var arrival_minutes: float = minf(rng.randf_range(fixed_activity.min_minutes, fixed_activity.max_minutes), block_minutes)
		plan.append(_make_planned(fixed_activity, arrival_minutes, rng))
		elapsed_minutes = arrival_minutes
		previous_id = fixed_activity.id

	while elapsed_minutes < block_minutes * FILL_FRACTION:
		var activity: ActivityDefinition = _pick_activity(block.id, history, previous_id, rng)
		if activity == null:
			break
		var duration_minutes: float = minf(rng.randf_range(activity.min_minutes, activity.max_minutes), block_minutes - elapsed_minutes)
		plan.append(_make_planned(activity, duration_minutes, rng))
		elapsed_minutes += duration_minutes
		previous_id = activity.id
	return plan


func weight_for(activity: ActivityDefinition, block_id: StringName, history: ActivityHistory, previous_id: StringName) -> float:
	if not activity.allowed_blocks.has(block_id) or activity.id == previous_id:
		return 0.0
	var weight: float = activity.base_weight
	if history.today_ids.has(activity.id):
		weight *= TODAY_PENALTY
	var yesterday_ids: Array = history.yesterday_by_block.get(block_id, [])
	if yesterday_ids.has(activity.id):
		weight *= YESTERDAY_PENALTY
	return weight


func _find_fixed(block_id: StringName) -> ActivityDefinition:
	for activity: ActivityDefinition in _pool.activities:
		if activity.is_fixed and activity.allowed_blocks.has(block_id):
			return activity
	return null


# No penalty-free rung: penalties are multipliers, so they never reduce a weight to zero.
func _pick_activity(block_id: StringName, history: ActivityHistory, previous_id: StringName, rng: RandomNumberGenerator) -> ActivityDefinition:
	var weights: Array[float] = []
	for activity: ActivityDefinition in _pool.activities:
		weights.append(0.0 if activity.is_fixed else weight_for(activity, block_id, history, previous_id))
	var picked: ActivityDefinition = _weighted_choice(weights, rng)
	if picked != null:
		return picked
	weights.clear()
	for activity: ActivityDefinition in _pool.activities:
		var eligible: bool = not activity.is_fixed and activity.allowed_blocks.has(block_id)
		weights.append(activity.base_weight if eligible else 0.0)
	return _weighted_choice(weights, rng)


func _weighted_choice(weights: Array[float], rng: RandomNumberGenerator) -> ActivityDefinition:
	var total: float = 0.0
	for weight: float in weights:
		total += weight
	if total <= 0.0:
		return null
	var roll: float = rng.randf() * total
	var last_positive: int = -1
	for index: int in weights.size():
		if weights[index] <= 0.0:
			continue
		last_positive = index
		roll -= weights[index]
		if roll < 0.0:
			return _pool.activities[index]
	return _pool.activities[last_positive]


func _make_planned(activity: ActivityDefinition, duration_minutes: float, rng: RandomNumberGenerator) -> PlannedActivity:
	var planned: PlannedActivity = PlannedActivity.new()
	planned.activity = activity
	planned.duration_minutes = duration_minutes
	var anchor_count: int = int(_anchor_counts.get(activity.id, 0))
	planned.anchor_index = rng.randi_range(0, anchor_count - 1) if anchor_count > 0 else 0
	for _stop: int in rng.randi_range(0, MAX_MICRO_STOPS):
		planned.micro_stops.append(MICRO_STOP_IDS[rng.randi_range(0, MICRO_STOP_IDS.size() - 1)])
	planned.walk_speed_scale = rng.randf_range(MIN_WALK_SPEED_SCALE, MAX_WALK_SPEED_SCALE)
	return planned
