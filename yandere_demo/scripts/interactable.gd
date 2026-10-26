class_name Interactable
extends Area3D

func _init() -> void:
	collision_layer = PhysicsLayers.INTERACTABLE
	collision_mask = 0


func prompt_text(_player: StealthPlayer) -> String:
	return ""


func can_interact(_player: StealthPlayer) -> bool:
	return true


func interact(_player: StealthPlayer) -> void:
	pass
