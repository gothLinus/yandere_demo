class_name YandereVision
extends Node
## Holding the vision key shows the target and the yandere items through walls (x-ray overlay on top of the toon
## materials, which stay untouched) and mutes the screen. It also owns the ObservationTracker, which needs the same
## player and target.

signal vision_toggled(active: bool)

const XRAY_SHADER: Shader = preload("res://assets/shaders/vision_xray.gdshader")
const SCREEN_SHADER: Shader = preload("res://assets/shaders/vision_screen.gdshader")
const YANDERE_ITEMS_GROUP: StringName = &"yandere_items"
const SCREEN_LAYER: int = 10

var target: TargetAI
var observation_tracker: ObservationTracker = ObservationTracker.new()

var _is_active: bool = false
var _was_key_held: bool = false
var _xray_material: ShaderMaterial = ShaderMaterial.new()
## MeshInstance3D -> the material_overlay it had before the vision overlay.
var _previous_overlays: Dictionary = {}

@onready var _player: StealthPlayer = get_parent() as StealthPlayer
@onready var _screen_layer: CanvasLayer = CanvasLayer.new()
@onready var _vision_screen: ColorRect = ColorRect.new()


func _init() -> void:
	observation_tracker.name = "ObservationTracker"
	add_child(observation_tracker)


func _ready() -> void:
	_xray_material.shader = XRAY_SHADER
	_screen_layer.layer = SCREEN_LAYER
	_vision_screen.set_anchors_preset(Control.PRESET_FULL_RECT)
	_vision_screen.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_vision_screen.material = ShaderMaterial.new()
	(_vision_screen.material as ShaderMaterial).shader = SCREEN_SHADER
	_vision_screen.visible = false
	_screen_layer.add_child(_vision_screen)
	add_child(_screen_layer)


func _process(_delta: float) -> void:
	var is_key_held: bool = Input.is_action_pressed(&"yandere_vision")
	if is_key_held != _was_key_held:
		_was_key_held = is_key_held
		set_vision(is_key_held)


func bind(new_target: TargetAI, new_meters: StealthMeters, new_day_run: DayRun, new_banked_intel: Array[StringName]) -> void:
	var was_active: bool = _is_active
	if was_active:
		_restore_overlays()
	target = new_target
	if was_active:
		_apply_overlays()
	observation_tracker.bind(get_parent() as StealthPlayer, new_target, new_meters, new_day_run, new_banked_intel)


func set_vision(active: bool) -> void:
	if active == _is_active:
		return
	_is_active = active
	_player.is_vision_active = active
	_vision_screen.visible = active
	if active:
		_apply_overlays()
	else:
		_restore_overlays()
	vision_toggled.emit(active)


func _apply_overlays() -> void:
	var roots: Array[Node] = get_tree().get_nodes_in_group(YANDERE_ITEMS_GROUP)
	if target != null:
		roots.append(target)
	for root: Node in roots:
		var meshes: Array[Node] = root.find_children("*", "MeshInstance3D", true, false)
		if root is MeshInstance3D:
			meshes.append(root)
		for node: Node in meshes:
			var mesh: MeshInstance3D = node as MeshInstance3D
			if not _previous_overlays.has(mesh):
				_previous_overlays[mesh] = mesh.material_overlay
				mesh.material_overlay = _xray_material


func _restore_overlays() -> void:
	for mesh: MeshInstance3D in _previous_overlays:
		if is_instance_valid(mesh):
			mesh.material_overlay = _previous_overlays[mesh]
	_previous_overlays.clear()
