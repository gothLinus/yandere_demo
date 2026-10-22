shader_type spatial;
render_mode diffuse_burley, specular_disabled;

#include "res://assets/shaders/toon_light.gdshaderinc"

uniform vec4 albedo_color : source_color = vec4(1.0);
uniform sampler2D albedo_texture : source_color, hint_default_white;
uniform bool use_texture = false;
uniform bool is_vision_highlight = false;
// Hair shine: a band across every lock at a fixed fraction from root (UV.y 0) to tip (UV.y 1). It drifts with
// the viewing angle and has a jagged edge, which reads as the anisotropic "angel ring" of anime hair.
uniform bool use_hair_band = false;
uniform vec4 hair_band_color : source_color = vec4(1.0, 0.95, 0.97, 1.0);
uniform float hair_band_center : hint_range(0.0, 1.0) = 0.36;
uniform float hair_band_width : hint_range(0.0, 0.5) = 0.09;
uniform float hair_band_strength : hint_range(0.0, 1.0) = 0.7;
uniform float hair_band_view_shift : hint_range(0.0, 0.5) = 0.12;

void fragment() {
	vec4 base = albedo_color;
	if (use_texture) {
		base *= texture(albedo_texture, UV);
	}
	if (use_hair_band) {
		float facing = clamp(dot(NORMAL, VIEW), 0.0, 1.0);
		float center = hair_band_center + hair_band_view_shift * (0.6 - facing) + 0.018 * sin(UV.x * TAU * 2.0);
		float band = 1.0 - smoothstep(hair_band_width * 0.55, hair_band_width, abs(UV.y - center));
		base.rgb = mix(base.rgb, hair_band_color.rgb, band * hair_band_strength * smoothstep(0.1, 0.5, facing));
	}
	ALBEDO = base.rgb;
	ALPHA = base.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
}
