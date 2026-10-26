class_name HideSpot
extends Interactable

signal player_hidden_changed(is_hidden: bool)

const DOOR_SECONDS: float = 0.3
const DOOR_OPEN_ANGLE: float = deg_to_rad(-100.0)
const PROMPT_HIDE: String = "E – Hide"
const PROMPT_LEAVE: String = "E – Leave"

@export var kind: StringName = &"locker"
## Local positions tried in order when the player leaves; the first one clear of world colliders wins.
@export var exit_offsets: Array[Vector3] = [Vector3.ZERO]

var _door_tween: Tween

@onready var view_point: Marker3D = $ViewPoint
@onready var _peek_point: Marker3D = $ViewPoint/PeekPoint
@onready var _door_pivot: Node3D = get_node_or_null("DoorPivot") as Node3D


func _ready() -> void:
	if _door_pivot != null:
		ToonConverter.convert_environment(_door_pivot)


func prompt_text(player: StealthPlayer) -> String:
	return PROMPT_LEAVE if player.hidden_spot == self else PROMPT_HIDE


func can_interact(player: StealthPlayer) -> bool:
	if player.hidden_spot == self:
		return true
	return player.mode == StealthPlayer.MODE_FREE and player.can_hide_callable.call()


func interact(player: StealthPlayer) -> void:
	if player.hidden_spot == self:
		_leave(player)
	else:
		_enter(player)


func _enter(player: StealthPlayer) -> void:
	if not player.enter_hidden(self):
		return
	player.global_transform = view_point.global_transform
	player.show_peek_view(_peek_point)
	_cycle_door()
	player_hidden_changed.emit(true)


func _leave(player: StealthPlayer) -> void:
	player.exit_hidden()
	player.global_position = _exit_position(player)
	_cycle_door()
	player_hidden_changed.emit(false)


func _exit_position(player: StealthPlayer) -> Vector3:
	for offset: Vector3 in exit_offsets:
		var candidate: Vector3 = global_transform * offset
		if player.is_position_clear(candidate):
			return candidate
	push_warning("HideSpot %s: no clear exit position" % name)
	return global_transform * exit_offsets[0]


func _cycle_door() -> void:
	if _door_pivot == null:
		return
	if _door_tween != null:
		_door_tween.kill()
	_door_tween = create_tween()
	_door_tween.tween_property(_door_pivot, "rotation:y", DOOR_OPEN_ANGLE, DOOR_SECONDS)
	_door_tween.tween_property(_door_pivot, "rotation:y", 0.0, DOOR_SECONDS)
