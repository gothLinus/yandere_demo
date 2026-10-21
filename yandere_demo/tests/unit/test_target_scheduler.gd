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
	var total: float = 0.0
	for planned: PlannedActivity in scheduler.plan_block(block(&"after_school"), 3, ActivityHistory.new()):
		total += planned.duration_minutes
	assert_true(total >= 90.0 * 0.85 - 0.01 and total <= 90.0 + 0.01)

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
