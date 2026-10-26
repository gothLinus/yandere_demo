extends Node
## Autoload: plays every sound effect and the BGM, and drives the heartbeat from Sanity.

const AUDIO_DIRECTORY: String = "res://assets/audio/"
const BGM_NAME: StringName = &"bgm_school_loop"
const HEARTBEAT_NAME: StringName = &"heartbeat"
const BGM_VOLUME_DB: float = -14.0
const SWELL_BEATS_PER_MINUTE: float = 140.0
const MIXER_RELEASE_MILLISECONDS: int = 250
const HIDE_SPOT_KIND_LOCKER: StringName = &"locker"

var _streams: Dictionary[StringName, AudioStream] = {}
var _bgm_player: AudioStreamPlayer
var _heartbeat_player: AudioStreamPlayer
var _is_heartbeat_enabled: bool = false
var _heartbeat_bpm: float = UiFormulas.BASE_BPM
var _heartbeat_volume_db: float = AudioFormulas.HEARTBEAT_QUIET_DB
var _beat_countdown: float = 0.0
var _swell_remaining: float = 0.0


func _ready() -> void:
	_bgm_player = _make_player(BGM_NAME, BGM_VOLUME_DB)
	_heartbeat_player = _make_player(HEARTBEAT_NAME, AudioFormulas.HEARTBEAT_QUIET_DB)
	GameManager.day_started.connect(_on_day_started)
	GameManager.day_completed.connect(_on_day_completed)
	GameManager.game_over.connect(_on_game_over)
	SchoolClock.bell_rang.connect(_on_bell_rang)
	SanitySystem.sanity_changed.connect(_on_sanity_changed)
	SanitySystem.noticed.connect(play_sfx.bind(&"suspicion_sting"))
	get_tree().node_added.connect(_on_node_added)


## The mixer thread only releases stopped playbacks on its next pass; quitting mid-sound would otherwise leak them.
func _exit_tree() -> void:
	for child: Node in get_children():
		child.call(&"stop")
		child.free()
	_streams.clear()
	OS.delay_msec(MIXER_RELEASE_MILLISECONDS)


func _process(delta: float) -> void:
	var is_swelling: bool = _swell_remaining > 0.0
	_swell_remaining = maxf(_swell_remaining - delta, 0.0)
	if is_swelling and _swell_remaining == 0.0:
		_apply_sanity(SanitySystem.meters.sanity)
	if not is_swelling and not (_is_heartbeat_enabled and AudioFormulas.heartbeat_is_audible(SanitySystem.meters.sanity)):
		_beat_countdown = 0.0
		return
	_beat_countdown -= delta
	if _beat_countdown <= 0.0:
		_beat_countdown = 60.0 / maxf(_heartbeat_bpm, 1.0)
		_heartbeat_player.play()


## Plays a one-shot from assets/audio. With a position the sound is spatial, otherwise it is flat.
func play_sfx(sound_name: StringName, position: Variant = null) -> void:
	var stream: AudioStream = _stream_for(sound_name)
	if stream == null:
		return
	if position is Vector3:
		var spatial_player: AudioStreamPlayer3D = AudioStreamPlayer3D.new()
		spatial_player.stream = stream
		spatial_player.finished.connect(spatial_player.queue_free)
		add_child(spatial_player)
		spatial_player.global_position = position
		spatial_player.play()
	else:
		var flat_player: AudioStreamPlayer = AudioStreamPlayer.new()
		flat_player.stream = stream
		flat_player.finished.connect(flat_player.queue_free)
		add_child(flat_player)
		flat_player.play()


func set_heartbeat_rate(bpm: float, volume_db: float) -> void:
	_heartbeat_bpm = bpm
	_heartbeat_volume_db = volume_db
	_heartbeat_player.volume_db = volume_db


## Full volume at the fastest rate for the given time, then the Sanity-driven heartbeat resumes.
func swell_heartbeat(duration_seconds: float) -> void:
	_swell_remaining = duration_seconds
	_beat_countdown = 0.0
	set_heartbeat_rate(SWELL_BEATS_PER_MINUTE, AudioFormulas.HEARTBEAT_LOUD_DB)


func stop_heartbeat() -> void:
	_swell_remaining = 0.0
	_is_heartbeat_enabled = false
	_heartbeat_player.stop()


func _stream_for(sound_name: StringName) -> AudioStream:
	if not _streams.has(sound_name):
		var stream: AudioStream = load("%s%s.wav" % [AUDIO_DIRECTORY, sound_name]) as AudioStream
		if stream == null:
			push_error("AudioDirector: no sound named %s" % sound_name)
			return null
		_streams[sound_name] = stream
	return _streams[sound_name]


func _make_player(sound_name: StringName, volume_db: float) -> AudioStreamPlayer:
	var player: AudioStreamPlayer = AudioStreamPlayer.new()
	player.stream = _stream_for(sound_name)
	player.volume_db = volume_db
	add_child(player)
	return player


func _apply_sanity(sanity: float) -> void:
	if _swell_remaining > 0.0:
		return
	set_heartbeat_rate(UiFormulas.beats_per_minute(sanity), AudioFormulas.heartbeat_volume_db(sanity))


func _on_day_started(_day_index: int) -> void:
	stop_heartbeat()
	_is_heartbeat_enabled = true
	_apply_sanity(SanitySystem.meters.sanity)
	_bgm_player.play()


func _on_day_completed(_summary: Dictionary) -> void:
	stop_heartbeat()
	_bgm_player.stop()


func _on_game_over(_reason: StringName) -> void:
	stop_heartbeat()
	_bgm_player.stop()
	play_sfx(&"game_over_sting")


func _on_bell_rang(_block: ScheduleBlock) -> void:
	play_sfx(&"bell_chime")


func _on_sanity_changed(sanity: float) -> void:
	_apply_sanity(sanity)


func _on_node_added(node: Node) -> void:
	var pickup: ItemPickup = node as ItemPickup
	if pickup != null:
		pickup.picked.connect(_on_item_picked)
	var photo_mode: PhotoMode = node as PhotoMode
	if photo_mode != null:
		photo_mode.photo_taken.connect(_on_photo_taken)
	var hide_spot: HideSpot = node as HideSpot
	if hide_spot != null:
		hide_spot.player_hidden_changed.connect(_on_player_hidden_changed.bind(hide_spot))


func _on_item_picked(_item_id: StringName) -> void:
	play_sfx(&"pickup_chime")


func _on_photo_taken(_result: PhotoScorer.PhotoResult, _image_path: String) -> void:
	play_sfx(&"shutter")


func _on_player_hidden_changed(_is_hidden: bool, hide_spot: HideSpot) -> void:
	if hide_spot.kind == HIDE_SPOT_KIND_LOCKER:
		play_sfx(&"locker_door", hide_spot.global_position)
