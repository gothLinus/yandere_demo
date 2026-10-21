extends TestCase


func class_block() -> ScheduleBlock:
	var block: ScheduleBlock = ScheduleBlock.new()
	block.id = &"morning_class"
	block.kind = GameTypes.BlockKind.CLASS
	return block


func free_block() -> ScheduleBlock:
	var block: ScheduleBlock = ScheduleBlock.new()
	block.id = &"lunch"
	block.kind = GameTypes.BlockKind.FREE
	return block


func test_on_time_late_and_skip() -> void:
	var tracker: AttendanceTracker = AttendanceTracker.new(30.0)
	var reasons: Array[StringName] = []
	tracker.penalty.connect(func(reason: StringName) -> void: reasons.append(reason))
	tracker.on_block_started(class_block())
	tracker.on_player_sat(10.0)
	tracker.on_block_ended(class_block())
	tracker.on_block_started(class_block())
	tracker.on_player_sat(45.0)
	tracker.on_block_ended(class_block())
	tracker.on_block_started(class_block())
	tracker.on_block_ended(class_block())
	assert_eq(reasons, [&"late", &"skipped_class"])
	assert_true(tracker.is_class_in_session(31.0))


func test_free_block_emits_nothing() -> void:
	var tracker: AttendanceTracker = AttendanceTracker.new(30.0)
	var reasons: Array[StringName] = []
	tracker.penalty.connect(func(reason: StringName) -> void: reasons.append(reason))
	tracker.on_block_started(free_block())
	tracker.on_player_sat(100.0)
	tracker.on_block_ended(free_block())
	assert_eq(reasons, [])
	assert_true(not tracker.is_class_in_session(100.0))


func test_only_first_sit_counts_and_no_block_is_not_in_session() -> void:
	var tracker: AttendanceTracker = AttendanceTracker.new(30.0)
	assert_true(not tracker.is_class_in_session(100.0))
	var reasons: Array[StringName] = []
	tracker.penalty.connect(func(reason: StringName) -> void: reasons.append(reason))
	tracker.on_block_started(class_block())
	tracker.on_player_sat(5.0)
	tracker.on_player_sat(50.0)
	assert_eq(reasons, [])
	assert_true(tracker.has_sat)
	tracker.on_block_started(class_block())
	assert_true(not tracker.has_sat)
