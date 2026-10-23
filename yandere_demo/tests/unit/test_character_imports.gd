extends TestCase

const ANIMATION_FPS: float = 30.0
const PROXY_MATERIAL_NAME: String = "M_CollisionProxy"
const UNIFORM_TINT_MATERIAL: String = "M_UniformTint"
# Mirrors character_post_import.gd: these play once, every other clip loops linearly.
const ONE_SHOT_ANIMATIONS: Array[StringName] = [&"player_hide", &"player_sit_down", &"player_stand_up"]
const STUDENT_ANIMATIONS: Dictionary[StringName, int] = {
	&"student_idle": 90,
	&"student_walk": 32,
	&"student_sit": 90,
	&"student_chat": 120,
}
# Per imported file: the armature node under the scene root, clip name -> frame count, bones, meshes that must
# exist, swappable hair meshes (exactly one visible after import) and meshes that use the tintable uniform.
const CHARACTERS: Dictionary[String, Dictionary] = {
	"res://assets/models/player.glb": {
		"armature": "PlayerChar",
		"animations": {
			&"player_idle": 90,
			&"player_walk": 24,
			&"player_run": 20,
			&"player_crouch_idle": 90,
			&"player_sneak": 32,
			&"player_take_photo": 90,
			&"player_hide": 20,
			&"player_sit": 90,
			&"player_sit_down": 30,
			&"player_stand_up": 30,
		},
		"bones": ["head", "index_03.L", "ponytail_01", "ponytail_04", "skirt_07_03"],
		"meshes": ["PlayerBody", "PlayerFace", "PlayerHair", "PlayerPonytail", "PlayerTop", "PlayerSkirt"],
		"hair_variants": [],
		"tinted_meshes": [],
	},
	"res://assets/models/student_female.glb": {
		"armature": "StudentFemaleChar",
		"animations": STUDENT_ANIMATIONS,
		"bones": ["head", "index_03.L", "skirt_07_03"],
		"meshes": ["StudentFemaleBody", "StudentFemaleFace", "StudentFemaleTop", "StudentFemaleSkirt"],
		"hair_variants": ["Hair_bob", "Hair_long", "Hair_twintails"],
		"tinted_meshes": ["StudentFemaleTop", "StudentFemaleSkirt"],
	},
	"res://assets/models/student_male.glb": {
		"armature": "StudentMaleChar",
		"animations": STUDENT_ANIMATIONS,
		"bones": ["head", "index_03.L"],
		"meshes": ["StudentMaleBody", "StudentMaleFace", "StudentMaleJacket", "StudentMaleTrousers"],
		"hair_variants": ["Hair_short", "Hair_messy"],
		"tinted_meshes": ["StudentMaleJacket", "StudentMaleTrousers"],
	},
	"res://assets/models/teacher.glb": {
		"armature": "TeacherChar",
		"animations": {&"teacher_idle": 90, &"teacher_walk": 32, &"teacher_look_around": 120},
		"bones": ["head", "index_03.L"],
		"meshes": ["TeacherBody", "TeacherFace", "TeacherHair", "TeacherJacket", "TeacherShirt", "TeacherTrousers"],
		"hair_variants": [],
		"tinted_meshes": [],
	},
}
const REQUIRED_BLEND_SHAPES: Array[String] = ["neutral", "blink"]


func test_character_glbs_import_with_rig_clips_and_body_shape() -> void:
	for scene_path: String in CHARACTERS:
		var root: Node = _instantiate(scene_path)
		if root == null:
			continue
		var expected: Dictionary = CHARACTERS[scene_path]
		var armature_name: String = expected["armature"]
		assert_true(root.get_node_or_null(armature_name) != null, "%s: armature %s under the root" % [scene_path, armature_name])
		_assert_skeleton(scene_path, root, expected["bones"])
		_assert_animations(scene_path, root, expected["animations"])
		assert_true(root.has_meta("body_shape"), "%s: root has body_shape meta" % scene_path)
		if root.has_meta("body_shape"):
			assert_true(root.get_meta("body_shape") is ConvexPolygonShape3D, "%s: body_shape is convex" % scene_path)
		assert_eq(root.find_children("*", "StaticBody3D", true, false).size(), 0, "%s: no StaticBody3D left" % scene_path)
		for mesh_name: String in expected["meshes"]:
			assert_true(root.find_child(mesh_name, true, false) is MeshInstance3D, "%s: mesh %s exists" % [scene_path, mesh_name])
		var face: MeshInstance3D = root.find_child(armature_name.trim_suffix("Char") + "Face", true, false) as MeshInstance3D
		assert_true(face != null, "%s: face mesh exists" % scene_path)
		if face != null:
			for blend_shape_name: String in REQUIRED_BLEND_SHAPES:
				assert_true(face.find_blend_shape_by_name(blend_shape_name) >= 0, "%s: blend shape %s" % [scene_path, blend_shape_name])
		_assert_materials(scene_path, root)
		root.free()


func test_student_hair_variants_are_separate_meshes_with_one_shown() -> void:
	for scene_path: String in CHARACTERS:
		var variants: Array = CHARACTERS[scene_path]["hair_variants"]
		if variants.is_empty():
			continue
		var root: Node = _instantiate(scene_path)
		if root == null:
			continue
		var visible_count: int = 0
		for variant_name: String in variants:
			var hair: MeshInstance3D = root.find_child(variant_name, true, false) as MeshInstance3D
			assert_true(hair != null, "%s: hair mesh %s exists" % [scene_path, variant_name])
			if hair == null:
				continue
			assert_eq(hair.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_OFF, "%s casts no shadow" % variant_name)
			if hair.visible:
				visible_count += 1
		assert_eq(visible_count, 1, "%s: exactly one hair variant is visible after import" % scene_path)
		root.free()


func test_student_uniforms_use_the_tintable_material() -> void:
	for scene_path: String in CHARACTERS:
		var tinted: Array = CHARACTERS[scene_path]["tinted_meshes"]
		if tinted.is_empty():
			continue
		var root: Node = _instantiate(scene_path)
		if root == null:
			continue
		for mesh_name: String in tinted:
			var instance: MeshInstance3D = root.find_child(mesh_name, true, false) as MeshInstance3D
			assert_true(instance != null and _material_names(instance).has(UNIFORM_TINT_MATERIAL),
				"%s: %s uses %s" % [scene_path, mesh_name, UNIFORM_TINT_MATERIAL])
		root.free()


func _instantiate(scene_path: String) -> Node:
	assert_true(ResourceLoader.exists(scene_path), "%s is imported" % scene_path)
	if not ResourceLoader.exists(scene_path):
		return null
	var packed: PackedScene = load(scene_path) as PackedScene
	assert_true(packed != null, "%s loads as a PackedScene" % scene_path)
	return packed.instantiate() if packed != null else null


func _assert_skeleton(scene_path: String, root: Node, bones: Array) -> void:
	var skeletons: Array[Node] = root.find_children("*", "Skeleton3D", true, false)
	assert_eq(skeletons.size(), 1, "%s: one Skeleton3D" % scene_path)
	if skeletons.is_empty():
		return
	var skeleton: Skeleton3D = skeletons[0] as Skeleton3D
	for bone_name: String in bones:
		assert_true(skeleton.find_bone(bone_name) >= 0, "%s: bone %s exists" % [scene_path, bone_name])


func _assert_animations(scene_path: String, root: Node, animations: Dictionary) -> void:
	var players: Array[Node] = root.find_children("*", "AnimationPlayer", true, false)
	assert_eq(players.size(), 1, "%s: one AnimationPlayer" % scene_path)
	if players.is_empty():
		return
	var player: AnimationPlayer = players[0] as AnimationPlayer
	for animation_name: StringName in animations:
		assert_true(player.has_animation(animation_name), "%s: animation %s exists" % [scene_path, animation_name])
		if not player.has_animation(animation_name):
			continue
		var animation: Animation = player.get_animation(animation_name)
		var frame_count: int = animations[animation_name]
		assert_near(animation.length, frame_count / ANIMATION_FPS, 0.5 / ANIMATION_FPS, "%s length" % animation_name)
		var expected_loop: Animation.LoopMode = Animation.LOOP_NONE if ONE_SHOT_ANIMATIONS.has(animation_name) else Animation.LOOP_LINEAR
		assert_eq(animation.loop_mode, expected_loop, "%s loop mode" % animation_name)


func _assert_materials(scene_path: String, root: Node) -> void:
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var instance: MeshInstance3D = node as MeshInstance3D
		for surface_index: int in instance.mesh.get_surface_count():
			var material: Material = instance.get_active_material(surface_index)
			assert_true(material is ShaderMaterial, "%s: %s surface %d is a ShaderMaterial" % [scene_path, instance.name, surface_index])
			if material != null:
				assert_true(material.resource_name != PROXY_MATERIAL_NAME, "%s: %s is not the collision proxy" % [scene_path, instance.name])


func _material_names(instance: MeshInstance3D) -> Array[String]:
	var names: Array[String] = []
	for surface_index: int in instance.mesh.get_surface_count():
		var material: Material = instance.get_active_material(surface_index)
		if material != null:
			names.append(material.resource_name)
	return names
