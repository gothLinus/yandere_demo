extends TestCase

const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"

var player: StealthPlayer
var seat: Node3D
var hiding_spot: Node3D
var _signal_log: Array[String] = []


func before_each() -> void:
	player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	player.can_hide_callable = func() -> bool: return true
	seat = Node3D.new()
	seat.transform = Transform3D(Basis.from_euler(Vector3(0.0, 1.0, 0.0)), Vector3(3.0, 0.0, -2.0))
	hiding_spot = Node3D.new()
	hiding_spot.position = Vector3(-4.0, 0.0, 1.0)
	_signal_log.clear()


func after_each() -> void:
	player.free()
	seat.free()
	hiding_spot.free()


func test_mode_exclusivity() -> void:
	assert_true(player.enter_camera_mode(), "camera mode enters from free")
	assert_eq(player.current_activity(), GameTypes.PlayerActivity.CAMERA_RAISED)
	assert_true(player.sit(seat), "sit succeeds")
	assert_eq(player.mode, &"seated")
	assert_true(player.current_activity() != GameTypes.PlayerActivity.CAMERA_RAISED, "camera mode exited by sit")
	assert_true(not player.enter_camera_mode(), "no camera while seated")
	player.stand_up()
	assert_true(player.pick_up(&"pen"))
	assert_eq(player.current_activity(), GameTypes.PlayerActivity.CARRYING_ITEM)
	assert_true(player.sit(seat))
	assert_eq(player.carried_item, &"pen", "carried item survives sitting")
	player.stand_up()
	player.can_hide_callable = func() -> bool: return false
	assert_true(not player.enter_hidden(hiding_spot), "hiding refused at low sanity")
	assert_eq(player.mode, &"free")


func test_hidden_excludes_camera_and_sitting() -> void:
	assert_true(player.enter_camera_mode())
	assert_true(player.enter_hidden(hiding_spot))
	assert_eq(player.mode, &"hidden")
	assert_eq(player.stance, GameTypes.Stance.HIDDEN)
	assert_true(not player.enter_camera_mode(), "no camera while hidden")
	assert_true(not player.sit(seat), "no sitting while hidden")
	player.exit_hidden()
	assert_eq(player.mode, &"free")
	assert_true(player.stance != GameTypes.Stance.HIDDEN, "stance restored")


func test_sit_snaps_to_the_seat_marker() -> void:
	assert_true(player.sit(seat))
	assert_true(player.transform.origin.is_equal_approx(seat.transform.origin), "position snapped")
	assert_near(player.rotation.y, 1.0, 0.0001, "yaw snapped")


func test_mode_and_carry_signals() -> void:
	player.mode_changed.connect(func(mode: StringName) -> void: _signal_log.append("mode:%s" % mode))
	player.carried_item_changed.connect(func(item_id: StringName) -> void: _signal_log.append("item:%s" % item_id))
	player.enter_camera_mode()
	player.exit_camera_mode()
	player.pick_up(&"pen")
	assert_true(not player.pick_up(&"key"), "cannot carry two items")
	assert_eq(player.drop_carried(), &"pen")
	assert_eq(player.drop_carried(), &"", "nothing left to drop")
	assert_eq(_signal_log, ["mode:camera", "mode:free", "item:pen", "item:"])


func test_speeds() -> void:
	player.stance = GameTypes.Stance.WALK
	assert_near(player.move_speed(), StealthPlayer.WALK_SPEED, 0.0001)
	player.stance = GameTypes.Stance.RUN
	assert_near(player.move_speed(), StealthPlayer.RUN_SPEED, 0.0001)
	player.stance = GameTypes.Stance.SNEAK
	assert_near(player.move_speed(), StealthPlayer.SNEAK_SPEED, 0.0001)
	player.low_sanity_slow = true
	assert_near(player.move_speed(), StealthPlayer.SNEAK_SPEED * 0.75, 0.0001)
	player.low_sanity_slow = false
	player.is_vision_active = true
	assert_near(player.move_speed(), StealthPlayer.SNEAK_SPEED * StealthPlayer.VISION_SPEED_MULTIPLIER, 0.0001)
