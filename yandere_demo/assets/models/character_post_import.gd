@tool
extends EditorScenePostImport

# Bangs sit a few centimetres in front of the face; their cast shadow would cut a hard band across it.
const SHADOWLESS_MESH_SUFFIXES: Array[String] = ["Hair", "Bows"]


func _post_import(scene: Node) -> Object:
	ToonConverter.convert_character(scene)
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		var instance: MeshInstance3D = node as MeshInstance3D
		for suffix: String in SHADOWLESS_MESH_SUFFIXES:
			if String(instance.name).ends_with(suffix):
				instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return scene
