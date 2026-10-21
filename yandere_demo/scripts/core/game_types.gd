class_name GameTypes
extends RefCounted

enum BlockKind { FREE, CLASS }
enum Stance { SNEAK, WALK, RUN, HIDDEN }
enum PlayerActivity { NONE, CAMERA_RAISED, CARRYING_ITEM }
enum Posture { STANDING, SITTING }

const WEEKDAY_NAMES: Array[String] = ["Mon", "Tue", "Wed", "Thu", "Fri"]
