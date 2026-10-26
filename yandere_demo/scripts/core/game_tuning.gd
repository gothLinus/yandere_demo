class_name GameTuning
extends Resource
## Day-flow numbers for the autoloads (spec §4.3): fast-forward, the low-Sanity camera shake and the daylight tick.

## Engine.time_scale while the fast-forward key is held (spec: about 4-8x).
@export var fast_forward_time_scale: float = 4.0
## CameraRig.shake_strength while Sanity is below StealthTuning.no_hide_sanity_threshold.
@export var low_sanity_shake_strength: float = 0.04
## Seconds of clock time (time-scaled, like ScheduleBlock.real_seconds) between daylight updates.
@export var daylight_tick_seconds: float = 1.0
