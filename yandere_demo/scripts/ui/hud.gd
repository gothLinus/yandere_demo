extends Control
## The in-day overlay: Sanity heart, Suspicion and School Alert bars, clock, carried item and interaction prompt.
## It listens to signals only; the player and target are looked up when a day starts.

const ITEM_CATALOG: ItemCatalog = preload("res://data/items.tres")
const PLAYER_GROUP: StringName = &"player"
const TARGET_GROUP: StringName = &"target"
const HEARD_ICON_SECONDS: float = 1.2
const EDGE_FLASH_SECONDS: float = 0.5
const ALERT_MARK_POP_SECONDS: float = 0.35
const ALERT_MARK_POP_SCALE: float = 1.8

var _player: StealthPlayer
var _perception: TargetPerception
var _is_seen: bool = false
var _heard_seconds_left: float = 0.0
var _alert: float = 0.0

@onready var _suspicion_bar: ProgressBar = %SuspicionBar
@onready var _suspicion_label: Label = %SuspicionLabel
@onready var _suspicion_edge: Panel = %SuspicionEdge
@onready var _sense_icon: SenseIcon = %SenseIcon
@onready var _alert_bar: ProgressBar = %AlertBar
@onready var _alert_label: Label = %AlertLabel
@onready var _alert_mark: Label = %AlertMark
@onready var _clock_label: Label = %ClockLabel
@onready var _item_slot: PanelContainer = %ItemSlot
@onready var _item_swatch: Panel = %ItemSwatch
@onready var _item_name: Label = %ItemName
@onready var _prompt_label: Label = %PromptLabel


func _ready() -> void:
	SanitySystem.suspicion_changed.connect(_on_suspicion_changed)
	SanitySystem.school_alert_changed.connect(_on_school_alert_changed)
	SanitySystem.suspicion_triggered.connect(_on_suspicion_triggered)
	SchoolClock.minute_ticked.connect(_on_minute_ticked)
	SchoolClock.block_changed.connect(_on_block_changed)
	GameManager.day_started.connect(_on_day_started)
	_suspicion_edge.modulate.a = 0.0
	_on_suspicion_changed(SanitySystem.meters.suspicion)
	_on_school_alert_changed(SanitySystem.meters.school_alert)
	_alert = SanitySystem.meters.school_alert
	_on_carried_item_changed(&"")
	_on_interact_prompt_changed("")
	_refresh_clock()
	_bind_actors()


func _process(delta: float) -> void:
	_heard_seconds_left = maxf(_heard_seconds_left - delta, 0.0)
	if _is_seen:
		_sense_icon.sense = SenseIcon.Sense.SEEN
	elif _heard_seconds_left > 0.0:
		_sense_icon.sense = SenseIcon.Sense.HEARD
	else:
		_sense_icon.sense = SenseIcon.Sense.NONE


func _bind_actors() -> void:
	var player: StealthPlayer = get_tree().get_first_node_in_group(PLAYER_GROUP) as StealthPlayer
	if player != null and player != _player:
		_player = player
		_player.interact_prompt_changed.connect(_on_interact_prompt_changed)
		_player.carried_item_changed.connect(_on_carried_item_changed)
	var target: TargetAI = get_tree().get_first_node_in_group(TARGET_GROUP) as TargetAI
	if target != null and target.perception != _perception:
		_perception = target.perception
		_perception.sight_changed.connect(_on_sight_changed)
		_perception.heard_player.connect(_on_heard_player)
	_is_seen = false


func _refresh_clock() -> void:
	if SchoolClock.model == null:
		_clock_label.text = ""
		return
	var day_index: int = GameManager.progress.day_index if GameManager.progress != null else 0
	_clock_label.text = "%s\n%s" % [SchoolClock.model.clock_text(day_index), SchoolClock.model.current_block().display_name]


func _on_day_started(_day_index: int) -> void:
	_bind_actors()
	_on_carried_item_changed(&"")
	_refresh_clock()


func _on_suspicion_changed(value: float) -> void:
	_suspicion_bar.value = value
	_suspicion_label.text = "%d%%" % roundi(value)


func _on_school_alert_changed(value: float) -> void:
	_alert_bar.value = value
	_alert_label.text = "%d%%" % roundi(value)
	if value > _alert:
		_pop_alert_mark()
	_alert = value


func _on_suspicion_triggered(_amount: float) -> void:
	var tween: Tween = create_tween()
	_suspicion_edge.modulate.a = 1.0
	tween.tween_property(_suspicion_edge, "modulate:a", 0.0, EDGE_FLASH_SECONDS)


func _pop_alert_mark() -> void:
	_alert_mark.pivot_offset = _alert_mark.size * 0.5
	_alert_mark.scale = Vector2.ONE * ALERT_MARK_POP_SCALE
	create_tween().tween_property(_alert_mark, "scale", Vector2.ONE, ALERT_MARK_POP_SECONDS).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)


func _on_minute_ticked(_minute: float) -> void:
	_refresh_clock()


func _on_block_changed(_block: ScheduleBlock) -> void:
	_refresh_clock()


func _on_sight_changed(is_seen: bool) -> void:
	_is_seen = is_seen


func _on_heard_player() -> void:
	_heard_seconds_left = HEARD_ICON_SECONDS


func _on_carried_item_changed(item_id: StringName) -> void:
	_item_slot.visible = item_id != &""
	if item_id == &"":
		return
	var definition: ItemDefinition = ITEM_CATALOG.find(item_id)
	_item_name.text = definition.display_name if definition != null else String(item_id)
	_item_swatch.self_modulate = definition.color if definition != null else Color.WHITE


func _on_interact_prompt_changed(text: String) -> void:
	_prompt_label.text = text
	_prompt_label.visible = not text.is_empty()
