// Subtle water caustics shader for Ghostty
// Creates a gentle, animated water light pattern over the terminal

#define TAU 6.28318530718
#define MAX_ITER 5

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    float time = iTime * 0.3 + 23.0;
    vec2 uv = fragCoord.xy / iResolution.xy;

    // Create caustic pattern
    vec2 p = mod(uv * TAU, TAU) - 250.0;
    vec2 i = vec2(p);
    float c = 1.0;
    float inten = 0.005;

    for (int n = 0; n < MAX_ITER; n++)
    {
        float t = time * (1.0 - (3.5 / float(n + 1)));
        i = p + vec2(
            cos(t - i.x) + sin(t + i.y),
            sin(t - i.y) + cos(t + i.x)
        );
        c += 1.0 / length(vec2(
            p.x / (sin(i.x + t) / inten),
            p.y / (cos(i.y + t) / inten)
        ));
    }

    c /= float(MAX_ITER);
    c = 1.17 - pow(c, 1.4);
    float intensity = pow(abs(c), 15.0);

    // Blue-cyan water tint
    vec3 waterColor = vec3(0.55, 0.75, 1.0);
    vec3 color = mix(waterColor, vec3(1.0), intensity * 0.5);

    // UV distortion for "through water" effect
    vec2 tc = vec2(cos(c) - 0.75, sin(c) - 0.75) * 0.01;
    uv = clamp(uv + tc, 0.0, 1.0);

    // Sample terminal content
    fragColor = texture(iChannel0, uv);

    // Blend the water effect
    fragColor.rgb *= mix(vec3(1.0), color, 0.14);
}
