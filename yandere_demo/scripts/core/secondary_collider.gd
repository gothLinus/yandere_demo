class_name SecondaryCollider
extends Resource
## A capsule collider attached to a skeleton bone, for SpringBoneCollisionCapsule3D.

@export var bone: StringName = &""
@export var radius: float = 0.05
## Full capsule height including both caps, along the bone's +Y axis.
@export var height: float = 0.2
## Capsule centre in the bone's local rest space.
@export var position_offset: Vector3 = Vector3.ZERO
@export var rotation_offset: Quaternion = Quaternion.IDENTITY
