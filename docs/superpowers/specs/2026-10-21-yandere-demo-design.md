# Yandere Demo — Design

Date: 2026-10-21
Engine: Godot 4.7.2 (GDScript) · Assets: Blender 5.2.2 via blender-mcp
Project root: `/Users/linusnadig/Developer/privat/games/yandere_demo/`

## 1. Intent

A 3D fan demo inspired by Yandere Simulator. The player is a secret admirer at a Japanese-style high school who spends a school day following one target student, taking photos of her, collecting things she leaves behind, and keeping both her and the school from noticing.

What makes it worth building:

- **The school feels alive and the target feels real.** She lives a believable day, moves smoothly between places, and does things at each place (reads, drinks, chats, fixes her braid). She is never a marker sliding along a path.
- **The day can't be memorized.** Each day she picks different activities, places, and timings in free periods, so the player has to watch her instead of following a script.
- **The target looks like the reference art** (four images of a specific pink-haired character, see §4.1), as close as a scripted Blender build with anime toon shading can get.

Success: you can play a full day of about 20–25 real minutes. The target is recognizable from the references. Her movement and reactions read as seamless. Two days in a row play out differently. Getting caught and finishing the day both work, and both lead into the next attempt or the next day.

## 2. Goals, non-goals, anti-goals

**Goals**
- Full school day loop: 07:00 → 18:00 clock, bell-driven blocks, mandatory class attendance.
- Schedule-driven target AI with weighted-random free-time activities and seamless transitions.
- Stealth: line of sight, hearing, stance, hiding spots, crowd cover.
- Photo mode with quality scoring; item collection with stashing.
- Three meters: target **Suspicion**, **School Alert**, player **Sanity**.
- Populated school: a teacher plus background students.
- Anime look: toon shading, outlines, soft lighting.
- A five-day week with four endings decided by photos and intel, saved to disk between sessions.

**Non-goals (out of scope for this demo)**
- No elimination, violence, rival, or matchmaking mechanics. Observation and stealth only.
- One target only. No dialogue system, story, or voice acting.
- No mid-day saves, no multiplayer, no export or packaging pipeline (the demo runs from the editor or CLI).
- Gamepad support is optional and not required.

**Anti-goals (failure even if it technically works)**
- The target teleports, pops, slides, or snaps rotation between stops or activities.
- After two days the player can predict her schedule.
- Grey-box or programmer-art look on the target. Props can be simple, but she can't.
- A meter rises without a cause the player can read. Every rise has a visible tell (eye or ear icon over her, red edge flash, teacher "!").
- Class attendance feels like a chore. Sitting takes seconds, not minutes.
- The target looks sexualized. She's a student in a school setting (see §4.1).

## 3. Constraints

- Godot 4.7.2 at `/opt/homebrew/bin/godot`, GDScript only, following the project CLAUDE.md:
  - explicit static typing everywhere
  - typed signals
  - `@onready` node references
  - PascalCase nodes and scenes, snake_case files, functions, and variables
  - physics in `_physics_process`
  - `CharacterBody3D` + `move_and_slide()` for every character
- Blender 5.2.2 is reachable through blender-mcp. **No asset libraries and no 3D generators are enabled**, so every mesh, rig, animation, and texture is made by Python scripts in Blender.
- **No audio files exist**, so all SFX and BGM are synthesized (see §8).
- Export rules:
  - GLTF 2.0 `.glb`, 1 unit = 1 m, −Z forward, Y up
  - Principled BSDF in Blender; final look comes from Godot toon materials
  - collision/nav suffixes `-col`, `-convcol`, `-navmesh`
  - object names `TargetChar`, `Target-col`, `Locker-col`, `School-navmesh`
- Node references are verified via godot-mcp before `.tscn` files are edited. A headless test run passes before anything is called done.
- The folder is not yet a git repo. Initialize it at `games/` on `main`, commit as `wip:` / `feat:` / `fix:` / `refactor:`, never push.

## 4. Decisions

Marked **(user)** where the user decided, **(builder call)** where I decided and the user has not objected.

### 4.1 Target character (user: match references as closely as possible; seamless motion matters most)

Reference images are in `docs/references/`:
- `target_ref_1_sailor_peace.png`, `target_ref_3_sailor_jump.png` and `target_ref_4_sailor_braid.png` are the ones to model from. Ref 4 is the clearest for the face, braid and bows.
- `target_ref_2_armor_unused.png` is only useful for the hair and face from behind. Its outfit is ignored.

From the references, identically:
- **Hair:** pink, shoulder-length and slightly messy. A white streak in the front fringe, a small ahoge, and a long single braid hanging over one shoulder down to roughly hip height.
- **Bows:** black ribbon bows. Two on the head (one each side, upper back), one tied at the end of the braid.
- **Face:** large violet/purple anime eyes with highlights. Small open-mouth smile with a single small fang for the "happy" expression.
- **Uniform colors:** white sailor top with a red/pink sailor collar and red cuffs, both with thin white stripe trim. Pink neckerchief. Red pleated skirt with white stripe trim near the hem. White thigh-high socks. Brown loafers.
- **Build:** slim and youthful.

**(builder call) Modest version of the uniform:** a full-length top (no exposed midriff) and a knee-length pleated skirt, still with white thigh-highs. The armor outfit from reference 2 isn't used.

**(builder call) Pipeline:**
- Built in Blender by scripts with real effort on silhouette:
  - subdivided smooth body
  - layered hair-card / shell meshes for the bangs and side locks
  - a tube-segment braid
  - separate bow meshes
- Eyes and brows are a painted texture on face planes (anime style), with UV-offset or material-swap support for expressions.
- In Godot: a toon (cel) shader with 2–3 bands, rim light, and an inverted-hull or screen-space outline. This is the main reason she will read as "anime art" instead of "low-poly".
- **Rig:** a humanoid armature (spine, neck, head, arms, hands with simple finger groups, legs, feet), plus a braid bone chain and skirt bones for secondary motion (spring/jiggle in Godot, or baked).
- **Shape keys:** `neutral`, `startled`, `suspicious`, `happy`, plus `blink`.
- **Animations:**
  - required: `target_idle`, `target_walk_routine`, `target_notice_player`
  - added for activities: `target_sit`, `target_sit_read`, `target_phone`, `target_drink`, `target_look_around`, `target_fix_braid`, `target_lean_chat`, `target_startled`
- **Collision:** `Target-col` (capsule-like). The root object is named `TargetChar`.

**(builder call) Other characters:**
- **Player:** "Yandere-chan" archetype. Black ponytail, dark navy sailor uniform, grey eyes. `Player-col` (convex). Animations `player_idle`, `player_walk`, `player_run`, `player_sneak`, `player_take_photo`, `player_hide`, `player_sit`.
- **Background students:** one shared body and rig with swappable hair meshes and color palettes. Male and female uniform variants, 6–10 on screen.
- **Teacher:** adult proportions on the shared rig, in a suit.
- Supporting characters can be clearly simpler than the target, but they use the same toon look.

### 4.2 School (user: "like Yandere Sim, a real school"; layout is builder call)

- **Ground floor:**
  - entrance with shoe lockers (the player's stash locker is here)
  - main hallway lined with lockers, some of them hide spots
  - class 1-A (the player's classroom)
  - one more classroom
  - cafeteria
  - restroom corridor with mirrors
- **Stairs to the 2nd floor:** class 2-B (the target's classroom), club room, library corner, rooftop door.
- **Rooftop:** fence, a bench, a water tank.
- **Outside:** courtyard with fountain, benches, cherry trees (petal particles), vending machine, school gate.
- **Hide spots:** hallway lockers, plus "under desk" in classrooms and the library. Each is an `Area3D` with an interact prompt.
- **Build:** made in Blender as modular pieces plus an assembled layout with `-col` colliders. Navigation uses a `School-navmesh` object or a Godot `NavigationRegion3D` bake (builder's choice). Stairs must be walkable by agents and the player.
- **Lighting:** a warm low sun, a sky gradient, soft ambient, mild bloom and glow, and slightly warm interiors. The time of day can tint the sun (morning → late-afternoon orange).

### 4.3 The day and class attendance (user: longer day, Yandere-Sim-style mandatory class)

- The clock runs 07:00–18:00. The rate is per block, so the free blocks add up to about 20–25 real minutes at 1×.
- Holding the fast-forward key speeds time up (≈ 4–8×).
- All block times and durations live in a data file (`data/schedule_blocks.tres` or JSON) so they're tunable.

| Block | Clock | Type | Approx. real time at 1× |
|---|---|---|---|
| Before school | 07:00–08:30 | free | 5 min |
| Morning classes | 08:30–13:00 | class | seconds (skipped by sitting) |
| Lunch | 13:00–13:45 | free | 6 min |
| Afternoon classes | 13:45–15:30 | class | seconds |
| Cleaning time | 15:30–16:00 | free (she cleans her classroom or the hall) | 3 min |
| After school / club | 16:00–17:30 | free | 6 min |
| Going home | 17:30–18:00 | free, she leaves via the gate | 2 min |

- **Class bell:** the player has a grace window (≈ 5 game minutes) to reach and sit at their desk in 1-A. Sitting (interact) fades out, fast-forwards to the block's end, and fades back in at the desk.
- **Late:** + School Alert (small). **Skipping a class block:** + School Alert (large).
- **(builder call) If the player doesn't sit**, the class block runs in real time at a slower "class rate": about 3 real minutes for morning classes and 2 for afternoon classes. That leaves enough time to get upstairs and snoop. The 5-game-minute grace window is about 30 real seconds.
- **During class blocks:**
  - the target is at her desk in 2-B (she is still visible through the door window)
  - **(builder call)** during class only **her locker** can be searched. Desk items appear during free blocks while she's away from 2-B.
  - halls are empty except for the patrolling teacher
  - her locker and her desk area can hold items
  - the teacher seeing the player out of class raises School Alert
- **Day ends at 18:00** with an end-of-day summary (photos, items, intel unlocked, alerts). Then the next day starts with a new random seed.

### 4.3a The week and endings (user: one school week, multiple endings based on photos and intel)

- **(builder call)** A week is 5 days, Monday to Friday. The weekday is shown on the clock.
- Progress (day number, banked photos, items, intel, seeds used) is saved to `user://save.json` after each completed day and survives quitting. The main menu has **Continue** and **New Week**.
- Failing a day retries that weekday (see §4.5).
- After Friday's summary, a short ending scene plays at the courtyard cherry tree. **(builder call)** Two scores pick the ending:
  - **Photo score:** the sum of the week's photo quality points.
  - **Intel:** the number of cards unlocked.

  | | Low intel | High intel |
  |---|---|---|
  | **High photos** | **"The Shrine":** you never approach her. The camera pans across a wall covered in her photos. Unsettling ending. | **"Under the Cherry Tree":** you confess, she smiles (`happy`). Best ending. |
  | **Low photos** | **"Just a Stranger":** she walks past you without a glance. | **"Friends First":** she recognizes you and waves. You talk. |

- Thresholds live in `data/`. Each ending is a simple scripted camera shot with character animations, a facial expression, and an ending title card. Afterwards: **New Week**.
- Endings stay non-violent, consistent with the non-goals.

### 4.4 Target AI (user: stops seamless and not predictable)

- **Schedule-driven state machine.** Fixed blocks put her in class or at her cleaning duty. In free blocks she draws activities from a weighted pool:

  | Activity | Place |
  |---|---|
  | read on a bench | courtyard or rooftop |
  | buy and drink from the vending machine | vending machine |
  | chat with students | fountain or hallway |
  | rooftop visit | rooftop |
  | browse books | library |
  | fix her braid at the mirror | restroom |
  | club activity | club room |
  | sit at her desk with her phone | 2-B |
  | stroll the courtyard | courtyard |

- **Against predictability:**
  - activities she did recently, or did in the same block yesterday, get lower weight
  - durations, which of several spots per activity she uses, and walking speed (small range) are all randomized
  - while walking, a random 0–2 micro-stops: check phone, look out a window, glance over her shoulder, which is also a detection moment
  - each day uses its own seed
- **Seamless:**
  - `NavigationAgent3D` pathing with corner smoothing, and rotation interpolated toward velocity
  - arrival slows down, then aligns to the activity's anchor (a `Marker3D` with position and facing) before entering the activity animation
  - all animation changes go through `AnimationTree` blends or state-machine crossfades (≈ 0.2–0.4 s), never hard cuts
  - she avoids other characters with `NavigationAgent3D` avoidance
- **Reaction states:**

  | State | What she does |
  |---|---|
  | Normal | follows the schedule |
  | Notice | head and eyes turn toward the player, `suspicious` face, short pause |
  | Suspicious | watches the player for a few seconds, may resume more slowly |
  | Startled | caused by the flash or the player standing right next to her: `startled` face and anim, big Suspicion spike |
  | Report | at 100% Suspicion she reports you → game over |

  Her face shape keys follow the state (`happy` while chatting, `neutral` by default, plus `blink` on a timer).
- **Personal items:** at random, from the item list, while she does certain activities she leaves an item at the spot:
  - hairpin
  - handkerchief
  - pen
  - drink can
  - note
  - spare black ribbon
  - bookmark

  Some items also spawn in her locker or desk, and those can only be reached during class (when it's safest to snoop).

### 4.5 Detection and meters (builder call; spec numbers are tunable)

**Target Suspicion** (0–100, can be reduced):
- **Sight:** a FOV cone (≈ 110°, ≈ 12 m) and a raycast to the player's head and chest.
- **Gain:** scaled by how close you are, your stance (standing > walking > sneaking), what you're doing (camera raised > carrying her item > staring/following), and Sanity.
- **Crowd cover:** standing near ≥ 2 background students lowers gain.
- **Hearing:** radius by player movement (run ≈ 8 m, walk ≈ 3 m, sneak ≈ 1 m). Hearing triggers Notice (a turn toward the noise) rather than direct gain.
- **Falling off:** slowly drains while she can't see you. While you're hidden it drains to 0 over a few seconds.

**School Alert** (0–100, persists all day, does not drain from hiding):
- **Teacher sight:** teacher FOV + raycast. Gain when the teacher sees you:
  - out of class during a class block
  - running in the halls
  - with the camera raised at a student
  - carrying a stolen item
- **Attendance:** + for being late or skipping (see §4.3).
- **Students:** background students who witness a camera flash or a high-Suspicion moment add a small amount.
- **At 100:** you're sent to the principal → game over.

**Sanity** (0–100):
- **Drains** while the target has been out of the player's sight for more than about 30 s. **Recovers** while watching her (in view, within ≈ 15 m) and on good photos.
- **Low Sanity effects:**
  - below 40: vignette pulse and a louder heartbeat
  - below 25: Suspicion gain ×1.5 and slower sneaking
  - below 10: the player can't hide and the camera shakes
- Sanity is never a game over by itself.

**Game over** (target reports, or School Alert reaches 100):
- A screen with the reason.
- **(builder call) Retry day** restarts the same day number with a **new seed**, so a failed run can't be memorized.
- Photos and items from the failed attempt are discarded. Only what was banked at a completed day's end persists.
- A failed attempt does not count as "yesterday" for the weighting against repeats.

### 4.6 Player controller (builder call)

- Third-person, over the shoulder, with a `SpringArm3D` camera and mouse look. Camera collision keeps the view out of walls.
- **Stances:** walk, run, crouch-sneak. An `AnimationTree` blend space blends crouch ↔ stand and idle ↔ walk ↔ run by speed. Crouching lowers the collision shape.
- **Yandere Vision** (hold):
  - the world desaturates and dims
  - the target and her dropped items get an outline that shows through walls
  - player movement slows slightly
  - Sanity drain pauses while you hold it
- **Camera mode** (hold aim):
  - first-person viewfinder with zoom, focus reticle, a live photo-quality readout, and a shot counter
  - the flash is a toggle
  - taking a photo plays the shutter flash effect and saves the image
- **Photo quality score:**
  - the target is near the center of the frame
  - distance in the 3–15 m band
  - the raycast to her is unobstructed
  - she isn't looking at the camera
  - her face is visible
  - bonus for the activity being "rare intel"

  A good photo grants points and goes into the album. The image is captured from the viewport and saved to `user://photos/`.
- **Intel** is separate from photos. Photos measure obsession, intel measures how well you actually know her. Intel cards ("She sometimes goes to the rooftop at lunch", "She ties her braid with a spare ribbon") unlock from:
  - observing an activity from close by, unnoticed, for its full duration. Yandere Vision must be held or she must be in view
  - picking up certain items (a note, a bookmark)
  - photographing a rare activity

  Activity cards show that activity's weights for the next day in the album. They help you read her without making her predictable.
- **Items:**
  - you pick items up through an `Area3D` prompt
  - one carried item at a time, shown in the HUD inventory slot
  - you stash it at your shoe locker to bank it
  - if she sees you carrying her item, Suspicion spikes
- **Hiding:** enter a locker or go under a desk with a prompt and a short animation. The camera goes to the locker-slit or under-desk view, and Suspicion drains. Exiting is the reverse animation.
- **Default controls (KB+M):**

  | Key | Action |
  |---|---|
  | WASD | move |
  | Shift | run |
  | C | crouch toggle |
  | E | interact (sit, hide, pick up, stash) |
  | RMB | camera mode |
  | LMB | snap |
  | F | flash toggle |
  | Q (hold) | Yandere Vision |
  | T (hold) | fast-forward time |
  | Tab | album |
  | Esc | pause |

### 4.7 UI (spec + builder call)

- **Look:** a minimal anime HUD, pastel pink and white on dark translucent panels, with a rounded display font. Fonts must be license-free, either bundled or from Godot's default fallback.
- **HUD elements:**
  - top-left: a circular Sanity/heartbeat meter that pulses at heart rate
  - Suspicion bar with an eye/ear tell icon
  - School Alert bar
  - top-right: clock and current block name ("Lunch 13:12")
  - carried-item slot
  - context prompt ("E – Hide")
- **Overlays and feedback:**
  - camera viewfinder: frame corners, focus reticle, zoom, quality meter, flash icon
  - vignette shader pulse when Sanity is low or Suspicion is high
  - shutter flash plus brief desaturation on capture
- **Screens:**
  - bell transition banner
  - class fade (sitting fast-forward)
  - pause menu
  - album (photos, items, intel)
  - end-of-day summary
  - game over
  - main menu (Continue / New Week)
  - ending title card

### 4.8 Audio (builder call)

All sounds are synthesized, either offline with a Python script writing `.wav` into `assets/audio/` or at runtime with `AudioStreamGenerator`. Prefer offline WAVs for simplicity.

- **SFX:**
  - footsteps (walk, run, sneak variants)
  - heartbeat
  - camera shutter
  - school bell chime (Westminster-style four notes)
  - locker door
  - pickup chime
  - suspicion sting
  - game over sting
- **BGM:** a soft ambient school loop (a gentle pad or music-box style).

## 5. Architecture outline

Follows the user's requested layout, extended where needed:

```
yandere_demo/
├── project.godot                 # input map, autoloads, main scene
├── assets/
│   ├── models/                   # .glb from Blender (target, player, students, teacher, school, props)
│   ├── textures/                 # face/eye textures, toon ramps
│   ├── shaders/                  # toon.gdshader, outline, vignette, yandere_vision
│   └── audio/                    # synthesized .wav
├── blender/                      # .blend sources + the Python scripts that generate them (reproducible)
├── scenes/
│   ├── main.tscn                 # school_env + characters + HUD
│   ├── school_env.tscn
│   ├── target.tscn  player.tscn  student.tscn  teacher.tscn
│   ├── props/                    # locker (hide spot), desk (hide spot / seat), item pickup, activity anchor
│   └── ui/                       # hud, viewfinder, album, summary, game_over, pause
├── scripts/
│   ├── game_manager.gd           # autoload: day state, game over, day transitions, persistence
│   ├── school_clock.gd           # autoload: time, blocks, bells, fast-forward
│   ├── stealth_player.gd
│   ├── target_ai.gd              # state machine, activity execution, reactions
│   ├── target_scheduler.gd       # weighted random daily plan from activity pool + seed
│   ├── detection.gd              # shared sight/hearing helpers (FOV + raycast)
│   ├── sanity_system.gd          # Suspicion / School Alert / Sanity meters
│   ├── photo_mode.gd             # viewfinder, scoring, capture
│   ├── teacher_ai.gd  student_ai.gd
│   └── ui/…
├── data/                         # schedule_blocks, activity pool, item list, intel cards, tuning values
└── tests/                        # headless test scripts
```

**Data flow:**
- `SchoolClock` emits `block_changed(block: ScheduleBlock)` and `bell_rang(block_name: String)`.
- `TargetScheduler` produces the day plan.
- `TargetAI` executes it, and reports `player_seen(amount: float)` / `player_heard(position: Vector3)` to `SanitySystem`.
- `SanitySystem` emits `suspicion_changed`, `school_alert_changed`, `sanity_changed`, and `suspicion_triggered(amount: float)`.
- `GameManager` listens and handles game over and end of day.
- The HUD only listens to signals.

## 6. Verification

- **Headless logic tests** (`godot --headless --script` or a small test runner in `tests/`):
  - scheduler: deterministic for the same seed, different across seeds, every block covered, no impossible transitions
  - meter math: gain and decay, hiding drains to 0, thresholds
  - photo scoring
  - clock block boundaries and the attendance penalties
- **Headless smoke test:** load `main.tscn`, simulate a compressed full day at high time scale, and assert:
  - no script errors
  - the target reaches each planned activity anchor
  - the day-end signal fires
- **Run the project** via godot-mcp and read the debug output for errors and warnings.
- **Visual check:** windowed screenshots of the target next to the references, plus a short capture of a walk → activity transition to judge seamlessness.
- **Assets:** export settings, names, and suffixes are checked in Blender before export, and node paths are checked via godot-mcp before scenes are edited.

## 7. Left to the builder

- exact tuning numbers (all live in `data/`)
- mesh topology and detail level of props
- exact room dimensions
- shader implementation details
- spring-bone vs. baked secondary motion
- runtime vs. offline audio synthesis
- navmesh source (Blender `-navmesh` vs. Godot bake)
- how many background students
- test runner choice
- additional file names beyond those listed
