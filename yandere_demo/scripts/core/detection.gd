class_name Detection
extends RefCounted


static func is_in_view_cone(origin: Vector3, forward: Vector3, point: Vector3, fov_degrees: float, max_distance: float) -> bool:
	var offset: Vector3 = point - origin
	var distance: float = offset.length()
	if distance > max_distance:
		return false
	if is_zero_approx(distance):
		return true
	var angle: float = forward.normalized().angle_to(offset / distance)
	return rad_to_deg(angle) <= fov_degrees * 0.5


static func has_line_of_sight(space: PhysicsDirectSpaceState3D, from: Vector3, to: Vector3, exclude: Array[RID]) -> bool:
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(from, to, PhysicsLayers.LINE_OF_SIGHT_MASK, exclude)
	var result: Dictionary = space.intersect_ray(query)
	return result.is_empty()


static func can_hear(listener: Vector3, source: Vector3, stance: GameTypes.Stance, tuning: StealthTuning) -> bool:
	var radius: float = tuning.hearing_radius[stance]
	return radius > 0.0 and listener.distance_to(source) <= radius
