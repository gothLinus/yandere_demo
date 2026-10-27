# Source assets

Raw third-party sources the Blender build scripts read. The `blender/` folder has a `.gdignore`, so Godot never
imports anything here.

## `astolfo/`: the target character (Phase D)

A hand-made Astolfo model in Source Engine format by the Steam Workshop author "tobycrack", supplied by the user. It
ships without a license file and is likely ripped from a commercial game: it is used for this private demo only and
must not be redistributed (spec addendum `docs/superpowers/specs/2026-10-26-astolfo-target-design.md`, §4).

| Path | What it is |
|---|---|
| `Models/tobycrack/astolfo/astolfo.mdl`, `.vvd`, `.dx90.vtx`, `.phy` | the original model (MDL v49), unchanged |
| `Materials/Models/tobycrack/astolfo/*.vmt`, `*.vtf` | the original materials and textures, unchanged |
| `textures/*.png` | the `.vtf` textures converted to PNG at native resolution by the one-time import |
| `astolfo_source.blend` | the imported model: armature `tobycrack\astolfo\Astolfo_ARM` (114 bones), 7 meshes, the head's 55 flexes, the attachment empties, materials pointing at `textures/` |

### Normal rebuild (no SourceIO needed)

`build_target.py` appends the armature and meshes from `astolfo_source.blend` and converts them to the target
contract (`lib/astolfo.py`), then keys every clip and exports `assets/models/target.glb`:

```
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python yandere_demo/blender/build_target.py
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python yandere_demo/blender/validate_assets.py -- --only target
```

Godot does not reimport a `.glb` when only its post-import script changes, so after an export clear the cached
import and reimport:

```
rm -rf yandere_demo/.godot/imported/target*
godot --headless --path yandere_demo --import
```

### Re-running the one-time import

Only needed if the raw source changes. It needs the SourceIO add-on, which must never be installed into your own
Blender: load it from an isolated scripts directory instead.

1. Download SourceIO 5.5.4 (MIT, <https://github.com/REDxEYE/SourceIO>, release asset for Blender 5.x).
2. Unpack it into a throwaway directory so that the add-on sits at `<scratch>/blender_user/scripts/addons/SourceIO/`.
3. Run the import with that directory as Blender's user scripts and factory settings, so nothing of your own
   configuration is read or written:

   ```
   BLENDER_USER_SCRIPTS=<scratch>/blender_user/scripts \
       /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
       --python yandere_demo/blender/import_astolfo_source.py
   ```

4. Expected: `textures/*.png` and `astolfo_source.blend` are rewritten, and the report prints 114 bones, 55 face
   flexes, the seven meshes with their triangles and materials, and the attachment empties.
5. Delete the scratch directory.

The script calls

```
bpy.ops.sourceio.mdl(filepath=..., directory=..., files=[{"name": "astolfo.mdl"}],
                     import_animations=False, import_physics=False, create_flex_drivers=False)
```

- `import_animations=True` crashes Blender on this model, and the model has no animations worth keeping.
- The physics meshes (`Astolfo_solid_*`) are ragdoll hulls the target does not use.
- Flex drivers are not needed: `lib/astolfo.py` bakes the flexes into the game's expression shape keys.
- SourceIO pins the attachment empties (`eyes`, `mouth`, `forward`, `anim_attachment_*`) with constraints. The script
  bakes their world placement and drops the constraints, so the `.blend` opens without the add-on.

### What `lib/astolfo.py` changes on the way to `target.glb`

- Uniform scale to a 1.62 m crown, soles on the floor. The `ValveBiped.Bip01_*` bones get the project's humanoid
  names (`rig.HUMANOID_BONES`); `Spine1` and `Spine4` fold into `spine` and `chest`. The hips bone points straight up.
- Helper bones (`*_helper`: shoulder, elbow, wrist, ulna, knee, ankle, chest, glute) keep their weights and follow
  their parents. They have no springs.
- Hair, bow and ribbon bones get project chain names (`hair_front_*`, `hair_side_*`, `hair_back_*`, `braid_NN`,
  `braid_bow_NN`, `head_bow_{L,R}_NN`, `ribbon_{L,R}_NN`). Eight 3-bone skirt chains (`skirt_00..07_01..03`) are
  added and the skirt is re-weighted to them.
- The forefoot of the body, socks and shoes is moved onto the toe bones (the model weights its feet to the foot
  only), so a heel lift keeps the toe box on the floor.
- The arms are lowered to the project's rest angle, so the FK clips apply unchanged.
- Meshes become `Target<Part>`, materials `M_<Part>` (Principled BSDF on the model's own textures). The face's flexes
  become the game's expression keys (`EXPRESSION_FLEXES` is the mapping table). `Target-col` is a capsule fitted to
  the body.
