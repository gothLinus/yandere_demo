class_name EndingResolver
extends RefCounted


static func resolve(photo_score_total: int, intel_count: int, tuning: EndingTuning) -> StringName:
	var high_photos: bool = photo_score_total >= tuning.high_photo_score
	var high_intel: bool = intel_count >= tuning.high_intel_count
	if high_photos and high_intel:
		return &"cherry_tree"
	if high_photos:
		return &"shrine"
	if high_intel:
		return &"friends"
	return &"stranger"
