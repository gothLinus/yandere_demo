extends TestCase

var tuning: StealthTuning
var meters: StealthMeters

func before_each() -> void:
	tuning = load("res://data/stealth_tuning.tres")
	meters = StealthMeters.new(tuning)

func test_sight_gain_scales_with_distance_and_stance() -> void:
	assert_near(meters.sight_gain_per_second(0.0, GameTypes.Stance.WALK, GameTypes.PlayerActivity.NONE, 0), 20.0, 0.001)
	assert_near(meters.sight_gain_per_second(6.0, GameTypes.Stance.SNEAK, GameTypes.PlayerActivity.NONE, 0), 4.0, 0.001)
	assert_near(meters.sight_gain_per_second(12.5, GameTypes.Stance.RUN, GameTypes.PlayerActivity.NONE, 0), 0.0, 0.001)

func test_camera_and_crowd_multipliers() -> void:
	assert_near(meters.sight_gain_per_second(6.0, GameTypes.Stance.WALK, GameTypes.PlayerActivity.CAMERA_RAISED, 2), 12.5, 0.001)

func test_low_sanity_multiplier() -> void:
	meters.sanity = 20.0
	assert_near(meters.sight_gain_per_second(0.0, GameTypes.Stance.WALK, GameTypes.PlayerActivity.NONE, 0), 30.0, 0.001)

func test_hidden_drain_never_reports() -> void:
	var caught_reasons: Array[StringName] = []
	meters.caught.connect(func(reason: StringName) -> void: caught_reasons.append(reason))
	meters.add_suspicion_spike(99.0)
	for frame: int in range(240):
		meters.apply_unseen(1.0 / 60.0, true)
	assert_near(meters.suspicion, 0.0, 0.001)
	assert_eq(caught_reasons.size(), 0)

func test_caught_fires_once() -> void:
	var caught_reasons: Array[StringName] = []
	meters.caught.connect(func(reason: StringName) -> void: caught_reasons.append(reason))
	meters.add_suspicion_spike(120.0)
	meters.add_alert_spike(&"skipped_class")
	meters.add_alert_rate(100.0, &"out_of_class")
	assert_eq(caught_reasons, [&"target_report"])

func test_sanity_drains_only_after_delay_and_not_in_vision() -> void:
	meters.update_sanity(10.0, 20.0, false, false)
	assert_near(meters.sanity, 100.0, 0.001)
	meters.update_sanity(10.0, 40.0, false, false)
	assert_near(meters.sanity, 95.0, 0.001)
	meters.update_sanity(10.0, 40.0, false, true)
	assert_near(meters.sanity, 95.0, 0.001)

func test_cannot_hide_below_ten_sanity() -> void:
	meters.sanity = 9.0
	assert_true(not meters.can_hide())

func test_noticed_fires_on_upward_crossing_and_rearms_below_hysteresis() -> void:
	var noticed_count: Array[int] = [0]
	meters.noticed.connect(func() -> void: noticed_count[0] += 1)
	meters.add_suspicion_spike(40.0)
	assert_eq(noticed_count[0], 1)
	assert_true(meters.is_noticed())
	meters.add_suspicion_spike(10.0)
	assert_eq(noticed_count[0], 1)
	meters.apply_unseen(10.0, true)
	meters.apply_unseen(0.2, true)
	assert_true(not meters.is_noticed())
	meters.add_suspicion_spike(40.0)
	assert_eq(noticed_count[0], 2)

func test_noticed_stays_latched_inside_hysteresis_band_and_rearms_below_it() -> void:
	var noticed_count: Array[int] = [0]
	meters.noticed.connect(func() -> void: noticed_count[0] += 1)
	meters.add_suspicion_spike(40.0)
	meters.apply_unseen(0.5, true)
	assert_near(meters.suspicion, 27.5, 0.001)
	meters.add_suspicion_spike(1.0)
	assert_eq(noticed_count[0], 1)
	assert_true(meters.is_noticed())
	meters.apply_unseen(0.2, true)
	assert_true(not meters.is_noticed())
	meters.add_suspicion_spike(15.0)
	assert_eq(noticed_count[0], 2)

func test_reset_clears_values_and_rearms_signals() -> void:
	var noticed_count: Array[int] = [0]
	var caught_reasons: Array[StringName] = []
	meters.noticed.connect(func() -> void: noticed_count[0] += 1)
	meters.caught.connect(func(reason: StringName) -> void: caught_reasons.append(reason))
	meters.add_suspicion_spike(100.0)
	meters.sanity = 10.0
	meters.reset()
	assert_near(meters.suspicion, 0.0, 0.001)
	assert_near(meters.school_alert, 0.0, 0.001)
	assert_near(meters.sanity, 100.0, 0.001)
	assert_true(not meters.is_noticed())
	meters.add_suspicion_spike(100.0)
	assert_eq(noticed_count[0], 2)
	assert_eq(caught_reasons, [&"target_report", &"target_report"])

func test_school_alert_caught_reason() -> void:
	var caught_reasons: Array[StringName] = []
	meters.caught.connect(func(reason: StringName) -> void: caught_reasons.append(reason))
	meters.add_alert_rate(20.0, &"out_of_class")
	assert_eq(caught_reasons, [&"school_alert"])
	meters.add_suspicion_spike(100.0)
	assert_eq(caught_reasons, [&"school_alert"])

func test_alert_spike_and_rate_use_tuning() -> void:
	meters.add_alert_spike(&"late")
	assert_near(meters.school_alert, 10.0, 0.001)
	meters.add_alert_rate(0.5, &"camera_at_student")
	assert_near(meters.school_alert, 15.0, 0.001)

func test_spike_signal_and_apply_seen() -> void:
	var spikes: Array[float] = []
	meters.suspicion_triggered.connect(func(amount: float) -> void: spikes.append(amount))
	meters.add_suspicion_spike(30.0)
	meters.apply_seen(1.0, 0.0, GameTypes.Stance.WALK, GameTypes.PlayerActivity.NONE, 0)
	assert_eq(spikes, [30.0])
	assert_near(meters.suspicion, 50.0, 0.001)

func test_changed_signals_only_on_actual_change() -> void:
	var values: Array[float] = []
	meters.suspicion_changed.connect(func(value: float) -> void: values.append(value))
	meters.apply_unseen(1.0, false)
	assert_eq(values.size(), 0)
	meters.add_suspicion_spike(10.0)
	assert_eq(values, [10.0])

func test_sanity_recovers_while_watching_and_photo_bonus() -> void:
	meters.sanity = 50.0
	meters.update_sanity(2.0, 100.0, true, false)
	assert_near(meters.sanity, 56.0, 0.001)
	meters.reward_photo()
	assert_near(meters.sanity, 66.0, 0.001)
