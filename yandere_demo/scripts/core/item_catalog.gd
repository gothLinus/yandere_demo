class_name ItemCatalog
extends Resource

@export var items: Array[ItemDefinition] = []


func find(id: StringName) -> ItemDefinition:
	for item: ItemDefinition in items:
		if item.id == id:
			return item
	return null
