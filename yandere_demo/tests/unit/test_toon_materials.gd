extends TestCase


func make_material(material_name: String, color: Color) -> StandardMaterial3D:
	var material: StandardMaterial3D = StandardMaterial3D.new()
	material.resource_name = material_name
	material.albedo_color = color
	return material


func make_mesh_instance(node_name: String, material: Material) -> MeshInstance3D:
	var instance: MeshInstance3D = MeshInstance3D.new()
	instance.name = node_name
	instance.mesh = BoxMesh.new()
	instance.mesh.surface_set_material(0, material)
	return instance


func test_convert_replaces_material_and_extracts_shape() -> void:
	var root: Node3D = Node3D.new()
	var skin_color: Color = Color(1, 0.9, 0.85)
	var skin: MeshInstance3D = make_mesh_instance("Body", make_material("M_Skin", skin_color))
	root.add_child(skin)

	var proxy: MeshInstance3D = make_mesh_instance("Target", make_material("M_CollisionProxy", Color.WHITE))
	root.add_child(proxy)
	var body: StaticBody3D = StaticBody3D.new()
	proxy.add_child(body)
	var collision: CollisionShape3D = CollisionShape3D.new()
	var concave: ConcavePolygonShape3D = ConcavePolygonShape3D.new()
	concave.set_faces(BoxMesh.new().get_faces())
	collision.shape = concave
	body.add_child(collision)

	ToonConverter.convert_character(root, 0.004)

	var converted: ShaderMaterial = skin.mesh.surface_get_material(0) as ShaderMaterial
	assert_true(converted != null, "skin surface is a ShaderMaterial")
	assert_eq(converted.get_shader_parameter("albedo_color"), skin_color)
	assert_true(converted.next_pass != null, "outline pass set")
	assert_true(root.has_meta("body_shape"), "body_shape meta stored")
	assert_true(root.get_meta("body_shape") is ConvexPolygonShape3D, "body_shape is convex")
	assert_eq(root.find_children("*", "StaticBody3D", true, false).size(), 0)
	assert_true(not is_instance_valid(proxy) or proxy.is_queued_for_deletion() or proxy.get_parent() == null, "proxy removed")
	assert_eq(root.get_child_count(), 1)
	root.free()


func test_face_materials_get_no_outline() -> void:
	var root: Node3D = Node3D.new()
	var eye: MeshInstance3D = make_mesh_instance("Eye", make_material("M_Eye", Color.BLUE))
	root.add_child(eye)
	ToonConverter.convert_character(root, 0.004)
	var converted: ShaderMaterial = eye.mesh.surface_get_material(0) as ShaderMaterial
	assert_true(converted != null)
	assert_true(converted.next_pass == null, "no outline on eye")
	root.free()


func test_environment_outlines_only_props_and_keeps_bodies() -> void:
	var root: Node3D = Node3D.new()
	var wall: MeshInstance3D = make_mesh_instance("Wall", make_material("M_Wall", Color.WHITE))
	var prop: MeshInstance3D = make_mesh_instance("Desk", make_material("M_PropDesk", Color.WHITE))
	root.add_child(wall)
	root.add_child(prop)
	var body: StaticBody3D = StaticBody3D.new()
	root.add_child(body)
	ToonConverter.convert_environment(root, 0.012)
	assert_true((wall.mesh.surface_get_material(0) as ShaderMaterial).next_pass == null)
	assert_true((prop.mesh.surface_get_material(0) as ShaderMaterial).next_pass != null)
	assert_true(body.get_parent() == root, "static body kept")
	assert_true(not root.has_meta("body_shape"))
	root.free()


func test_hair_materials_get_the_highlight_band() -> void:
	var root: Node3D = Node3D.new()
	var hair: MeshInstance3D = make_mesh_instance("Hair", make_material("M_Hair", Color.PINK))
	var shade: MeshInstance3D = make_mesh_instance("Shade", make_material("M_HairShade", Color.PINK))
	var clip: MeshInstance3D = make_mesh_instance("Clip", make_material("M_HairClip", Color.GOLD))
	root.add_child(hair)
	root.add_child(shade)
	root.add_child(clip)
	ToonConverter.convert_character(root, 0.004)
	assert_eq((hair.mesh.surface_get_material(0) as ShaderMaterial).get_shader_parameter("use_hair_band"), true, "M_Hair has the band")
	assert_true((shade.mesh.surface_get_material(0) as ShaderMaterial).get_shader_parameter("use_hair_band") != true, "M_HairShade has no band")
	assert_true((clip.mesh.surface_get_material(0) as ShaderMaterial).get_shader_parameter("use_hair_band") != true, "M_HairClip is not hair")
	root.free()


func test_blush_uses_the_alpha_blended_toon_shader_without_outline() -> void:
	var root: Node3D = Node3D.new()
	var blush_color: Color = Color(0.95, 0.5, 0.58, 0.6)
	var blush: MeshInstance3D = make_mesh_instance("Blush", make_material("M_FaceBlush", blush_color))
	root.add_child(blush)
	ToonConverter.convert_character(root, 0.004)
	var converted: ShaderMaterial = blush.mesh.surface_get_material(0) as ShaderMaterial
	assert_true(converted != null, "blush is a ShaderMaterial")
	assert_eq(converted.shader, ToonConverter.BLUSH_SHADER, "blush uses the blush shader")
	assert_eq(converted.get_shader_parameter("albedo_color"), blush_color, "blush keeps its colour and alpha")
	assert_true(converted.next_pass == null, "no outline on the blush")
	root.free()
