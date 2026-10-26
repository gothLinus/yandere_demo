extends TestCase


func test_default_profile_hits_the_keyframes() -> void:
	var profile: DaylightProfile = load("res://data/daylight_profile.tres") as DaylightProfile
	var sun: DirectionalLight3D = DirectionalLight3D.new()
	profile.apply_to(sun, 420.0)
	assert_true(is_equal_approx(sun.light_energy, 1.2))
	profile.apply_to(sun, 720.0)
	assert_true(sun.light_color.is_equal_approx(Color.WHITE))
	profile.apply_to(sun, 1050.0)
	assert_true(sun.light_color.is_equal_approx(Color("ffb070")))
	assert_true(is_equal_approx(sun.light_energy, 0.8))
	assert_true(is_equal_approx(sun.rotation_degrees.x, -18.0))
	sun.free()


func test_minutes_outside_the_keyframes_clamp() -> void:
	var profile: DaylightProfile = DaylightProfile.new()
	var sun: DirectionalLight3D = DirectionalLight3D.new()
	profile.apply_to(sun, 0.0)
	assert_true(is_equal_approx(sun.light_energy, profile.morning_energy))
	profile.apply_to(sun, 1400.0)
	assert_true(is_equal_approx(sun.light_energy, profile.evening_energy))
	sun.free()
