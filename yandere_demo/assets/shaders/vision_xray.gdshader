shader_type spatial;
render_mode unshaded, depth_test_disabled, cull_back;

uniform vec4 rim_color : source_color = vec4(1.0, 0.1647, 0.4275, 1.0);
uniform float rim_power : hint_range(0.5, 8.0) = 2.5;
uniform float base_alpha : hint_range(0.0, 1.0) = 0.18;

void fragment() {
	float rim = pow(1.0 - clamp(dot(normalize(NORMAL), normalize(VIEW)), 0.0, 1.0), rim_power);
	ALBEDO = rim_color.rgb;
	ALPHA = clamp(base_alpha + rim, 0.0, 1.0);
}
