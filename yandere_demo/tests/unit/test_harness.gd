extends TestCase


func test_assert_eq_records_failure() -> void:
	var inner: TestCase = TestCase.new()
	inner.assert_eq(1, 2)
	assert_eq(inner.failures.size(), 1)


func test_assert_eq_compares_arrays_element_wise() -> void:
	var typed: Array[int] = [1, 2]
	var inner: TestCase = TestCase.new()
	inner.assert_eq(typed, [1, 2])
	inner.assert_eq([[1], [2]], [[1], [2]])
	assert_eq(inner.failures.size(), 0)
	inner.assert_eq(typed, [1, 3])
	assert_eq(inner.failures.size(), 1)


func test_assert_eq_compares_dictionaries() -> void:
	var inner: TestCase = TestCase.new()
	inner.assert_eq({"a": [1]}, {"a": [1]})
	assert_eq(inner.failures.size(), 0)
	inner.assert_eq({"a": 1}, {"a": 2})
	assert_eq(inner.failures.size(), 1)


func test_assert_near_respects_tolerance() -> void:
	var inner: TestCase = TestCase.new()
	inner.assert_near(1.0, 1.05, 0.1)
	assert_eq(inner.failures.size(), 0)
	inner.assert_near(1.0, 2.0, 0.1)
	assert_eq(inner.failures.size(), 1)
