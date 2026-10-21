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
