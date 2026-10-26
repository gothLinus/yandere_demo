class_name Vignette
extends ColorRect
## Screen-edge darkening that grows as Sanity falls or Suspicion climbs and pulses with the heart.

const SHADER: Shader = preload("res://assets/shaders/vignette.gdshader")
const SANITY_FULL_BELOW: float = 0.0
const SANITY_START_BELOW: float = 40.0
const SUSPICION_START: float = 50.0
const SUSPICION_FULL: float = 100.0
const PULSE_DEPTH: float = 0.2

var intensity: float = 0.0

var _sanity: float = 100.0
var _suspicion: float = 0.0
var _beat_phase: float = 0.0
var _shader_material: ShaderMaterial = ShaderMaterial.new()


static func intensity_for(sanity: float, suspicion: float) -> float:
	return maxf(smoothstep(SANITY_START_BELOW, SANITY_FULL_BELOW, sanity), smoothstep(SUSPICION_START, SUSPICION_FULL, suspicion))


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
	_beat_phase = fposmod(_beat_phase + delta * SanityHeart.beats_per_minute(_sanity) / 60.0, 1.0)
	var pulse: float = 0.5 + 0.5 * sin(_beat_phase * TAU)
	_shader_material.set_shader_parameter(&"strength", intensity * (1.0 - PULSE_DEPTH + PULSE_DEPTH * pulse))


func _on_sanity_changed(value: float) -> void:
	_sanity = value
	_update_intensity()


func _on_suspicion_changed(value: float) -> void:
	_suspicion = value
	_update_intensity()


func _update_intensity() -> void:
	intensity = intensity_for(_sanity, _suspicion)
