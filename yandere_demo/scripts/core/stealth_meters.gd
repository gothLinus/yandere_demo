class_name StealthMeters
extends RefCounted

signal suspicion_changed(value: float)
signal school_alert_changed(value: float)
signal sanity_changed(value: float)
signal suspicion_triggered(amount: float)
signal noticed()
signal caught(reason: StringName)

const METER_MAXIMUM: float = 100.0
const NOTICE_REARM_MARGIN: float = 10.0

var suspicion: float = 0.0
var school_alert: float = 0.0
var sanity: float = 100.0

var _tuning: StealthTuning
var _is_noticed: bool = false
var _has_caught: bool = false


func _init(tuning: StealthTuning) -> void:
	_tuning = tuning


func is_noticed() -> bool:
	return _is_noticed


func sight_gain_per_second(distance: float, stance: GameTypes.Stance, activity: GameTypes.PlayerActivity, crowd_count: int) -> float:
	var distance_factor: float = clampf(1.0 - distance / _tuning.sight_range, 0.0, 1.0)
	var stance_factor: float = _tuning.stance_multipliers[stance]
	var activity_factor: float = _tuning.activity_multipliers[activity]
	var crowd_factor: float = _tuning.crowd_multiplier if crowd_count >= _tuning.crowd_minimum else 1.0
	var sanity_factor: float = _tuning.low_sanity_multiplier if sanity < _tuning.low_sanity_threshold else 1.0
	return _tuning.base_sight_gain * distance_factor * stance_factor * activity_factor * crowd_factor * sanity_factor


func apply_seen(delta: float, distance: float, stance: GameTypes.Stance, activity: GameTypes.PlayerActivity, crowd_count: int) -> void:
	_set_suspicion(suspicion + sight_gain_per_second(distance, stance, activity, crowd_count) * delta)


func apply_unseen(delta: float, is_hidden: bool) -> void:
	var decay_rate: float = _tuning.hidden_decay if is_hidden else _tuning.unseen_decay
	_set_suspicion(suspicion - decay_rate * delta)


func add_suspicion_spike(amount: float) -> void:
	_set_suspicion(suspicion + amount)
	suspicion_triggered.emit(amount)


func add_alert_rate(delta: float, reason: StringName) -> void:
	if not _tuning.alert_rates.has(reason):
		push_error("Unknown alert rate reason: %s" % reason)
		return
	var rate: float = _tuning.alert_rates[reason]
	_set_school_alert(school_alert + rate * delta)


func add_alert_spike(reason: StringName) -> void:
	if not _tuning.alert_spikes.has(reason):
		push_error("Unknown alert spike reason: %s" % reason)
		return
	var amount: float = _tuning.alert_spikes[reason]
	_set_school_alert(school_alert + amount)


func update_sanity(delta: float, seconds_since_target_seen: float, is_watching_target: bool, is_vision_active: bool) -> void:
	if is_watching_target:
		_set_sanity(sanity + _tuning.sanity_recover_rate * delta)
	elif seconds_since_target_seen > _tuning.sanity_drain_delay and not is_vision_active:
		_set_sanity(sanity - _tuning.sanity_drain_rate * delta)


func reward_photo() -> void:
	_set_sanity(sanity + _tuning.sanity_photo_bonus)


func can_hide() -> bool:
	return sanity >= _tuning.no_hide_sanity_threshold


func reset() -> void:
	_is_noticed = false
	_has_caught = false
	_set_suspicion(0.0)
	_set_school_alert(0.0)
	_set_sanity(METER_MAXIMUM)


func _set_suspicion(value: float) -> void:
	var clamped: float = clampf(value, 0.0, METER_MAXIMUM)
	var has_changed: bool = clamped != suspicion
	suspicion = clamped
	if has_changed:
		suspicion_changed.emit(suspicion)
	_update_notice()
	if suspicion >= METER_MAXIMUM:
		_report_caught(&"target_report")


func _set_school_alert(value: float) -> void:
	var clamped: float = clampf(value, 0.0, METER_MAXIMUM)
	var has_changed: bool = clamped != school_alert
	school_alert = clamped
	if has_changed:
		school_alert_changed.emit(school_alert)
	if school_alert >= METER_MAXIMUM:
		_report_caught(&"school_alert")


func _set_sanity(value: float) -> void:
	var clamped: float = clampf(value, 0.0, METER_MAXIMUM)
	var has_changed: bool = clamped != sanity
	sanity = clamped
	if has_changed:
		sanity_changed.emit(sanity)


func _update_notice() -> void:
	if _is_noticed:
		if suspicion < _tuning.notice_threshold - NOTICE_REARM_MARGIN:
			_is_noticed = false
	elif suspicion >= _tuning.notice_threshold:
		_is_noticed = true
		noticed.emit()


func _report_caught(reason: StringName) -> void:
	if _has_caught:
		return
	_has_caught = true
	caught.emit(reason)
