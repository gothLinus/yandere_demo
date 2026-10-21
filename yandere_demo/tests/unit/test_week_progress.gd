extends TestCase

const TEST_PATH: String = "user://test_save.json"


func test_bank_advances_day_and_merges() -> void:
	var progress: WeekProgress = WeekProgress.new()
	var run: DayRun = DayRun.new()
	run.add_photo("user://photos/a.png", 80, 0)
	run.stashed_items.append(&"pen")
	run.carried_item = &"note"
	assert_true(run.unlock_intel(&"intel_read_bench", progress.banked_intel))
	progress.bank(run)
	assert_eq(progress.day_index, 1)
	assert_eq(progress.photo_score_total(), 80)
	assert_eq(progress.banked_items, [&"pen"])
	assert_eq(progress.banked_intel, [&"intel_read_bench"])


func test_retry_keeps_progress_changes_seed() -> void:
	var progress: WeekProgress = WeekProgress.new()
	var before_seed: int = progress.day_seed
	progress.history.record(&"lunch", &"read_bench")
	progress.retry_seed()
	assert_eq(progress.day_index, 0)
	assert_true(progress.day_seed != before_seed)
	progress.bank(DayRun.new())
	assert_eq(progress.history.yesterday_by_block.get(&"lunch", []), [])


func test_round_trip_save() -> void:
	var progress: WeekProgress = WeekProgress.new()
	progress.banked_intel.append(&"intel_poems")
	assert_eq(SaveStore.save(progress, TEST_PATH), OK)
	var loaded: WeekProgress = SaveStore.load_progress(TEST_PATH)
	assert_eq(loaded.banked_intel, [&"intel_poems"])
	SaveStore.erase(TEST_PATH)


func test_load_corrupt_returns_null() -> void:
	var file: FileAccess = FileAccess.open(TEST_PATH, FileAccess.WRITE)
	file.store_string("{not json")
	file.close()
	assert_eq(SaveStore.load_progress(TEST_PATH), null)
	file = FileAccess.open(TEST_PATH, FileAccess.WRITE)
	file.store_string(JSON.stringify({"version": 999}))
	file.close()
	assert_eq(SaveStore.load_progress(TEST_PATH), null)
	SaveStore.erase(TEST_PATH)
	assert_eq(SaveStore.load_progress(TEST_PATH), null)


func test_unlock_intel_rejects_duplicates_and_banked() -> void:
	var run: DayRun = DayRun.new()
	var banked: Array[StringName] = [&"intel_banked"]
	assert_true(run.unlock_intel(&"intel_new", banked))
	assert_true(not run.unlock_intel(&"intel_new", banked))
	assert_true(not run.unlock_intel(&"intel_banked", banked))
	assert_true(not run.unlock_intel(&"", banked))
	assert_eq(run.intel, [&"intel_new"])


func test_round_trip_preserves_state() -> void:
	var progress: WeekProgress = WeekProgress.new()
	var run: DayRun = DayRun.new()
	run.add_photo("user://photos/a.png", 80, 0)
	run.stashed_items.append(&"pen")
	progress.history.record(&"lunch", &"read_bench")
	progress.bank(run)
	assert_eq(SaveStore.save(progress, TEST_PATH), OK)
	var loaded: WeekProgress = SaveStore.load_progress(TEST_PATH)
	SaveStore.erase(TEST_PATH)
	assert_true(loaded != null)
	assert_eq(loaded.day_index, 1)
	assert_eq(loaded.day_seed, progress.day_seed)
	assert_eq(loaded.banked_photos, [{"path": "user://photos/a.png", "score": 80, "day": 0}])
	assert_true(typeof(loaded.banked_photos[0]["score"]) == TYPE_INT)
	assert_eq(loaded.banked_items, [&"pen"])
	assert_eq(loaded.history.yesterday_by_block, {&"lunch": [&"read_bench"]})
	assert_true(loaded.banked_items[0] == &"pen")


func test_bank_dedupes_intel_and_seed_changes() -> void:
	var progress: WeekProgress = WeekProgress.new()
	progress.banked_intel.append(&"intel_a")
	var run: DayRun = DayRun.new()
	run.intel.append(&"intel_a")
	run.intel.append(&"intel_b")
	var before_seed: int = progress.day_seed
	progress.bank(run)
	assert_eq(progress.banked_intel, [&"intel_a", &"intel_b"])
	assert_true(progress.day_seed != before_seed)
	assert_true(progress.day_seed != 0)
