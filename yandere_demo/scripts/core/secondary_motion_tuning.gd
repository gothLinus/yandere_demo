class_name SecondaryMotionTuning
extends Resource
## Spring-bone tuning for the target's secondary chains and the body colliders that keep them off the body.

## Every chain simulates relative to this bone (SpringBoneSimulator3D CENTER_FROM_BONE), so walking and turning
## are not a headwind that blows the skirt and braid backward; only the animation's own motion swings them.
@export var center_bone: StringName = &"root"
@export var chains: Array[SecondaryChainSetting] = []
@export var colliders: Array[SecondaryCollider] = []


func chain(prefix: StringName) -> SecondaryChainSetting:
	for setting: SecondaryChainSetting in chains:
		if setting.chain_prefix == prefix:
			return setting
	return null


func collider(bone: StringName) -> SecondaryCollider:
	for entry: SecondaryCollider in colliders:
		if entry.bone == bone:
			return entry
	return null
