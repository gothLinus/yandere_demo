class_name FootstepPlayer
extends AudioStreamPlayer3D
## Plays a random footstep matching the stance of each noise StealthPlayer makes.

const AUDIO_DIRECTORY: String = "res://assets/audio/"
const STANCE_PREFIXES: Dictionary[GameTypes.Stance, String] = {
	GameTypes.Stance.SNEAK: "footstep_sneak",
	GameTypes.Stance.WALK: "footstep_walk",
	GameTypes.Stance.RUN: "footstep_run",
}
const VARIANT_COUNTS: Dictionary[GameTypes.Stance, int] = {
	GameTypes.Stance.SNEAK: 2,
	GameTypes.Stance.WALK: 3,
	GameTypes.Stance.RUN: 3,
}


func _ready() -> void:
	(get_parent() as StealthPlayer).noise_made.connect(_on_noise_made)


func _on_noise_made(_position: Vector3, stance: GameTypes.Stance) -> void:
	if not STANCE_PREFIXES.has(stance):
		return
	var variant_number: int = randi_range(1, VARIANT_COUNTS[stance])
	stream = load("%s%s_%02d.wav" % [AUDIO_DIRECTORY, STANCE_PREFIXES[stance], variant_number]) as AudioStream
	play()
