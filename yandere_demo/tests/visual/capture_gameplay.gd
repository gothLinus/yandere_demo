extends VisualCapture
## Windowed gameplay captures (Task 22). The default run plays one test-mode day on main.tscn and saves the hallway,
## courtyard, viewfinder and Yandere Vision shots, the hide spots, the camera prop and every UI screen, then the
## main menu and the stranger and cherry-tree endings. With `-- --movie` it instead frames one seated activity for a movie capture:
##   godot --path yandere_demo --write-movie <dir>/frame.png --fixed-fps 30 res://tests/visual/capture_gameplay.tscn -- --movie
## `--movie-activity=<id>` picks the activity (default read_bench, a walk -> target_sit_down -> target_sit_read);
## the run quits MOVIE_SECONDS after the walk starts and prints that frame's number.

const MAIN_SCENE: PackedScene = preload("res://scenes/main.tscn")
const MAIN_MENU_SCENE: PackedScene = preload("res://scenes/ui/main_menu.tscn")
const ENDING_SCENE: PackedScene = preload("res://scenes/ending.tscn")
const SCHOOL_ENV_SCENE: PackedScene = preload("res://scenes/school_env.tscn")
const TARGET_SCENE: PackedScene = preload("res://scenes/target.tscn")
const ACTIVITY_POOL: ActivityPool = preload("res://data/activity_pool.tres")
const TEST_SAVE_PATH: String = "user://test_save.json"
const MOVIE_ARGUMENT: String = "--movie"
const MOVIE_ACTIVITY_PREFIX: String = "--movie-activity="
const DEFAULT_MOVIE_ACTIVITY: StringName = &"read_bench"
const MOVIE_SECONDS: float = 6.0
const MOVIE_WALK_DISTANCE: float = 4.0
const PLANNED_MINUTES: float = 30.0
const BENCH_ACTIVITY: StringName = &"read_bench"
const SITTING_DEADLINE_SECONDS: float = 20.0
const SETTLE_SECONDS: float = 0.6
const HALLWAY_POSITION: Vector3 = Vector3(0.3, 0.0, -25.6)
const COURTYARD_PLAYER_POSITION: Vector3 = Vector3(16.0, 0.0, -30.5)
const COURTYARD_OVERVIEW_FROM: Vector3 = Vector3(1.0, 9.0, -8.0)
const COURTYARD_OVERVIEW_AT: Vector3 = Vector3(12.5, 1.0, -31.0)
const ENDING_CAPTURE_SECONDS: Array[float] = [0.5, 3.0, 6.0, 9.0, 11.5]
const ENDING_TITLE_WAIT_SECONDS: float = 2.0

var _main: Node
var _player: StealthPlayer
var _target: TargetAI
var _school_env: SchoolEnv
var _rig: PlayerCameraRig
var _free_camera: Camera3D = Camera3D.new()


func _ready() -> void:
	_free_camera.name = "FreeCamera"
	add_child(_free_camera)
	var arguments: PackedStringArray = OS.get_cmdline_user_args()
	if arguments.has(MOVIE_ARGUMENT):
		await _run_movie(_movie_activity(arguments))
	else:
		await _run_gameplay()
		await _capture_main_menu()
		await _capture_ending(&"stranger")
		await _capture_ending(&"cherry_tree")
	finish()


func _run_gameplay() -> void:
	SaveStore.erase(TEST_SAVE_PATH)
	GameManager.test_mode = true
	_main = MAIN_SCENE.instantiate()
	add_child(_main)
	var tree: SceneTree = get_tree()
	_player = tree.get_first_node_in_group(&"player") as StealthPlayer
	_target = tree.get_first_node_in_group(&"target") as TargetAI
	_school_env = tree.get_first_node_in_group(&"school_env") as SchoolEnv
	_rig = _player.get_node(^"CameraRig") as PlayerCameraRig
	_player.can_hide_callable = func() -> bool: return true
	GameManager.new_week()
	await GameManager.day_started
	# The rig captured the mouse; give it back to the desktop while the window runs by itself.
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	_send_target_to_bench()
	await _capture_bell_banners()
	await _capture_hallway()
	await _capture_hide_spots()
	await _capture_courtyard()
	await _capture_camera_mode()
	await _capture_vision()
	await _capture_screens()
	_main.queue_free()
	await wait_frames(2)


func _send_target_to_bench() -> void:
	var anchor: Node3D = _school_env.anchors_for(BENCH_ACTIVITY)[0]
	_target.global_position = _closest_navigation_point(anchor.global_position + Vector3(-2.5, 0.0, 2.5))
	_target.start_plan([_planned(BENCH_ACTIVITY, 0)])


## The class banner counts down from the current block's start, so it runs while the day is only seconds old.
func _capture_bell_banners() -> void:
	_place_player(HALLWAY_POSITION, 0.0)
	var banner: Node = _main.find_child("BellBanner", true, false)
	for block: ScheduleBlock in SchoolClock.schedule.blocks:
		if block.kind == GameTypes.BlockKind.CLASS:
			banner.call(&"_on_bell_rang", block)
			break
	await wait_seconds(1.0)
	await save_capture("bell_banner_class")
	banner.call(&"_on_bell_rang", SchoolClock.schedule.blocks.back())
	await wait_seconds(1.0)
	await save_capture("bell_banner_free")


func _capture_hallway() -> void:
	_place_player(HALLWAY_POSITION, 0.0)
	_player.pick_up(&"pen")
	SanitySystem.meters.add_suspicion_spike(35.0)
	SanitySystem.meters.add_alert_spike(&"late")
	await wait_seconds(SETTLE_SECONDS)
	await save_capture("hud_hallway")
	_player.drop_carried()


func _capture_hide_spots() -> void:
	var locker: HideSpot = _school_env.get_node(^"Interactable_HideLocker_01") as HideSpot
	_place_player(locker.global_position + locker.global_basis.z * 0.6, locker.global_rotation.y + PI)
	await wait_seconds(SETTLE_SECONDS)
	locker.interact(_player)
	await wait_seconds(1.0)
	await save_capture("hide_locker_peek")
	_look_from(locker.global_transform * Vector3(0.9, 1.3, 1.6), locker.global_transform * Vector3(0.0, 1.0, -0.4))
	await save_capture("hide_locker_outside")
	_look_from(locker.global_transform * Vector3(0.6, 0.9, -0.2), locker.global_transform * Vector3(-0.1, 0.9, -0.42))
	await save_capture("hide_locker_door_edge")
	_rig_camera_current()
	locker.interact(_player)
	var desk: HideSpot = _school_env.get_node(^"Interactable_HideDesk_01") as HideSpot
	_place_player(desk.global_position + desk.global_basis.x * 0.9, desk.global_rotation.y)
	await wait_seconds(SETTLE_SECONDS)
	desk.interact(_player)
	await wait_seconds(1.0)
	await save_capture("hide_desk_peek")
	_look_from(desk.global_transform * Vector3(1.6, 1.1, 0.9), desk.global_transform * Vector3(0.0, 0.7, 0.0))
	await save_capture("hide_desk_outside")
	_look_from(desk.global_transform * Vector3(1.5, 0.8, 0.0), desk.global_transform * Vector3(0.0, 0.8, 0.0))
	await save_capture("hide_desk_side")
	_rig_camera_current()
	desk.interact(_player)


func _capture_courtyard() -> void:
	var to_bench: Vector3 = _school_env.anchors_for(BENCH_ACTIVITY)[0].global_position - COURTYARD_PLAYER_POSITION
	_place_player(COURTYARD_PLAYER_POSITION, atan2(-to_bench.x, -to_bench.z))
	await _wait_until_sitting()
	await wait_seconds(SETTLE_SECONDS)
	await save_capture("courtyard")
	_look_from(COURTYARD_OVERVIEW_FROM, COURTYARD_OVERVIEW_AT)
	await save_capture("courtyard_overview")
	for tree_index: int in range(1, 5):
		var foliage: Node3D = _school_env.find_child("CherryFoliage_%02d" % tree_index, true, false) as Node3D
		if foliage == null:
			continue
		var center: Vector3 = (foliage as MeshInstance3D).global_transform * (foliage as MeshInstance3D).get_aabb().get_center()
		_look_from(center + Vector3(6.0, -1.5, 6.0), center + Vector3(0.0, -1.5, 0.0))
		await save_capture("cherry_tree_%02d" % tree_index)
	_look_from(_school_env.marker("EndingStand_Player").global_position + Vector3(0.0, 1.5, 0.0),
			_school_env.marker("EndingStand_Target").global_position + Vector3(0.0, 2.5, 0.0))
	await save_capture("petals_near_camera")
	_rig_camera_current()


func _capture_camera_mode() -> void:
	var head: Vector3 = _target.head_position()
	var to_target: Vector3 = head - _player.global_position
	_rig.yaw = atan2(-to_target.x, -to_target.z)
	_rig.pitch = 0.0
	_player.rotation.y = _rig.yaw
	_player.enter_camera_mode()
	await wait_seconds(1.0)
	await save_capture("viewfinder")
	var hand: Node3D = _player.find_child("CameraPropAttachment", true, false) as Node3D
	var forward: Vector3 = -_player.global_basis.z
	var right: Vector3 = _player.global_basis.x
	_look_from(hand.global_position + forward * 0.5 + right * 0.25 + Vector3.UP * 0.05, hand.global_position)
	await save_capture("camera_prop_front")
	_look_from(hand.global_position + right * 0.5 - forward * 0.05 + Vector3.UP * 0.05, hand.global_position)
	await save_capture("camera_prop_side")
	_look_from(hand.global_position + Vector3.UP * 0.5 + forward * 0.1, hand.global_position)
	await save_capture("camera_prop_top")
	_look_from(_player.global_position + forward * 2.2 + Vector3.UP * 1.3, _player.global_position + Vector3.UP * 1.2)
	await save_capture("camera_prop_full_body")
	_rig_camera_current()
	(_player.get_node(^"PhotoMode") as PhotoMode).snap()
	await wait_seconds(0.05)
	await save_capture("viewfinder_shutter")
	await wait_seconds(1.0)
	_player.exit_camera_mode()


func _capture_vision() -> void:
	_rig.pitch = deg_to_rad(-10.0)
	var vision: YandereVision = _player.get_node(^"YandereVision") as YandereVision
	vision.set_vision(true)
	await wait_seconds(SETTLE_SECONDS)
	await save_capture("yandere_vision")
	vision.set_vision(false)


func _capture_screens() -> void:
	SanitySystem.meters.call(&"_set_sanity", 15.0)
	await wait_seconds(1.0)
	await save_capture("hud_low_sanity")
	SanitySystem.meters.call(&"_set_sanity", 100.0)
	var class_fade: ClassFade = _main.find_child("ClassFade", true, false) as ClassFade
	await class_fade.fade_out()
	await save_capture("class_fade")
	await class_fade.fade_in()
	var album: Album = _main.find_child("Album", true, false) as Album
	album.open()
	var tabs: TabContainer = album.find_child("Tabs", true, false) as TabContainer
	for tab_index: int in tabs.get_tab_count():
		tabs.current_tab = tab_index
		await wait_seconds(0.3)
		await save_capture("album_%s" % tabs.get_tab_title(tab_index).to_lower())
	album.close()
	var pause_menu: PauseMenu = _main.find_child("PauseMenu", true, false) as PauseMenu
	pause_menu.call(&"_open")
	await wait_seconds(0.3)
	await save_capture("pause_menu")
	pause_menu.resume()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	GameManager.complete_day()
	await wait_seconds(0.5)
	await save_capture("day_summary")
	var summary: DaySummary = _main.find_child("DaySummary", true, false) as DaySummary
	(summary.get_node(^"Root") as Control).visible = false
	GameManager.game_over.emit(&"target_report")
	await wait_seconds(0.5)
	await save_capture("game_over")


func _capture_main_menu() -> void:
	var menu: Node = MAIN_MENU_SCENE.instantiate()
	add_child(menu)
	await wait_seconds(2.0)
	await save_capture("main_menu")
	menu.queue_free()
	await wait_frames(2)


func _capture_ending(ending_id: StringName) -> void:
	var ending: EndingDirector = ENDING_SCENE.instantiate() as EndingDirector
	add_child(ending)
	var school_env: SchoolEnv = ending.get_node(^"SchoolEnv") as SchoolEnv
	if not school_env.is_navigation_ready:
		await school_env.navigation_ready
	var started_msec: int = Time.get_ticks_msec()
	ending.ending_finished.connect(func(_id: StringName) -> void:
		print("ENDING %s finished after %.1f s (time scale %.1f)" % [ending_id, (Time.get_ticks_msec() - started_msec) / 1000.0, Engine.time_scale]))
	ending.play(ending_id, WeekProgress.new())
	var elapsed: float = 0.0
	for capture_second: float in ENDING_CAPTURE_SECONDS:
		await wait_seconds(capture_second - elapsed)
		elapsed = capture_second
		await save_capture("ending_%s_%03ds" % [ending_id, roundi(capture_second * 10.0)])
	# The sequence cuts to the title card after EndingDirector.SEQUENCE_SECONDS; the card then fades in.
	await wait_seconds(EndingDirector.SEQUENCE_SECONDS - elapsed + ENDING_TITLE_WAIT_SECONDS)
	await save_capture("ending_%s_title" % ending_id)
	ending.queue_free()
	await wait_frames(2)


func _run_movie(activity_id: StringName) -> void:
	_school_env = SCHOOL_ENV_SCENE.instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_target = TARGET_SCENE.instantiate() as TargetAI
	add_child(_target)
	_target.setup(_school_env, 1, ActivityHistory.new())
	var anchor: Node3D = _school_env.anchors_for(activity_id)[0]
	var anchor_forward: Vector3 = -anchor.global_basis.z
	var side: Vector3 = anchor_forward.cross(Vector3.UP)
	_target.global_position = _closest_navigation_point(anchor.global_position + anchor_forward * MOVIE_WALK_DISTANCE * 0.6 + side * MOVIE_WALK_DISTANCE * 0.8)
	# Three-quarter front view of the seat, far enough back to hold the whole walk.
	_look_from(anchor.global_position + anchor_forward * 3.2 - side * 2.0 + Vector3.UP * 1.5, anchor.global_position + Vector3.UP * 0.7)
	await get_tree().physics_frame
	_target.start_plan([_planned(activity_id, 0)])
	print("MOVIE %s walk starts at frame %d" % [activity_id, Engine.get_process_frames()])
	_target.activity_started.connect(func(activity: ActivityDefinition) -> void:
		print("MOVIE activity %s started at frame %d" % [activity.id, Engine.get_process_frames()]))
	for second: int in int(MOVIE_SECONDS):
		await wait_seconds(1.0)
		print("MOVIE t=%d s at frame %d: %s, %.2f m from the anchor" % [second + 1, Engine.get_process_frames(), TargetAI.State.keys()[_target.state], _target.global_position.distance_to(anchor.global_position)])
	print("MOVIE ends at frame %d" % Engine.get_process_frames())


func _movie_activity(arguments: PackedStringArray) -> StringName:
	for argument: String in arguments:
		if argument.begins_with(MOVIE_ACTIVITY_PREFIX):
			return StringName(argument.trim_prefix(MOVIE_ACTIVITY_PREFIX))
	return DEFAULT_MOVIE_ACTIVITY


func _wait_until_sitting() -> void:
	var seconds: float = 0.0
	while seconds < SITTING_DEADLINE_SECONDS:
		var activity: ActivityDefinition = _target.current_activity()
		if activity != null and activity.id == BENCH_ACTIVITY:
			return
		await get_tree().process_frame
		seconds += get_process_delta_time()
	push_warning("CaptureGameplay: the target did not start %s within %.0f s" % [BENCH_ACTIVITY, SITTING_DEADLINE_SECONDS])


func _place_player(at: Vector3, yaw: float) -> void:
	_player.global_position = at
	_player.rotation.y = yaw
	_player.velocity = Vector3.ZERO
	_rig.yaw = yaw
	_rig.pitch = deg_to_rad(-10.0)


func _look_from(from: Vector3, at: Vector3) -> void:
	_free_camera.global_position = from
	_free_camera.look_at(at)
	_free_camera.make_current()


func _rig_camera_current() -> void:
	_free_camera.clear_current(false)
	_player.current_camera().make_current()


func _closest_navigation_point(point: Vector3) -> Vector3:
	return NavigationServer3D.map_get_closest_point(_school_env.navigation_map(), point)


func _planned(activity_id: StringName, anchor_index: int) -> PlannedActivity:
	var planned: PlannedActivity = PlannedActivity.new()
	planned.activity = ACTIVITY_POOL.find(activity_id)
	planned.anchor_index = anchor_index
	planned.duration_minutes = PLANNED_MINUTES
	return planned
