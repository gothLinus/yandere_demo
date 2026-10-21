shader_type spatial;
render_mode unshaded, cull_front;

uniform float outline_width = 0.004;
uniform vec4 outline_color : source_color = vec4(0.169, 0.114, 0.18, 1.0);

void vertex() {
	VERTEX += NORMAL * outline_width;
}

void fragment() {
	ALBEDO = outline_color.rgb;
}
