shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_burley, specular_disabled, shadows_disabled;

#include "res://assets/shaders/toon_light.gdshaderinc"

// Window glass: translucent and never alpha-scissored, so it stays visible while the room behind shows through.
// Grazing angles turn more opaque, as real glass reflects more there.
uniform vec4 albedo_color : source_color = vec4(0.83, 0.93, 0.97, 0.25);
uniform float edge_opacity : hint_range(0.0, 1.0) = 0.25;

void fragment() {
	float grazing = pow(1.0 - clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0), 3.0);
	ALBEDO = albedo_color.rgb;
	ALPHA = clamp(albedo_color.a + grazing * edge_opacity, 0.0, 0.9);
}
