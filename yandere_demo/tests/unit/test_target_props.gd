extends TestCase
## Ruling R9 (Task 23b): each hand prop is held by its clip's hand pose. The holding hand's palm lies on the prop and,
## for the can and the broom, the fingers wrap round it; two-handed props touch the other palm too. Sampled through
## each clip, with the prop at its TargetProps placement on the hand bone.

const TARGET_SCENE_PATH: String = "res://assets/models/target.glb"
const SAMPLE_COUNT: int = 8
## Palm centre: this share of the way from the wrist to the knuckles; its skin lies this far out toward the palm side
## (measured on the model's hands: 16-19 mm).
const PALM_CENTRE_SHARE: float = 0.6
const PALM_SKIN_DEPTH: float = 0.017
const KNUCKLES: Array[String] = ["index_01", "middle_01", "ring_01", "pinky_01"]
## Middle finger joints of a wrapping grip.
const WRAPPING_JOINTS: Array[String] = ["index_03", "middle_03", "ring_03"]
## Holding: the prop's surface lies within this of the palm skin, measured along the palm's normal (either way)...
const PALM_CONTACT_TOLERANCE: float = 0.012
## ...and lies flush: the palm normal is within this of a flat prop's face normal, or square to a round prop's axis.
const PALM_FLUSH_DEGREES: float = 35.0
const PALM_RAY_REACH: float = 0.05
const PALM_RAY_STEP: float = 0.001
## A wrapping finger joint (finger half-thickness ~8 mm) within this of the prop's surface.
const FINGER_CONTACT_TOLERANCE: float = 0.02

## Clip -> (prop, wraps, support hand or "" for one hand). The support hand is checked at the loop start and the middle.
const GRIPS: Dictionary[StringName, Array] = {
	&"target_sit_read": [TargetProps.BOOK, false, "hand.L"],
	&"target_phone": [TargetProps.PHONE, false, ""],
	&"target_drink": [TargetProps.CAN, true, ""],
	&"target_sweep": [TargetProps.BROOM, true, "hand.R"],
}


func test_every_prop_is_held_by_its_clip() -> void:
	if not ResourceLoader.exists(TARGET_SCENE_PATH):
		assert_true(false, "target.glb is imported")
		return
	var root: Node = (load(TARGET_SCENE_PATH) as PackedScene).instantiate()
	var skeleton: Skeleton3D = root.find_child("Skeleton3D", true, false) as Skeleton3D
	var player: AnimationPlayer = root.find_child("AnimationPlayer", true, false) as AnimationPlayer
	for animation_name: StringName in GRIPS:
		var grip: Array = GRIPS[animation_name]
		var prop_name: StringName = grip[0]
		var prop: Node3D = TargetProps.build_prop(prop_name)
		var hand_bone: String = TargetProps.PROP_BONES[prop_name]
		var animation: Animation = player.get_animation(animation_name)
		var worst_palm: float = 0.0
		var worst_tilt: float = 0.0
		var worst_finger: float = 0.0
		var worst_support: float = 0.0
		for sample: int in SAMPLE_COUNT:
			var time: float = animation.length * sample / SAMPLE_COUNT
			_pose(skeleton, animation, time)
			var hand: Transform3D = _global_pose(skeleton, skeleton.find_bone(hand_bone))
			var palm: Array[Vector3] = _palm(skeleton, hand_bone)
			worst_palm = maxf(worst_palm, _palm_gap(prop, hand, palm))
			worst_tilt = maxf(worst_tilt, _palm_tilt(prop, hand, palm))
			if grip[1]:
				for joint: String in WRAPPING_JOINTS:
					var joint_bone: int = skeleton.find_bone(joint + hand_bone.right(2))
					var joint_point: Vector3 = _global_pose(skeleton, joint_bone).origin
					worst_finger = maxf(worst_finger, absf(_prop_distance(prop, hand, joint_point)))
			if grip[2] != "" and (sample == 0 or sample == SAMPLE_COUNT / 2):
				worst_support = maxf(worst_support, _palm_gap(prop, hand, _palm(skeleton, grip[2])))
		assert_true(worst_palm <= PALM_CONTACT_TOLERANCE, "%s: the %s lies %.3f m from the %s palm (at most %.3f)"
				% [animation_name, prop_name, worst_palm, hand_bone, PALM_CONTACT_TOLERANCE])
		assert_true(worst_tilt <= PALM_FLUSH_DEGREES, "%s: the %s sits %.0f degrees off flush with the %s palm (at most %.0f)"
				% [animation_name, prop_name, worst_tilt, hand_bone, PALM_FLUSH_DEGREES])
		assert_true(worst_finger <= FINGER_CONTACT_TOLERANCE, "%s: the %s fingers lie up to %.3f m off the %s (at most %.3f)"
				% [animation_name, hand_bone, worst_finger, prop_name, FINGER_CONTACT_TOLERANCE])
		assert_true(worst_support <= PALM_CONTACT_TOLERANCE, "%s: the %s lies %.3f m from the %s palm (at most %.3f)"
				% [animation_name, prop_name, worst_support, grip[2], PALM_CONTACT_TOLERANCE])
		prop.free()
	root.free()


## A bone's pose in skeleton space, composed from the local poses: outside the scene tree Skeleton3D's own global-pose
## cache is never refreshed after the first evaluation.
func _global_pose(skeleton: Skeleton3D, bone: int) -> Transform3D:
	var pose: Transform3D = skeleton.get_bone_pose(bone)
	var parent: int = skeleton.get_bone_parent(bone)
	while parent >= 0:
		pose = skeleton.get_bone_pose(parent) * pose
		parent = skeleton.get_bone_parent(parent)
	return pose


## Applies an animation's bone tracks at `time` to the skeleton (no AnimationPlayer processing needed).
func _pose(skeleton: Skeleton3D, animation: Animation, time: float) -> void:
	skeleton.reset_bone_poses()
	for track: int in animation.get_track_count():
		var bone: int = skeleton.find_bone(animation.track_get_path(track).get_concatenated_subnames())
		if bone < 0:
			continue
		match animation.track_get_type(track):
			Animation.TYPE_ROTATION_3D:
				skeleton.set_bone_pose_rotation(bone, animation.rotation_track_interpolate(track, time))
			Animation.TYPE_POSITION_3D:
				skeleton.set_bone_pose_position(bone, animation.position_track_interpolate(track, time))
			Animation.TYPE_SCALE_3D:
				skeleton.set_bone_pose_scale(bone, animation.scale_track_interpolate(track, time))


## The palm's skin point and normal in skeleton space. The palm faces the body at rest, so its normal is the inward
## axis there, carried along by the hand bone.
func _palm(skeleton: Skeleton3D, hand_bone: String) -> Array[Vector3]:
	var side: String = hand_bone.right(2)
	var hand_index: int = skeleton.find_bone(hand_bone)
	var hand: Transform3D = _global_pose(skeleton, hand_index)
	var knuckles: Vector3 = Vector3.ZERO
	var rest_knuckles: Vector3 = Vector3.ZERO
	for knuckle: String in KNUCKLES:
		var bone: int = skeleton.find_bone(knuckle + side)
		knuckles += _global_pose(skeleton, bone).origin / KNUCKLES.size()
		rest_knuckles += skeleton.get_bone_global_rest(bone).origin / KNUCKLES.size()
	var rest: Transform3D = skeleton.get_bone_global_rest(hand_index)
	var along: Vector3 = (rest_knuckles - rest.origin).normalized()
	var inward: Vector3 = Vector3.LEFT if side == ".L" else Vector3.RIGHT
	var rest_normal: Vector3 = (inward - along * inward.dot(along)).normalized()
	var normal: Vector3 = (hand.basis * (rest.basis.inverse() * rest_normal)).normalized()
	return [hand.origin.lerp(knuckles, PALM_CENTRE_SHARE) + normal * PALM_SKIN_DEPTH, normal]


## How far along the palm's normal (either way) the prop's surface lies from the palm skin; INF when it is not in front
## of the palm within PALM_RAY_REACH.
func _palm_gap(prop: Node3D, hand: Transform3D, palm: Array[Vector3]) -> float:
	var steps: int = roundi(PALM_RAY_REACH / PALM_RAY_STEP)
	for step: int in steps + 1:
		for direction: float in [1.0, -1.0]:
			var reach: float = step * PALM_RAY_STEP * direction
			if _prop_distance(prop, hand, palm[0] + palm[1] * reach) <= 0.0:
				return absf(reach)
	return INF


## Degrees by which the palm misses lying flush on the prop part nearest to it.
func _palm_tilt(prop: Node3D, hand: Transform3D, palm: Array[Vector3]) -> float:
	var nearest: float = INF
	var tilt: float = 0.0
	for node: Node in prop.find_children("*", "MeshInstance3D", true, false):
		var instance: MeshInstance3D = node as MeshInstance3D
		var placement: Transform3D = hand * prop.transform * _transform_below(prop, instance)
		var distance: float = _mesh_distance(instance, placement.affine_inverse() * palm[0])
		if distance >= nearest:
			continue
		nearest = distance
		var local_normal: Vector3 = (placement.basis.inverse() * palm[1]).normalized()
		if instance.mesh is BoxMesh:
			var size: Vector3 = (instance.mesh as BoxMesh).size
			var thin_axis: int = size.min_axis_index()
			tilt = rad_to_deg(acos(clampf(absf(local_normal[thin_axis]), 0.0, 1.0)))
		else:
			tilt = rad_to_deg(asin(clampf(absf(local_normal.y), 0.0, 1.0)))
	return tilt


## Signed distance from a skeleton-space point to the nearest surface of the prop's meshes (negative inside).
func _prop_distance(prop: Node3D, hand: Transform3D, point: Vector3) -> float:
	var nearest: float = INF
	for node: Node in prop.find_children("*", "MeshInstance3D", true, false):
		var instance: MeshInstance3D = node as MeshInstance3D
		var local: Vector3 = (hand * prop.transform * _transform_below(prop, instance)).affine_inverse() * point
		nearest = minf(nearest, _mesh_distance(instance, local))
	return nearest


func _mesh_distance(instance: MeshInstance3D, local: Vector3) -> float:
	if instance.mesh is BoxMesh:
		return _box_distance(local, (instance.mesh as BoxMesh).size * 0.5)
	var cylinder: CylinderMesh = instance.mesh as CylinderMesh
	return _cylinder_distance(local, cylinder.top_radius, cylinder.height * 0.5)


func _transform_below(prop: Node3D, node: Node3D) -> Transform3D:
	var transform: Transform3D = Transform3D.IDENTITY
	var current: Node3D = node
	while current != prop:
		transform = current.transform * transform
		current = current.get_parent() as Node3D
	return transform


func _box_distance(point: Vector3, half_size: Vector3) -> float:
	var outside: Vector3 = point.abs() - half_size
	return outside.max(Vector3.ZERO).length() + minf(maxf(outside.x, maxf(outside.y, outside.z)), 0.0)


func _cylinder_distance(point: Vector3, radius: float, half_height: float) -> float:
	var outside: Vector2 = Vector2(Vector2(point.x, point.z).length() - radius, absf(point.y) - half_height)
	return outside.max(Vector2.ZERO).length() + minf(maxf(outside.x, outside.y), 0.0)
