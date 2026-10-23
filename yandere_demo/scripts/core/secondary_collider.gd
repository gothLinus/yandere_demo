class_name SecondaryCollider
extends Resource
## A capsule collider attached to a skeleton bone, for SpringBoneCollisionCapsule3D.
##
## The radii are fixed by design; the placement is fitted to the rest body: the capsule covers as much of its body
## part as it can while every joint of every chain that collides with it stays outside it at rest (allowing for the
## chain's joint radius), so the simulation never pushes the authored drape. See the Task 9b report, fix round 1.

@export var bone: StringName = &""
@export var radius: float = 0.05
## Full capsule height including both caps, along the capsule's local +Y axis.
@export var height: float = 0.2
## Capsule centre in the bone's local rest space.
@export var position_offset: Vector3 = Vector3.ZERO
## Capsule orientation in the bone's local rest space (its axis is the rotated +Y).
@export var rotation_offset: Quaternion = Quaternion.IDENTITY
