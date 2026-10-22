// Shared cel lighting for toon.gdshader and toon_blush.gdshader: two bands with a tinted shadow and a soft rim.
uniform vec4 shadow_tint : source_color = vec4(0.722, 0.639, 0.788, 1.0);
uniform float band_threshold : hint_range(0.0, 1.0) = 0.45;
uniform float band_softness : hint_range(0.0, 0.5) = 0.03;
uniform float rim_strength : hint_range(0.0, 1.0) = 0.25;
uniform vec4 rim_color : source_color = vec4(1.0);

void light() {
	float lit = clamp(dot(NORMAL, LIGHT), 0.0, 1.0) * ATTENUATION;
	float band = smoothstep(band_threshold - band_softness, band_threshold + band_softness, lit);
	vec3 light_energy = LIGHT_COLOR / PI;
	DIFFUSE_LIGHT += mix(shadow_tint.rgb * 0.6, vec3(1.0), band) * light_energy;
	float rim = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0) * rim_strength;
	SPECULAR_LIGHT += rim_color.rgb * rim * band * light_energy;
}
