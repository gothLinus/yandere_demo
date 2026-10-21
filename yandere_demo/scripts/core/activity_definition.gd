class_name ActivityDefinition
extends Resource

@export var id: StringName
@export var display_name: String
@export var allowed_blocks: Array[StringName] = []
@export var base_weight: float = 1.0
## Game minutes.
@export var min_minutes: float = 5.0
@export var max_minutes: float = 10.0
@export var animation: StringName
@export var posture: GameTypes.Posture = GameTypes.Posture.STANDING
@export var expression: StringName = &"neutral"
@export var is_rare: bool = false
## A fixed activity is always scheduled and never drawn from the pool.
@export var is_fixed: bool = false
@export var item_ids: Array[StringName] = []
@export var item_drop_chance: float = 0.0
@export var intel_card_id: StringName
