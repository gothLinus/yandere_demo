@tool
extends EditorScenePostImport

# Bangs sit a few centimetres in front of the face; their cast shadow would cut a hard band across it.
# Matches TargetHair, Hair_bob, TargetBows, Bow_left and similar names.
const SHADOWLESS_NAME_PARTS: Array[String] = ["Hair", "Bow"]


func _post_import(scene: Node) -> Object:
	ToonConverter.convert_character(scene)
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		var instance: MeshInstance3D = node as MeshInstance3D
		for name_part: String in SHADOWLESS_NAME_PARTS:
			if String(instance.name).contains(name_part):
				instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return scene
