extends TestCase

const TARGET_SCENE_PATH: String = "res://assets/models/target.glb"
const REQUIRED_BONES: Array[String] = ["head", "braid_06", "skirt_front_02"]
const REQUIRED_BLEND_SHAPES: Array[String] = ["neutral", "startled", "suspicious", "happy", "blink"]
const REQUIRED_MESHES: Array[String] = [
	"TargetBody", "TargetHead", "TargetFace", "TargetHair", "TargetBraid", "TargetBows", "TargetUniform",
]
const SHADOWLESS_MESHES: Array[String] = ["TargetHair", "TargetBows"]
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
}
const LOOPING_ANIMATIONS: Array[StringName] = [&"target_idle", &"target_walk_routine", &"target_sit"]
const ONE_SHOT_ANIMATIONS: Array[StringName] = [&"target_sit_down", &"target_startled"]


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
		for bone_name: String in REQUIRED_BONES:
			assert_true(skeleton.find_bone(bone_name) >= 0, "bone %s exists" % bone_name)

	for mesh_name: String in REQUIRED_MESHES:
		assert_true(root.find_child(mesh_name, true, false) is MeshInstance3D, "mesh %s exists" % mesh_name)

	var face: MeshInstance3D = root.find_child("TargetFace", true, false) as MeshInstance3D
	if face != null:
		var blend_shape_names: Array[String] = []
		for blend_shape_index: int in face.mesh.get_blend_shape_count():
			blend_shape_names.append(String(face.mesh.get_blend_shape_name(blend_shape_index)))
		for blend_shape_name: String in REQUIRED_BLEND_SHAPES:
			assert_true(blend_shape_names.has(blend_shape_name), "blend shape %s exists" % blend_shape_name)

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
			assert_true(player.get_animation(animation_name).loop_mode != Animation.LOOP_NONE, "%s loops" % animation_name)
	for animation_name: StringName in ONE_SHOT_ANIMATIONS:
		if player.has_animation(animation_name):
			assert_eq(player.get_animation(animation_name).loop_mode, Animation.LOOP_NONE, "%s plays once" % animation_name)
