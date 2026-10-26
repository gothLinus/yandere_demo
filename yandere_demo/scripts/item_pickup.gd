class_name ItemPickup
extends Interactable

signal picked(item_id: StringName)

const SCENE_PATH: String = "res://scenes/props/item_pickup.tscn"
const CATALOG: ItemCatalog = preload("res://data/items.tres")
const YANDERE_ITEMS_GROUP: StringName = &"yandere_items"
const MESH_SIZE: Vector3 = Vector3(0.1, 0.14, 0.1)
const GLOW_ENERGY: float = 1.5

@export var item_id: StringName

@onready var _mesh_instance: MeshInstance3D = $Mesh


static func spawn(parent: Node3D, new_item_id: StringName, at: Vector3) -> ItemPickup:
	var pickup: ItemPickup = (load(SCENE_PATH) as PackedScene).instantiate() as ItemPickup
	pickup.item_id = new_item_id
	parent.add_child(pickup)
	pickup.global_position = at
	return pickup


static func definition_for(wanted_id: StringName) -> ItemDefinition:
	return CATALOG.find(wanted_id)


func _ready() -> void:
	add_to_group(YANDERE_ITEMS_GROUP)
	_mesh_instance.mesh = _build_mesh()
	_mesh_instance.position.y = MESH_SIZE.y * 0.5


func prompt_text(_player: StealthPlayer) -> String:
	var definition: ItemDefinition = definition_for(item_id)
	return "E – Take %s" % (definition.display_name if definition != null else String(item_id))


func can_interact(player: StealthPlayer) -> bool:
	return player.carried_item == &""


func interact(player: StealthPlayer) -> void:
	if player.pick_up(item_id):
		picked.emit(item_id)
		queue_free()


func _build_mesh() -> BoxMesh:
	var definition: ItemDefinition = definition_for(item_id)
	if definition == null:
		push_error("ItemPickup: unknown item '%s'" % item_id)
	var color: Color = definition.color if definition != null else Color.WHITE
	var source: StandardMaterial3D = StandardMaterial3D.new()
	source.resource_name = "M_ItemPickup"
	source.albedo_color = color
	source.emission_enabled = true
	source.emission = color
	source.emission_energy_multiplier = GLOW_ENERGY
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = MESH_SIZE
	mesh.material = ToonConverter.make_toon_material(source)
	return mesh
