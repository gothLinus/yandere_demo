class_name TargetPerception
extends Node
## The target's senses (spec §4.5). Every physics frame his sight feeds Suspicion; noticing, startling, seeing his
## own item carried, footsteps and the report drive his reaction states on the parent TargetAI.

@export var tuning: StealthTuning = preload("res://data/stealth_tuning.tres")

var player: StealthPlayer
## Injected until the Task 18 autoload holds the meters.
var meters: StealthMeters
var sees_player: bool = false

var _startle_armed: bool = true
## Ids of his items already punished as carried, as a set: each counts once.
var _spiked_item_ids: Dictionary = {}

@onready var _target: TargetAI = get_parent() as TargetAI


func _physics_process(delta: float) -> void:
	if player == null or meters == null or not _is_aware():
		sees_player = false
		return
	var player_head: Vector3 = player.head_position()
	var is_hidden: bool = player.mode == StealthPlayer.MODE_HIDDEN
	sees_player = not is_hidden and can_see(player_head)
	var is_close: bool = _target.global_position.distance_to(player.global_position) <= tuning.startle_distance
	if not is_close:
		_startle_armed = true
	if not sees_player:
		meters.apply_unseen(delta, is_hidden)
		_update_reaction(player_head)
		return
	var distance: float = _target.head_position().distance_to(player_head)
	meters.apply_seen(delta, distance, player.stance, player.current_activity(), _crowd_count())
	if is_close and _startle_armed and _is_aware():
		_startle_armed = false
		_target.startle(player_head)
		meters.add_suspicion_spike(tuning.startle_spike)
	_check_carried_item()
	_update_reaction(player_head)


func watch(watched_player: StealthPlayer, stealth_meters: StealthMeters) -> void:
	if player != null and player.noise_made.is_connected(_on_noise_made):
		player.noise_made.disconnect(_on_noise_made)
	if meters != null and meters.noticed.is_connected(_on_noticed):
		meters.noticed.disconnect(_on_noticed)
		meters.caught.disconnect(_on_caught)
	player = watched_player
	meters = stealth_meters
	player.noise_made.connect(_on_noise_made)
	meters.noticed.connect(_on_noticed)
	meters.caught.connect(_on_caught)
	reset()


func reset() -> void:
	sees_player = false
	_startle_armed = true
	_spiked_item_ids.clear()


## Sight cone from his eyes along where his face looks, then a ray that only geometry blocks (ruling R15). Photo
## mode (Task 17) uses it for "the flash fired while he can see it" (ruling R21).
func can_see(point: Vector3) -> bool:
	var eye: Vector3 = _target.head_position()
	if not Detection.is_in_view_cone(eye, _target.eye_forward(), point, tuning.sight_fov_degrees, tuning.sight_range):
		return false
	return Detection.has_line_of_sight(_target.get_world_3d().direct_space_state, eye, point, [])


func _is_aware() -> bool:
	return _target.school != null and _target.state != TargetAI.State.GONE and _target.state != TargetAI.State.REPORTING


func _crowd_count() -> int:
	var count: int = 0
	for student: Node in get_tree().get_nodes_in_group(StudentAI.GROUP):
		if (student as Node3D).global_position.distance_to(player.global_position) <= tuning.crowd_radius:
			count += 1
	return count


func _check_carried_item() -> void:
	var item_id: StringName = player.carried_item
	if item_id == &"" or _spiked_item_ids.has(item_id) or not _target.is_own_item(item_id):
		return
	_spiked_item_ids[item_id] = true
	meters.add_suspicion_spike(tuning.carrying_seen_spike)


## While he notices or suspects, his head follows the player he can see; once Suspicion falls below the notice
## threshold minus the re-arm margin, he calms down.
func _update_reaction(player_head: Vector3) -> void:
	if not _target.is_reacting():
		return
	if sees_player and meters.suspicion >= tuning.notice_threshold:
		_target.look_toward(player_head)
	var calm_below: float = tuning.notice_threshold - StealthMeters.NOTICE_REARM_MARGIN
	if _target.state == TargetAI.State.SUSPICIOUS and meters.suspicion < calm_below:
		_target.calm_down()


func _on_noticed() -> void:
	if _is_aware():
		_target.notice(player.head_position())


func _on_caught(reason: StringName) -> void:
	if reason == &"target_report":
		_target.report()


func _on_noise_made(noise_position: Vector3, stance: GameTypes.Stance) -> void:
	if _is_aware() and Detection.can_hear(_target.global_position, noise_position, stance, tuning):
		_target.glance_at(player.head_position())
