# Character upgrade prompt (user-supplied, 2026-10-21)

The user's optimized character prompt, kept as reference material. The binding version is spec §4.1b. Its scope decisions:

- **No glasses:** the prompt mentions glasses, but the reference images don't show any, so they're dropped.
- **Godot only:** no offline cloth simulation, VRM/FBX export, Rigify, or T-pose.
- **Inaccurate description of the old render:** the "two small ear accessories" the prompt describes were round bows in the first render, and they're now flat ribbon bows. The neckerchief is pink.

## Design direction (femboy anime look)

**Silhouette**
- Slim and soft: narrow shoulders, slender neck, a gently defined but narrow waist, modest hips, a flat chest under the uniform, and long slim legs with soft knees.
- Delicate and cute; not muscular, not exaggerated.

**Face**
- Soft rounded jaw, small nose, large expressive anime eyes with long lashes, thin soft brows, a small mouth, and an optional slight blush.
- 8–10 blendshapes: smile, blush, surprised, sad, wink L/R, mouth A/I/U/E/O, blink.
- Eye-highlight and pupil controls.

**Hands and feet:** small, slender fingers and neat small feet, with simple but clean topology.

**Posing:** three idle poses (shy, playful, confident), each with a weight shift, a slight hip tilt and a head tilt.

**Uniform fit**
- The sailor top sits slightly loose on the narrow frame.
- The sleeves rest softly on the upper arms.
- The skirt hangs over narrow hips with even pleats: 16–24, from a pleat generator with adjustable count, depth and hem flare.

**Details:** hair clips on the head accessories, a thin ribbon or pin on the collar, knee-high or thigh-high socks, and optional hair-highlight textures.

## Mesh and topology
- Head-to-body ratio about 1:6.5–7, narrow shoulders, slim limbs.
- Edge loops around the eyes, mouth, shoulders, elbows, knees and waist.
- Separate objects and material slots: body, face, eyes, eyelashes, hair, braid, uniform top, neckerchief, skirt, socks, shoes, accessories.
- Uniform: soft fabric folds, collar and sleeve thickness, a neckerchief with a knot, hem trim.
- Toon shading: cel ramp, outline (inverted hull), soft rim light, hair highlight band, and a subtle cheek blush.

## Rig
- A clean humanoid armature.
- Extra bones for secondary motion: hair clusters, the ahoge, the full braid chain (8–12 bones), the bow, the neckerchief ends, the skirt (one chain per panel or pleat group) and the sleeves.
- Automatic Weights, then Data Transfer, then cleanup. Check the shoulders, armpits, and the hips and thighs under the skirt.

## Physics (real-time)
- **Hair, braid, ahoge:** spring-bone stiffness, damping, gravity and collision radius per chain. The braid is heavier and swings slower; the ahoge is light and bouncy.
- **Skirt:** bone chains with thigh and hip colliders sized for the slim build, so the skirt never clips through the legs.
- **Sleeves, neckerchief, bow:** light spring-bone motion.

## Testing
- Test animations: idle, walk, turn, jump, sit.
- Common failures to watch for: jitter, clipping, exploding chains.
