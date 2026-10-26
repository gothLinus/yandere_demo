class_name DaySummary
extends CanvasLayer
## End-of-day recap. Continue starts the next day; after the final day it hands over to the ending instead.

## Task 20 listens here: the week is over and `ending_id` is the resolved ending.
signal ending_requested(ending_id: StringName)

const ITEM_CATALOG: ItemCatalog = preload("res://data/items.tres")
const INTEL_CATALOG: IntelCatalog = preload("res://data/intel_cards.tres")

var _ending_id: StringName = &""

@onready var _root: Control = $Root
@onready var _title_label: Label = %TitleLabel
@onready var _photos_label: Label = %PhotosLabel
@onready var _items_label: Label = %ItemsLabel
@onready var _intel_label: Label = %IntelLabel
@onready var _alert_label: Label = %AlertLabel
@onready var _continue_button: Button = %ContinueButton


func _ready() -> void:
	_root.visible = false
	GameManager.day_completed.connect(_on_day_completed)
	GameManager.week_completed.connect(_on_week_completed)
	GameManager.day_started.connect(_on_day_started)
	_continue_button.pressed.connect(_on_continue_pressed)


func show_summary(summary: Dictionary, completed_day_number: int) -> void:
	var photos: Array = summary["photos"]
	_title_label.text = "Day %d complete" % completed_day_number
	_photos_label.text = "Photos kept: %d  (%d pts)" % [photos.size(), int(summary["photo_score"])]
	_items_label.text = "Stashed: %s" % _join_or_none(_item_names(summary["items"]))
	_intel_label.text = "New intel: %s" % _join_or_none(_card_titles(summary["intel_new"]))
	_alert_label.text = "School alert: %d%%" % roundi(float(summary["school_alert"]))
	_ending_id = &""
	_continue_button.text = "Continue"
	ScreenSupport.show_cursor()
	_root.visible = true
	_continue_button.grab_focus()


func _item_names(item_ids: Array) -> Array[String]:
	var names: Array[String] = []
	for item_id: StringName in item_ids:
		var definition: ItemDefinition = ITEM_CATALOG.find(item_id)
		names.append(definition.display_name if definition != null else String(item_id))
	return names


func _card_titles(card_ids: Array) -> Array[String]:
	var titles: Array[String] = []
	for card_id: StringName in card_ids:
		var card: IntelCard = INTEL_CATALOG.find(card_id)
		titles.append(card.title if card != null else String(card_id))
	return titles


func _join_or_none(entries: Array[String]) -> String:
	return ", ".join(entries) if not entries.is_empty() else "none"


func _on_day_completed(summary: Dictionary) -> void:
	show_summary(summary, GameManager.progress.day_index)


func _on_week_completed(ending_id: StringName) -> void:
	_ending_id = ending_id
	_continue_button.text = "See the ending"


func _on_day_started(_day_index: int) -> void:
	_root.visible = false


func _on_continue_pressed() -> void:
	if _ending_id != &"":
		_root.visible = false
		ending_requested.emit(_ending_id)
		return
	_root.visible = false
	ScreenSupport.capture_cursor()
	GameManager.start_day()
