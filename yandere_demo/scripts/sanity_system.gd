extends Node
## Autoload: holds the day's StealthMeters (Suspicion, School Alert, Sanity; spec §4.5) and re-emits all of their
## signals under the same names, so the HUD and GameManager listen here.

signal suspicion_changed(value: float)
signal school_alert_changed(value: float)
signal sanity_changed(value: float)
signal suspicion_triggered(amount: float)
signal noticed()
signal caught(reason: StringName)

const TUNING: StealthTuning = preload("res://data/stealth_tuning.tres")

var meters: StealthMeters = StealthMeters.new(TUNING)


func _init() -> void:
	meters.suspicion_changed.connect(suspicion_changed.emit)
	meters.school_alert_changed.connect(school_alert_changed.emit)
	meters.sanity_changed.connect(sanity_changed.emit)
	meters.suspicion_triggered.connect(suspicion_triggered.emit)
	meters.noticed.connect(noticed.emit)
	meters.caught.connect(caught.emit)


func reset() -> void:
	meters.reset()
