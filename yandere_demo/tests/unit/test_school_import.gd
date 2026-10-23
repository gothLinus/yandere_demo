extends TestCase

const SCHOOL_SCENE_PATH: String = "res://assets/models/school.glb"
const ACTIVITY_POOL_PATH: String = "res://data/activity_pool.tres"
const SECOND_FLOOR_HEIGHT: float = 3.6
const FIXED_ANCHORS: Array[String] = [
	"Anchor_attend_class_00", "Anchor_cleaning_duty_00", "Anchor_cleaning_duty_01", "Anchor_go_home_00",
	"Anchor_arrive_locker_00",
]
const SINGLE_MARKERS: Array[String] = [
	"PlayerSpawn", "TargetSpawn", "Gate", "PlayerSeat", "TargetSeat", "StashLocker", "TargetLocker",
	"ItemSpawn_target_locker_00", "ItemSpawn_target_locker_01",
	"EndingStand_Target", "EndingStand_Player",
	"EndingCamera_cherry_tree", "EndingCamera_friends", "EndingCamera_stranger", "EndingCamera_shrine",
]
# Prefix -> count, numbered from 01.
const NUMBERED_MARKERS: Dictionary[String, int] = {
	"StudentSeat_": 12,
	"HideLocker_": 6,
	"HideDesk_": 4,
	"TeacherPatrol_": 8,
	"StudentSpot_": 16,
	"Window_": 4,
}
const VOLUMES: Array[String] = ["Volume_Class1A", "Volume_Halls"]
# Blender `-col` objects import as a MeshInstance3D without the suffix, with a StaticBody3D child.
const COLLIDER_MESHES: Array[String] = [
	"Floor1", "Walls1", "Stairs", "Floor2", "Walls2", "Roof", "Courtyard", "Fountain", "Bench_01", "Locker",
	"Desks_1A", "Desks_2B", "Cafeteria", "Library", "ClubRoom",
]
const REQUIRED_MATERIALS: Array[String] = [
	"M_Wall", "M_Floor_Wood", "M_Floor_Tile", "M_Locker", "M_PropWood", "M_PropMetal", "M_Grass", "M_Path",
	"M_Foliage", "M_Glass", "M_Sky", "M_PropVending",
]
const MINIMUM_STATIC_BODIES: int = 10


func test_markers_and_colliders() -> void:
	var root: Node = _instantiate_school()
	if root == null:
		return
	for marker_name: String in _required_marker_names():
		var marker: Node = root.find_child(marker_name, true, false)
		assert_true(marker != null, "marker %s exists" % marker_name)
		if marker == null:
			continue
		assert_true(marker.get_class() == "Node3D", "%s is a plain Node3D, not %s" % [marker_name, marker.get_class()])
		var marker_scale: Vector3 = _global_transform(marker as Node3D).basis.get_scale()
		assert_true(marker_scale.is_equal_approx(Vector3.ONE), "%s has unit scale, got %s" % [marker_name, marker_scale])
		assert_true(absf(_global_transform(marker as Node3D).basis.y.y - 1.0) < 0.001 or marker_name.begins_with("EndingCamera_"),
			"%s stands upright" % marker_name)

	for volume_name: String in VOLUMES:
		var volume: Node3D = root.find_child(volume_name, true, false) as Node3D
		assert_true(volume != null, "volume %s exists" % volume_name)
		if volume != null:
			var half_extents: Vector3 = _global_transform(volume).basis.get_scale()
			assert_true(half_extents.x > 1.0 and half_extents.y > 1.0 and half_extents.z > 1.0,
				"%s scale holds its half extents, got %s" % [volume_name, half_extents])

	var shrine_wall: Node = root.find_child("ShrineWall", true, false)
	assert_true(shrine_wall is MeshInstance3D, "ShrineWall is a mesh plane")

	for mesh_name: String in COLLIDER_MESHES:
		var collider_mesh: Node = root.find_child(mesh_name, true, false)
		assert_true(collider_mesh is MeshInstance3D, "collider mesh %s exists" % mesh_name)
		if collider_mesh != null:
			assert_true(not collider_mesh.find_children("*", "StaticBody3D", false, false).is_empty(),
				"%s has a StaticBody3D" % mesh_name)
	var static_body_count: int = root.find_children("*", "StaticBody3D", true, false).size()
	assert_true(static_body_count >= MINIMUM_STATIC_BODIES, "at least %d static bodies, got %d" % [MINIMUM_STATIC_BODIES, static_body_count])

	var player_seat: Node3D = root.find_child("PlayerSeat", true, false) as Node3D
	var target_seat: Node3D = root.find_child("TargetSeat", true, false) as Node3D
	if player_seat != null and target_seat != null:
		assert_true(_global_transform(player_seat).origin.y < SECOND_FLOOR_HEIGHT, "PlayerSeat is downstairs")
		assert_true(_global_transform(target_seat).origin.y > 3.0, "TargetSeat is upstairs")
	_assert_same_transform(root, "Anchor_attend_class_00", "TargetSeat")
	_assert_same_transform(root, "Anchor_go_home_00", "Gate")
	root.free()


func test_materials_and_prop_outlines() -> void:
	var root: Node = _instantiate_school()
	if root == null:
		return
	var materials_by_name: Dictionary[String, ShaderMaterial] = {}
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var instance: MeshInstance3D = node as MeshInstance3D
		for surface_index: int in instance.mesh.get_surface_count():
			var material: ShaderMaterial = instance.get_active_material(surface_index) as ShaderMaterial
			assert_true(material != null, "%s surface %d is a toon ShaderMaterial" % [instance.name, surface_index])
			if material != null:
				materials_by_name[material.resource_name] = material
	for material_name: String in REQUIRED_MATERIALS:
		assert_true(materials_by_name.has(material_name), "material %s is used" % material_name)
	for material_name: String in materials_by_name:
		var has_outline: bool = materials_by_name[material_name].next_pass != null
		assert_eq(has_outline, material_name.begins_with("M_Prop"), "%s outline only on M_Prop*" % material_name)
	root.free()


func _instantiate_school() -> Node:
	assert_true(ResourceLoader.exists(SCHOOL_SCENE_PATH), "school.glb is imported")
	if not ResourceLoader.exists(SCHOOL_SCENE_PATH):
		return null
	var packed: PackedScene = load(SCHOOL_SCENE_PATH) as PackedScene
	assert_true(packed != null, "school.glb loads as a PackedScene")
	if packed == null:
		return null
	return packed.instantiate()


func _required_marker_names() -> Array[String]:
	var names: Array[String] = []
	names.append_array(SINGLE_MARKERS)
	names.append_array(FIXED_ANCHORS)
	var pool: ActivityPool = load(ACTIVITY_POOL_PATH) as ActivityPool
	for activity: ActivityDefinition in pool.activities:
		if activity.is_fixed:
			continue
		for index: int in 2:
			names.append("Anchor_%s_%02d" % [activity.id, index])
	for anchor_name: String in names.duplicate():
		if anchor_name.begins_with("Anchor_"):
			names.append(anchor_name.replace("Anchor_", "ItemSpawn_"))
	for prefix: String in NUMBERED_MARKERS:
		for number: int in range(1, NUMBERED_MARKERS[prefix] + 1):
			names.append("%s%02d" % [prefix, number])
	return names


func _assert_same_transform(root: Node, alias_name: String, original_name: String) -> void:
	var alias: Node3D = root.find_child(alias_name, true, false) as Node3D
	var original: Node3D = root.find_child(original_name, true, false) as Node3D
	if alias == null or original == null:
		return
	assert_true(_global_transform(alias).is_equal_approx(_global_transform(original)), "%s matches %s" % [alias_name, original_name])


# The instance is never added to the tree, so global_transform is not available.
func _global_transform(node: Node3D) -> Transform3D:
	var composed: Transform3D = node.transform
	var parent: Node = node.get_parent()
	while parent != null:
		if parent is Node3D:
			composed = (parent as Node3D).transform * composed
		parent = parent.get_parent()
	return composed
