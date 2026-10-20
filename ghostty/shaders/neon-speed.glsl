// Neon Speed Lines - racing light streaks

float hash(float n) {
    return fract(sin(n) * 43758.5453123);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord.xy / iResolution.xy;
    vec2 p = uv - vec2(0.5);
    p.x *= iResolution.x / iResolution.y;

    float speed = iTime * 1.5;
    vec3 glow = vec3(0.0);

    // Create multiple light streaks
    for (int i = 0; i < 12; i++)
    {
        float fi = float(i);
        float h = hash(fi * 17.3);
        float h2 = hash(fi * 31.7);

        // Horizontal position of this streak
        float xPos = (h - 0.5) * 1.8;

        // Vertical motion - streaks fly upward
        float yPos = mod(speed * (0.6 + h2 * 0.8) + h * 20.0, 2.4) - 1.2;

        // Distance from streak center
        float dx = p.x - xPos;
        float dy = p.y - yPos;

        // Elongated vertically (speed streak shape)
        float streak = exp(-abs(dx) * 80.0) * exp(-dy * dy * 8.0);

        // Tail fade
        float tail = smoothstep(0.0, -0.4, dy) * exp(-abs(dx) * 60.0);

        // Color varies per streak
        vec3 col;
        if (h > 0.66) col = vec3(0.2, 0.6, 1.0);      // blue
        else if (h > 0.33) col = vec3(1.0, 0.3, 0.5);  // red-pink
        else col = vec3(0.3, 1.0, 0.7);                  // cyan-green

        glow += col * (streak * 0.6 + tail * 0.3) * (0.5 + h2 * 0.5);
    }

    // Sample terminal
    vec4 terminal = texture(iChannel0, uv);

    // Subtle overlay
    fragColor = vec4(terminal.rgb + glow * 0.12, terminal.a);
}
