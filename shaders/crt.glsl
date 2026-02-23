// Retro CRT Monitor - scanlines, curvature, and phosphor glow

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord.xy / iResolution.xy;

    // Screen curvature
    vec2 curved = uv * 2.0 - 1.0;
    float dist = dot(curved, curved) * 0.08;
    curved *= 1.0 + dist;
    vec2 curvedUV = curved * 0.5 + 0.5;

    // Check bounds
    if (curvedUV.x < 0.0 || curvedUV.x > 1.0 || curvedUV.y < 0.0 || curvedUV.y > 1.0) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // Sample terminal with slight RGB offset (chromatic aberration)
    float aberration = 0.0008;
    vec4 r = texture(iChannel0, curvedUV + vec2(aberration, 0.0));
    vec4 g = texture(iChannel0, curvedUV);
    vec4 b = texture(iChannel0, curvedUV - vec2(aberration, 0.0));
    vec4 terminal = vec4(r.r, g.g, b.b, g.a);

    // Scanlines
    float scanline = sin(fragCoord.y * 3.14159) * 0.04;
    terminal.rgb -= scanline;

    // Subtle phosphor flicker
    float flicker = 1.0 - sin(iTime * 8.0) * 0.008;
    terminal.rgb *= flicker;

    // Vignette - darken edges
    vec2 vig = uv * (1.0 - uv);
    float vignette = pow(vig.x * vig.y * 20.0, 0.15);
    terminal.rgb *= vignette;

    // Slight green/amber tint for that retro feel
    terminal.rgb *= vec3(0.95, 1.0, 0.95);

    fragColor = terminal;
}
