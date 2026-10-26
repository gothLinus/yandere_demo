class_name SecondaryMotionTuning
extends Resource
## Spring-bone tuning for the target's secondary chains and the body colliders that keep them off the body.

## One entry per chain family, simulated in the skeleton's own space (see SecondaryMotion). The skirt's gravity is
## 0.1, not the plan's 0.7: with 0.7 against stiffness 1.1 the flared skirt collapses toward vertical and the legs
## show through between the panels (isolated in the Task 9b report, fix round 1).
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
