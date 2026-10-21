class_name PhotoScorer
extends RefCounted

const GOOD_THRESHOLD: int = 60
const MAX_SCORE: int = 100
const CENTERING_POINTS: float = 40.0
const DISTANCE_POINTS: float = 30.0
const FACE_POINTS: float = 20.0
const CANDID_POINTS: float = 10.0
const RARE_POINTS: float = 20.0
const IDEAL_DISTANCE_MIN: float = 3.0
const IDEAL_DISTANCE_MAX: float = 15.0
const FALLOFF_DISTANCE_MAX: float = 25.0


class PhotoResult extends RefCounted:
	var score: int = 0
	var is_good: bool = false
	var notes: Array[String] = []


static func score(shot: PhotoShot) -> PhotoResult:
	var result: PhotoResult = PhotoResult.new()
	if not shot.target_in_frame:
		result.notes.append("target not in frame")
		return result
	if shot.is_obstructed:
		result.notes.append("obstructed")
		return result

	var total: float = CENTERING_POINTS * (1.0 - clampf(shot.center_offset, 0.0, 1.0))
	total += _distance_points(shot.distance)
	if shot.distance < IDEAL_DISTANCE_MIN:
		result.notes.append("too close")
	elif shot.distance > IDEAL_DISTANCE_MAX:
		result.notes.append("too far")
	if shot.face_visible:
		total += FACE_POINTS
		result.notes.append("face visible")
	if not shot.target_looking_at_camera:
		total += CANDID_POINTS
		result.notes.append("candid")
	if shot.activity_is_rare:
		total += RARE_POINTS
		result.notes.append("rare moment")

	result.score = mini(roundi(total), MAX_SCORE)
	result.is_good = result.score >= GOOD_THRESHOLD
	return result


static func _distance_points(distance: float) -> float:
	if distance < IDEAL_DISTANCE_MIN:
		return DISTANCE_POINTS * maxf(distance, 0.0) / IDEAL_DISTANCE_MIN
	if distance <= IDEAL_DISTANCE_MAX:
		return DISTANCE_POINTS
	return DISTANCE_POINTS * maxf(FALLOFF_DISTANCE_MAX - distance, 0.0) / (FALLOFF_DISTANCE_MAX - IDEAL_DISTANCE_MAX)
