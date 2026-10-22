class_name SecondaryChainSetting
extends Resource
## Spring values for one family of secondary bone chains (SpringBoneSimulator3D settings).

## Bone-name prefix shared by the chains, for example `skirt` for `skirt_00_01..skirt_07_03`.
@export var chain_prefix: StringName = &""
@export var stiffness: float = 1.0
@export var drag: float = 0.4
@export var gravity: float = 0.0
@export var radius: float = 0.02
## Root bone of each chain in this family, parallel to `end_bones`.
@export var root_bones: PackedStringArray = PackedStringArray()
## Leaf bone of each chain; the simulator extends it by `end_bone_length` along the bone axis.
@export var end_bones: PackedStringArray = PackedStringArray()
## Rest length of the leaf bones (glTF drops bone tails, so the simulator needs it explicitly).
@export var end_bone_length: float = 0.05
