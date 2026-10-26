class_name SecondaryChainSetting
extends Resource
## Spring values for one family of secondary bone chains (SpringBoneSimulator3D settings).

## Bone-name prefix shared by the chains, for example `skirt` for `skirt_00_01..skirt_07_03`.
@export var chain_prefix: StringName = &""
@export var stiffness: float = 1.0
@export var drag: float = 0.4
@export var gravity: float = 0.0
## Joint radius used against the colliders.
@export var radius: float = 0.02
## Root bone of each chain in this family, parallel to `end_bones` and `end_bone_lengths`.
@export var root_bones: PackedStringArray = PackedStringArray()
## Leaf bone of each chain (single-bone chains use the same bone as root and end).
@export var end_bones: PackedStringArray = PackedStringArray()
## Rest length of each leaf bone. glTF drops bone tails, so the simulator needs it to place the chain's tip.
@export var end_bone_lengths: PackedFloat32Array = PackedFloat32Array()
## Simulate a tip joint past the leaf bone (`set_extend_end_bone`), `end_bone_lengths` along `end_bone_direction`.
@export var extend_end_bone: bool = true
## Imported bones point along their +Y axis.
@export var end_bone_direction: SkeletonModifier3D.BoneDirection = SkeletonModifier3D.BONE_DIRECTION_PLUS_Y
## Bones of the `SecondaryMotionTuning.colliders` this family collides with; every joint clears them at rest.
@export var colliders: Array[StringName] = []
## Share of the simulated motion blended over the animated pose (`SkeletonModifier3D.influence`).
@export_range(0.0, 1.0) var influence: float = 1.0
## Animation name -> influence while that animation plays, for clips whose hands hold the chain.
@export var animation_influence: Dictionary[StringName, float] = {}
