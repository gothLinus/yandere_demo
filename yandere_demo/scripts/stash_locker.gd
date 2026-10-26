class_name StashLocker
extends Interactable

signal item_stashed(item_id: StringName)


func prompt_text(player: StealthPlayer) -> String:
	var definition: ItemDefinition = ItemPickup.definition_for(player.carried_item)
	return "E – Stash %s" % (definition.display_name if definition != null else player.carried_item)


func can_interact(player: StealthPlayer) -> bool:
	return player.carried_item != &""


func interact(player: StealthPlayer) -> void:
	var stashed_id: StringName = player.drop_carried()
	if stashed_id != &"":
		item_stashed.emit(stashed_id)
