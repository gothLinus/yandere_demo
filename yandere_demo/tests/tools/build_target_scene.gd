extends SceneTree
## Builds scenes/target.tscn: the node tree from the Task 15 brief plus Task 16's TargetPerception, and the
## AnimationTree state machine (a state per target clip, `locomotion` and `check_phone`, every state joined to every
## other by one shared 0.3 s crossfade).
## godot-mcp cannot instance the glb or build animation resources, so the scene is packed here instead.
## Run: godot --headless --path yandere_demo --script res://tests/tools/build_target_scene.gd

const OUTPUT_PATH: String = "res://scenes/target.tscn"
const MODEL_PATH: String = "res://assets/models/target.glb"
const SKELETON_PATH: NodePath = ^"../Model/TargetChar/Skeleton3D"
const CROSSFADE_SECONDS: float = 0.3
const EYE_HEIGHT: float = 1.48
const LOOK_TARGET_OFFSET: Vector3 = Vector3(0.0, 1.48, -2.0)
## check_phone layers target_phone's upper body fully over target_idle.
const CHECK_PHONE_BLEND_PARAMETER: StringName = &"parameters/check_phone/upper_body/blend_amount"
const SKELETON_TRACK_PREFIX: String = "TargetChar/Skeleton3D:"
## Bone subtrees check_phone takes from target_phone; the hips, legs, skirt, braid, hair, bows and ribbons keep the idle.
const UPPER_BODY_ROOTS: Array[String] = ["spine"]
const UPPER_BODY_EXCLUDED_PREFIXES: Array[String] = ["braid", "hair_", "ahoge", "head_bow", "ribbon"]


func _initialize() -> void:
	var root: CharacterBody3D = CharacterBody3D.new()
	root.name = "Target"
	root.set_script(load("res://scripts/target_ai.gd"))

	var model: Node3D = (load(MODEL_PATH) as PackedScene).instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	model.name = "Model"
	model.rotation.y = PI
	_add(root, root, model)
	root.set_editable_instance(model, true)
	var skeleton: Skeleton3D = model.get_node("TargetChar/Skeleton3D") as Skeleton3D
	var player: AnimationPlayer = model.get_node("AnimationPlayer") as AnimationPlayer

	var look_at: LookAtModifier3D = LookAtModifier3D.new()
	look_at.name = "LookAtModifier3D"
	look_at.bone_name = "head"
	look_at.forward_axis = SkeletonModifier3D.BONE_AXIS_PLUS_Z
	look_at.influence = 0.0
	_add(root, skeleton, look_at)

	var body_shape: Node = Node.new()
	body_shape.name = "CharacterBodyShape"
	body_shape.set_script(load("res://scripts/character_body_shape.gd"))
	body_shape.set("model_path", NodePath("../Model"))
	_add(root, root, body_shape)

	var agent: NavigationAgent3D = NavigationAgent3D.new()
	agent.name = "NavigationAgent3D"
	agent.path_desired_distance = 0.5
	agent.target_desired_distance = 0.3
	agent.avoidance_enabled = true
	agent.radius = 0.3
	_add(root, root, agent)

	var tree: AnimationTree = AnimationTree.new()
	tree.name = "AnimationTree"
	tree.anim_player = NodePath("../Model/AnimationPlayer")
	tree.root_node = NodePath("../Model")
	tree.tree_root = _state_machine(player, skeleton)
	_add(root, root, tree)
	tree.set(CHECK_PHONE_BLEND_PARAMETER, 1.0)

	var expression: Node = Node.new()
	expression.name = "ExpressionController"
	expression.set_script(load("res://scripts/expression_controller.gd"))
	expression.set("model_path", NodePath("../Model"))
	_add(root, root, expression)

	var secondary: Node = Node.new()
	secondary.name = "SecondaryMotion"
	secondary.set_script(load("res://scripts/secondary_motion.gd"))
	secondary.set("tuning", load("res://data/secondary_motion.tres"))
	secondary.set("skeleton_path", SKELETON_PATH)
	_add(root, root, secondary)

	var props: Node = Node.new()
	props.name = "TargetProps"
	props.set_script(load("res://scripts/target_props.gd"))
	props.set("skeleton_path", SKELETON_PATH)
	_add(root, root, props)

	var perception: Node = Node.new()
	perception.name = "TargetPerception"
	perception.set_script(load("res://scripts/target_perception.gd"))
	_add(root, root, perception)

	var eye_point: Marker3D = Marker3D.new()
	eye_point.name = "EyePoint"
	eye_point.position = Vector3(0.0, EYE_HEIGHT, 0.0)
	_add(root, root, eye_point)

	var look_target: Marker3D = Marker3D.new()
	look_target.name = "LookTarget"
	look_target.top_level = true
	look_target.position = LOOK_TARGET_OFFSET
	_add(root, root, look_target)
	look_at.target_node = look_at.get_path_to(look_target)

	var packed: PackedScene = PackedScene.new()
	var pack_result: Error = packed.pack(root)
	var save_result: Error = ResourceSaver.save(packed, OUTPUT_PATH) if pack_result == OK else pack_result
	print("pack %s, save %s -> %s" % [error_string(pack_result), error_string(save_result), OUTPUT_PATH])
	root.free()
	quit(0 if save_result == OK else 1)


func _add(owner_node: Node, parent: Node, child: Node) -> void:
	parent.add_child(child)
	child.owner = owner_node


func _state_machine(player: AnimationPlayer, skeleton: Skeleton3D) -> AnimationNodeStateMachine:
	var machine: AnimationNodeStateMachine = AnimationNodeStateMachine.new()
	var states: Array[StringName] = [&"locomotion", &"check_phone"]
	machine.add_node(&"locomotion", _locomotion(), Vector2(0.0, 0.0))
	machine.add_node(&"check_phone", _check_phone(skeleton), Vector2(0.0, 120.0))
	var clip_names: PackedStringArray = player.get_animation_list()
	clip_names.sort()
	for index: int in clip_names.size():
		var clip: StringName = StringName(clip_names[index])
		if not String(clip).begins_with("target_"):
			continue
		machine.add_node(clip, _animation(clip), Vector2(300.0 + 200.0 * (index % 3), 60.0 * index))
		states.append(clip)
	var start_transition: AnimationNodeStateMachineTransition = AnimationNodeStateMachineTransition.new()
	start_transition.advance_mode = AnimationNodeStateMachineTransition.ADVANCE_MODE_AUTO
	machine.add_transition(&"Start", &"locomotion", start_transition)
	var crossfade: AnimationNodeStateMachineTransition = AnimationNodeStateMachineTransition.new()
	crossfade.xfade_time = CROSSFADE_SECONDS
	for from_state: StringName in states:
		for to_state: StringName in states:
			if from_state != to_state:
				machine.add_transition(from_state, to_state, crossfade)
	return machine


func _locomotion() -> AnimationNodeBlendSpace1D:
	var walk: AnimationNodeBlendTree = AnimationNodeBlendTree.new()
	walk.add_node(&"animation", _animation(&"target_walk_routine"), Vector2(0.0, 0.0))
	walk.add_node(&"time_scale", AnimationNodeTimeScale.new(), Vector2(200.0, 0.0))
	walk.connect_node(&"time_scale", 0, &"animation")
	walk.connect_node(&"output", 0, &"time_scale")
	var locomotion: AnimationNodeBlendSpace1D = AnimationNodeBlendSpace1D.new()
	locomotion.min_space = 0.0
	locomotion.max_space = 1.0
	locomotion.add_blend_point(_animation(&"target_idle"), 0.0, -1, &"idle")
	locomotion.add_blend_point(walk, 1.0, -1, &"walk")
	return locomotion


func _check_phone(skeleton: Skeleton3D) -> AnimationNodeBlendTree:
	var upper_body: AnimationNodeBlend2 = AnimationNodeBlend2.new()
	upper_body.filter_enabled = true
	for bone: int in skeleton.get_bone_count():
		if _is_upper_body(skeleton, bone):
			upper_body.set_filter_path(NodePath(SKELETON_TRACK_PREFIX + skeleton.get_bone_name(bone)), true)
	var blend_tree: AnimationNodeBlendTree = AnimationNodeBlendTree.new()
	blend_tree.add_node(&"idle", _animation(&"target_idle"), Vector2(0.0, 0.0))
	blend_tree.add_node(&"phone", _animation(&"target_phone"), Vector2(0.0, 150.0))
	blend_tree.add_node(&"upper_body", upper_body, Vector2(250.0, 50.0))
	blend_tree.connect_node(&"upper_body", 0, &"idle")
	blend_tree.connect_node(&"upper_body", 1, &"phone")
	blend_tree.connect_node(&"output", 0, &"upper_body")
	return blend_tree


func _is_upper_body(skeleton: Skeleton3D, bone: int) -> bool:
	var bone_name: String = skeleton.get_bone_name(bone)
	for prefix: String in UPPER_BODY_EXCLUDED_PREFIXES:
		if bone_name.begins_with(prefix):
			return false
	var walker: int = bone
	while walker >= 0:
		if UPPER_BODY_ROOTS.has(skeleton.get_bone_name(walker)):
			return true
		walker = skeleton.get_bone_parent(walker)
	return false


func _animation(clip: StringName) -> AnimationNodeAnimation:
	var node: AnimationNodeAnimation = AnimationNodeAnimation.new()
	node.animation = clip
	return node
