class_name SecondaryMotion
extends Node
## Builds spring-bone simulation for a skeleton's secondary chains from a SecondaryMotionTuning resource.
##
## Each chain family gets its own SpringBoneSimulator3D, in tuning order, because `influence` is per modifier and a
## family's influence changes with the playing animation. A simulator's only collision children are its family's
## capsules, so the engine's default "all child collisions" is exactly the family's `colliders` membership.
##
## The chains simulate in the skeleton's own space (CENTER_FROM_NODE on the skeleton), so walking and turning are not
## a headwind. CENTER_FROM_BONE is not usable here: the engine maps joints through the center bone's pose but
## colliders through skeleton⁻¹ · center · skeleton and gravity through the inverse center rotation, which only agree
## for an identity-rotation bone at the world origin (this rig's root bone is turned -90 degrees about X).

const INFLUENCE_BLEND_SECONDS: float = 0.3

@export var tuning: SecondaryMotionTuning
@export var skeleton_path: NodePath

var _simulators: Dictionary[StringName, SpringBoneSimulator3D] = {}
var _influence_tweens: Dictionary[StringName, Tween] = {}


func _ready() -> void:
	var skeleton: Skeleton3D = get_node_or_null(skeleton_path) as Skeleton3D
	if skeleton == null:
		push_error("SecondaryMotion: no Skeleton3D at %s" % skeleton_path)
		return
	if tuning == null:
		push_error("SecondaryMotion: no tuning resource")
		return
	build(skeleton)


func build(skeleton: Skeleton3D) -> void:
	for setting: SecondaryChainSetting in tuning.chains:
		var simulator: SpringBoneSimulator3D = SpringBoneSimulator3D.new()
		simulator.name = "SpringBoneSimulator3D_%s" % setting.chain_prefix
		simulator.influence = setting.influence
		skeleton.add_child(simulator)
		# The simulator caches each setting's collisions when its children change, so settings come first.
		_configure(simulator, setting)
		for collider_bone: StringName in setting.colliders:
			var entry: SecondaryCollider = tuning.collider(collider_bone)
			if entry == null:
				push_error("SecondaryMotion: chain %s lists unknown collider %s" % [setting.chain_prefix, collider_bone])
				continue
			_add_capsule(simulator, entry)
		_simulators[setting.chain_prefix] = simulator


func simulator_for(chain_prefix: StringName) -> SpringBoneSimulator3D:
	return _simulators.get(chain_prefix) as SpringBoneSimulator3D


## Blends every family to the influence its tuning gives for `animation_name`.
func on_animation_changed(animation_name: StringName) -> void:
	for setting: SecondaryChainSetting in tuning.chains:
		var simulator: SpringBoneSimulator3D = simulator_for(setting.chain_prefix)
		if simulator == null:
			continue
		var wanted: float = float(setting.animation_influence.get(animation_name, setting.influence))
		if is_equal_approx(simulator.influence, wanted):
			continue
		var running: Tween = _influence_tweens.get(setting.chain_prefix) as Tween
		if running != null:
			running.kill()
		var tween: Tween = create_tween()
		tween.tween_property(simulator, "influence", wanted, INFLUENCE_BLEND_SECONDS)
		_influence_tweens[setting.chain_prefix] = tween


## Drops the springs' momentum, for teleports where a swing would whip the chains.
func reset() -> void:
	for simulator: SpringBoneSimulator3D in _simulators.values():
		simulator.reset()


func _configure(simulator: SpringBoneSimulator3D, setting: SecondaryChainSetting) -> void:
	simulator.setting_count = setting.root_bones.size()
	for index: int in setting.root_bones.size():
		simulator.set_root_bone_name(index, setting.root_bones[index])
		simulator.set_end_bone_name(index, setting.end_bones[index])
		simulator.set_extend_end_bone(index, setting.extend_end_bone)
		simulator.set_end_bone_direction(index, setting.end_bone_direction)
		simulator.set_end_bone_length(index, setting.end_bone_lengths[index])
		simulator.set_stiffness(index, setting.stiffness)
		simulator.set_drag(index, setting.drag)
		simulator.set_gravity(index, setting.gravity)
		simulator.set_radius(index, setting.radius)
		simulator.set_center_from(index, SpringBoneSimulator3D.CENTER_FROM_NODE)
		simulator.set_center_node(index, NodePath(".."))


func _add_capsule(simulator: SpringBoneSimulator3D, entry: SecondaryCollider) -> void:
	var capsule: SpringBoneCollisionCapsule3D = SpringBoneCollisionCapsule3D.new()
	capsule.name = "Collider_%s" % String(entry.bone).replace(".", "_")
	simulator.add_child(capsule)
	capsule.bone_name = entry.bone
	capsule.radius = entry.radius
	capsule.height = entry.height
	capsule.position_offset = entry.position_offset
	capsule.rotation_offset = entry.rotation_offset
