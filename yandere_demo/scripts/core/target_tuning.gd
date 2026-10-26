class_name TargetTuning
extends Resource
## Movement, schedule-execution and face tuning for the target AI (spec §4.4). Distances in metres, real seconds
## unless named otherwise.

## Body yaw follows the walking direction with lerp_angle at this rate, capped at the same rate in radians per second.
@export var turn_rate: float = 8.0
## Walking speed change per second, so starts and micro-stops ease in and out.
@export var acceleration: float = 2.5
## Within this distance of the anchor he slows linearly toward `arriving_speed_ratio` of his walk speed.
@export var arriving_radius: float = 1.5
@export var arriving_speed_ratio: float = 0.35
## ENTERING starts this close to a standing anchor.
@export var entering_distance: float = 0.3
## A seated anchor sits between desk and chair, off the navmesh: ENTERING also starts when navigation finishes this
## close to it (ruling R12).
@export var seated_entering_distance: float = 0.8
## The ENTERING and stand-up glides last max(min seconds, distance / max speed).
@export var entering_min_seconds: float = 0.4
@export var entering_max_speed: float = 1.2
## Path-length fractions where the planned micro-stops happen, in order.
@export var micro_stop_path_fractions: Array[float] = [0.3, 0.65]
@export var micro_stop_seconds: float = 3.0
@export var window_search_radius: float = 6.0
@export var glance_back_degrees: float = 120.0
@export var head_turn_seconds: float = 0.3
## TRAVEL or ARRIVING that gains less than `unreachable_min_progress` m/s of path over this window skips the anchor.
@export var unreachable_seconds: float = 8.0
@export var unreachable_min_progress: float = 0.2
## Courtyard StudentSpot markers that courtyard_stroll walks between (the ground-level spots east of the building).
@export var courtyard_spots: Array[StringName] = [
	&"StudentSpot_01", &"StudentSpot_02", &"StudentSpot_03", &"StudentSpot_04", &"StudentSpot_05", &"StudentSpot_06",
]
@export var stroll_spot_count: int = 3
## Items that can turn up in his shoe locker at the start of each class block.
@export var class_locker_items: Array[StringName] = [&"hairpin", &"note", &"pen"]
@export var class_locker_min_items: int = 1
@export var class_locker_max_items: int = 2
@export var blink_min_seconds: float = 2.0
@export var blink_max_seconds: float = 6.0
@export var blink_seconds: float = 0.15
## After noticing the player he pauses this long, then turns SUSPICIOUS.
@export var notice_pause_seconds: float = 2.5
## Calming down resumes his plan at this walking-speed scale for `calm_slow_seconds`.
@export var calm_speed_scale: float = 0.85
@export var calm_slow_seconds: float = 20.0
## A heard footstep turns his head toward it for this long, with no Suspicion.
@export var hearing_turn_seconds: float = 1.5
