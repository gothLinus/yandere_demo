@tool
extends EditorScenePostImport

# Bangs sit a few centimetres in front of the face; their cast shadow would cut a hard band across it.
# Matches TargetHair, Hair_bob, TargetBows, Bow_left and similar names.
const SHADOWLESS_NAME_PARTS: Array[String] = ["Hair", "Bow"]
# Every other imported clip loops; glTF carries no loop flag.
const ONE_SHOT_ANIMATIONS: Array[StringName] = [
	&"target_notice_player",
	&"target_startled",
	&"target_sit_down",
	&"target_stand_up",
	&"player_hide",
	&"player_sit_down",
	&"player_stand_up",
]


func _post_import(scene: Node) -> Object:
	ToonConverter.convert_character(scene)
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		var instance: MeshInstance3D = node as MeshInstance3D
		for name_part: String in SHADOWLESS_NAME_PARTS:
			if String(instance.name).contains(name_part):
				instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_set_loop_modes(scene)
	return scene


func _set_loop_modes(scene: Node) -> void:
	for node: Node in scene.find_children("*", "AnimationPlayer", true, false):
		var player: AnimationPlayer = node as AnimationPlayer
		for library_name: StringName in player.get_animation_library_list():
			var library: AnimationLibrary = player.get_animation_library(library_name)
			for animation_name: StringName in library.get_animation_list():
				var animation: Animation = library.get_animation(animation_name)
				var is_one_shot: bool = ONE_SHOT_ANIMATIONS.has(animation_name)
				animation.loop_mode = Animation.LOOP_NONE if is_one_shot else Animation.LOOP_LINEAR
