extends PanelContainer
## Slides in from the top when a bell rings. Free blocks show the block name for a moment; a class block also
## shows the grace countdown until the player sits or the grace runs out.

const SLIDE_SECONDS: float = 0.35
const FREE_BLOCK_HOLD_SECONDS: float = 2.5
const HIDDEN_Y: float = -120.0
const SHOWN_Y: float = 24.0

var _hold_seconds_left: float = 0.0
var _is_counting_grace: bool = false
var _is_shown: bool = false
var _slide_tween: Tween

@onready var _label: Label = $Label


func _ready() -> void:
	position.y = HIDDEN_Y
	SchoolClock.bell_rang.connect(_on_bell_rang)
	GameManager.day_started.connect(_on_day_started)


func _process(delta: float) -> void:
	if not _is_shown:
		return
	if _is_counting_grace:
		var seconds_left: float = SchoolClock.schedule.class_grace_real_seconds - SchoolClock.model.seconds_into_block()
		if seconds_left <= 0.0 or GameManager.attendance.has_sat:
			_slide_out()
		else:
			_label.text = _class_text(seconds_left)
		return
	_hold_seconds_left -= delta
	if _hold_seconds_left <= 0.0:
		_slide_out()


func _on_bell_rang(block: ScheduleBlock) -> void:
	_is_counting_grace = block.kind == GameTypes.BlockKind.CLASS and GameManager.attendance != null and not GameManager.attendance.has_sat
	_hold_seconds_left = FREE_BLOCK_HOLD_SECONDS
	_label.text = _class_text(SchoolClock.schedule.class_grace_real_seconds) if _is_counting_grace else "♪ %s" % block.display_name
	_slide_in()


func _on_day_started(_day_index: int) -> void:
	_is_counting_grace = false
	if _is_shown:
		_slide_out()


func _class_text(seconds_left: float) -> String:
	return "Class started — go to 1-A  (%d s)" % ceili(seconds_left)


func _slide_in() -> void:
	_is_shown = true
	_move_to(SHOWN_Y)


func _slide_out() -> void:
	_is_shown = false
	_is_counting_grace = false
	_move_to(HIDDEN_Y)


func _move_to(target_y: float) -> void:
	if _slide_tween != null:
		_slide_tween.kill()
	_slide_tween = create_tween()
	_slide_tween.tween_property(self, "position:y", target_y, SLIDE_SECONDS).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
