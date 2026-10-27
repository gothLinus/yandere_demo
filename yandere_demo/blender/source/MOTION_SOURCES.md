# Motion sources

Where every target clip's motion comes from. Spec addendum §6: only sources that allow use in a private, non-commercial
project, each recorded here with its license. "scripted" means keyed by `lib/target_animations.py` on the converted
rig, with no external motion data.

Task 23b (anime acting pass) re-authored every clip and chose scripted for all eighteen; no external motion data is
used, so no third-party license applies. Reasons, per clip below and overall:
- Every clip is tied to landmarks measured on this model (seat height and clearance, lap, mouth, eyes, braid, the
  prop grips) and to the checks that guard them (IK-planted feet with no slide at 1.3 m/s, knees together when seated,
  the front skirt over the lap, no sightline under the skirt, props in the palm with the fingers round them). Retargeted
  capture would need the same IK and contact passes on top, and its proportions would fight the seat and the props.
- Motion capture is realistic rather than anime-styled; the acting bar (anticipation, head-led turns, overlapping lags,
  graceful hands, the startle hop) is easier to hit exactly with keyed curves on this rig.

| Clip | Source | Author | License | URL | Acting (Task 23b) |
|---|---|---|---|---|---|
| `target_idle` | scripted (`lib/target_animations.py`) | project | project | n/a | weight shift led by the hips, chest and head trailing; a finger roll and a head tilt mid-loop |
| `target_walk_routine` | scripted (`lib/target_animations.py`) | project | project | n/a | narrow-tracking walk with fuller hip sway; steeper swing lift so the toe and heel never skim the floor; trailing hands |
| `target_notice_player` | scripted (`lib/target_animations.py`) | project | project | n/a | a caught breath, then a head-first turn the body follows; the right hand drifts to the chest |
| `target_startled` | scripted (`lib/target_animations.py`) | project | project | n/a | flinch, hop onto the toes with the hands snapping to the chest, landing into bent knees, quick breaths |
| `target_look_around` | scripted (`lib/target_animations.py`) | project | project | n/a | counter-move before each turn, head leads, overshoots and settles; wary hand at the chest |
| `target_sit_down` | scripted (`lib/target_animations.py`) | project | project | n/a | glance back at the seat, hands press the skirt front down over the thighs and ride onto the lap; knees together |
| `target_stand_up` | scripted (`lib/target_animations.py`) | project | project | n/a | push off the lap, the hands slide up the thighs and let go as he rises; knees together |
| `target_sit` | scripted (`lib/target_animations.py`) | project | project | n/a | seated breathing and weight shift, hands together on the lap, a head-led glance, a heel tap |
| `target_sit_read` | scripted (`lib/target_animations.py`) | project | project | n/a | open book held in both hands from below, reading the lines, the left hand turns a page |
| `target_phone` | scripted (`lib/target_animations.py`) | project | project | n/a | phone in the right palm, thumb scrolling, lift closer and a giggle; left hand on the lap |
| `target_drink` | scripted (`lib/target_animations.py`) | project | project | n/a | can in a wrapped grip: dip, raise, tip to the lips with the head back, swallows, sigh, index tap |
| `target_fix_braid` | scripted (`lib/target_animations.py`) | project | project | n/a | cradle and stroke the braid, fingers opening off it between strokes |
| `target_lean_chat` | scripted (`lib/target_animations.py`) | project | project | n/a | lean with a weight rock, open fanned talking hand, giggle behind the hand, nods |
| `target_sweep` | scripted (`lib/target_animations.py`) | project | project | n/a | broom in both fists, its head kept on the floor by the handle length, strokes with body lag |
| `target_wave` | scripted (`lib/target_animations.py`) | project | project | n/a | wave from the elbow with the hand trailing and flicking over, bob on the beats, head tilt against it |
| `target_idle_shy` | scripted (`lib/target_animations.py`) | project | project | n/a | toe turned in and rocking, twiddling fingers, a peek up and back down |
| `target_idle_playful` | scripted (`lib/target_animations.py`) | project | project | n/a | heel bounce with the head riding it late, hands behind the back |
| `target_idle_confident` | scripted (`lib/target_animations.py`) | project | project | n/a | hand on hip, chin up, slow rock with a hip pop |
