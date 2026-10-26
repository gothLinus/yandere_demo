shader_type canvas_item;

uniform sampler2D screen_texture : hint_screen_texture, filter_linear_mipmap;
uniform float amount : hint_range(0.0, 1.0) = 0.0;

void fragment() {
	vec3 scene_color = textureLod(screen_texture, SCREEN_UV, 0.0).rgb;
	float luminance = dot(scene_color, vec3(0.299, 0.587, 0.114));
	COLOR = vec4(mix(scene_color, vec3(luminance), amount), amount);
}
