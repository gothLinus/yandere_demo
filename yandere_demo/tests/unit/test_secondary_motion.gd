extends TestCase

const TUNING_PATH: String = "res://data/secondary_motion.tres"
const TARGET_SCENE_PATH: String = "res://assets/models/target.glb"
# Chain prefix -> [stiffness, drag, gravity, radius, influence]: the Task 23a starting values on the Astolfo chains
# (Task 23c tunes them). Braid, bow and skirt keep the ruling R10 values, measured by
# tests/integration/target_secondary_motion.
const EXPECTED_CHAINS: Dictionary[StringName, Array] = {
	&"braid": [3.0, 0.5, 0.2, 0.03, 0.3],
	&"hair_front": [1.6, 0.35, 0.3, 0.015, 1.0],
	&"hair_side": [1.2, 0.4, 0.5, 0.02, 1.0],
	&"hair_back": [1.2, 0.4, 0.5, 0.02, 1.0],
	&"head_bow": [2.5, 0.5, 0.2, 0.015, 1.0],
	&"ribbon": [1.0, 0.45, 0.6, 0.015, 1.0],
	&"skirt": [4.0, 0.55, 0.1, 0.025, 0.3],
	&"braid_bow": [3.0, 0.4, 0.2, 0.02, 0.3],
}
# The hands hold the braid in target_fix_braid, so its springs let go for that clip.
const EXPECTED_ANIMATION_INFLUENCE: Dictionary[StringName, Dictionary] = {
	&"braid": {&"target_fix_braid": 0.0},
}
# Which capsules each chain family collides with: the hair and bows keep off the head, the braid and the ribbons off
# the body, the skirt and the braid bow off the legs and hips.
const EXPECTED_COLLIDERS: Dictionary[StringName, Array] = {
	&"braid": [&"chest", &"hips"],
	&"hair_front": [&"head"],
	&"hair_side": [&"head"],
	&"hair_back": [&"head"],
	&"head_bow": [&"head"],
	&"ribbon": [&"chest"],
	&"skirt": [&"thigh.L", &"thigh.R", &"hips"],
	&"braid_bow": [&"hips", &"thigh.L", &"thigh.R"],
}
# Leaf bone rest lengths of the Blender rig (glTF drops bone tails, so Godot cannot measure them); printed by
# blender/build_target.py (astolfo.secondary_motion_report).
const EXPECTED_END_BONE_LENGTHS: Dictionary[StringName, float] = {
	&"braid_06": 0.2043,
	&"hair_front_C_01": 0.0951, &"hair_front_L_01": 0.0773, &"hair_front_L_02": 0.113, &"hair_front_L_03": 0.1823,
	&"hair_front_R_01": 0.0831, &"hair_front_R_02": 0.1128, &"hair_front_R_03": 0.1461,
	&"hair_side_L_01": 0.0989, &"hair_side_L_02": 0.1265, &"hair_side_L_03": 0.1177, &"hair_side_L_04": 0.135,
	&"hair_side_R_01": 0.1157, &"hair_side_R_02": 0.1264, &"hair_side_R_03": 0.1206, &"hair_side_R_04": 0.1349,
	&"hair_back_C_01": 0.0997, &"hair_back_L_01": 0.1116, &"hair_back_L_02": 0.1612, &"hair_back_L_03": 0.1513,
	&"hair_back_L_04": 0.1032, &"hair_back_R_01": 0.1126, &"hair_back_R_02": 0.161, &"hair_back_R_03": 0.1502,
	&"hair_back_R_04": 0.1039,
	&"head_bow_L_01": 0.0937, &"head_bow_L_02": 0.0507, &"head_bow_L_03": 0.0916, &"head_bow_L_04": 0.0548,
	&"head_bow_R_01": 0.0939, &"head_bow_R_02": 0.0507, &"head_bow_R_03": 0.0917, &"head_bow_R_04": 0.0548,
	&"ribbon_L_02": 0.1173, &"ribbon_R_02": 0.135,
	&"skirt_00_03": 0.0875, &"skirt_01_03": 0.0884, &"skirt_02_03": 0.0877, &"skirt_03_03": 0.0877,
	&"skirt_04_03": 0.0874, &"skirt_05_03": 0.0876, &"skirt_06_03": 0.0878, &"skirt_07_03": 0.0884,
	&"braid_bow_01": 0.12, &"braid_bow_02": 0.1533, &"braid_bow_03": 0.12, &"braid_bow_04": 0.1533,
}
# Wanted radii are thigh 0.065, hips 0.12, chest 0.11 and head 0.085; each capsule is shrunk to clear every chain
# joint at rest (astolfo.fit_colliders).
const EXPECTED_COLLIDER_RADII: Dictionary[StringName, float] = {
	&"thigh.L": 0.0487,
	&"thigh.R": 0.0433,
	&"hips": 0.0695,
	&"chest": 0.0749,
	&"head": 0.085,
}
# The bone each capsule's body part runs to, so a capsule can be checked to sit on its own body part. The head has no
# bone above it; its part runs up the bone to the crown.
const COLLIDER_BONE_ENDS: Dictionary[StringName, StringName] = {
	&"thigh.L": &"shin.L", &"thigh.R": &"shin.R", &"hips": &"spine", &"chest": &"neck",
}
const COLLIDER_PART_LENGTHS: Dictionary[StringName, float] = {&"head": 0.165}
const HELPER_SUFFIX: String = "_helper"
const SKIRT_CHAIN_COUNT: int = 8
const SKIRT_CHAIN_BONES: int = 3
const LENGTH_TOLERANCE: float = 0.001


func _load_tuning() -> SecondaryMotionTuning:
	assert_true(ResourceLoader.exists(TUNING_PATH), "%s exists" % TUNING_PATH)
	if not ResourceLoader.exists(TUNING_PATH):
		return null
	var tuning: SecondaryMotionTuning = load(TUNING_PATH) as SecondaryMotionTuning
	assert_true(tuning != null, "secondary_motion.tres is a SecondaryMotionTuning")
	return tuning


func _load_target() -> Node:
	if not ResourceLoader.exists(TARGET_SCENE_PATH):
		return null
	return (load(TARGET_SCENE_PATH) as PackedScene).instantiate()


func _skeleton_of(root: Node) -> Skeleton3D:
	var skeletons: Array[Node] = root.find_children("*", "Skeleton3D", true, false)
	assert_true(not skeletons.is_empty(), "target.glb has a Skeleton3D")
	return null if skeletons.is_empty() else skeletons[0] as Skeleton3D


func test_secondary_motion_has_every_chain_family() -> void:
	var tuning: SecondaryMotionTuning = _load_tuning()
	if tuning == null:
		return
	assert_eq(tuning.chains.size(), EXPECTED_CHAINS.size(), "one entry per chain family")
	for prefix: StringName in EXPECTED_CHAINS:
		var setting: SecondaryChainSetting = tuning.chain(prefix)
		assert_true(setting != null, "chain %s exists" % prefix)
		if setting == null:
			continue
		var values: Array = EXPECTED_CHAINS[prefix]
		assert_near(setting.stiffness, values[0], 1e-6, "%s stiffness" % prefix)
		assert_near(setting.drag, values[1], 1e-6, "%s drag" % prefix)
		assert_near(setting.gravity, values[2], 1e-6, "%s gravity" % prefix)
		assert_near(setting.radius, values[3], 1e-6, "%s radius" % prefix)
		assert_near(setting.influence, values[4], 1e-6, "%s influence" % prefix)
		assert_eq(setting.animation_influence, EXPECTED_ANIMATION_INFLUENCE.get(prefix, {}), "%s animation influence" % prefix)
		assert_true(not setting.root_bones.is_empty(), "%s lists its chains" % prefix)
		assert_eq(setting.root_bones.size(), setting.end_bones.size(), "%s roots and ends pair up" % prefix)
		assert_eq(setting.end_bone_lengths.size(), setting.end_bones.size(), "%s has one end length per chain" % prefix)
		for chain_index: int in setting.end_bones.size():
			var end_name: StringName = StringName(setting.end_bones[chain_index])
			assert_true(EXPECTED_END_BONE_LENGTHS.has(end_name), "%s is a known leaf bone" % end_name)
			if EXPECTED_END_BONE_LENGTHS.has(end_name) and chain_index < setting.end_bone_lengths.size():
				assert_near(setting.end_bone_lengths[chain_index], EXPECTED_END_BONE_LENGTHS[end_name], LENGTH_TOLERANCE,
						"%s end bone length" % end_name)
		assert_true(setting.extend_end_bone, "%s extends its end bone" % prefix)
		assert_eq(setting.end_bone_direction, SkeletonModifier3D.BONE_DIRECTION_PLUS_Y, "%s bones point along +Y" % prefix)
		assert_eq(setting.colliders, EXPECTED_COLLIDERS[prefix], "%s collider membership" % prefix)
		assert_true(not setting.colliders.is_empty(), "%s lists at least one collider" % prefix)
		for bone_name: StringName in setting.colliders:
			assert_true(tuning.collider(bone_name) != null, "%s collides with a defined capsule %s" % [prefix, bone_name])
	var skirt: SecondaryChainSetting = tuning.chain(&"skirt")
	if skirt != null:
		assert_eq(skirt.root_bones.size(), SKIRT_CHAIN_COUNT, "eight skirt chains")


func test_braid_simulates_before_its_bow() -> void:
	var tuning: SecondaryMotionTuning = _load_tuning()
	if tuning == null:
		return
	var prefixes: Array[StringName] = []
	for setting: SecondaryChainSetting in tuning.chains:
		prefixes.append(setting.chain_prefix)
	# The bow hangs from the braid, so its setting must run after the braid has moved it.
	assert_true(prefixes.find(&"braid") >= 0 and prefixes.find(&"braid") < prefixes.find(&"braid_bow"),
			"braid comes before braid_bow")


func test_chain_bones_and_colliders_match_the_rig() -> void:
	var tuning: SecondaryMotionTuning = _load_tuning()
	if tuning == null:
		return
	var root: Node = _load_target()
	if root == null:
		return
	var skeleton: Skeleton3D = _skeleton_of(root)
	if skeleton == null:
		root.free()
		return
	for setting: SecondaryChainSetting in tuning.chains:
		for chain_index: int in setting.root_bones.size():
			var root_bone: int = skeleton.find_bone(setting.root_bones[chain_index])
			var end_bone: int = skeleton.find_bone(setting.end_bones[chain_index])
			assert_true(root_bone >= 0 and end_bone >= 0, "%s chain %d bones exist" % [setting.chain_prefix, chain_index])
			if root_bone < 0 or end_bone < 0:
				continue
			var walker: int = end_bone
			var depth: int = 1
			while walker >= 0 and walker != root_bone:
				assert_true(not skeleton.get_bone_name(walker).contains(HELPER_SUFFIX),
						"%s chain %d has no spring on a helper bone" % [setting.chain_prefix, chain_index])
				walker = skeleton.get_bone_parent(walker)
				depth += 1
			assert_eq(walker, root_bone, "%s end bone descends from its root" % setting.end_bones[chain_index])
			assert_true(not setting.root_bones[chain_index].contains(HELPER_SUFFIX),
					"%s chain %d does not start on a helper bone" % [setting.chain_prefix, chain_index])
			if setting.chain_prefix == &"skirt":
				assert_eq(depth, SKIRT_CHAIN_BONES, "skirt chain %d has three bones" % chain_index)
	assert_eq(tuning.colliders.size(), EXPECTED_COLLIDER_RADII.size(), "collider count")
	for bone_name: StringName in EXPECTED_COLLIDER_RADII:
		var entry: SecondaryCollider = tuning.collider(bone_name)
		assert_true(entry != null, "collider on %s" % bone_name)
		if entry == null:
			continue
		assert_near(entry.radius, EXPECTED_COLLIDER_RADII[bone_name], 1e-6, "%s collider radius" % bone_name)
		assert_true(entry.height >= 2.0 * entry.radius, "%s capsule height includes both caps" % bone_name)
		var bone: int = skeleton.find_bone(bone_name)
		assert_true(bone >= 0, "%s collider bone exists" % bone_name)
		if bone < 0:
			continue
		var bone_rest: Transform3D = skeleton.get_bone_global_rest(bone)
		var part_end: Vector3 = bone_rest * Vector3(0.0, COLLIDER_PART_LENGTHS.get(bone_name, 0.0), 0.0)
		if COLLIDER_BONE_ENDS.has(bone_name):
			var end_bone: int = skeleton.find_bone(COLLIDER_BONE_ENDS[bone_name])
			assert_true(end_bone >= 0, "%s collider part end exists" % bone_name)
			if end_bone < 0:
				continue
			part_end = skeleton.get_bone_global_rest(end_bone).origin
		# The capsule is fitted to the body, not centred on the bone, but it must sit on its own body part.
		var segment: PackedVector3Array = _capsule_segment(skeleton, entry)
		var center: Vector3 = (segment[0] + segment[1]) * 0.5
		var on_bone: Vector3 = Geometry3D.get_closest_point_to_segment(center, bone_rest.origin, part_end)
		assert_true(center.distance_to(on_bone) < entry.radius,
				"%s capsule centre %s lies within its radius of the bone" % [bone_name, center])
	root.free()


func test_every_joint_clears_its_colliders_at_rest() -> void:
	var tuning: SecondaryMotionTuning = _load_tuning()
	if tuning == null:
		return
	var root: Node = _load_target()
	if root == null:
		return
	var skeleton: Skeleton3D = _skeleton_of(root)
	if skeleton == null:
		root.free()
		return
	for setting: SecondaryChainSetting in tuning.chains:
		for chain_index: int in setting.root_bones.size():
			var joints: Dictionary[String, Vector3] = _non_root_joints(skeleton, setting, chain_index)
			for collider_bone: StringName in setting.colliders:
				var entry: SecondaryCollider = tuning.collider(collider_bone)
				if entry == null:
					continue
				var segment: PackedVector3Array = _capsule_segment(skeleton, entry)
				for joint_name: String in joints:
					var joint: Vector3 = joints[joint_name]
					var closest: Vector3 = Geometry3D.get_closest_point_to_segment(joint, segment[0], segment[1])
					var clearance: float = joint.distance_to(closest) - entry.radius - setting.radius
					assert_true(clearance >= 0.0, "%s clears the %s capsule at rest (%.4f m)" % [joint_name, collider_bone, clearance])
	root.free()


## Rest positions of every simulated joint after the fixed root: the heads of the chain's other bones and the
## extended tip.
func _non_root_joints(skeleton: Skeleton3D, setting: SecondaryChainSetting, chain_index: int) -> Dictionary[String, Vector3]:
	var joints: Dictionary[String, Vector3] = {}
	var root_bone: int = skeleton.find_bone(setting.root_bones[chain_index])
	var end_bone: int = skeleton.find_bone(setting.end_bones[chain_index])
	if root_bone < 0 or end_bone < 0:
		return joints
	var walker: int = end_bone
	while walker >= 0 and walker != root_bone:
		joints[skeleton.get_bone_name(walker)] = skeleton.get_bone_global_rest(walker).origin
		walker = skeleton.get_bone_parent(walker)
	if setting.extend_end_bone and chain_index < setting.end_bone_lengths.size():
		joints[setting.end_bones[chain_index] + " tip"] = (skeleton.get_bone_global_rest(end_bone)
				* Vector3(0.0, setting.end_bone_lengths[chain_index], 0.0))
	return joints


## The capsule's axis end points (cap centres) in skeleton rest space.
func _capsule_segment(skeleton: Skeleton3D, entry: SecondaryCollider) -> PackedVector3Array:
	var bone_rest: Transform3D = skeleton.get_bone_global_rest(skeleton.find_bone(entry.bone))
	var capsule: Transform3D = bone_rest * Transform3D(Basis(entry.rotation_offset), entry.position_offset)
	var half: float = maxf(0.0, entry.height * 0.5 - entry.radius)
	return PackedVector3Array([capsule * Vector3(0.0, -half, 0.0), capsule * Vector3(0.0, half, 0.0)])
