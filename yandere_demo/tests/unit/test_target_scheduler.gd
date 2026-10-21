extends TestCase

var pool: ActivityPool
var table: ScheduleTable
var anchors: Dictionary

func before_each() -> void:
	pool = load("res://data/activity_pool.tres")
	table = load("res://data/schedule_table.tres")
	anchors = {}
	for activity: ActivityDefinition in pool.activities:
		anchors[activity.id] = 2

func block(id: StringName) -> ScheduleBlock:
	for candidate: ScheduleBlock in table.blocks:
		if candidate.id == id:
			return candidate
	return null

func ids(plan: Array[PlannedActivity]) -> Array[StringName]:
	var result: Array[StringName] = []
	for planned: PlannedActivity in plan:
		result.append(planned.activity.id)
	return result

func test_same_seed_same_plan() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	var first: Array[PlannedActivity] = scheduler.plan_block(block(&"lunch"), 42, ActivityHistory.new())
	var second: Array[PlannedActivity] = scheduler.plan_block(block(&"lunch"), 42, ActivityHistory.new())
	assert_eq(ids(first), ids(second))

func test_different_seeds_differ_across_ten_days() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	var distinct: Dictionary = {}
	for seed_value: int in range(10):
		distinct[str(ids(scheduler.plan_block(block(&"lunch"), seed_value, ActivityHistory.new())))] = true
	assert_true(distinct.size() >= 6, "expected varied lunch plans, got %d" % distinct.size())

func test_before_school_starts_at_locker() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	assert_eq(scheduler.plan_block(block(&"before_school"), 7, ActivityHistory.new())[0].activity.id, &"arrive_locker")

func test_class_block_is_attend_class_only() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	assert_eq(ids(scheduler.plan_block(block(&"morning_class"), 7, ActivityHistory.new())), [&"attend_class"])

func test_no_immediate_repeat_and_only_allowed() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	for seed_value: int in range(50):
		var plan: Array[PlannedActivity] = scheduler.plan_block(block(&"after_school"), seed_value, ActivityHistory.new())
		for index: int in range(plan.size()):
			assert_true(plan[index].activity.allowed_blocks.has(&"after_school"))
			if index > 0:
				assert_true(plan[index].activity.id != plan[index - 1].activity.id)

func test_plan_fills_block() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	for block_id: StringName in [&"before_school", &"lunch", &"after_school"]:
		var target_block: ScheduleBlock = block(block_id)
		var length: float = float(target_block.end_minute - target_block.start_minute)
		for seed_value: int in range(50):
			var total: float = 0.0
			for planned: PlannedActivity in scheduler.plan_block(target_block, seed_value, ActivityHistory.new()):
				total += planned.duration_minutes
			assert_true(total >= length * 0.85 - 0.01 and total <= length + 0.01, "%s seed %d total %f" % [block_id, seed_value, total])

func make_activity(id: StringName, blocks: Array[StringName], is_fixed: bool = false, weight: float = 1.0) -> ActivityDefinition:
	var activity: ActivityDefinition = ActivityDefinition.new()
	activity.id = id
	activity.allowed_blocks = blocks
	activity.is_fixed = is_fixed
	activity.base_weight = 0.0 if is_fixed else weight
	activity.min_minutes = 5.0
	activity.max_minutes = 10.0
	return activity

func make_pool(activities: Array[ActivityDefinition]) -> ActivityPool:
	var custom_pool: ActivityPool = ActivityPool.new()
	custom_pool.activities = activities
	return custom_pool

func test_single_eligible_activity_allows_repeat_and_terminates() -> void:
	var only: ActivityDefinition = make_activity(&"only", [&"lunch"] as Array[StringName])
	var scheduler: TargetScheduler = TargetScheduler.new(make_pool([only] as Array[ActivityDefinition]), {})
	var plan: Array[PlannedActivity] = scheduler.plan_block(block(&"lunch"), 1, ActivityHistory.new())
	assert_true(plan.size() >= 2, "expected repeats of the only activity")
	for planned: PlannedActivity in plan:
		assert_eq(planned.activity.id, &"only")
	var total: float = 0.0
	for planned: PlannedActivity in plan:
		total += planned.duration_minutes
	assert_true(total >= 45.0 * 0.85 - 0.01 and total <= 45.01)

func test_two_activities_alternate_when_one_excluded_by_previous() -> void:
	var first: ActivityDefinition = make_activity(&"first", [&"lunch"] as Array[StringName])
	var second: ActivityDefinition = make_activity(&"second", [&"lunch"] as Array[StringName])
	var scheduler: TargetScheduler = TargetScheduler.new(make_pool([first, second] as Array[ActivityDefinition]), {})
	var plan: Array[PlannedActivity] = scheduler.plan_block(block(&"lunch"), 2, ActivityHistory.new())
	for index: int in range(1, plan.size()):
		assert_true(plan[index].activity.id != plan[index - 1].activity.id)

func test_everything_penalized_still_builds_plan() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	var history: ActivityHistory = ActivityHistory.new()
	for activity: ActivityDefinition in pool.activities:
		for block_id: StringName in activity.allowed_blocks:
			history.record(block_id, activity.id)
	history.yesterday_by_block = history.today_by_block.duplicate(true)
	for seed_value: int in range(20):
		var plan: Array[PlannedActivity] = scheduler.plan_block(block(&"lunch"), seed_value, history)
		assert_true(plan.size() > 0)
		for index: int in range(1, plan.size()):
			assert_true(plan[index].activity.id != plan[index - 1].activity.id)

func test_zero_weight_pool_returns_without_looping() -> void:
	var dead: ActivityDefinition = make_activity(&"dead", [&"lunch"] as Array[StringName], false, 0.0)
	var scheduler: TargetScheduler = TargetScheduler.new(make_pool([dead] as Array[ActivityDefinition]), {})
	assert_eq(scheduler.plan_block(block(&"lunch"), 1, ActivityHistory.new()).size(), 0)

func test_fixed_activities_stay_in_their_blocks() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	for block_id: StringName in [&"before_school", &"lunch", &"after_school"]:
		for seed_value: int in range(50):
			var plan: Array[PlannedActivity] = scheduler.plan_block(block(block_id), seed_value, ActivityHistory.new())
			for index: int in range(plan.size()):
				if plan[index].activity.is_fixed:
					assert_true(block_id == &"before_school" and index == 0 and plan[index].activity.id == &"arrive_locker", "%s seed %d index %d" % [block_id, seed_value, index])

func test_arrive_locker_lasts_four_to_eight_minutes() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	for seed_value: int in range(50):
		var duration: float = scheduler.plan_block(block(&"before_school"), seed_value, ActivityHistory.new())[0].duration_minutes
		assert_true(duration >= 4.0 and duration <= 8.0, "seed %d duration %f" % [seed_value, duration])

func test_yesterday_penalty() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	var history: ActivityHistory = ActivityHistory.new()
	history.yesterday_by_block = {&"lunch": [&"read_bench"]}
	assert_near(scheduler.weight_for(pool.find(&"read_bench"), &"lunch", history, &""), 0.4, 0.0001)

func test_cleaning_and_going_home_are_fixed_full_length() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	var cleaning: Array[PlannedActivity] = scheduler.plan_block(block(&"cleaning"), 1, ActivityHistory.new())
	assert_eq(ids(cleaning), [&"cleaning_duty"])
	var cleaning_block: ScheduleBlock = block(&"cleaning")
	assert_near(cleaning[0].duration_minutes, float(cleaning_block.end_minute - cleaning_block.start_minute), 0.0001)
	assert_eq(ids(scheduler.plan_block(block(&"going_home"), 1, ActivityHistory.new())), [&"go_home"])

func test_plan_does_not_mutate_history() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	var history: ActivityHistory = ActivityHistory.new()
	scheduler.plan_block(block(&"lunch"), 5, history)
	assert_eq(history.today_ids, [])
	assert_eq(history.today_by_block, {})
	assert_eq(history.yesterday_by_block, {})

func test_planned_values_in_range() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	for seed_value: int in range(30):
		for planned: PlannedActivity in scheduler.plan_block(block(&"lunch"), seed_value, ActivityHistory.new()):
			assert_true(planned.anchor_index >= 0 and planned.anchor_index <= 1)
			assert_true(planned.walk_speed_scale >= 0.9 and planned.walk_speed_scale <= 1.1)
			assert_true(planned.micro_stops.size() <= 2)
			for micro_stop: StringName in planned.micro_stops:
				assert_true(TargetScheduler.MICRO_STOP_IDS.has(micro_stop))

func test_missing_anchor_count_gives_index_zero() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, {})
	for planned: PlannedActivity in scheduler.plan_block(block(&"lunch"), 4, ActivityHistory.new()):
		assert_eq(planned.anchor_index, 0)

func test_history_penalties_and_round_trip() -> void:
	var scheduler: TargetScheduler = TargetScheduler.new(pool, anchors)
	var history: ActivityHistory = ActivityHistory.new()
	history.record(&"lunch", &"read_bench")
	assert_near(scheduler.weight_for(pool.find(&"read_bench"), &"lunch", history, &""), 0.25, 0.0001)
	assert_near(scheduler.weight_for(pool.find(&"read_bench"), &"lunch", history, &"read_bench"), 0.0, 0.0001)
	assert_near(scheduler.weight_for(pool.find(&"club_activity"), &"lunch", history, &""), 0.0, 0.0001)
	var restored: ActivityHistory = ActivityHistory.from_dictionary(history.to_dictionary())
	assert_eq(restored.today_ids, [&"read_bench"])
	assert_eq(restored.today_by_block, {&"lunch": [&"read_bench"]})
	history.roll_over()
	assert_eq(history.yesterday_by_block, {&"lunch": [&"read_bench"]})
	assert_eq(history.today_ids, [])
	history.record(&"lunch", &"vending_drink")
	history.clear_today()
	assert_eq(history.today_by_block, {})
	assert_eq(history.yesterday_by_block, {&"lunch": [&"read_bench"]})
