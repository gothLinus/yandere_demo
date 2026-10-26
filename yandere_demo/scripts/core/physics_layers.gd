class_name PhysicsLayers
extends RefCounted

const WORLD: int = 1
const PLAYER: int = 2
const INTERACTABLE: int = 4
const CHARACTERS: int = 8

## Sight and hearing rays stop at geometry only, so a character's own body never hides its head.
const LINE_OF_SIGHT_MASK: int = WORLD
