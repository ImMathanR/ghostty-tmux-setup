// Aurora Borealis - flowing northern lights

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord.xy / iResolution.xy;
    float t = iTime * 0.3;

    vec3 aurora = vec3(0.0);

    // Layer multiple flowing waves
    for (int i = 0; i < 5; i++)
    {
        float fi = float(i);
        float freq = 1.5 + fi * 0.7;
        float amp = 0.03 - fi * 0.004;
        float speed = t * (0.8 + fi * 0.15);

        // Wavy band position
        float wave = sin(uv.x * freq + speed) * amp
                   + sin(uv.x * freq * 2.3 + speed * 1.3) * amp * 0.5
                   + sin(uv.x * freq * 0.7 - speed * 0.7) * amp * 0.7;

        float band = 0.75 + fi * 0.04 + wave;

        // Soft glow around band
        float glow = exp(-pow((uv.y - band) * 18.0, 2.0));

        // Color shifts between green, teal, purple
        vec3 col;
        float phase = fi * 1.2 + t * 0.4;
        col.r = 0.1 + 0.15 * sin(phase + 3.5);
        col.g = 0.5 + 0.3 * sin(phase + 0.5);
        col.b = 0.4 + 0.35 * sin(phase + 1.8);

        aurora += col * glow * (0.4 + 0.2 * sin(t + fi));
    }

    // Sample terminal
    vec4 terminal = texture(iChannel0, uv);

    // Blend aurora subtly
    fragColor = vec4(terminal.rgb + aurora * 0.15, terminal.a);
}
