class_name CastTuning
extends Resource
## Teacher and background-student behaviour and looks (spec §4.5). Distances in metres, real seconds.

## student_walk and teacher_walk are both keyed for this speed.
@export var walk_speed: float = 1.2
@export var turn_rate: float = 8.0
@export var acceleration: float = 2.5
@export var arrive_distance: float = 0.3
## Seated anchors sit off the navmesh (ruling R12): finishing navigation this close counts as arrival.
@export var seated_arrive_distance: float = 0.8
## Glides onto and off a seat last max(min seconds, distance / max speed).
@export var glide_min_seconds: float = 0.4
@export var glide_max_speed: float = 1.2
## Walking slower than `stuck_speed` for this long gives up the current destination.
@export var stuck_seconds: float = 5.0
@export var stuck_speed: float = 0.1

@export var teacher_look_around_seconds: float = 4.0
## He looks around at every Nth patrol point.
@export var teacher_look_around_every: int = 3
## `camera_at_student`: a student or the target this close inside the raised camera's view.
@export var camera_at_student_range: float = 15.0

@export var student_spot_min_seconds: float = 20.0
@export var student_spot_max_seconds: float = 60.0
## What a student does at a StudentSpot; the spots have no seats, so student_sit is kept for class.
@export var student_spot_animations: Array[StringName] = [&"student_idle", &"student_chat"]
@export var witness_range: float = 10.0
@export var witness_fov_degrees: float = 120.0
@export var witness_cooldown_seconds: float = 20.0

## Female uniforms and neckerchiefs, paired by index; none are the player's navy and red.
@export var female_uniform_colors: Array[Color] = [
	Color(0.22, 0.36, 0.28), Color(0.45, 0.44, 0.47), Color(0.55, 0.42, 0.3), Color(0.4, 0.27, 0.42),
]
@export var female_neckerchief_colors: Array[Color] = [
	Color(0.86, 0.69, 0.28), Color(0.18, 0.52, 0.55), Color(0.2, 0.4, 0.3), Color(0.5, 0.7, 0.88),
]
@export var male_uniform_colors: Array[Color] = [
	Color(0.12, 0.14, 0.2), Color(0.1, 0.1, 0.11), Color(0.26, 0.27, 0.3), Color(0.22, 0.25, 0.18),
]
@export var hair_colors: Array[Color] = [
	Color(0.07, 0.06, 0.07), Color(0.17, 0.14, 0.13), Color(0.35, 0.24, 0.18), Color(0.45, 0.26, 0.15),
	Color(0.62, 0.5, 0.32),
]
## M_HairShade, the dark under-layer, is the hair colour darkened to this ratio (as in the exported files).
@export var hair_shade_ratio: float = 0.68
