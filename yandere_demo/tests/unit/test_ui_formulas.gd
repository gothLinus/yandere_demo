extends TestCase


func test_heart_bpm_rises_as_sanity_falls() -> void:
	assert_near(SanityHeart.beats_per_minute(100.0), 60.0, 0.001)
	assert_near(SanityHeart.beats_per_minute(0.0), 140.0, 0.001)
	assert_near(SanityHeart.beats_per_minute(50.0), 100.0, 0.001)


func test_vignette_intensity_follows_the_stronger_meter() -> void:
	assert_near(Vignette.intensity_for(100.0, 0.0), 0.0, 0.001)
	assert_near(Vignette.intensity_for(20.0, 0.0), 0.5, 0.001)
	assert_near(Vignette.intensity_for(100.0, 100.0), 1.0, 0.001)
	assert_near(Vignette.intensity_for(0.0, 75.0), 1.0, 0.001)
	assert_near(Vignette.intensity_for(100.0, 75.0), 0.5, 0.001)
