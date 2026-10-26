class_name Album
extends CanvasLayer
## The album (Tab): the week's photos, banked and stashed items, unlocked intel and the target's activity weights for
## tomorrow. Opening it pauses the game.

signal closed()

const GROUP: StringName = &"album"
const ITEM_CATALOG: ItemCatalog = preload("res://data/items.tres")
const INTEL_CATALOG: IntelCatalog = preload("res://data/intel_cards.tres")
const ACTIVITY_POOL: ActivityPool = preload("res://data/activity_pool.tres")
const THUMBNAIL_SIZE: Vector2 = Vector2(208, 117)
const SWATCH_SIZE: Vector2 = Vector2(28, 28)
const WEIGHT_BAR_SIZE: Vector2 = Vector2(220, 14)
const PLACEHOLDER_COLOR: Color = Color("2a1a33")

var _was_paused: bool = false

@onready var _photo_grid: GridContainer = %PhotoGrid
@onready var _item_list: VBoxContainer = %ItemList
@onready var _intel_list: VBoxContainer = %IntelList
@onready var _weight_list: VBoxContainer = %WeightList
@onready var _close_button: Button = %CloseButton
@onready var _root: Control = $Root


func _ready() -> void:
	add_to_group(GROUP)
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root.visible = false
	_close_button.pressed.connect(close)


func _unhandled_input(event: InputEvent) -> void:
	if _root.visible and (event.is_action_pressed(&"album") or event.is_action_pressed(&"pause")):
		close()
		get_viewport().set_input_as_handled()
	elif not _root.visible and event.is_action_pressed(&"album") and SchoolClock.running and not get_tree().paused:
		open()
		get_viewport().set_input_as_handled()


func is_open() -> bool:
	return _root.visible


func open() -> void:
	_was_paused = get_tree().paused
	get_tree().paused = true
	ScreenSupport.show_cursor()
	_rebuild()
	_root.visible = true
	_close_button.grab_focus()


func close() -> void:
	if not _root.visible:
		return
	_root.visible = false
	get_tree().paused = _was_paused
	if not _was_paused:
		ScreenSupport.capture_cursor()
	closed.emit()


func _rebuild() -> void:
	for container: Container in [_photo_grid, _item_list, _intel_list, _weight_list]:
		for child: Node in container.get_children():
			child.queue_free()
	_build_photos()
	_build_items()
	_build_intel()
	_build_weights()


func _build_photos() -> void:
	var photos: Array[Dictionary] = []
	if GameManager.progress != null:
		photos.append_array(GameManager.progress.banked_photos)
	if GameManager.day_run != null:
		photos.append_array(GameManager.day_run.photos)
	if photos.is_empty():
		_photo_grid.add_child(_make_note("No photos yet. Raise the camera and shoot him."))
	for photo: Dictionary in photos:
		_photo_grid.add_child(_make_photo_tile(photo))


func _make_photo_tile(photo: Dictionary) -> Control:
	var tile: VBoxContainer = VBoxContainer.new()
	var texture: Texture2D = _load_thumbnail(String(photo["path"]))
	if texture != null:
		var picture: TextureRect = TextureRect.new()
		picture.texture = texture
		picture.custom_minimum_size = THUMBNAIL_SIZE
		picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		picture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		tile.add_child(picture)
	else:
		var placeholder: ColorRect = ColorRect.new()
		placeholder.color = PLACEHOLDER_COLOR
		placeholder.custom_minimum_size = THUMBNAIL_SIZE
		var placeholder_label: Label = Label.new()
		placeholder_label.text = "No image"
		placeholder_label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		placeholder_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		placeholder_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		placeholder.add_child(placeholder_label)
		tile.add_child(placeholder)
	var caption: Label = Label.new()
	caption.text = "%s  %d pts" % [GameTypes.WEEKDAY_NAMES[clampi(int(photo["day"]), 0, GameTypes.WEEKDAY_NAMES.size() - 1)], int(photo["score"])]
	tile.add_child(caption)
	return tile


func _load_thumbnail(path: String) -> Texture2D:
	if path.is_empty() or not FileAccess.file_exists(path):
		return null
	var image: Image = Image.load_from_file(path)
	return ImageTexture.create_from_image(image) if image != null else null


func _build_items() -> void:
	var has_items: bool = false
	if GameManager.progress != null and not GameManager.progress.banked_items.is_empty():
		has_items = true
		_item_list.add_child(_make_heading("Banked"))
		for item_id: StringName in GameManager.progress.banked_items:
			_item_list.add_child(_make_item_row(item_id))
	if GameManager.day_run != null and not GameManager.day_run.stashed_items.is_empty():
		has_items = true
		_item_list.add_child(_make_heading("Stashed today"))
		for item_id: StringName in GameManager.day_run.stashed_items:
			_item_list.add_child(_make_item_row(item_id))
	if not has_items:
		_item_list.add_child(_make_note("Nothing stashed yet. Carry items to the locker to keep them."))


func _make_item_row(item_id: StringName) -> Control:
	var definition: ItemDefinition = ITEM_CATALOG.find(item_id)
	var row: HBoxContainer = HBoxContainer.new()
	var swatch: ColorRect = ColorRect.new()
	swatch.custom_minimum_size = SWATCH_SIZE
	swatch.color = definition.color if definition != null else Color.WHITE
	row.add_child(swatch)
	var name_label: Label = Label.new()
	name_label.text = definition.display_name if definition != null else String(item_id)
	row.add_child(name_label)
	return row


func _build_intel() -> void:
	var unlocked: Array[StringName] = []
	if GameManager.progress != null:
		unlocked.append_array(GameManager.progress.banked_intel)
	if GameManager.day_run != null:
		for card_id: StringName in GameManager.day_run.intel:
			if not unlocked.has(card_id):
				unlocked.append(card_id)
	if unlocked.is_empty():
		_intel_list.add_child(_make_note("No intel yet. Watch him, or find what he leaves behind."))
	for card_id: StringName in unlocked:
		var card: IntelCard = INTEL_CATALOG.find(card_id)
		if card == null:
			continue
		_intel_list.add_child(_make_heading(card.title))
		var text_label: Label = Label.new()
		text_label.text = card.text
		text_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_intel_list.add_child(text_label)


## Weight of each free-time activity for tomorrow: the best weight over its allowed blocks, given the current history.
func _build_weights() -> void:
	if GameManager.progress == null:
		return
	var scheduler: TargetScheduler = TargetScheduler.new(ACTIVITY_POOL, {})
	var weights: Dictionary = {}
	var highest_weight: float = 0.0
	for activity: ActivityDefinition in ACTIVITY_POOL.activities:
		if activity.is_fixed:
			continue
		var best_weight: float = 0.0
		for block_id: StringName in activity.allowed_blocks:
			best_weight = maxf(best_weight, scheduler.weight_for(activity, block_id, GameManager.progress.history, &""))
		weights[activity] = best_weight
		highest_weight = maxf(highest_weight, best_weight)
	for activity: ActivityDefinition in weights:
		var row: HBoxContainer = HBoxContainer.new()
		var name_label: Label = Label.new()
		name_label.text = activity.display_name
		name_label.custom_minimum_size = Vector2(200, 0)
		row.add_child(name_label)
		var bar: ProgressBar = ProgressBar.new()
		bar.custom_minimum_size = WEIGHT_BAR_SIZE
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		bar.show_percentage = false
		bar.max_value = maxf(highest_weight, 0.001)
		bar.value = weights[activity]
		row.add_child(bar)
		_weight_list.add_child(row)


func _make_heading(text: String) -> Label:
	var label: Label = Label.new()
	label.text = text
	label.add_theme_color_override(&"font_color", Color("ff8fb8"))
	return label


func _make_note(text: String) -> Label:
	var label: Label = Label.new()
	label.text = text
	label.modulate = Color(1, 1, 1, 0.7)
	return label
