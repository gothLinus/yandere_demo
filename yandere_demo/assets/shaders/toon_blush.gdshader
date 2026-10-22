shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_burley, specular_disabled, shadows_disabled;

#include "res://assets/shaders/toon_light.gdshaderinc"

// Cheek blush: a soft oval fading out from the patch centre (UV 0.5, 0.5), crossed by short diagonal strokes.
uniform vec4 albedo_color : source_color = vec4(0.95, 0.49, 0.58, 0.6);
uniform vec4 stroke_color : source_color = vec4(0.86, 0.33, 0.45, 1.0);
uniform float edge_softness : hint_range(0.0, 1.0) = 0.65;
uniform float stroke_strength : hint_range(0.0, 1.0) = 0.5;
uniform float stroke_count = 4.0;

void fragment() {
	vec2 offset = (UV - vec2(0.5)) * 2.0;
	float distance_from_center = length(offset);
	float fade = 1.0 - smoothstep(1.0 - edge_softness, 1.0, distance_from_center);
	float stroke_phase = fract((offset.x * 0.7 + offset.y) * stroke_count * 0.5);
	float strokes = (1.0 - smoothstep(0.08, 0.16, abs(stroke_phase - 0.5))) * (1.0 - smoothstep(0.25, 0.6, abs(offset.y)))
			* (1.0 - smoothstep(0.45, 0.7, abs(offset.x)));
	ALBEDO = mix(albedo_color.rgb, stroke_color.rgb, strokes * stroke_strength);
	ALPHA = albedo_color.a * fade + strokes * stroke_strength * 0.35 * fade;
}
