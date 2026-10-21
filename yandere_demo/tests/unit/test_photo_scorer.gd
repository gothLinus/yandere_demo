extends TestCase


func shot(offset: float, distance: float) -> PhotoShot:
	var result: PhotoShot = PhotoShot.new()
	result.target_in_frame = true
	result.center_offset = offset
	result.distance = distance
	result.face_visible = true
	return result


func test_perfect_candid_photo() -> void:
	assert_eq(PhotoScorer.score(shot(0.0, 8.0)).score, 100)


func test_obstructed_is_zero() -> void:
	var obstructed: PhotoShot = shot(0.0, 8.0)
	obstructed.is_obstructed = true
	assert_eq(PhotoScorer.score(obstructed).score, 0)


func test_far_edge_looking_is_bad() -> void:
	var weak: PhotoShot = shot(0.9, 20.0)
	weak.target_looking_at_camera = true
	weak.face_visible = false
	var result: PhotoScorer.PhotoResult = PhotoScorer.score(weak)
	assert_eq(result.score, 4 + 15)
	assert_true(not result.is_good)


func test_rare_bonus_caps_at_hundred() -> void:
	var rare: PhotoShot = shot(0.0, 8.0)
	rare.activity_is_rare = true
	assert_eq(PhotoScorer.score(rare).score, 100)


func test_distance_below_minimum_scales_points() -> void:
	var close: PhotoShot = shot(0.0, 1.5)
	close.target_looking_at_camera = true
	close.face_visible = false
	assert_eq(PhotoScorer.score(close).score, 40 + 15)


func test_not_in_frame_is_zero() -> void:
	var missed: PhotoShot = shot(0.0, 8.0)
	missed.target_in_frame = false
	var result: PhotoScorer.PhotoResult = PhotoScorer.score(missed)
	assert_eq(result.score, 0)
	assert_true(not result.is_good)


func test_good_threshold_boundary() -> void:
	var borderline: PhotoShot = shot(0.5, 8.0)
	borderline.target_looking_at_camera = true
	borderline.face_visible = false
	assert_eq(PhotoScorer.score(borderline).score, 50)
	borderline.face_visible = true
	var result: PhotoScorer.PhotoResult = PhotoScorer.score(borderline)
	assert_eq(result.score, 70)
	assert_true(result.is_good)
