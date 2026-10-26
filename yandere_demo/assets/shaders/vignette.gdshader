shader_type canvas_item;

uniform float strength : hint_range(0.0, 1.0) = 0.0;
uniform vec4 tint : source_color = vec4(0.45, 0.02, 0.18, 1.0);

void fragment() {
	float distance_from_center = length((UV - vec2(0.5)) * vec2(1.0, 0.8)) * 1.6;
	float edge = smoothstep(0.35, 1.0, distance_from_center);
	COLOR = vec4(tint.rgb, edge * strength);
}
