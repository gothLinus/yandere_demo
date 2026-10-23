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


func test_intel_text_uses_he_him() -> void:
	var intel: IntelCatalog = load("res://data/intel_cards.tres")
	var feminine_pronoun: RegEx = RegEx.create_from_string("\\b([Ss]he|[Hh]er|[Hh]erself)\\b")
	for card: IntelCard in intel.cards:
		assert_true(feminine_pronoun.search(card.title) == null, "title of %s uses she/her" % card.id)
		assert_true(feminine_pronoun.search(card.text) == null, "text of %s uses she/her" % card.id)
