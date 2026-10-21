extends TestCase

var table: ScheduleTable

func before_each() -> void:
	table = load("res://data/schedule_table.tres")

func test_starts_before_school_at_seven() -> void:
	var clock: SchoolClockModel = SchoolClockModel.new(table)
	assert_eq(clock.current_block().id, &"before_school")
	assert_near(clock.current_minute, 420.0, 0.001)

func test_free_block_rate() -> void:
	var clock: SchoolClockModel = SchoolClockModel.new(table)
	clock.advance(150.0)
	assert_near(clock.current_minute, 465.0, 0.01)

func test_large_delta_emits_every_block_in_order() -> void:
	var clock: SchoolClockModel = SchoolClockModel.new(table)
	var seen: Array[StringName] = []
	clock.block_changed.connect(func(block: ScheduleBlock) -> void: seen.append(block.id))
	clock.advance(300.0 + 180.0 + 1.0)
	assert_eq(seen, [&"morning_class", &"lunch"])

func test_skip_to_block_end_enters_next_block() -> void:
	var clock: SchoolClockModel = SchoolClockModel.new(table)
	clock.advance(301.0)
	clock.skip_to_block_end()
	assert_eq(clock.current_block().id, &"lunch")
	assert_near(clock.current_minute, 780.0, 0.001)

func test_day_ends_once_at_eighteen() -> void:
	var clock: SchoolClockModel = SchoolClockModel.new(table)
	var ended_count: Array[int] = [0]
	clock.day_ended.connect(func() -> void: ended_count[0] += 1)
	clock.advance(100000.0)
	clock.advance(10.0)
	assert_true(clock.is_day_over())
	assert_eq(ended_count[0], 1)
	assert_near(clock.current_minute, 1080.0, 0.001)

func test_clock_text() -> void:
	var clock: SchoolClockModel = SchoolClockModel.new(table)
	clock.advance(150.0)
	assert_eq(clock.clock_text(2), "Wed 07:45")
