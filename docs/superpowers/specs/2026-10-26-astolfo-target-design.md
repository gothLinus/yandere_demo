# Astolfo Target — Design

Addendum to `2026-10-21-yandere-demo-design.md`. It supersedes §4.1 and §4.1b wherever they conflict. Becomes plan **Task 23**, the last task, after Task 22's full verification.

Marked **(user)** where the user decided, **(builder call)** where I decided.

## 1. Intent

The current target is built by script from primitives (Tasks 8–9b). It matches the references, but it reads as "procedural", not as a real anime character.

**(user)** The user supplied a hand-made Astolfo model (Source Engine format, by the Workshop author "tobycrack"). It is now in `Astolfo/` at the repo root. The user wants:
- the art quality of that model
- shading that feels like a high-end anime 3D game, improved beyond what the model ships with
- animations, expressions and physics "as many, as good and as anime-like as possible"

Success: in-game, the target looks and moves like a character from a polished anime game, not a tech demo.

## 2. What the model contains (recon, 2026-10-26)

- **Format:** `.mdl` (v49) / `.vvd` / `.dx90.vtx` / `.phy`, plus `.vmt`/`.vtf` materials. It imports cleanly into Blender 5.2 with SourceIO 5.5.4 (MIT) when `import_animations=False`. With animations on, the import crashes, and the model has no animations worth keeping.
- **Meshes:** about 48k triangles in total, split into body, head, hair, school shirt, school skirt, socks and shoes.
- **Materials:** body, Face, Pupils, five hair materials, shirt, skirt, socks, shoes2.
- **Face:** 55 flex shape keys on the head mesh:
  - mouth shapes (open, cute, cat, triangle, A/I/O-like lip shapes, tongue)
  - smiles
  - eyes closed, happy, sleepy and surprised, with separate left/right closed and happy keys
  - brows (angry, up, down, tender)
  - pupil size and white pupils
  - eye-look directions for each eye
- **Skeleton:** 114 bones.
  - `ValveBiped.Bip01_*` humanoid with full fingers.
  - Hair chains `Hair.*`.
  - Bow chains `Bow.*`, covering the head bows and the braid bow.
  - `ribbon_L/R_1-2`.
  - Pectoral and glute helper bones.
  - **There are no skirt bones.**
- **Scale:** imports about 1.22 m tall. The target is 1.62 m (`build_target.py`).
- **Outfit:** the design matches the references exactly: white sailor top with red striped collar and cuffs, pink neckerchief, red pleated skirt with white hem stripes, long pink braid with a black bow, black head bows. The model's top is cropped, showing the midriff, and the skirt is short. The socks are black thigh-highs and the shoes are black.

Recon renders: the controller's scratchpad, `astolfo_recon/shots/`. Not committed.

## 3. Goals

1. **Replace the target's model.** `target.glb` becomes the Astolfo model, rigged, animated and exported through the existing pipeline. The import uses `character_post_import.gd`, then the toon conversion.
2. **(user) Keep the outfit exactly as the model has it.** This overrides the "modest uniform" decision in §4.1 and §4.1b. Colors and design come from the model's textures, not from §4.1's text: black socks and black shoes stay.
3. **Improve the art past the source model** in the Godot toon look:
   - clean anime face shading, with no blotchy self-shadow on the face (face normals smoothed toward a head-shaped proxy, or an equivalent technique)
   - per-material outline widths, thinner on the face
   - soft rim light
   - hair highlight band
   - eye highlights that read at gameplay distance
   - a blush layer (the model has none)
   - textures kept at their native resolution
4. **Expressions.**
   - Every expression name the game uses keeps working. The names are in §4.1b: `neutral`, `startled`, `suspicious`, `happy`, `blink`, `smile`, `sad`, `blush`, `wink_L`, `wink_R`, `mouth_A/I/U/E/O`, plus the pupil and eye controls.
   - Each one is built from the model's flexes, as composite shape keys baked under the game's names, so `ExpressionController`, which tweens shape keys by name, is unchanged.
   - **(builder call)** Add expressions where the model allows it: embarrassed, pout, sleepy, determined. Eye-look keys drive glances. Blinks pair with eye darts.
5. **Animations.**
   - Every current target clip keeps its name, its loop mode and roughly its length. These are the contract with Tasks 15–20:

     | Clip | Frames | Loops |
     |---|---|---|
     | `target_idle` | 90 | loop |
     | `target_walk_routine` | 32 | loop |
     | `target_notice_player` | 30 | once |
     | `target_startled` | 20 | once |
     | `target_look_around` | 120 | loop |
     | `target_sit_down` | 30 | once |
     | `target_stand_up` | 30 | once |
     | `target_sit` | 90 | loop |
     | `target_sit_read` | 120 | loop |
     | `target_phone` | 120 | loop |
     | `target_drink` | 120 | loop |
     | `target_fix_braid` | 150 | loop |
     | `target_lean_chat` | 120 | loop |
     | `target_sweep` | 60 | loop |
     | `target_wave` | 45 | loop |
     | `target_idle_shy` | 120 | loop |
     | `target_idle_playful` | 90 | loop |
     | `target_idle_confident` | 120 | loop |

   - Quality bar: anime acting.
     - anticipation and follow-through
     - head-led turns
     - weight shifts and breathing in every hold
     - expressive hands
     - expression changes timed with the body
     - overlapping action from the physics
   - **(builder call)** Add variants where they make the AI less predictable, for example a second walk, more idles and talk gestures. Anything new is wired into the AI and its tests in the same task.
   - **(user)** Animations may be keyed by script, or come from external motion data (motion capture or animator-made anime motion packs) retargeted onto the rig, whichever is clearly better per clip.
6. **(user) Physics rebuilt clean** with `SpringBoneSimulator3D` and per-chain colliders:
   - hair clusters, ahoge, braid, braid bow, head bows, ribbons
   - the skirt, which needs new chains: about 8 × 3 bones, skinned to the skirt
   - The R10 limits apply: braid and bow drift < 0.08 m from the baked pose, and the bow stays outside the skirt in idle and walk.
   - The skirt never clips the legs.
   - **(user) The skirt is lively.** It swings, flutters and can lift on runs, turns, the startled jump and quick stops. **(user)** It never reveals anything inappropriate.
     - **(user)** No hard lift limit up front. The coverage check below decides. If it passes with spring tuning alone, no limit is added. If it fails and tuning can't fix it, add the smallest limit that makes it pass: a per-chain rotation limit or a collider shell.
     - The coverage check below runs across the most energetic clips (walk, look_around, startled, idles), with the springs active.
   - **(builder call) Seated coverage with the short skirt:**
     - The hem is not changed; the user wants the outfit kept exactly.
     - Seated clips (`target_sit`, `target_sit_read`, `target_phone`, `target_sit_down`, `target_stand_up`) keep the knees together and rest the hands or the prop (book, phone) on the lap.
     - The coverage check becomes: no underwear or crotch region is visible from any camera position the player can reach, meaning the third-person rig and the viewfinder at standing and crouch heights.
     - Bare thigh between the sock and the hem is part of the outfit and allowed.

## 4. Non-goals

- No change to gameplay, the AI logic, the player or the supporting cast. They stay procedural.
- No cloth simulation, no VRM/FBX export, no Rigify (§4.1b).
- No redistribution. The model has no license file and is likely ripped from a commercial game, so it is for this private demo only.

## 5. Anti-goals

- **(builder call, kept after the user's outfit decision)** Nothing in the game sexualizes the target:
  - no low or upskirt camera framing
  - no suggestive poses or animations
  - skirt physics may lift the hem but never reveals what the skirt covers (§3.6)
  - real (jiggle) physics on the chest and glutes
  - photo scoring (Task 5/17) never rewards such angles

  The outfit itself is the user's choice and stays.

  **(builder call) Scope:** enforced in the target's animations, poses and skirt physics. Also add one check of `PhotoScorer` (Task 5) and the camera rig (Task 13).
  - Add a rule and a test only if a low or under-skirt framing could score at least as well as a face or upper-body framing, or if the rig can reach a below-hem viewpoint.
  - Otherwise, record in the report that the existing code already prevents it.
- The target looks worse in motion than the old one: stiff limbs, foot sliding, popping physics, or skin poking through clothes.
- Any Task 15–20 test regresses.

## 6. Constraints

- Godot 4 project, glTF `.glb`, −Z forward, Y up, 1 unit = 1 m, Principled BSDF materials. Shader nodes are looked up by type and enums read from `bl_rna` (global constraints).
- **Reproducible build.**
  - **(builder call)** Commit the raw source to `yandere_demo/blender/source/astolfo/` (it has a `.gdignore`) and remove the root `Astolfo/` folder.
  - A one-time import script (SourceIO, run with an isolated `BLENDER_USER_SCRIPTS` directory) writes `astolfo_source.blend`. That `.blend` is committed.
  - `build_target.py` builds from it, so a normal rebuild doesn't need SourceIO.
- **Interface contracts the rest of the game depends on.** These must keep working, or be updated together with every consumer in this task:
  - the root `TargetChar` and the `Target-col` proxy (Ruling R4)
  - the `head` bone (LookAtModifier3D, `eye_forward`)
  - the hand bones (R9 props)
  - `data/secondary_motion.tres` and its scripts
  - `test_target_import.gd` and `test_secondary_motion.gd`
  - the clip names above
  - shape key names
  - `body_shape` metadata
  - **(builder call)** Rename the ValveBiped bones to the project's humanoid names (`HUMANOID_BONES` in `blender/lib/rig.py`), so existing Blender animation code and Godot lookups keep working.
- **(builder call) Tests describe behaviour, not the old build.** The *structural* assertions in `test_target_import.gd`, `test_secondary_motion.gd`, `validate_assets.py` and the R10 probe are rewritten to match the new model:
  - mesh split
  - secondary bone and chain names
  - which mesh carries which shape key

  The *behaviours* they check stay asserted:
  - root and proxy
  - every clip with its length and loop mode
  - every expression name present
  - per-chain colliders
  - drift and coverage limits
  - toon materials on every surface

  Do not cut or rename the model's meshes and bones just to satisfy the old names. Code that looks up a specific mesh or chain by name (`SecondaryMotion`, `ExpressionController`, the R10 probe) is updated in the same task.
- **(user) Helper bones stay as the model has them.** The pectoral and glute helper bones and their weights are kept, so the body deforms exactly as the model was made. **(builder call)** They stay plain deformation helpers that follow their parents. They shall get spring or jiggle physics (anti-goal, §5).
- **(builder call) Scale.** Scale uniformly to 1.62 m. If the model's proportions then miss the world's fixed points (seat height 0.45 m, the R12 seat anchors, hand props, doorways), small rig fixes are allowed: limb lengths within ±5%. Beyond that, adapt the animations and the hitbox, not the world or the markers.
- **Height** is 1.62 m. The head-to-height ratio and silhouette come from the model, not from §4.1b's numbers.
- **Budget:** the target may stay well above the cast. It is the most detailed character, so ≤ 100k triangles.
- Every external motion source used is recorded with its license in `yandere_demo/blender/source/MOTION_SOURCES.md`. Only sources that allow use in a private non-commercial project.

## 7. Verification

- `validate_assets.py` passes, updated for the new mesh split, with no pleat-count check, since the skirt's pleats are modeled in.
- The unit, import and integration suites pass: `run_all.sh`, including `target_routine` and every T15–T20 test.
- The R10 drift probe and the seated-coverage check pass.
- Turnaround and expression renders, plus in-game screenshots of walk, sit, phone and startled, go in the report.
- **The user looks at the result before the task is marked done.**

## 8. Left to the builder

- the face-shading technique
- whether blush and pupil size are shape keys or shader parameters. Either is fine, as long as `ExpressionController`'s by-name contract is kept or updated in the same task.
- how flexes combine into each expression
- which clips come from external motion data, and from where
- the skirt chain layout
- per-chain spring values
- extra clip and expression variants
- how to fit `Target-col`
