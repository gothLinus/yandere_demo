class_name TestCase
extends RefCounted

var failures: Array[String] = []


func before_each() -> void:
	pass


func assert_true(condition: bool, message: String = "") -> void:
	if not condition:
		failures.append("assert_true failed. %s" % message)


func assert_eq(actual: Variant, expected: Variant, message: String = "") -> void:
	if not _values_equal(actual, expected):
		failures.append("expected %s but got %s. %s" % [var_to_str(expected), var_to_str(actual), message])


func assert_near(actual: float, expected: float, tolerance: float, message: String = "") -> void:
	if absf(actual - expected) > tolerance:
		failures.append("expected %s +/- %s but got %s. %s" % [expected, tolerance, actual, message])


func _values_equal(actual: Variant, expected: Variant) -> bool:
	if actual is Array and expected is Array:
		var actual_array: Array = actual
		var expected_array: Array = expected
		if actual_array.size() != expected_array.size():
			return false
		for index: int in actual_array.size():
			if not _values_equal(actual_array[index], expected_array[index]):
				return false
		return true
	if actual is Dictionary and expected is Dictionary:
		var actual_dictionary: Dictionary = actual
		var expected_dictionary: Dictionary = expected
		if actual_dictionary.size() != expected_dictionary.size():
			return false
		for key: Variant in expected_dictionary:
			if not actual_dictionary.has(key):
				return false
			if not _values_equal(actual_dictionary[key], expected_dictionary[key]):
				return false
		return true
	if _is_number(actual) and _is_number(expected):
		return actual == expected
	return typeof(actual) == typeof(expected) and actual == expected


func _is_number(value: Variant) -> bool:
	return value is int or value is float
