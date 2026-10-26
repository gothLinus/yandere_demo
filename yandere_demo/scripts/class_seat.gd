class_name ClassSeat
extends Interactable

signal player_sat()

@export var is_player_seat: bool = false

var is_class_block_callable: Callable = _default_is_class_block


func prompt_text(_player: StealthPlayer) -> String:
	return "E – Sit"


func can_interact(_player: StealthPlayer) -> bool:
	return is_player_seat and is_class_block_callable.call()


func interact(player: StealthPlayer) -> void:
	if player.sit(self):
		player_sat.emit()


func _default_is_class_block() -> bool:
	if not is_inside_tree():
		return false
	var clock: Node = get_node_or_null("/root/SchoolClock")
	if clock == null:
		return false
	var block: ScheduleBlock = clock.model.current_block()
	return block != null and block.kind == GameTypes.BlockKind.CLASS
