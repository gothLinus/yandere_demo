extends TestCase

const AUDIO_DIRECTORY: String = "res://assets/audio/"
const SOUND_NAMES: Array[String] = [
	"footstep_walk_01", "footstep_walk_02", "footstep_walk_03",
	"footstep_run_01", "footstep_run_02", "footstep_run_03",
	"footstep_sneak_01", "footstep_sneak_02",
	"heartbeat", "shutter", "bell_chime", "locker_door", "pickup_chime",
	"suspicion_sting", "game_over_sting", "bgm_school_loop",
]


func _load_wav(sound_name: String) -> AudioStreamWAV:
	return load("%s%s.wav" % [AUDIO_DIRECTORY, sound_name]) as AudioStreamWAV


func test_all_wavs_load() -> void:
	for sound_name: String in SOUND_NAMES:
		var stream: AudioStreamWAV = _load_wav(sound_name)
		assert_true(stream != null, "%s should load as AudioStreamWAV" % sound_name)
		if stream != null:
			assert_true(stream.get_length() > 0.0, "%s should have a length" % sound_name)


func test_bgm_is_about_32_seconds_and_loops_forward() -> void:
	var stream: AudioStreamWAV = _load_wav("bgm_school_loop")
	assert_true(stream != null, "bgm should load")
	if stream == null:
		return
	assert_true(stream.get_length() >= 31.0 and stream.get_length() <= 33.0, "bgm length %s" % stream.get_length())
	assert_eq(stream.loop_mode, AudioStreamWAV.LOOP_FORWARD)


func test_bell_chime_lasts_at_least_three_seconds() -> void:
	var stream: AudioStreamWAV = _load_wav("bell_chime")
	assert_true(stream != null and stream.get_length() >= 3.0, "bell chime too short")


func test_heartbeat_volume_follows_sanity() -> void:
	assert_true(AudioFormulas.heartbeat_is_audible(60.0) == false)
	assert_true(AudioFormulas.heartbeat_is_audible(59.0))
	assert_near(AudioFormulas.heartbeat_volume_db(0.0), -6.0, 0.001)
	assert_true(AudioFormulas.heartbeat_volume_db(30.0) < -6.0)
	assert_true(AudioFormulas.heartbeat_volume_db(30.0) > AudioFormulas.heartbeat_volume_db(50.0))
