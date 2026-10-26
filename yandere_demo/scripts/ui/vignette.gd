class_name Vignette
extends ColorRect
## Screen-edge darkening that grows as Sanity falls or Suspicion climbs and pulses with the heart.

const SHADER: Shader = preload("res://assets/shaders/vignette.gdshader")
const PULSE_DEPTH: float = 0.2

var intensity: float = 0.0

var _sanity: float = 100.0
var _suspicion: float = 0.0
var _beat_phase: float = 0.0
var _shader_material: ShaderMaterial = ShaderMaterial.new()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_shader_material.shader = SHADER
	material = _shader_material
	SanitySystem.sanity_changed.connect(_on_sanity_changed)
	SanitySystem.suspicion_changed.connect(_on_suspicion_changed)
	_sanity = SanitySystem.meters.sanity
	_suspicion = SanitySystem.meters.suspicion
	_update_intensity()


func _process(delta: float) -> void:
	_beat_phase = fposmod(_beat_phase + delta * UiFormulas.beats_per_minute(_sanity) / 60.0, 1.0)
	var pulse: float = 0.5 + 0.5 * sin(_beat_phase * TAU)
	_shader_material.set_shader_parameter(&"strength", intensity * (1.0 - PULSE_DEPTH + PULSE_DEPTH * pulse))


func _on_sanity_changed(value: float) -> void:
	_sanity = value
	_update_intensity()


func _on_suspicion_changed(value: float) -> void:
	_suspicion = value
	_update_intensity()


func _update_intensity() -> void:
	intensity = UiFormulas.vignette_intensity(_sanity, _suspicion)
