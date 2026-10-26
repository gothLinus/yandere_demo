class_name DaylightProfile
extends Resource

@export var morning_minute: float = 420.0
@export var noon_minute: float = 720.0
@export var evening_minute: float = 1050.0
@export var morning_color: Color = Color(1.0, 0.95, 0.86)
@export var noon_color: Color = Color(1.0, 1.0, 1.0)
@export var evening_color: Color = Color("ffb070")
@export var morning_energy: float = 1.2
@export var noon_energy: float = 1.0
@export var evening_energy: float = 0.8
@export var morning_pitch_degrees: float = -35.0
@export var noon_pitch_degrees: float = -65.0
@export var evening_pitch_degrees: float = -18.0
@export var sun_yaw_degrees: float = -30.0


func apply_to(sun: DirectionalLight3D, minute: float) -> void:
	var morning_to_noon: bool = minute < noon_minute
	var from_minute: float = morning_minute if morning_to_noon else noon_minute
	var to_minute: float = noon_minute if morning_to_noon else evening_minute
	var weight: float = clampf(inverse_lerp(from_minute, to_minute, minute), 0.0, 1.0)
	var from_color: Color = morning_color if morning_to_noon else noon_color
	var to_color: Color = noon_color if morning_to_noon else evening_color
	var from_energy: float = morning_energy if morning_to_noon else noon_energy
	var to_energy: float = noon_energy if morning_to_noon else evening_energy
	var from_pitch: float = morning_pitch_degrees if morning_to_noon else noon_pitch_degrees
	var to_pitch: float = noon_pitch_degrees if morning_to_noon else evening_pitch_degrees
	sun.light_color = from_color.lerp(to_color, weight)
	sun.light_energy = lerpf(from_energy, to_energy, weight)
	sun.rotation_degrees = Vector3(lerpf(from_pitch, to_pitch, weight), sun_yaw_degrees, 0.0)
