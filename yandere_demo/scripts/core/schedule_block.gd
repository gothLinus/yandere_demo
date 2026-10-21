class_name ScheduleBlock
extends Resource

@export var id: StringName
@export var display_name: String
@export var kind: GameTypes.BlockKind
@export var start_minute: int
@export var end_minute: int
## Real duration at 1x; for class blocks, when the player does not sit.
@export var real_seconds: float = 1.0


func game_minutes_per_second() -> float:
	return float(end_minute - start_minute) / real_seconds
