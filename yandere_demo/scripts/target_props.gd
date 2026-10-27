class_name TargetProps
extends Node
## Hand props (ruling R9): simple toon meshes on the hands, each visible only while the clip that holds it plays.
## Placements are in the hand bone's space: the open book lies against both palms, the phone in the right palm, the
## can in a wrapped grip, and the broom shaft runs through both fists to the floor.

const BOOK: StringName = &"book"
const PHONE: StringName = &"phone"
const CAN: StringName = &"can"
const BROOM: StringName = &"broom"
const PROP_FOR_ANIMATION: Dictionary[StringName, StringName] = {
	&"target_sit_read": BOOK,
	&"target_phone": PHONE,
	&"check_phone": PHONE,
	&"target_drink": CAN,
	&"target_sweep": BROOM,
}
const PROP_BONES: Dictionary[StringName, StringName] = {
	BOOK: &"hand.R", PHONE: &"hand.R", CAN: &"hand.R", BROOM: &"hand.L",
}
## Printed by blender/build_target.py from the grips in lib/target_animations.py (a hand bone's frame is the same in
## Blender and Godot); each clip poses the hands from the prop, so the prop lies in the palm with the fingers round it.
const PROP_PLACEMENTS: Dictionary[StringName, Transform3D] = {
	BOOK: Transform3D(Basis(Vector3(-0.5786, 0.3900, -0.7163), Vector3(0.1741, 0.9171, 0.3587), Vector3(0.7968, 0.0829, -0.5985)),
			Vector3(0.0697, 0.0414, 0.0909)),
	PHONE: Transform3D(Basis(Vector3(-0.4163, -0.3011, -0.8579), Vector3(-0.1315, 0.9536, -0.2709), Vector3(0.8997, 0.0000, -0.4365)),
			Vector3(0.0178, 0.0580, -0.0126)),
	CAN: Transform3D(Basis(Vector3(0.0000, -1.0000, 0.0000), Vector3(-0.4365, 0.0000, -0.8997), Vector3(0.8997, 0.0000, -0.4365)),
			Vector3(0.0447, 0.0586, -0.0172)),
	BROOM: Transform3D(Basis(Vector3(0.0000, 1.0000, 0.0000), Vector3(0.4365, 0.0000, -0.8997), Vector3(-0.8997, 0.0000, -0.4365)),
			Vector3(0.0394, 0.0466, -0.1476)),
}
## The open book: two leaves, each turned BOOK_OPEN_DEGREES toward the reader (+Z) about the spine (Y).
const BOOK_LEAF_SIZE: Vector3 = Vector3(0.14, 0.2, 0.012)
const BOOK_OPEN_DEGREES: float = 12.0
const BOOK_COVER_DEPTH: float = 0.004
const BOOK_COLOR: Color = Color(0.22, 0.32, 0.62)
const PAGES_COLOR: Color = Color(0.95, 0.93, 0.86)
const PHONE_SIZE: Vector3 = Vector3(0.07, 0.14, 0.009)
const PHONE_COLOR: Color = Color(0.96, 0.72, 0.82)
const SCREEN_COLOR: Color = Color(0.1, 0.1, 0.14)
const CAN_RADIUS: float = 0.033
const CAN_HEIGHT: float = 0.12
const CAN_COLOR: Color = Color(1.0, 0.7, 0.78)
const BROOM_HANDLE_RADIUS: float = 0.012
const BROOM_HANDLE_LENGTH: float = 1.25
const BROOM_HEAD_SIZE: Vector3 = Vector3(0.28, 0.12, 0.05)
const BROOM_HANDLE_COLOR: Color = Color(0.55, 0.38, 0.22)
const BROOM_HEAD_COLOR: Color = Color(0.82, 0.68, 0.36)
const PAGE_INSET: float = 0.006
const SCREEN_INSET: float = 0.006

@export var skeleton_path: NodePath

var _props: Dictionary[StringName, Node3D] = {}


func _ready() -> void:
	var skeleton: Skeleton3D = get_node_or_null(skeleton_path) as Skeleton3D
	if skeleton == null:
		push_error("TargetProps: no Skeleton3D at %s" % skeleton_path)
		return
	for prop_name: StringName in PROP_BONES:
		var attachment: BoneAttachment3D = BoneAttachment3D.new()
		attachment.name = "%sAttachment" % String(prop_name).capitalize()
		attachment.bone_name = PROP_BONES[prop_name]
		skeleton.add_child(attachment)
		var prop: Node3D = build_prop(prop_name)
		prop.visible = false
		attachment.add_child(prop)
		_props[prop_name] = prop


## The prop's meshes, placed in its hand bone's space.
static func build_prop(prop_name: StringName) -> Node3D:
	var prop: Node3D
	match prop_name:
		BOOK:
			prop = _make_book()
		PHONE:
			prop = _make_phone()
		CAN:
			prop = _make_can()
		_:
			prop = _make_broom()
	prop.name = String(prop_name).capitalize()
	prop.transform = PROP_PLACEMENTS[prop_name]
	return prop


func show_for(animation_name: StringName) -> void:
	var wanted: StringName = PROP_FOR_ANIMATION.get(animation_name, &"")
	for prop_name: StringName in _props:
		_props[prop_name].visible = prop_name == wanted


static func _make_book() -> Node3D:
	var book: Node3D = Node3D.new()
	for side: float in [1.0, -1.0]:
		var leaf: Node3D = Node3D.new()
		leaf.basis = Basis(Vector3.UP, deg_to_rad(-side * BOOK_OPEN_DEGREES))
		leaf.position = leaf.basis.x * side * BOOK_LEAF_SIZE.x * 0.5
		var cover: Vector3 = Vector3(BOOK_LEAF_SIZE.x, BOOK_LEAF_SIZE.y, BOOK_COVER_DEPTH)
		leaf.add_child(_box(cover, BOOK_COLOR, Vector3(0.0, 0.0, (BOOK_COVER_DEPTH - BOOK_LEAF_SIZE.z) * 0.5)))
		var pages: Vector3 = Vector3(BOOK_LEAF_SIZE.x - PAGE_INSET, BOOK_LEAF_SIZE.y - PAGE_INSET,
				BOOK_LEAF_SIZE.z - BOOK_COVER_DEPTH)
		leaf.add_child(_box(pages, PAGES_COLOR, Vector3(side * -PAGE_INSET * 0.5, 0.0, BOOK_COVER_DEPTH * 0.5)))
		book.add_child(leaf)
	return book


static func _make_phone() -> Node3D:
	var phone: Node3D = Node3D.new()
	phone.add_child(_box(PHONE_SIZE, PHONE_COLOR, Vector3.ZERO))
	var screen: Vector3 = Vector3(PHONE_SIZE.x - SCREEN_INSET, PHONE_SIZE.y - SCREEN_INSET, PHONE_SIZE.z * 0.2)
	phone.add_child(_box(screen, SCREEN_COLOR, Vector3(0.0, 0.0, PHONE_SIZE.z * 0.5)))
	return phone


static func _make_can() -> Node3D:
	var can: Node3D = Node3D.new()
	var mesh: CylinderMesh = CylinderMesh.new()
	mesh.top_radius = CAN_RADIUS
	mesh.bottom_radius = CAN_RADIUS
	mesh.height = CAN_HEIGHT
	mesh.material = _material(CAN_COLOR)
	var instance: MeshInstance3D = MeshInstance3D.new()
	instance.mesh = mesh
	can.add_child(instance)
	return can


static func _make_broom() -> Node3D:
	var broom: Node3D = Node3D.new()
	var handle: CylinderMesh = CylinderMesh.new()
	handle.top_radius = BROOM_HANDLE_RADIUS
	handle.bottom_radius = BROOM_HANDLE_RADIUS
	handle.height = BROOM_HANDLE_LENGTH
	handle.material = _material(BROOM_HANDLE_COLOR)
	var handle_instance: MeshInstance3D = MeshInstance3D.new()
	handle_instance.mesh = handle
	handle_instance.position.y = -BROOM_HANDLE_LENGTH * 0.5
	broom.add_child(handle_instance)
	broom.add_child(_box(BROOM_HEAD_SIZE, BROOM_HEAD_COLOR, Vector3(0.0, -BROOM_HANDLE_LENGTH, 0.0)))
	return broom


static func _box(size: Vector3, color: Color, offset: Vector3) -> MeshInstance3D:
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = size
	mesh.material = _material(color)
	var instance: MeshInstance3D = MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = offset
	return instance


static func _material(color: Color) -> ShaderMaterial:
	var source: StandardMaterial3D = StandardMaterial3D.new()
	source.resource_name = "M_TargetProp"
	source.albedo_color = color
	return ToonConverter.make_toon_material(source)
