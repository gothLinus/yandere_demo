class_name ActivityPool
extends Resource

@export var activities: Array[ActivityDefinition] = []


func find(id: StringName) -> ActivityDefinition:
	for activity: ActivityDefinition in activities:
		if activity.id == id:
			return activity
	return null
