"""Structural checks for generated character assets, run inside Blender."""

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

PROXY_MATERIAL_NAME = "M_CollisionProxy"
# Godot's import suffixes for a trimesh and a convex collision proxy.
PROXY_SUFFIXES = ("-col", "-convcol")
IDENTITY_TOLERANCE = 1e-5
LOOP_SEAM_TOLERANCE = 1e-4
ANIMATION_FPS = 30


def validate_character(
    prefix: str,
    required_shape_keys: list[str],
    required_actions: dict[str, tuple[int, bool]],
    required_bones: list[str],
    required_meshes: list[str] | None = None,
    proxy_name: str | None = None,
) -> list[str]:
    """Return error strings.

    `required_actions` maps action name to (frame count, loops). `required_meshes` are part names,
    checked as f"{prefix}{part}" mesh children. `proxy_name` defaults to f"{prefix}-col".
    """
    errors: list[str] = []
    armature = bpy.data.objects.get(f"{prefix}Char")
    if armature is None or armature.type != "ARMATURE":
        return [f"armature {prefix}Char is missing"]

    bone_names = {bone.name for bone in armature.data.bones}
    for bone_name in required_bones:
        if bone_name not in bone_names:
            errors.append(f"bone {bone_name} is missing from {armature.name}")

    for part in required_meshes or []:
        mesh_object = bpy.data.objects.get(f"{prefix}{part}")
        if mesh_object is None or mesh_object.type != "MESH" or mesh_object.parent != armature:
            errors.append(f"mesh {prefix}{part} is missing or not parented to {armature.name}")

    errors.extend(_validate_face(prefix, required_shape_keys))
    errors.extend(_validate_collision_proxy(proxy_name or f"{prefix}-col", armature))
    errors.extend(_validate_meshes(armature))

    errors.extend(_validate_actions(armature, required_actions))
    return errors


def _validate_actions(armature, required_actions: dict[str, tuple[int, bool]]) -> list[str]:
    errors: list[str] = []
    if required_actions and bpy.context.scene.render.fps != ANIMATION_FPS:
        errors.append(f"scene runs at {bpy.context.scene.render.fps} fps, expected {ANIMATION_FPS}")
    animation_data = armature.animation_data
    strip_actions = set()
    if animation_data is not None:
        strip_actions = {strip.action.name for track in animation_data.nla_tracks for strip in track.strips if strip.action}
    for action_name, (frame_count, loops) in required_actions.items():
        action = bpy.data.actions.get(action_name)
        if action is None:
            errors.append(f"action {action_name} is missing")
            continue
        if action_name not in strip_actions:
            errors.append(f"action {action_name} has no NLA strip on {armature.name}")
        frame_range = tuple(round(value) for value in action.frame_range)
        if frame_range != (0, frame_count):
            errors.append(f"action {action_name} spans frames {frame_range}, expected (0, {frame_count})")
        if loops:
            for fcurve in action_fcurves(action):
                points = fcurve.keyframe_points
                if len(points) and abs(points[0].co[1] - points[-1].co[1]) > LOOP_SEAM_TOLERANCE:
                    errors.append(f"action {action_name} loops but {fcurve.data_path}[{fcurve.array_index}] differs at the seam")
                    break
    return errors


def action_fcurves(action) -> list:
    """F-curves of every layer, strip and slot (Blender 4.4+ layered actions)."""
    fcurves = []
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                fcurves.extend(channelbag.fcurves)
    return fcurves


def _validate_face(prefix: str, required_shape_keys: list[str]) -> list[str]:
    face = bpy.data.objects.get(f"{prefix}Face")
    if face is None:
        return [f"face mesh {prefix}Face is missing"] if required_shape_keys else []
    keys = face.data.shape_keys
    names = sorted(block.name for block in keys.key_blocks) if keys else []
    expected = sorted(["Basis"] + list(required_shape_keys))
    if names != expected:
        return [f"{face.name} shape keys are {names}, expected exactly {expected}"]
    return []


def _validate_collision_proxy(proxy_name: str, armature) -> list[str]:
    errors: list[str] = []
    proxy = bpy.data.objects.get(proxy_name)
    if proxy is None:
        return [f"collision proxy {proxy_name} is missing"]
    if proxy.parent != armature:
        errors.append(f"{proxy.name} must be parented to {armature.name}")
    if proxy.parent_bone:
        errors.append(f"{proxy.name} must not be parented to a bone")
    material_names = [slot.material.name for slot in proxy.material_slots if slot.material]
    if material_names != [PROXY_MATERIAL_NAME]:
        errors.append(f"{proxy.name} must use only {PROXY_MATERIAL_NAME}, has {material_names}")
    if not _is_identity(proxy.matrix_local):
        errors.append(f"{proxy.name} must sit at an identity transform under {armature.name}")
    return errors


def _validate_meshes(armature) -> list[str]:
    errors: list[str] = []
    meshes = [child for child in armature.children_recursive if child.type == "MESH"]
    if not meshes:
        errors.append(f"{armature.name} has no mesh children")
    for mesh_object in meshes:
        if not mesh_object.material_slots:
            errors.append(f"{mesh_object.name} has no material")
        for slot in mesh_object.material_slots:
            if slot.material is None or not slot.material.name.startswith("M_"):
                errors.append(f"{mesh_object.name} has a material not named M_<Part>")
        unapplied = [modifier.name for modifier in mesh_object.modifiers if modifier.type != "ARMATURE"]
        if unapplied:
            errors.append(f"{mesh_object.name} has unapplied modifiers {unapplied}")
        if mesh_object.name.endswith(PROXY_SUFFIXES):
            continue
        if not any(modifier.type == "ARMATURE" for modifier in mesh_object.modifiers):
            errors.append(f"{mesh_object.name} is not skinned to {armature.name}")
        if not mesh_object.vertex_groups:
            errors.append(f"{mesh_object.name} has no vertex groups")
    return errors


def _is_identity(matrix) -> bool:
    for row in range(4):
        for column in range(4):
            expected = 1.0 if row == column else 0.0
            if abs(matrix[row][column] - expected) > IDENTITY_TOLERANCE:
                return False
    return True


HEAD_RATIO_RANGE = (6.5, 7.0)
TINT_MATERIAL_NAME = "M_UniformTint"
HEIGHT_TOLERANCE = 0.005
SHOULDER_TO_HIP_LIMIT = 1.05
TORSO_GROUPS = {"hips", "spine", "thigh.L", "thigh.R"}
ZERO_AREA = 1e-10


def validate_target_extras(prefix: str, shape_keys: list[str], pleat_count: int,
                           skirt_clear_actions: list[str] | None = None,
                           braid_clear_actions: list[str] | None = None) -> list[str]:
    """Checks for the 4.1b target: shape keys on the split face meshes, the hidden blush, the pleat count,
    skinned fingers, the femboy silhouette, no leg poking through the skirt in `skirt_clear_actions`, and no
    braid or bow sinking into the skirt in `braid_clear_actions`."""
    errors: list[str] = []
    for action_name in braid_clear_actions or []:
        if bpy.data.actions.get(action_name) is None:
            continue
        sunk = [(frame, count, depth) for frame, count, depth in braid_skirt_penetrations(prefix, action_name) if count]
        if sunk:
            frame, count, depth = max(sunk, key=lambda item: item[2])
            errors.append(f"{action_name}: the braid or its bow sinks into the skirt in {len(sunk)} frames "
                          f"(worst frame {frame}: {count} vertices, {depth * 1000:.1f} mm)")
    for action_name in skirt_clear_actions or []:
        if bpy.data.actions.get(action_name) is None:
            continue
        pokes = [(frame, count, depth) for frame, count, depth in skirt_penetrations(prefix, action_name) if count]
        if pokes:
            frame, count, depth = max(pokes, key=lambda item: item[2])
            errors.append(f"{action_name}: legs poke through the skirt in {len(pokes)} frames "
                          f"(worst frame {frame}: {count} vertices, {depth * 1000:.1f} mm)")
    for part in ("Eyes", "Lashes"):
        errors.extend(_validate_shape_keys(f"{prefix}{part}", shape_keys))
    errors.extend(_validate_shape_keys(f"{prefix}Blush", ["blush"]))
    errors.extend(_validate_blush_hidden(f"{prefix}Blush"))
    skirt = bpy.data.objects.get(f"{prefix}Skirt")
    if skirt is not None and skirt.get("pleat_count") != pleat_count:
        errors.append(f"{skirt.name} pleat_count is {skirt.get('pleat_count')}, expected {pleat_count}")
    body = bpy.data.objects.get(f"{prefix}Body")
    if body is not None:
        group_names = {group.name for group in body.vertex_groups}
        for finger_tip in ("thumb_03.L", "index_03.L", "pinky_03.R"):
            if finger_tip not in group_names:
                errors.append(f"{body.name} has no weights for {finger_tip}")
        errors.extend(_validate_silhouette(prefix, body))
    return errors


def validate_cast_extras(prefix: str, shape_keys: list[str], hair_variants: list[str], absent_bones: list[str],
                         tinted_meshes: list[str], required_materials: list[str], height: float,
                         triangle_budget: int | None = None, skirt_clear_actions: list[str] | None = None) -> list[str]:
    """Checks for the supporting cast: shape keys on the eyes and lashes, swappable hair meshes named exactly,
    bones that must not exist, meshes using a tintable material, required material names, the character's
    height, a triangle budget for one visible outfit (one hair variant shown), skinned fingers, and no leg
    poking through the skirt in `skirt_clear_actions`."""
    errors: list[str] = []
    armature = bpy.data.objects.get(f"{prefix}Char")
    if armature is None:
        return [f"armature {prefix}Char is missing"]
    for part in ("Eyes", "Lashes"):
        errors.extend(_validate_shape_keys(f"{prefix}{part}", shape_keys))
    for variant in hair_variants:
        hair = bpy.data.objects.get(variant)
        if hair is None or hair.type != "MESH" or hair.parent != armature:
            errors.append(f"hair mesh {variant} is missing or not parented to {armature.name}")
        elif "M_Hair" not in [slot.material.name for slot in hair.material_slots if slot.material]:
            errors.append(f"{variant} does not use M_Hair")
    bone_names = {bone.name for bone in armature.data.bones}
    for bone_name in absent_bones:
        if bone_name in bone_names:
            errors.append(f"bone {bone_name} must not exist on {armature.name}")
    for part in tinted_meshes:
        mesh_object = bpy.data.objects.get(f"{prefix}{part}")
        names = [slot.material.name for slot in mesh_object.material_slots if slot.material] if mesh_object else []
        if TINT_MATERIAL_NAME not in names:
            errors.append(f"{prefix}{part} does not use {TINT_MATERIAL_NAME}")
    used_materials = {slot.material.name for child in armature.children if child.type == "MESH"
                      for slot in child.material_slots if slot.material}
    for material_name in required_materials:
        if material_name not in used_materials:
            errors.append(f"no mesh of {armature.name} uses {material_name}")
    crown = (armature.matrix_world @ armature.data.bones["head"].tail_local).z
    if abs(crown - height) > HEIGHT_TOLERANCE:
        errors.append(f"{armature.name} is {crown:.3f} m tall, expected {height:.3f} m")
    if triangle_budget is not None:
        triangles = visible_triangles(armature, hair_variants)
        if triangles > triangle_budget:
            errors.append(f"{armature.name} shows {triangles} triangles, over the budget of {triangle_budget}")
    body = bpy.data.objects.get(f"{prefix}Body")
    if body is not None:
        group_names = {group.name for group in body.vertex_groups}
        for finger_tip in ("thumb_03.L", "index_03.L", "pinky_03.R"):
            if finger_tip not in group_names:
                errors.append(f"{body.name} has no weights for {finger_tip}")
    for action_name in skirt_clear_actions or []:
        if bpy.data.actions.get(action_name) is None:
            continue
        pokes = [(frame, count, depth) for frame, count, depth in skirt_penetrations(prefix, action_name) if count]
        if pokes:
            frame, count, depth = max(pokes, key=lambda item: item[2])
            errors.append(f"{action_name}: legs poke through the skirt in {len(pokes)} frames "
                          f"(worst frame {frame}: {count} vertices, {depth * 1000:.1f} mm)")
    return errors


def visible_triangles(armature, hair_variants: list[str]) -> int:
    """Triangles of every mesh under the armature with only the largest hair variant counted (one is shown)."""
    total = 0
    variant_triangles = [0]
    for child in armature.children:
        if child.type != "MESH" or child.name.endswith(PROXY_SUFFIXES):
            continue
        triangles = sum(len(polygon.vertices) - 2 for polygon in child.data.polygons)
        if child.name in hair_variants:
            variant_triangles.append(triangles)
        else:
            total += triangles
    return total + max(variant_triangles)


def _validate_shape_keys(object_name: str, required: list[str]) -> list[str]:
    mesh_object = bpy.data.objects.get(object_name)
    if mesh_object is None:
        return [f"{object_name} is missing"]
    keys = mesh_object.data.shape_keys
    names = sorted(block.name for block in keys.key_blocks) if keys else []
    expected = sorted(["Basis"] + list(required))
    if names != expected:
        return [f"{object_name} shape keys are {names}, expected exactly {expected}"]
    return []


def _validate_blush_hidden(object_name: str) -> list[str]:
    """At blush = 0 every blush polygon must have zero area, so nothing renders."""
    blush = bpy.data.objects.get(object_name)
    if blush is None or blush.data.shape_keys is None:
        return []
    basis = blush.data.shape_keys.key_blocks["Basis"].data
    for polygon in blush.data.polygons:
        corners = [basis[index].co for index in polygon.vertices]
        area = sum(((corners[index] - corners[0]).cross(corners[index + 1] - corners[0])).length
                   for index in range(1, len(corners) - 1))
        if area > ZERO_AREA:
            return [f"{object_name} is visible with blush at 0 (polygon {polygon.index} has area {area:.2e})"]
    return []


def _validate_silhouette(prefix: str, body) -> list[str]:
    errors: list[str] = []
    armature = body.parent
    names = {group.index: group.name for group in body.vertex_groups}
    upper_arm = armature.matrix_world @ armature.data.bones["upper_arm.L"].head_local
    hips = armature.matrix_world @ armature.data.bones["hips"].head_local
    shoulder_half = 0.0
    hip_half = 0.0
    for vertex in body.data.vertices:
        point = body.matrix_world @ vertex.co
        if abs(point.z - upper_arm.z) < 0.01:
            shoulder_half = max(shoulder_half, abs(point.x))
        dominant = max(vertex.groups, key=lambda element: element.weight, default=None)
        if dominant is not None and names[dominant.group] in TORSO_GROUPS and hips.z - 0.14 < point.z < hips.z + 0.02:
            hip_half = max(hip_half, abs(point.x))
    if hip_half <= 0.0 or shoulder_half > hip_half * SHOULDER_TO_HIP_LIMIT:
        errors.append(f"shoulder width {2 * shoulder_half:.3f} m exceeds {SHOULDER_TO_HIP_LIMIT} x hip width {2 * hip_half:.3f} m")
    face = bpy.data.objects.get(f"{prefix}Face")
    if face is not None and "head" in face.vertex_groups:
        head_group = face.vertex_groups["head"].index
        heights = [(face.matrix_world @ vertex.co).z for vertex in face.data.vertices
                   if any(element.group == head_group for element in vertex.groups)]
        crown = max(heights)
        ratio = (armature.matrix_world @ armature.data.bones["head"].tail_local).z / (crown - min(heights))
        if not HEAD_RATIO_RANGE[0] <= ratio <= HEAD_RATIO_RANGE[1]:
            errors.append(f"head-to-height ratio is 1:{ratio:.2f}, expected 1:{HEAD_RATIO_RANGE[0]}-{HEAD_RATIO_RANGE[1]}")
    return errors


SKIRT_PENETRATION_TOLERANCE = 0.003
# Skirt faces this close to the hem (rest pose, fraction of the skirt length) count as the hem edge, where legs
# legitimately show below the fabric.
SKIRT_HEM_FRACTION = 0.9
# A poke is a leg vertex just outside the fabric; anything further away is leg showing below the hem.
SKIRT_POKE_RANGE = 0.04
# A ray this steeply downward leaves through the hem opening: that skin is only seen from beneath the skirt.
SKIRT_OPENING_SLOPE = 0.6


def skirt_penetrations(prefix: str, action_name: str) -> list[tuple[int, int, float]]:
    """(frame, leg vertices poking out through the skirt, deepest poke in metres) for every frame of an action.

    A thigh or knee vertex pokes through when no skirt lies further out along the ray from its leg bone through
    it, while the nearest
    skirt face is above the hem edge (so a leg simply showing below the hem does not count).
    """
    armature = bpy.data.objects[f"{prefix}Char"]
    skirt = bpy.data.objects[f"{prefix}Skirt"]
    legs = [bpy.data.objects[f"{prefix}{part}"] for part in ("Body", "Socks")]
    action = bpy.data.actions[action_name]
    rest_z = [polygon.center.z for polygon in skirt.data.polygons]
    top, bottom = max(rest_z), min(rest_z)
    interior = [(top - z) / (top - bottom) < SKIRT_HEM_FRACTION for z in rest_z]
    leg_vertices = {}
    for leg in legs:
        names = {group.index: group.name for group in leg.vertex_groups}
        leg_vertices[leg.name] = [(vertex.index, names[dominant.group]) for vertex in leg.data.vertices
                                  if (dominant := max(vertex.groups, key=lambda element: element.weight, default=None))
                                  and names[dominant.group].startswith(("thigh", "shin"))]
    animation_data = armature.animation_data_create()
    previous_action = animation_data.action
    animation_data.action = action
    if hasattr(animation_data, "action_slot") and action.slots:
        animation_data.action_slot = action.slots[0]
    scene = bpy.context.scene
    results = []
    for frame in range(int(action.frame_range[0]), int(action.frame_range[1]) + 1):
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated_skirt = skirt.evaluated_get(depsgraph)
        mesh = evaluated_skirt.to_mesh()
        vertices = [skirt.matrix_world @ vertex.co for vertex in mesh.vertices]
        tree = BVHTree.FromPolygons(vertices, [tuple(polygon.vertices) for polygon in mesh.polygons])
        evaluated_skirt.to_mesh_clear()
        bones = {name: (armature.matrix_world @ armature.pose.bones[name].head, armature.matrix_world @ armature.pose.bones[name].tail)
                 for name in ("thigh.L", "thigh.R", "shin.L", "shin.R")}
        count = 0
        deepest = 0.0
        for leg in legs:
            evaluated_leg = leg.evaluated_get(depsgraph)
            leg_mesh = evaluated_leg.to_mesh()
            for index, bone_name in leg_vertices[leg.name]:
                point = leg.matrix_world @ leg_mesh.vertices[index].co
                start, end = bones[bone_name]
                segment = end - start
                along = (point - start).dot(segment) / segment.length_squared
                if along <= 0.0:
                    # Above the hip joint (the crease of a raised thigh) a leg has no radial direction: the ray would
                    # run up inside the torso. That skin sits under the skirt's waist.
                    continue
                along = min(1.0, along)
                direction = point - (start + segment * along)
                length = direction.length
                if length < 1e-6 or direction.z < -SKIRT_OPENING_SLOPE * length:
                    continue
                # Covered when the skirt lies further out along the ray from the body axis through the vertex.
                hit, _, _, _ = tree.ray_cast(point, direction / length, 1.0)
                if hit is not None:
                    continue
                location, normal, face_index, distance = tree.find_nearest(point)
                if (location is None or not interior[face_index % len(interior)]
                        or not SKIRT_PENETRATION_TOLERANCE <= distance <= SKIRT_POKE_RANGE):
                    continue
                count += 1
                deepest = max(deepest, distance)
            evaluated_leg.to_mesh_clear()
        results.append((frame, count, deepest))
    animation_data.action = previous_action
    return results


# Braid bones whose hair hangs at skirt height, plus the bow on its tip.
BRAID_SKIRT_BONES = ("braid_07", "braid_08", "braid_09", "braid_10", "braid_bow")
BRAID_SKIRT_TOLERANCE = 0.001
BRAID_SKIRT_RANGE = 0.08


def braid_skirt_penetrations(prefix: str, action_name: str) -> list[tuple[int, int, float]]:
    """(frame, braid and bow vertices hidden inside the skirt, deepest in metres) for every frame of a standing action.

    A vertex is inside when a ray from it, pointing away from the hips' vertical axis, still meets the skirt: the
    fabric then lies further out than the bow or braid at that height.
    """
    armature = bpy.data.objects[f"{prefix}Char"]
    skirt = bpy.data.objects[f"{prefix}Skirt"]
    sources = [bpy.data.objects[f"{prefix}{part}"] for part in ("Braid", "Accessories")]
    action = bpy.data.actions[action_name]
    vertex_lists = {}
    for source in sources:
        names = {group.index: group.name for group in source.vertex_groups}
        vertex_lists[source.name] = [vertex.index for vertex in source.data.vertices
                                     if (dominant := max(vertex.groups, key=lambda element: element.weight, default=None))
                                     and names[dominant.group] in BRAID_SKIRT_BONES]
    animation_data = armature.animation_data_create()
    previous_action = animation_data.action
    animation_data.action = action
    if hasattr(animation_data, "action_slot") and action.slots:
        animation_data.action_slot = action.slots[0]
    scene = bpy.context.scene
    results = []
    for frame in range(int(action.frame_range[0]), int(action.frame_range[1]) + 1):
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated_skirt = skirt.evaluated_get(depsgraph)
        mesh = evaluated_skirt.to_mesh()
        vertices = [skirt.matrix_world @ vertex.co for vertex in mesh.vertices]
        tree = BVHTree.FromPolygons(vertices, [tuple(polygon.vertices) for polygon in mesh.polygons])
        evaluated_skirt.to_mesh_clear()
        hips = armature.matrix_world @ armature.pose.bones["hips"].matrix
        axis_origin = hips.translation
        up = (hips.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
        count = 0
        deepest = 0.0
        for source in sources:
            evaluated = source.evaluated_get(depsgraph)
            source_mesh = evaluated.to_mesh()
            for index in vertex_lists[source.name]:
                point = source.matrix_world @ source_mesh.vertices[index].co
                radial = point - axis_origin
                radial -= up * radial.dot(up)
                if radial.length < 1e-6:
                    continue
                location, _, _, distance = tree.ray_cast(point, radial.normalized(), BRAID_SKIRT_RANGE)
                if location is None or distance < BRAID_SKIRT_TOLERANCE:
                    continue
                count += 1
                deepest = max(deepest, distance)
            evaluated.to_mesh_clear()
        results.append((frame, count, deepest))
    animation_data.action = previous_action
    return results
