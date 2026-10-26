class_name ToonConverter
extends RefCounted

const TOON_SHADER: Shader = preload("res://assets/shaders/toon.gdshader")
const OUTLINE_SHADER: Shader = preload("res://assets/shaders/outline.gdshader")
const BLUSH_SHADER: Shader = preload("res://assets/shaders/toon_blush.gdshader")
const GLASS_SHADER: Shader = preload("res://assets/shaders/toon_glass.gdshader")
const BLUSH_MATERIAL_NAME: String = "M_FaceBlush"
# Exact names: M_HairShade (the dark under-layer) and M_HairClip (metal) get no shine band.
const HAIR_BAND_MATERIALS: Array[String] = ["M_Hair", "M_HairStreak"]
const PROXY_MATERIAL_NAME: String = "M_CollisionProxy"
const CHARACTER_NO_OUTLINE_PREFIXES: Array[String] = ["M_Eye", "M_Face", "M_Mouth"]
const ENVIRONMENT_OUTLINE_PREFIXES: Array[String] = ["M_Prop"]


static func convert_character(scene: Node, outline_width: float = 0.004) -> void:
	_extract_body_shape(scene)
	_remove_proxy_meshes(scene)
	for instance: MeshInstance3D in _collect_mesh_instances(scene):
		_convert_instance(instance, outline_width, _character_wants_outline, false)


static func convert_environment(scene: Node, outline_width: float = 0.012) -> void:
	for instance: MeshInstance3D in _collect_mesh_instances(scene):
		_convert_instance(instance, outline_width, _environment_wants_outline, true)


static func _character_wants_outline(material_name: String) -> bool:
	return not _has_any_prefix(material_name, CHARACTER_NO_OUTLINE_PREFIXES)


static func _environment_wants_outline(material_name: String) -> bool:
	return _has_any_prefix(material_name, ENVIRONMENT_OUTLINE_PREFIXES)


static func _has_any_prefix(text: String, prefixes: Array[String]) -> bool:
	for prefix: String in prefixes:
		if text.begins_with(prefix):
			return true
	return false


static func _collect_mesh_instances(scene: Node) -> Array[MeshInstance3D]:
	var instances: Array[MeshInstance3D] = []
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		instances.append(node as MeshInstance3D)
	if scene is MeshInstance3D:
		instances.append(scene as MeshInstance3D)
	return instances


static func _convert_instance(instance: MeshInstance3D, outline_width: float, wants_outline: Callable, allows_glass: bool) -> void:
	var mesh: Mesh = instance.mesh
	if mesh == null:
		return
	for surface_index: int in mesh.get_surface_count():
		var override_material: Material = instance.get_surface_override_material(surface_index)
		var source: Material = override_material if override_material != null else mesh.surface_get_material(surface_index)
		var standard: BaseMaterial3D = source as BaseMaterial3D
		if standard == null:
			continue
		var is_glass: bool = allows_glass and _is_glass(standard)
		var converted: ShaderMaterial = _make_glass_material(standard) if is_glass else _make_toon_material(standard)
		if not is_glass and wants_outline.call(standard.resource_name):
			converted.next_pass = _make_outline_material(outline_width)
		mesh.surface_set_material(surface_index, converted)
		if override_material != null:
			instance.set_surface_override_material(surface_index, null)


static func _make_toon_material(source: BaseMaterial3D) -> ShaderMaterial:
	var material: ShaderMaterial = ShaderMaterial.new()
	material.resource_name = source.resource_name
	material.set_shader_parameter("albedo_color", source.albedo_color)
	if source.resource_name == BLUSH_MATERIAL_NAME:
		material.shader = BLUSH_SHADER
		return material
	material.shader = TOON_SHADER
	if source.albedo_texture != null:
		material.set_shader_parameter("albedo_texture", source.albedo_texture)
		material.set_shader_parameter("use_texture", true)
	if HAIR_BAND_MATERIALS.has(source.resource_name):
		material.set_shader_parameter("use_hair_band", true)
	if source.emission_enabled:
		material.set_shader_parameter("emission_color", source.emission)
		material.set_shader_parameter("emission_energy", source.emission_energy_multiplier)
	return material


# Untextured alpha-blended environment surfaces (window glass) stay translucent instead of being alpha-scissored.
static func _is_glass(source: BaseMaterial3D) -> bool:
	var is_blended: bool = source.transparency in [BaseMaterial3D.TRANSPARENCY_ALPHA, BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS]
	return is_blended and source.albedo_texture == null and source.albedo_color.a < 1.0


static func _make_glass_material(source: BaseMaterial3D) -> ShaderMaterial:
	var material: ShaderMaterial = ShaderMaterial.new()
	material.resource_name = source.resource_name
	material.shader = GLASS_SHADER
	material.set_shader_parameter("albedo_color", source.albedo_color)
	return material


static func _make_outline_material(outline_width: float) -> ShaderMaterial:
	var material: ShaderMaterial = ShaderMaterial.new()
	material.shader = OUTLINE_SHADER
	material.set_shader_parameter("outline_width", outline_width)
	return material


static func _extract_body_shape(scene: Node) -> void:
	for node: Node in scene.find_children("*", "StaticBody3D", true, false):
		var body: StaticBody3D = node as StaticBody3D
		if not scene.has_meta("body_shape"):
			var shape: ConvexPolygonShape3D = _find_convex_shape(body)
			if shape != null:
				scene.set_meta("body_shape", shape)
		body.get_parent().remove_child(body)
		body.free()


static func _find_convex_shape(body: StaticBody3D) -> ConvexPolygonShape3D:
	for node: Node in body.find_children("*", "CollisionShape3D", true, false):
		var shape: Shape3D = (node as CollisionShape3D).shape
		if shape is ConvexPolygonShape3D:
			return shape as ConvexPolygonShape3D
		if shape is ConcavePolygonShape3D:
			var convex: ConvexPolygonShape3D = ConvexPolygonShape3D.new()
			convex.points = (shape as ConcavePolygonShape3D).get_faces()
			return convex
	return null


static func _remove_proxy_meshes(scene: Node) -> void:
	for instance: MeshInstance3D in _collect_mesh_instances(scene):
		if instance == scene or not _uses_proxy_material(instance):
			continue
		instance.get_parent().remove_child(instance)
		instance.free()


static func _uses_proxy_material(instance: MeshInstance3D) -> bool:
	if instance.mesh == null:
		return false
	for surface_index: int in instance.mesh.get_surface_count():
		var override_material: Material = instance.get_surface_override_material(surface_index)
		var material: Material = override_material if override_material != null else instance.mesh.surface_get_material(surface_index)
		if material != null and material.resource_name == PROXY_MATERIAL_NAME:
			return true
	return false
