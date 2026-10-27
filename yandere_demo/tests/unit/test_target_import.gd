extends TestCase

const TARGET_SCENE_PATH: String = "res://assets/models/target.glb"
const REQUIRED_BONES: Array[String] = ["head", "hand.R", "index_03.L", "braid_01", "skirt_07_03"]
# The model's own bones kept under project names: deformation helpers (no springs), the neckerchief ribbons, the
# head bows and the braid bow.
const MODEL_BONES: Array[String] = [
	"chest_helper.L", "glute_helper.R", "wrist_helper.L", "ribbon_L_02", "head_bow_R_01", "braid_bow_01",
]
# Every expression ExpressionController drives, baked from the model's flexes onto the face mesh.
const REQUIRED_BLEND_SHAPES: Array[String] = [
	"neutral", "startled", "suspicious", "happy", "blink", "smile", "sad", "blush", "wink_L", "wink_R",
	"mouth_A", "mouth_I", "mouth_U", "mouth_E", "mouth_O", "pupil_small", "pupil_large",
]
const FACE_MESH: String = "TargetFace"
const REQUIRED_MESHES: Array[String] = [
	"TargetBody", "TargetFace", "TargetHair", "TargetTop", "TargetSkirt", "TargetSocks", "TargetShoes",
]
const SHADOWLESS_MESHES: Array[String] = ["TargetHair"]
const PROXY_MATERIAL_NAME: String = "M_CollisionProxy"
const ANIMATION_FPS: float = 30.0
# Clip name -> frame count at 30 fps.
const REQUIRED_ANIMATIONS: Dictionary[StringName, int] = {
	&"target_idle": 90,
	&"target_walk_routine": 32,
	&"target_notice_player": 30,
	&"target_startled": 20,
	&"target_look_around": 120,
	&"target_sit_down": 30,
	&"target_stand_up": 30,
	&"target_sit": 90,
	&"target_sit_read": 120,
	&"target_phone": 120,
	&"target_drink": 120,
	&"target_fix_braid": 150,
	&"target_lean_chat": 120,
	&"target_sweep": 60,
	&"target_wave": 45,
	&"target_idle_shy": 120,
	&"target_idle_playful": 90,
	&"target_idle_confident": 120,
}
const LOOPING_ANIMATIONS: Array[StringName] = [
	&"target_idle", &"target_walk_routine", &"target_sit",
	&"target_idle_shy", &"target_idle_playful", &"target_idle_confident",
]
# Mirrors character_post_import.gd: these play once, every other clip loops linearly.
const ONE_SHOT_ANIMATIONS: Array[StringName] = [
	&"target_notice_player", &"target_startled", &"target_sit_down", &"target_stand_up",
]


func test_target_glb_structure() -> void:
	assert_true(ResourceLoader.exists(TARGET_SCENE_PATH), "target.glb is imported")
	if not ResourceLoader.exists(TARGET_SCENE_PATH):
		return
	var packed: PackedScene = load(TARGET_SCENE_PATH) as PackedScene
	assert_true(packed != null, "target.glb loads as a PackedScene")
	if packed == null:
		return
	var root: Node = packed.instantiate()

	var skeletons: Array[Node] = root.find_children("*", "Skeleton3D", true, false)
	assert_eq(skeletons.size(), 1, "one Skeleton3D")
	if not skeletons.is_empty():
		var skeleton: Skeleton3D = skeletons[0] as Skeleton3D
		assert_eq(String(skeleton.get_parent().name), "TargetChar", "the skeleton sits under the TargetChar armature root")
		for bone_name: String in REQUIRED_BONES + MODEL_BONES:
			assert_true(skeleton.find_bone(bone_name) >= 0, "bone %s exists" % bone_name)

	for mesh_name: String in REQUIRED_MESHES:
		assert_true(root.find_child(mesh_name, true, false) is MeshInstance3D, "mesh %s exists" % mesh_name)
	var mesh_names: Array[String] = []
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		mesh_names.append(String(node.name))
	mesh_names.sort()
	var expected_meshes: Array[String] = REQUIRED_MESHES.duplicate()
	expected_meshes.sort()
	assert_eq(mesh_names, expected_meshes, "the meshes are the model's own split")

	var face: MeshInstance3D = root.find_child(FACE_MESH, true, false) as MeshInstance3D
	if face != null:
		var blend_shape_names: Array[String] = _blend_shape_names(face)
		for blend_shape_name: String in REQUIRED_BLEND_SHAPES:
			assert_true(blend_shape_names.has(blend_shape_name), "%s has blend shape %s" % [FACE_MESH, blend_shape_name])

	assert_true(root.has_meta("body_shape"), "root has body_shape meta")
	if root.has_meta("body_shape"):
		assert_true(root.get_meta("body_shape") is ConvexPolygonShape3D, "body_shape is convex")
	assert_true(root.find_child("Target-col", true, false) == null, "no node named Target-col")
	assert_eq(root.find_children("*", "StaticBody3D", true, false).size(), 0, "no StaticBody3D left")

	for mesh_name: String in SHADOWLESS_MESHES:
		var shadowless: MeshInstance3D = root.find_child(mesh_name, true, false) as MeshInstance3D
		if shadowless != null:
			assert_eq(shadowless.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_OFF, "%s casts no shadow" % mesh_name)

	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var instance: MeshInstance3D = node as MeshInstance3D
		for surface_index: int in instance.mesh.get_surface_count():
			var material: Material = instance.get_active_material(surface_index)
			assert_true(material is ShaderMaterial, "%s surface %d is a ShaderMaterial" % [instance.name, surface_index])
			if material != null:
				assert_true(material.resource_name != PROXY_MATERIAL_NAME, "%s is not the collision proxy" % instance.name)

	_assert_animations(root)
	root.free()


func _blend_shape_names(instance: MeshInstance3D) -> Array[String]:
	var names: Array[String] = []
	for blend_shape_index: int in instance.mesh.get_blend_shape_count():
		names.append(String(instance.mesh.get_blend_shape_name(blend_shape_index)))
	return names


func _assert_animations(root: Node) -> void:
	var players: Array[Node] = root.find_children("*", "AnimationPlayer", true, false)
	assert_eq(players.size(), 1, "one AnimationPlayer")
	if players.is_empty():
		return
	var player: AnimationPlayer = players[0] as AnimationPlayer
	for animation_name: StringName in REQUIRED_ANIMATIONS:
		assert_true(player.has_animation(animation_name), "animation %s exists" % animation_name)
		if not player.has_animation(animation_name):
			continue
		var expected_length: float = REQUIRED_ANIMATIONS[animation_name] / ANIMATION_FPS
		assert_near(player.get_animation(animation_name).length, expected_length, 0.5 / ANIMATION_FPS, "%s length" % animation_name)
	for animation_name: StringName in LOOPING_ANIMATIONS:
		if player.has_animation(animation_name):
			assert_eq(player.get_animation(animation_name).loop_mode, Animation.LOOP_LINEAR, "%s loops" % animation_name)
	for animation_name: StringName in player.get_animation_list():
		var expected_loop: Animation.LoopMode = Animation.LOOP_NONE if ONE_SHOT_ANIMATIONS.has(animation_name) else Animation.LOOP_LINEAR
		assert_eq(player.get_animation(animation_name).loop_mode, expected_loop, "%s loop mode" % animation_name)
