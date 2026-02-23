// Matrix Digital Rain - falling green characters effect

float hash(vec2 p) {
    float h = dot(p, vec2(127.1, 311.7));
    return fract(sin(h) * 43758.5453123);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord.xy / iResolution.xy;

    // Grid for the rain drops
    float columns = 80.0;
    float cellW = iResolution.x / columns;
    float cellH = cellW * 1.6;

    vec2 cell = vec2(floor(fragCoord.x / cellW), floor(fragCoord.y / cellH));
    vec2 cellUV = vec2(fract(fragCoord.x / cellW), fract(fragCoord.y / cellH));

    // Each column has its own speed and offset
    float colHash = hash(vec2(cell.x, 0.0));
    float speed = 3.0 + colHash * 5.0;
    float offset = colHash * 100.0;

    // Falling position
    float fall = mod(iTime * speed + offset, 60.0);
    float rowPos = cell.y + fall;

    // Character randomness (changes over time for animation)
    float charHash = hash(vec2(cell.x, floor(rowPos)));
    float charFlicker = hash(vec2(cell.x, floor(rowPos) + floor(iTime * 8.0)));

    // Trail fade - brighter at the head, fading behind
    float headPos = fall;
    float dist = mod(headPos - cell.y, 60.0);
    float trailLen = 15.0 + colHash * 15.0;
    float brightness = smoothstep(trailLen, 0.0, dist);

    // Head glow (white-green)
    float isHead = smoothstep(1.5, 0.0, dist);

    // Build the rain color
    vec3 green = vec3(0.0, 0.9, 0.3);
    vec3 white = vec3(0.8, 1.0, 0.85);
    vec3 rainColor = mix(green, white, isHead) * brightness;

    // Fade some columns to create depth variation
    rainColor *= 0.3 + 0.7 * colHash;

    // Flicker effect
    rainColor *= 0.8 + 0.2 * charFlicker;

    // Only show "characters" (not full cells)
    float charMask = step(0.15, cellUV.x) * step(cellUV.x, 0.85) *
                     step(0.1, cellUV.y) * step(cellUV.y, 0.9);
    // Randomize which cells have characters
    float showChar = step(0.3, charHash);
    rainColor *= charMask * showChar;

    // Sample terminal content
    vec4 terminal = texture(iChannel0, uv);

    // Overlay rain on top of terminal content
    float rainAlpha = brightness * 0.15 * showChar;
    fragColor = vec4(terminal.rgb + rainColor * rainAlpha, terminal.a);
}
