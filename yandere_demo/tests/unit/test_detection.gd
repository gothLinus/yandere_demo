extends TestCase

func test_view_cone() -> void:
	assert_true(Detection.is_in_view_cone(Vector3.ZERO, Vector3.FORWARD, Vector3(0, 0, -5), 110.0, 12.0))
	assert_true(not Detection.is_in_view_cone(Vector3.ZERO, Vector3.FORWARD, Vector3(0, 0, 5), 110.0, 12.0))
	assert_true(not Detection.is_in_view_cone(Vector3.ZERO, Vector3.FORWARD, Vector3(0, 0, -13), 110.0, 12.0))
	assert_true(not Detection.is_in_view_cone(Vector3.ZERO, Vector3.FORWARD, Vector3(5, 0, -1), 110.0, 12.0))

func test_view_cone_origin_counts_as_in_view() -> void:
	assert_true(Detection.is_in_view_cone(Vector3.ZERO, Vector3.FORWARD, Vector3.ZERO, 110.0, 12.0))

func test_hearing_by_stance() -> void:
	var tuning: StealthTuning = load("res://data/stealth_tuning.tres")
	assert_true(Detection.can_hear(Vector3.ZERO, Vector3(0, 0, 7), GameTypes.Stance.RUN, tuning))
	assert_true(not Detection.can_hear(Vector3.ZERO, Vector3(0, 0, 2), GameTypes.Stance.SNEAK, tuning))
	assert_true(not Detection.can_hear(Vector3.ZERO, Vector3.ZERO, GameTypes.Stance.HIDDEN, tuning))
