extends TestCase

const TUNING_PATH: String = "res://data/secondary_motion.tres"
const TARGET_SCENE_PATH: String = "res://assets/models/target.glb"
# Chain prefix -> [stiffness, drag, gravity, radius] (task 9b defaults). Skirt gravity is 0.1, not the plan's
# 0.7: with 0.7 the flared skirt sagged onto the slim legs in the spring-bone check (see the task 9b report).
const EXPECTED_CHAINS: Dictionary[StringName, Array] = {
	&"braid": [0.45, 0.5, 1.0, 0.03],
	&"ahoge": [2.0, 0.15, 0.1, 0.01],
	&"hair_front": [1.6, 0.35, 0.3, 0.015],
	&"hair_side": [1.2, 0.4, 0.5, 0.02],
	&"neckerchief": [1.0, 0.45, 0.6, 0.015],
	&"sleeve": [2.5, 0.6, 0.2, 0.03],
	&"skirt": [1.1, 0.55, 0.1, 0.025],
	&"braid_bow": [1.5, 0.4, 0.6, 0.02],
}
const EXPECTED_COLLIDER_RADII: Dictionary[StringName, float] = {
	&"thigh.L": 0.065,
	&"thigh.R": 0.065,
	&"hips": 0.12,
	&"chest": 0.11,
}
const POSITION_TOLERANCE: float = 0.005


func _load_tuning() -> SecondaryMotionTuning:
	assert_true(ResourceLoader.exists(TUNING_PATH), "%s exists" % TUNING_PATH)
	if not ResourceLoader.exists(TUNING_PATH):
		return null
	var tuning: SecondaryMotionTuning = load(TUNING_PATH) as SecondaryMotionTuning
	assert_true(tuning != null, "secondary_motion.tres is a SecondaryMotionTuning")
	return tuning


func test_secondary_motion_has_eight_chain_entries() -> void:
	var tuning: SecondaryMotionTuning = _load_tuning()
	if tuning == null:
		return
	assert_eq(tuning.chains.size(), 8, "eight chain entries")
	assert_eq(tuning.center_bone, &"root", "chains simulate in the character's own space")
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
		assert_true(not setting.root_bones.is_empty(), "%s lists its chains" % prefix)
		assert_eq(setting.root_bones.size(), setting.end_bones.size(), "%s roots and ends pair up" % prefix)
		assert_true(setting.end_bone_length > 0.0, "%s end bone length" % prefix)
	var skirt: SecondaryChainSetting = tuning.chain(&"skirt")
	if skirt != null:
		assert_eq(skirt.root_bones.size(), 8, "eight skirt chains")


func test_chain_bones_and_colliders_match_the_rig() -> void:
	var tuning: SecondaryMotionTuning = _load_tuning()
	if tuning == null or not ResourceLoader.exists(TARGET_SCENE_PATH):
		return
	var root: Node = (load(TARGET_SCENE_PATH) as PackedScene).instantiate()
	var skeleton: Skeleton3D = root.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	for setting: SecondaryChainSetting in tuning.chains:
		for chain_index: int in setting.root_bones.size():
			var root_bone: int = skeleton.find_bone(setting.root_bones[chain_index])
			var end_bone: int = skeleton.find_bone(setting.end_bones[chain_index])
			assert_true(root_bone >= 0 and end_bone >= 0, "%s chain %d bones exist" % [setting.chain_prefix, chain_index])
			if root_bone < 0 or end_bone < 0:
				continue
			var walker: int = end_bone
			while walker >= 0 and walker != root_bone:
				walker = skeleton.get_bone_parent(walker)
			assert_eq(walker, root_bone, "%s end bone descends from its root" % setting.end_bones[chain_index])
	assert_eq(tuning.colliders.size(), EXPECTED_COLLIDER_RADII.size(), "collider count")
	for bone_name: StringName in EXPECTED_COLLIDER_RADII:
		var entry: SecondaryCollider = tuning.collider(bone_name)
		assert_true(entry != null, "collider on %s" % bone_name)
		if entry == null:
			continue
		assert_near(entry.radius, EXPECTED_COLLIDER_RADII[bone_name], 1e-6, "%s collider radius" % bone_name)
		var bone: int = skeleton.find_bone(bone_name)
		var child: int = _first_child(skeleton, bone)
		if bone < 0 or child < 0:
			continue
		# Each capsule spans its bone: centred on the bone midpoint, axis along the bone.
		var bone_rest: Transform3D = skeleton.get_bone_global_rest(bone)
		var child_rest: Transform3D = skeleton.get_bone_global_rest(child)
		var center: Vector3 = bone_rest * entry.position_offset
		var expected_center: Vector3 = (bone_rest.origin + child_rest.origin) * 0.5
		assert_true(center.distance_to(expected_center) < POSITION_TOLERANCE,
				"%s capsule centre %s is at the bone midpoint %s" % [bone_name, center, expected_center])
		var length: float = bone_rest.origin.distance_to(child_rest.origin)
		assert_near(entry.height, length + 2.0 * entry.radius, POSITION_TOLERANCE, "%s capsule spans the bone" % bone_name)
	root.free()


func _first_child(skeleton: Skeleton3D, bone: int) -> int:
	var preferred: Dictionary[String, String] = {"thigh.L": "shin.L", "thigh.R": "shin.R", "hips": "spine", "chest": "neck"}
	var bone_name: String = skeleton.get_bone_name(bone)
	if preferred.has(bone_name):
		return skeleton.find_bone(preferred[bone_name])
	return -1
