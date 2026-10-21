extends TestCase


func test_intel_total_and_item_links() -> void:
	var intel: IntelCatalog = load("res://data/intel_cards.tres")
	var items: ItemCatalog = load("res://data/items.tres")
	assert_eq(intel.total(), 12)
	for item: ItemDefinition in items.items:
		if item.intel_card_id != &"":
			assert_true(intel.find(item.intel_card_id) != null, "missing card %s" % item.intel_card_id)


func test_every_activity_intel_card_exists() -> void:
	var intel: IntelCatalog = load("res://data/intel_cards.tres")
	var pool: ActivityPool = load("res://data/activity_pool.tres")
	for activity: ActivityDefinition in pool.activities:
		if activity.intel_card_id != &"":
			assert_true(intel.find(activity.intel_card_id) != null)
		for item_id: StringName in activity.item_ids:
			assert_true((load("res://data/items.tres") as ItemCatalog).find(item_id) != null)
