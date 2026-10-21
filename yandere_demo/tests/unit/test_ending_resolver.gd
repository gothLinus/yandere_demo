extends TestCase


func test_four_endings() -> void:
	var tuning: EndingTuning = load("res://data/ending_tuning.tres")
	assert_eq(EndingResolver.resolve(500, 7, tuning), &"cherry_tree")
	assert_eq(EndingResolver.resolve(900, 2, tuning), &"shrine")
	assert_eq(EndingResolver.resolve(100, 9, tuning), &"friends")
	assert_eq(EndingResolver.resolve(499, 6, tuning), &"stranger")
