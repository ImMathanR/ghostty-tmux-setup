// Cyberpunk Grid - Tron-like perspective grid rushing forward

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord.xy / iResolution.xy;
    vec2 p = uv - vec2(0.5);
    p.x *= iResolution.x / iResolution.y;

    float t = iTime * 0.8;
    vec3 grid = vec3(0.0);

    // Only draw grid in bottom portion (ground plane)
    if (p.y < 0.05)
    {
        // Perspective projection
        float depth = 0.15 / (0.05 - p.y);
        float x = p.x * depth;
        float z = depth + t * 3.0;

        // Grid lines
        float lineX = smoothstep(0.06, 0.0, abs(fract(x * 0.5) - 0.5));
        float lineZ = smoothstep(0.06, 0.0, abs(fract(z * 0.15) - 0.5));
        float gridVal = max(lineX, lineZ);

        // Fade with distance
        float fade = exp(-depth * 0.15);
        gridVal *= fade;

        // Neon color - pink/cyan mix
        vec3 pink = vec3(1.0, 0.2, 0.6);
        vec3 cyan = vec3(0.1, 0.8, 1.0);
        vec3 col = mix(cyan, pink, lineX * 0.7);

        grid = col * gridVal * 0.7;

        // Horizon glow
        float horizon = exp(-pow((p.y - 0.05) * 40.0, 2.0));
        grid += mix(pink, cyan, 0.5) * horizon * 0.3;
    }
    else
    {
        // Subtle horizon glow bleeds upward
        float horizonGlow = exp(-(p.y - 0.05) * 12.0);
        grid = vec3(0.6, 0.2, 0.8) * horizonGlow * 0.08;
    }

    // Sample terminal
    vec4 terminal = texture(iChannel0, uv);

    fragColor = vec4(terminal.rgb + grid * 0.18, terminal.a);
}
