// Starfield - flying through space

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord.xy / iResolution.xy;
    vec2 p = (fragCoord.xy - iResolution.xy * 0.5) / iResolution.y;

    float t = iTime * 0.4;
    vec3 stars = vec3(0.0);

    // Multiple star layers for depth
    for (int layer = 0; layer < 4; layer++)
    {
        float fl = float(layer);
        float speed = 0.5 + fl * 0.4;
        float scale = 30.0 + fl * 20.0;
        float brightness = 0.6 - fl * 0.1;

        // Grid cells for star placement
        vec2 st = p * scale;
        vec2 cell = floor(st);
        vec2 f = fract(st) - 0.5;

        for (int x = -1; x <= 1; x++)
        for (int y = -1; y <= 1; y++)
        {
            vec2 neighbor = vec2(float(x), float(y));
            vec2 id = cell + neighbor;

            float h = hash(id + fl * 100.0);
            if (h > 0.7) continue; // only some cells have stars

            // Star position within cell
            vec2 starPos = neighbor + vec2(hash(id * 1.3), hash(id * 2.7)) - 0.5 - f;

            // Streaking effect - stretch toward center based on distance
            vec2 dir = normalize(starPos);
            float dist = length(starPos);
            float streak = exp(-dist * (8.0 - speed * 2.0));

            // Twinkle
            float twinkle = 0.7 + 0.3 * sin(t * 3.0 + h * 30.0);

            // Star color - mostly white with hints of blue/warm
            vec3 col = vec3(1.0);
            if (h < 0.2) col = vec3(0.7, 0.85, 1.0); // blue tint
            else if (h < 0.35) col = vec3(1.0, 0.9, 0.75); // warm tint

            stars += col * streak * brightness * twinkle * 0.5;
        }
    }

    // Sample terminal
    vec4 terminal = texture(iChannel0, uv);

    fragColor = vec4(terminal.rgb + stars * 0.1, terminal.a);
}
