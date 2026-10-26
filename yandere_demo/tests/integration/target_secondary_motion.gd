extends IntegrationTest
## Ruling R10: with SecondaryMotion active, the braid and its bow stay near the baked pose, the bow stays outside the
## skirt and the legs stay inside it. A simulated target and an unsimulated twin play the same clips:
## a 1.3 m/s walk, a stop with a 135 degree turn into target_idle_playful, target_idle_playful held, then
## target_fix_braid. Joint positions compare in the skeleton's own space. The skirt surface is skinned on the CPU
## and binned by azimuth and height around the hips axis, so a bow vertex inside the outermost skirt vertex of its
## bin is a clip, and a leg vertex outside it pokes through.

const TARGET_MODEL_PATH: String = "res://assets/models/target.glb"
const TUNING_PATH: String = "res://data/secondary_motion.tres"
const FRAME_SECONDS: float = 1.0 / 30.0
const WALK_SPEED: float = 1.3
const SETTLE_FRAMES: int = 30
const STOP_FRAME: int = 150
const TURN_FRAMES: int = 20
const TURN_RADIANS: float = PI * 0.75
const FIX_BRAID_FRAME: int = 300
const END_FRAME: int = 420
const CROSSFADE_SECONDS: float = 0.3
const MEASURE_EVERY_FRAMES: int = 3
const MAX_DRIFT: float = 0.08
## Bin-quantisation allowance: the skirt bins are 4 degrees by 2 cm, so their outermost vertex can sit a few
## millimetres outside the fabric under a bow or leg vertex.
const SURFACE_TOLERANCE: float = 0.004
const AZIMUTH_BINS: int = 90
const HEIGHT_BIN_METERS: float = 0.02
const EDGE_BINS: int = 2
const BRAID_PREFIX: StringName = &"braid"
const BOW_PREFIX: StringName = &"braid_bow"
const FIX_BRAID_ANIMATION: StringName = &"target_fix_braid"
const LEG_BONES: Array[String] = ["thigh.L", "thigh.R", "shin.L", "shin.R"]


class SkinnedVertices:
	extends RefCounted
	## A subset of a skinned mesh's vertices, deformed on the CPU from a skeleton's current pose.

	var _positions: PackedVector3Array = PackedVector3Array()
	var _bones: PackedInt32Array = PackedInt32Array()
	var _weights: PackedFloat32Array = PackedFloat32Array()
	var _bind_bones: PackedInt32Array = PackedInt32Array()
	var _bind_poses: Array[Transform3D] = []

	func _init(instance: MeshInstance3D, skeleton: Skeleton3D, keep: Callable) -> void:
		for bind_index: int in instance.skin.get_bind_count():
			_bind_bones.append(skeleton.find_bone(instance.skin.get_bind_name(bind_index)))
			_bind_poses.append(instance.skin.get_bind_pose(bind_index))
		for surface_index: int in instance.mesh.get_surface_count():
			var arrays: Array = instance.mesh.surface_get_arrays(surface_index)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var influences: int = bones.size() / vertices.size()
			for vertex_index: int in vertices.size():
				var dominant_bind: int = bones[vertex_index * influences]
				if not keep.call(skeleton.get_bone_name(_bind_bones[dominant_bind]), vertices[vertex_index]):
					continue
				_positions.append(vertices[vertex_index])
				for slot: int in 4:
					var source: int = vertex_index * influences + slot
					_bones.append(bones[source] if slot < influences else 0)
					_weights.append(weights[source] if slot < influences else 0.0)

	func size() -> int:
		return _positions.size()

	func deform(skeleton: Skeleton3D) -> PackedVector3Array:
		var bind_transforms: Array[Transform3D] = []
		for bind_index: int in _bind_bones.size():
			var bone: int = _bind_bones[bind_index]
			bind_transforms.append(skeleton.get_bone_global_pose(bone) * _bind_poses[bind_index] if bone >= 0 else Transform3D())
		var deformed: PackedVector3Array = PackedVector3Array()
		deformed.resize(_positions.size())
		for vertex_index: int in _positions.size():
			var position: Vector3 = Vector3.ZERO
			for slot: int in 4:
				var weight: float = _weights[vertex_index * 4 + slot]
				if weight > 0.0:
					position += (bind_transforms[_bones[vertex_index * 4 + slot]] * _positions[vertex_index]) * weight
			deformed[vertex_index] = position
		return deformed


class Rig:
	extends RefCounted
	## One instanced target: its skeleton, animation player and CPU-skinned skirt, bow and leg samples.

	var model: Node3D
	var skeleton: Skeleton3D
	var player: AnimationPlayer
	var skirt: SkinnedVertices
	var bow: SkinnedVertices
	var legs: Array[SkinnedVertices] = []

	func _init(parent: Node, path: String) -> void:
		model = (load(path) as PackedScene).instantiate() as Node3D
		parent.add_child(model)
		skeleton = model.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
		skeleton.modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
		player = model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var skirt_top: float = skeleton.get_bone_global_rest(skeleton.find_bone("skirt_00_01")).origin.y
		skirt = SkinnedVertices.new(model.find_child("TargetSkirt", true, false) as MeshInstance3D, skeleton,
				func(_bone: String, _vertex: Vector3) -> bool: return true)
		bow = SkinnedVertices.new(model.find_child("TargetAccessories", true, false) as MeshInstance3D, skeleton,
				func(bone: String, _vertex: Vector3) -> bool: return bone == "braid_bow")
		var keep_leg: Callable = func(bone: String, vertex: Vector3) -> bool:
			return LEG_BONES.has(bone) and vertex.y < skirt_top
		for mesh_name: String in ["TargetBody", "TargetSocks"]:
			legs.append(SkinnedVertices.new(model.find_child(mesh_name, true, false) as MeshInstance3D, skeleton, keep_leg))

	func leg_vertex_count() -> int:
		var count: int = 0
		for sampler: SkinnedVertices in legs:
			count += sampler.size()
		return count

	func step(seconds: float) -> void:
		player.advance(seconds)
		skeleton.advance(seconds)


var _tuning: SecondaryMotionTuning
var _simulated: Rig
var _baked: Rig
var _secondary_motion: SecondaryMotion
var _frame: int = 0
var _max_drift: Dictionary[StringName, float] = {}
var _phase_drift: Dictionary[String, float] = {}
var _min_bow_margin: Dictionary[String, float] = {"simulated": INF, "baked": INF}
var _min_leg_margin: Dictionary[String, float] = {"simulated": INF, "baked": INF}
var _min_capsule_clearance: Dictionary[StringName, float] = {}
var _fix_braid_influence: float = -1.0
var _worst_leg: Dictionary[String, String] = {}
var _measured_frame: int = -1


func _ready() -> void:
	timeout_seconds = 240.0
	_tuning = load(TUNING_PATH) as SecondaryMotionTuning
	_simulated = Rig.new(self, TARGET_MODEL_PATH)
	_baked = Rig.new(self, TARGET_MODEL_PATH)
	_baked.model.visible = false
	_secondary_motion = SecondaryMotion.new()
	_secondary_motion.tuning = _tuning
	_secondary_motion.skeleton_path = _simulated.skeleton.get_path()
	add_child(_secondary_motion)
	# Modifier output is only in the bone poses during the skeleton's update.
	_simulated.skeleton.skeleton_updated.connect(_on_simulated_skeleton_updated)
	for rig: Rig in [_simulated, _baked]:
		rig.player.play(&"target_walk_routine")
	print("samples: skirt %d, bow %d, legs %d" % [_simulated.skirt.size(), _simulated.bow.size(), _simulated.leg_vertex_count()])
	if _simulated.bow.size() == 0 or _simulated.leg_vertex_count() == 0 or _simulated.skirt.size() == 0:
		fail_test("no skirt, bow or leg vertices to measure")


func _process(delta: float) -> void:
	super._process(delta)
	if _frame >= END_FRAME:
		return
	_advance_frame()
	_frame += 1
	if _frame == END_FRAME:
		_report()


func _advance_frame() -> void:
	if _frame == STOP_FRAME:
		for rig: Rig in [_simulated, _baked]:
			rig.player.play(&"target_idle_playful", CROSSFADE_SECONDS)
	if _frame == FIX_BRAID_FRAME:
		for rig: Rig in [_simulated, _baked]:
			rig.player.play(FIX_BRAID_ANIMATION, CROSSFADE_SECONDS)
		_secondary_motion.on_animation_changed(FIX_BRAID_ANIMATION)
	for rig: Rig in [_baked, _simulated]:
		if _frame < STOP_FRAME:
			rig.model.position.z = WALK_SPEED * _frame * FRAME_SECONDS
		else:
			rig.model.rotation.y = lerp_angle(0.0, TURN_RADIANS, clampf(float(_frame - STOP_FRAME) / TURN_FRAMES, 0.0, 1.0))
		rig.step(FRAME_SECONDS)


func _on_simulated_skeleton_updated() -> void:
	if _frame > SETTLE_FRAMES and _frame < END_FRAME and _frame != _measured_frame:
		_measured_frame = _frame
		_measure()


func _phase() -> String:
	if _frame < STOP_FRAME:
		return "walk"
	if _frame < FIX_BRAID_FRAME:
		return "stop_turn_idle_playful"
	return "fix_braid"


func _measure() -> void:
	var phase: String = _phase()
	for setting: SecondaryChainSetting in _tuning.chains:
		var prefix: StringName = setting.chain_prefix
		var simulated_joints: PackedVector3Array = _joints(_simulated.skeleton, setting)
		var baked_joints: PackedVector3Array = _joints(_baked.skeleton, setting)
		for joint_index: int in simulated_joints.size():
			var drift: float = simulated_joints[joint_index].distance_to(baked_joints[joint_index])
			var key: String = "%s %s" % [prefix, phase]
			_phase_drift[key] = maxf(_phase_drift.get(key, 0.0), drift)
			if phase != "fix_braid":
				_max_drift[prefix] = maxf(_max_drift.get(prefix, 0.0), drift)
	if phase == "fix_braid":
		_fix_braid_influence = _secondary_motion.simulator_for(BRAID_PREFIX).influence
		return
	_measure_capsule_clearance()
	if _frame % MEASURE_EVERY_FRAMES == 0:
		_measure_skirt("simulated", _simulated)
		_measure_skirt("baked", _baked)


## Every simulated joint's clearance from its family's capsules, allowing for the joint radius.
func _measure_capsule_clearance() -> void:
	var skeleton: Skeleton3D = _simulated.skeleton
	for setting: SecondaryChainSetting in _tuning.chains:
		for collider_bone: StringName in setting.colliders:
			var entry: SecondaryCollider = _tuning.collider(collider_bone)
			var pose: Transform3D = skeleton.get_bone_global_pose(skeleton.find_bone(entry.bone))
			var capsule: Transform3D = pose * Transform3D(Basis(entry.rotation_offset), entry.position_offset)
			var half: float = maxf(0.0, entry.height * 0.5 - entry.radius)
			var segment_start: Vector3 = capsule * Vector3(0.0, -half, 0.0)
			var segment_end: Vector3 = capsule * Vector3(0.0, half, 0.0)
			for joint: Vector3 in _joints(skeleton, setting):
				var closest: Vector3 = Geometry3D.get_closest_point_to_segment(joint, segment_start, segment_end)
				var clearance: float = joint.distance_to(closest) - entry.radius - setting.radius
				_min_capsule_clearance[setting.chain_prefix] = minf(_min_capsule_clearance.get(setting.chain_prefix, INF), clearance)


func _measure_skirt(label: String, rig: Rig) -> void:
	var hips: Transform3D = rig.skeleton.get_bone_global_pose(rig.skeleton.find_bone("hips"))
	var outermost: Dictionary[Vector2i, float] = {}
	for vertex: Vector3 in rig.skirt.deform(rig.skeleton):
		var cylinder: Vector3 = _cylinder(hips, vertex)
		var bin: Vector2i = _bin(cylinder)
		outermost[bin] = maxf(outermost.get(bin, 0.0), cylinder.x)
	# A leg below the hem or above the waistband is not under the fabric, so only bins with skirt above and below count.
	var covered: Dictionary[Vector2i, float] = {}
	for bin: Vector2i in outermost:
		if outermost.has(bin + Vector2i(0, EDGE_BINS)) and outermost.has(bin - Vector2i(0, EDGE_BINS)):
			covered[bin] = outermost[bin]
	for vertex: Vector3 in rig.bow.deform(rig.skeleton):
		var skirt_radius: float = _skirt_radius(outermost, _cylinder(hips, vertex))
		if skirt_radius > 0.0:
			_min_bow_margin[label] = minf(_min_bow_margin[label], _cylinder(hips, vertex).x - skirt_radius)
	for sampler: SkinnedVertices in rig.legs:
		for vertex: Vector3 in sampler.deform(rig.skeleton):
			var skirt_radius: float = _skirt_radius(covered, _cylinder(hips, vertex))
			if skirt_radius > 0.0 and skirt_radius - _cylinder(hips, vertex).x < _min_leg_margin[label]:
				_min_leg_margin[label] = skirt_radius - _cylinder(hips, vertex).x
				_worst_leg[label] = "f%d cylinder %s" % [_frame, _cylinder(hips, vertex)]


## (radius from the hips axis, azimuth, height along it) of a skeleton-space point.
func _cylinder(hips: Transform3D, point: Vector3) -> Vector3:
	var local: Vector3 = hips.affine_inverse() * point
	return Vector3(Vector2(local.x, local.z).length(), atan2(local.x, local.z), local.y)


func _bin(cylinder: Vector3) -> Vector2i:
	var azimuth_bin: int = posmod(floori((cylinder.y + PI) / TAU * AZIMUTH_BINS), AZIMUTH_BINS)
	return Vector2i(azimuth_bin, floori(cylinder.z / HEIGHT_BIN_METERS))


## The outermost skirt radius in the point's bin, or 0 when the skirt does not reach that azimuth and height.
func _skirt_radius(outermost: Dictionary[Vector2i, float], cylinder: Vector3) -> float:
	return outermost.get(_bin(cylinder), 0.0) + SURFACE_TOLERANCE if outermost.has(_bin(cylinder)) else 0.0


## The chain's simulated joints in skeleton space: the heads after each root, then the extended tips.
func _joints(skeleton: Skeleton3D, setting: SecondaryChainSetting) -> PackedVector3Array:
	var joints: PackedVector3Array = PackedVector3Array()
	for chain_index: int in setting.root_bones.size():
		var root_bone: int = skeleton.find_bone(setting.root_bones[chain_index])
		var end_bone: int = skeleton.find_bone(setting.end_bones[chain_index])
		var walker: int = end_bone
		while walker >= 0 and walker != root_bone:
			joints.append(skeleton.get_bone_global_pose(walker).origin)
			walker = skeleton.get_bone_parent(walker)
		joints.append(skeleton.get_bone_global_pose(end_bone) * Vector3(0.0, setting.end_bone_lengths[chain_index], 0.0))
	return joints


func _report() -> void:
	for key: String in _phase_drift:
		print("drift %-40s %.4f m" % [key, _phase_drift[key]])
	for prefix: StringName in _min_capsule_clearance:
		print("min joint clearance %-12s %.4f m" % [prefix, _min_capsule_clearance[prefix]])
	for label: String in ["simulated", "baked"]:
		print("%s: min bow margin outside the skirt %.4f m, min leg margin inside the skirt %.4f m" % [
				label, _min_bow_margin[label], _min_leg_margin[label]])
		print("  worst leg %s" % _worst_leg.get(label, "-"))
	print("braid influence during %s: %.3f" % [FIX_BRAID_ANIMATION, _fix_braid_influence])
	var failures: PackedStringArray = PackedStringArray()
	for prefix: StringName in [BRAID_PREFIX, BOW_PREFIX]:
		if _max_drift.get(prefix, INF) >= MAX_DRIFT:
			failures.append("%s drifts %.4f m from the baked pose (limit %.2f)" % [prefix, _max_drift.get(prefix, INF), MAX_DRIFT])
	if _min_bow_margin["simulated"] < 0.0:
		failures.append("the bow dips %.4f m into the skirt" % -_min_bow_margin["simulated"])
	if _min_leg_margin["simulated"] < 0.0:
		failures.append("a leg pokes %.4f m through the skirt" % -_min_leg_margin["simulated"])
	var braid_setting: SecondaryChainSetting = _tuning.chain(BRAID_PREFIX)
	var wanted_influence: float = float(braid_setting.animation_influence.get(FIX_BRAID_ANIMATION, 1.0))
	if not braid_setting.animation_influence.has(FIX_BRAID_ANIMATION) or wanted_influence >= braid_setting.influence:
		failures.append("the braid keeps its influence during %s" % FIX_BRAID_ANIMATION)
	elif not is_equal_approx(_fix_braid_influence, wanted_influence):
		failures.append("braid influence %.3f during %s, expected %.3f" % [_fix_braid_influence, FIX_BRAID_ANIMATION, wanted_influence])
	if failures.is_empty():
		pass_test()
	else:
		fail_test("; ".join(failures))
