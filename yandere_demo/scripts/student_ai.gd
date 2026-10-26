class_name StudentAI
extends CastCharacter
## A background student (spec §4.5): wanders between StudentSpots in free blocks, sits at an assigned seat in class,
## gives the player crowd cover and may witness a camera flash. `variant` picks the model, hair and palette.

enum Mode { IDLE, TO_SPOT, AT_SPOT, TO_SEAT, ENTERING_SEAT, SEATED, LEAVING_SEAT }

const GROUP: StringName = &"students"
const FEMALE_MODEL: PackedScene = preload("res://assets/models/student_female.glb")
const MALE_MODEL: PackedScene = preload("res://assets/models/student_male.glb")
const FEMALE_HAIR_STYLES: Array[StringName] = [&"Hair_bob", &"Hair_long", &"Hair_twintails"]
const MALE_HAIR_STYLES: Array[StringName] = [&"Hair_short", &"Hair_messy"]
const HAIR_PREFIX: String = "Hair_"
const MATERIAL_UNIFORM: String = "M_UniformTint"
const MATERIAL_NECKERCHIEF: String = "M_Neckerchief"
const MATERIAL_HAIR: String = "M_Hair"
const MATERIAL_HAIR_SHADE: String = "M_HairShade"
const ALBEDO_PARAMETER: StringName = &"albedo_color"
const ANIMATION_IDLE: StringName = &"student_idle"
const ANIMATION_WALK: StringName = &"student_walk"
const ANIMATION_SIT: StringName = &"student_sit"
const SPOT_PREFIX: String = "StudentSpot_"
const WITNESS_REASON: StringName = &"student_witness"
## Independent bit ranges of the variant hash pick the hair style, the palette and the hair colour.
const STYLE_SHIFT: int = 1
const PALETTE_SHIFT: int = 8
const HAIR_COLOR_SHIFT: int = 16

@export var variant: int = 0

var seat: Node3D
## Injected until the Task 18 autoload holds the meters.
var meters: StealthMeters
var mode: Mode = Mode.IDLE

var _random: RandomNumberGenerator = RandomNumberGenerator.new()
var _spot: Node3D
var _spot_seconds_left: float = 0.0
var _seconds_since_witness: float = INF
var _after_leaving_seat: Callable


func _ready() -> void:
	add_to_group(GROUP)
	var model: Node3D = (FEMALE_MODEL if is_female() else MALE_MODEL).instantiate() as Node3D
	model.name = "Model"
	model.rotation.y = PI
	add_child(model)
	_apply_looks(model)
	var body_shape: CharacterBodyShape = CharacterBodyShape.new()
	body_shape.name = "CharacterBodyShape"
	body_shape.model_path = ^"../Model"
	add_child(body_shape)
	_attach_model(model, body_shape, ANIMATION_IDLE, ANIMATION_WALK)


func is_female() -> bool:
	return posmod(variant, 2) == 0


func setup(school_env: SchoolEnv, assigned_seat: Node3D, random_seed: int) -> void:
	school = school_env
	seat = assigned_seat
	_random.seed = random_seed
	_agent.set_navigation_map(school.navigation_map())
	_reset_motion()
	if clock == null:
		clock = _autoload_clock()
	if clock == null:
		_begin_wander()
		return
	if not clock.block_changed.is_connected(on_block_changed):
		clock.block_changed.connect(on_block_changed)
	on_block_changed(clock.current_block())


func on_block_changed(block: ScheduleBlock) -> void:
	if school == null:
		return
	var next: Callable = _go_to_seat if block.kind == GameTypes.BlockKind.CLASS else _begin_wander
	if _seated:
		_leave_seat(next)
	else:
		next.call()


func snap_to_seat() -> void:
	if seat == null:
		return
	global_position = seat.global_position
	rotation.y = seat.global_rotation.y
	velocity = Vector3.ZERO
	_reset_motion()
	_gliding = false
	_set_seated(true)
	mode = Mode.SEATED
	_playback.start(ANIMATION_SIT)


## Witness hook for photo mode (Task 17): a flash within `witness_range` in this student's view adds
## `student_witness` School Alert, at most once per `witness_cooldown_seconds`.
func on_flash(flash_position: Vector3) -> void:
	if meters == null or _seconds_since_witness < tuning.witness_cooldown_seconds:
		return
	var eye: Vector3 = head_position()
	if not Detection.is_in_view_cone(eye, body_forward(), flash_position, tuning.witness_fov_degrees, tuning.witness_range):
		return
	if not Detection.has_line_of_sight(get_world_3d().direct_space_state, eye, flash_position, []):
		return
	_seconds_since_witness = 0.0
	meters.add_alert_spike(WITNESS_REASON)


func _step_behaviour(delta: float) -> void:
	_seconds_since_witness += delta
	if school == null:
		return
	match mode:
		Mode.TO_SPOT:
			if _step_walk(delta):
				_arrive_at_spot()
		Mode.AT_SPOT:
			_step_halt(delta)
			_turn_toward(_spot.global_rotation.y, delta)
			_spot_seconds_left -= delta
			if _spot_seconds_left <= 0.0:
				_begin_wander()
		Mode.TO_SEAT:
			if _step_walk(delta):
				_arrive_near_seat()
		Mode.ENTERING_SEAT:
			if _step_glide(delta):
				mode = Mode.SEATED
				_play(ANIMATION_SIT)
		Mode.LEAVING_SEAT:
			if _step_glide(delta):
				_set_seated(false)
				_reset_motion()
				_after_leaving_seat.call()
		_:
			_step_halt(delta)


func _begin_wander() -> void:
	var spots: Array[Node3D] = school.markers_with_prefix(SPOT_PREFIX)
	spots.erase(_spot)
	while not spots.is_empty():
		_spot = spots.pop_at(_random.randi_range(0, spots.size() - 1))
		if _walk_to(_spot.global_position):
			mode = Mode.TO_SPOT
			return
	_idle()


func _arrive_at_spot() -> void:
	mode = Mode.AT_SPOT
	_spot_seconds_left = _random.randf_range(tuning.student_spot_min_seconds, tuning.student_spot_max_seconds)
	var pastimes: Array[StringName] = tuning.student_spot_animations
	_play(pastimes[_random.randi_range(0, pastimes.size() - 1)])


func _go_to_seat() -> void:
	if seat == null or not _walk_to(seat.global_position):
		_idle()
		return
	mode = Mode.TO_SEAT


## Seats sit off the navmesh (ruling R12): finishing within `seated_arrive_distance` glides the rest of the way.
func _arrive_near_seat() -> void:
	if global_position.distance_to(seat.global_position) > tuning.seated_arrive_distance:
		_idle()
		return
	_begin_glide(seat.global_position, seat.global_rotation.y)
	_set_seated(true)
	mode = Mode.ENTERING_SEAT


func _leave_seat(then: Callable) -> void:
	var aisle: Vector3 = NavigationServer3D.map_get_closest_point(school.navigation_map(), global_position)
	aisle.y = global_position.y
	_after_leaving_seat = then
	_begin_glide(aisle, rotation.y)
	mode = Mode.LEAVING_SEAT
	_play(STATE_LOCOMOTION)


func _idle() -> void:
	mode = Mode.IDLE
	_play(STATE_LOCOMOTION)


func _apply_looks(model: Node3D) -> void:
	var styles: Array[StringName] = FEMALE_HAIR_STYLES if is_female() else MALE_HAIR_STYLES
	var style: StringName = styles[posmod(variant >> STYLE_SHIFT, styles.size())]
	var hair_color: Color = tuning.hair_colors[posmod(variant >> HAIR_COLOR_SHIFT, tuning.hair_colors.size())]
	var tints: Dictionary = {
		MATERIAL_HAIR: hair_color,
		MATERIAL_HAIR_SHADE: hair_color.darkened(1.0 - tuning.hair_shade_ratio),
	}
	var uniforms: Array[Color] = tuning.female_uniform_colors if is_female() else tuning.male_uniform_colors
	var palette: int = posmod(variant >> PALETTE_SHIFT, uniforms.size())
	tints[MATERIAL_UNIFORM] = uniforms[palette]
	if is_female():
		tints[MATERIAL_NECKERCHIEF] = tuning.female_neckerchief_colors[palette]
	var tinted: Dictionary = {}
	for node: Node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance: MeshInstance3D = node as MeshInstance3D
		if String(mesh_instance.name).begins_with(HAIR_PREFIX):
			mesh_instance.visible = mesh_instance.name == style
		for surface: int in mesh_instance.mesh.get_surface_count():
			var material: ShaderMaterial = mesh_instance.mesh.surface_get_material(surface) as ShaderMaterial
			if material == null or not tints.has(material.resource_name):
				continue
			if not tinted.has(material.resource_name):
				var copy: ShaderMaterial = material.duplicate() as ShaderMaterial
				copy.set_shader_parameter(ALBEDO_PARAMETER, tints[material.resource_name])
				tinted[material.resource_name] = copy
			mesh_instance.set_surface_override_material(surface, tinted[material.resource_name])
