// Plasma - smooth flowing color blobs

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord.xy / iResolution.xy;
    float t = iTime * 0.4;

    vec2 p = uv * 3.0;

    // Classic plasma formula - overlapping sine waves
    float v1 = sin(p.x + t);
    float v2 = sin(p.y + t * 0.7);
    float v3 = sin(p.x + p.y + t * 0.5);
    float v4 = sin(length(p - vec2(1.5)) * 1.5 - t * 0.8);
    float v5 = sin(length(p - vec2(1.5, 1.0)) * 2.0 + t * 0.6);

    float v = (v1 + v2 + v3 + v4 + v5) * 0.2;

    // Map to colors - vibrant purple/pink/blue/teal
    vec3 plasma;
    plasma.r = sin(v * 3.14159 + 0.0) * 0.5 + 0.5;
    plasma.g = sin(v * 3.14159 + 2.1) * 0.5 + 0.5;
    plasma.b = sin(v * 3.14159 + 4.2) * 0.5 + 0.5;

    // Sample terminal
    vec4 terminal = texture(iChannel0, uv);

    // Subtle blend
    fragColor = vec4(terminal.rgb + plasma * 0.08, terminal.a);
}
