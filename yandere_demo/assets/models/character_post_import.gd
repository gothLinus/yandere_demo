@tool
extends EditorScenePostImport


func _post_import(scene: Node) -> Object:
	ToonConverter.convert_character(scene)
	return scene
