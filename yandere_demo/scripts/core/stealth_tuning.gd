class_name StealthTuning
extends Resource

@export var sight_range: float = 12.0
@export var sight_fov_degrees: float = 110.0
@export var base_sight_gain: float = 20.0
@export var stance_multipliers: Dictionary = {
	GameTypes.Stance.SNEAK: 0.4,
	GameTypes.Stance.WALK: 1.0,
	GameTypes.Stance.RUN: 1.5,
	GameTypes.Stance.HIDDEN: 0.0,
}
@export var activity_multipliers: Dictionary = {
	GameTypes.PlayerActivity.NONE: 1.0,
	GameTypes.PlayerActivity.CAMERA_RAISED: 2.5,
	GameTypes.PlayerActivity.CARRYING_ITEM: 2.0,
}
@export var crowd_multiplier: float = 0.5
@export var crowd_minimum: int = 2
@export var crowd_radius: float = 3.0
@export var low_sanity_threshold: float = 25.0
@export var low_sanity_multiplier: float = 1.5
@export var unseen_decay: float = 3.0
@export var hidden_decay: float = 25.0
@export var notice_threshold: float = 35.0
@export var hearing_radius: Dictionary = {
	GameTypes.Stance.SNEAK: 1.0,
	GameTypes.Stance.WALK: 3.0,
	GameTypes.Stance.RUN: 8.0,
	GameTypes.Stance.HIDDEN: 0.0,
}
@export var flash_spike: float = 40.0
@export var carrying_seen_spike: float = 30.0
@export var startle_distance: float = 1.2
@export var startle_spike: float = 25.0
@export var teacher_sight_range: float = 14.0
@export var teacher_fov_degrees: float = 100.0
@export var alert_rates: Dictionary = {
	&"out_of_class": 8.0,
	&"running_in_hall": 4.0,
	&"camera_at_student": 10.0,
	&"carrying_stolen_item": 10.0,
}
@export var alert_spikes: Dictionary = {
	&"late": 10.0,
	&"skipped_class": 25.0,
	&"student_witness": 5.0,
}
@export var sanity_drain_delay: float = 30.0
@export var sanity_drain_rate: float = 0.5
@export var sanity_recover_rate: float = 3.0
@export var sanity_watch_range: float = 15.0
@export var sanity_photo_bonus: float = 10.0
@export var vignette_sanity_threshold: float = 40.0
@export var no_hide_sanity_threshold: float = 10.0
@export var sneak_speed_low_sanity_multiplier: float = 0.75
