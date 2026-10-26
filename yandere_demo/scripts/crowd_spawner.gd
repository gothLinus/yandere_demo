class_name CrowdSpawner
extends Node3D
## Spawns the day's background students: looks drawn deterministically from the day seed, one per StudentSpot to
## start, and StudentSeat_* markers assigned round-robin.

const STUDENT_SCENE: PackedScene = preload("res://scenes/student.tscn")
const SEAT_PREFIX: String = "StudentSeat_"
const SPOT_PREFIX: String = "StudentSpot_"
const RANDOM_SALT: StringName = &"student"

@export var student_count: int = 10

## Both injected until the Task 18 autoloads exist; passed on to every student.
var meters: StealthMeters
var clock: SchoolClockModel
var students: Array[StudentAI] = []


static func variant_for(day_seed: int, index: int) -> int:
	return hash([day_seed, index])


## Replaces any earlier crowd. The school's navigation must be ready.
func spawn(school_env: SchoolEnv, day_seed: int) -> void:
	for student: StudentAI in students:
		student.queue_free()
	students.clear()
	var seats: Array[Node3D] = school_env.markers_with_prefix(SEAT_PREFIX)
	var spots: Array[Node3D] = school_env.markers_with_prefix(SPOT_PREFIX)
	for index: int in student_count:
		var student: StudentAI = STUDENT_SCENE.instantiate() as StudentAI
		student.name = "Student%02d" % index
		student.variant = variant_for(day_seed, index)
		student.meters = meters
		student.clock = clock
		add_child(student)
		if not spots.is_empty():
			student.global_transform = spots[index % spots.size()].global_transform
		var seat: Node3D = seats[index % seats.size()] if not seats.is_empty() else null
		student.setup(school_env, seat, hash([day_seed, index, RANDOM_SALT]))
		students.append(student)


func snap_all_to_seats() -> void:
	for student: StudentAI in students:
		student.snap_to_seat()
