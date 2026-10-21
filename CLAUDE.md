# Project Guidelines (Godot 4 + Blender + Claude)

Context file for project layout, GDScript conventions, Blender asset workflow, and MCP tooling.

## Workflow & Tooling

- **Commits:** Prefix messages with `wip:`, `feat:`, `fix:`, or `refactor:`. Never push without confirmation.
- **Godot MCP Tooling:** 
  - Use `@coding-solo/godot-mcp` for inspecting scene trees, executing GDScript in-editor, checking node references, and reading logs.
  - Verify node paths and `@onready` dependencies via MCP before editing `.tscn` scene files directly.
- **Blender MCP Tooling:**
  - Use `blender-mcp` (or equivalent Blender MCP server) to run Python scripts in Blender, inspect mesh hierarchies, check origin points/transforms, and automate `.glb`/`.gltf` exports directly into the Godot project asset folder.
  - Verify export settings, material bindings, and object naming suffixes (`-col`, `-convcol`, `-navmesh`) before exporting.
- **Testing & Verification:** Run Godot in headless/debug mode via CLI or trigger scene dry-runs using MCP before confirming tasks as finished.

## GDScript & Godot 4 Rules

- **Type Safety:** Always use explicit static typing (e.g., `var speed: float = 5.0`, `func move(dir: Vector3) -> void:`).
- **Node Referencing:** Use `@onready var node_name: NodeType = $NodePath` or `get_node("NodePath")`.
- **Node Naming:** Use `PascalCase` for Nodes and Scenes; use `snake_case` for GDScript files, functions, variables, and signals.
- **Signals:** Always define typed signals (e.g., `signal health_changed(new_health: float)`). Connect via code in `_ready()` or explicit scene connections.
- **3D Movement & Physics:** Use `CharacterBody3D` with `move_and_slide()` for entities. Keep physics calculations strictly inside `_physics_process(delta: float)`.
- **Scene Files (`.tscn`):** Treat `.tscn` files as human-readable text, but prefer instantiating sub-scenes or adding nodes via script when structurally complex.

## Blender & 3D Asset Pipeline

- **File Format:** Export all 3D assets, models, and animations from Blender as GLTF 2.0 (`.glb` / `.gltf`).
- **Import Suffixes (Godot Automatic Physics):**
  - Mesh collisions: Append `-col` to Blender object names for static colliders (e.g., `Rock-col`).
  - Convex collisions: Append `-convcol` for complex shapes.
  - Navigation: Append `-navmesh` for pathfinding regions.
- **Scale & Orientation:** 1 Blender Unit = 1 Meter in Godot. Export with `-Z Forward, Y Up` (Blender GLTF default).
- **Materials:** Use standard PBR shader node setup (Principled BSDF) in Blender for clean Godot material conversions.

## Response Style

- **Tone:** Concise, direct, and technically accurate.
- **Trade-offs:** State architectural trade-offs briefly and provide a default recommendation.
- **Gaps:** Explicitly call out any missing assets, missing node references, or unlinked signals at the end of a task.
