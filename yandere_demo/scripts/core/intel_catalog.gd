class_name IntelCatalog
extends Resource

@export var cards: Array[IntelCard] = []


func find(id: StringName) -> IntelCard:
	for card: IntelCard in cards:
		if card.id == id:
			return card
	return null


func total() -> int:
	return cards.size()
