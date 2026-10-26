extends IntegrationTest
## Spec §4.2: petal particles fall at the cherry trees, so every CherryFoliage_* crown has an emitter above it. The
## cherry-tree ending moves the one named Petals, so that one stays.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const FOLIAGE_PREFIX: String = "CherryFoliage_"
const ENDING_EMITTER_NAME: String = "Petals"
const MAXIMUM_HORIZONTAL_OFFSET: float = 1.5
const MINIMUM_TREES: int = 4


func _ready() -> void:
	var school_env: SchoolEnv = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(school_env)
	await school_env.navigation_ready
	var failure: String = _every_tree_has_petals(school_env)
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _every_tree_has_petals(school_env: SchoolEnv) -> String:
	if not school_env.get_node_or_null(ENDING_EMITTER_NAME) is GPUParticles3D:
		return "SchoolEnv lost its %s emitter, which the cherry-tree ending moves" % ENDING_EMITTER_NAME
	var emitters: Array[GPUParticles3D] = []
	for child: Node in school_env.get_children():
		if child is GPUParticles3D:
			emitters.append(child as GPUParticles3D)
	var trees: Array[Node3D] = school_env.markers_with_prefix(FOLIAGE_PREFIX)
	if trees.size() < MINIMUM_TREES:
		return "expected at least %d cherry trees, found %d" % [MINIMUM_TREES, trees.size()]
	for tree: Node3D in trees:
		var foliage: MeshInstance3D = tree as MeshInstance3D
		var crown: Vector3 = foliage.global_transform * foliage.get_aabb().get_center()
		var has_emitter: bool = false
		for emitter: GPUParticles3D in emitters:
			var offset: Vector3 = emitter.global_position - crown
			offset.y = 0.0
			if offset.length() <= MAXIMUM_HORIZONTAL_OFFSET and emitter.global_position.y >= crown.y:
				has_emitter = true
		if not has_emitter:
			return "%s at %s has no petal emitter above it" % [tree.name, crown]
	return ""
