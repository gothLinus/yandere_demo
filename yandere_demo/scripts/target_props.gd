class_name TargetProps
extends Node
## Hand props (ruling R9): simple toon meshes on the hands, each visible only while the clip that holds it plays.
## Placements are in the hand bone's space, fitted to each clip's mid pose: the book and phone sit between both hands
## facing the eyes, the can points at the mouth, and the broom shaft runs through both hands to the floor.

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
const PROP_PLACEMENTS: Dictionary[StringName, Transform3D] = {
	BOOK: Transform3D(Basis(Vector3(-0.969, -0.243, -0.037), Vector3(-0.209, 0.737, 0.643), Vector3(-0.129, 0.631, -0.765)),
			Vector3(0.055, 0.127, 0.019)),
	PHONE: Transform3D(Basis(Vector3(-0.947, 0.018, -0.319), Vector3(-0.202, 0.740, 0.642), Vector3(0.248, 0.673, -0.697)),
			Vector3(0.023, 0.057, 0.01)),
	CAN: Transform3D(Basis(Vector3(-0.698, -0.395, 0.597), Vector3(-0.662, 0.041, -0.748), Vector3(0.271, -0.918, -0.29)),
			Vector3(0.04, 0.05, 0.0)),
	BROOM: Transform3D(Basis(Vector3(-0.364, -0.888, 0.282), Vector3(0.858, -0.438, -0.268), Vector3(0.361, 0.144, 0.921)),
			Vector3(0.129, -0.016, -0.04)),
}
const BOOK_SIZE: Vector3 = Vector3(0.15, 0.21, 0.025)
const BOOK_COLOR: Color = Color(0.22, 0.32, 0.62)
const PAGES_COLOR: Color = Color(0.95, 0.93, 0.86)
const PHONE_SIZE: Vector3 = Vector3(0.07, 0.14, 0.009)
const PHONE_COLOR: Color = Color(0.96, 0.72, 0.82)
const SCREEN_COLOR: Color = Color(0.1, 0.1, 0.14)
const CAN_RADIUS: float = 0.033
const CAN_HEIGHT: float = 0.12
const CAN_COLOR: Color = Color(1.0, 0.7, 0.78)
const BROOM_HANDLE_RADIUS: float = 0.012
const BROOM_HANDLE_LENGTH: float = 1.08
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
	var builders: Dictionary[StringName, Callable] = {
		BOOK: _make_book, PHONE: _make_phone, CAN: _make_can, BROOM: _make_broom,
	}
	for prop_name: StringName in builders:
		var attachment: BoneAttachment3D = BoneAttachment3D.new()
		attachment.name = "%sAttachment" % String(prop_name).capitalize()
		attachment.bone_name = PROP_BONES[prop_name]
		skeleton.add_child(attachment)
		var prop: Node3D = builders[prop_name].call()
		prop.name = String(prop_name).capitalize()
		prop.transform = PROP_PLACEMENTS[prop_name]
		prop.visible = false
		attachment.add_child(prop)
		_props[prop_name] = prop


func show_for(animation_name: StringName) -> void:
	var wanted: StringName = PROP_FOR_ANIMATION.get(animation_name, &"")
	for prop_name: StringName in _props:
		_props[prop_name].visible = prop_name == wanted


func _make_book() -> Node3D:
	var book: Node3D = Node3D.new()
	book.add_child(_box(BOOK_SIZE, BOOK_COLOR, Vector3.ZERO))
	var pages: Vector3 = BOOK_SIZE - Vector3(PAGE_INSET, PAGE_INSET, -PAGE_INSET)
	book.add_child(_box(pages, PAGES_COLOR, Vector3(PAGE_INSET * 0.5, 0.0, 0.0)))
	return book


func _make_phone() -> Node3D:
	var phone: Node3D = Node3D.new()
	phone.add_child(_box(PHONE_SIZE, PHONE_COLOR, Vector3.ZERO))
	var screen: Vector3 = Vector3(PHONE_SIZE.x - SCREEN_INSET, PHONE_SIZE.y - SCREEN_INSET, PHONE_SIZE.z * 0.2)
	phone.add_child(_box(screen, SCREEN_COLOR, Vector3(0.0, 0.0, PHONE_SIZE.z * 0.5)))
	return phone


func _make_can() -> Node3D:
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


func _make_broom() -> Node3D:
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


func _box(size: Vector3, color: Color, offset: Vector3) -> MeshInstance3D:
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = size
	mesh.material = _material(color)
	var instance: MeshInstance3D = MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = offset
	return instance


func _material(color: Color) -> ShaderMaterial:
	var source: StandardMaterial3D = StandardMaterial3D.new()
	source.resource_name = "M_TargetProp"
	source.albedo_color = color
	return ToonConverter.make_toon_material(source)
