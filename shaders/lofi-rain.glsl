// Lofi Rain - realistic rain with water body and ripples

float hash(float n) {
    return fract(sin(n) * 43758.5453);
}

float hash2(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float hash3(vec2 p) {
    return fract(sin(dot(p, vec2(269.5, 183.3))) * 43758.5453);
}

// Smooth noise for organic shapes
float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash2(i);
    float b = hash2(i + vec2(1.0, 0.0));
    float c = hash2(i + vec2(0.0, 1.0));
    float d = hash2(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

// Fractional brownian motion for natural-looking turbulence
float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    vec2 shift = vec2(100.0);
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
    for (int i = 0; i < 4; i++) {
        v += a * noise(p);
        p = rot * p * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

// Single ripple ring
float ripple(vec2 uv, vec2 center, float birth, float t) {
    float age = t - birth;
    if (age < 0.0 || age > 2.5) return 0.0;

    float dist = length(uv - center);
    float radius = age * 0.06;
    float ringWidth = 0.003 + age * 0.004;
    float ring = exp(-pow((dist - radius) / ringWidth, 2.0));

    // Fade out over lifetime
    float fade = exp(-age * 1.8);
    // Second smaller ring
    float radius2 = age * 0.035;
    float ring2 = exp(-pow((dist - radius2) / (ringWidth * 0.7), 2.0)) * 0.5;

    return (ring + ring2) * fade;
}

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord.xy / iResolution.xy;
    float aspect = iResolution.x / iResolution.y;
    float t = iTime;

    vec3 effect = vec3(0.0);

    // Slowly shifting wind
    float windPhase = t * 0.08;
    float wind = sin(windPhase) * 0.015 + sin(windPhase * 1.7 + 1.3) * 0.008
               + sin(windPhase * 0.3 + 3.0) * 0.004;
    float angle = wind * 6.0;
    float sa = sin(angle);
    float ca = cos(angle);

    // Water body height
    float waterLevel = 0.12;
    // Slight wave on the water edge
    float waveEdge = waterLevel + sin(uv.x * 25.0 + t * 1.2) * 0.003
                                + sin(uv.x * 40.0 - t * 0.8) * 0.002;

    // ========== RAIN DROPS ==========

    // --- Foreground drops: large, slow, bright ---
    for (int i = 0; i < 18; i++)
    {
        float fi = float(i);
        float h1 = hash(fi * 17.31);
        float h2 = hash(fi * 43.17);
        float h3 = hash(fi * 71.93);
        float h4 = hash(fi * 97.51);

        // Staggered lifecycles
        float cycle = 2.0 + h2 * 2.5;
        float birth = h1 * 25.0 + h3 * 9.0;
        float localT = mod(t - birth, cycle);

        // Fall from above screen to water level
        float fallDist = 1.15 - waveEdge;
        float speed = 0.28 + h3 * 0.18;
        float fallTime = fallDist / speed;
        float alive = step(localT, fallTime);

        float y = 1.15 - localT * speed;

        // Clustered x with organic spread
        float x = h1 + sin(fi * 3.7) * 0.15 + (h2 - 0.5) * 0.2;
        x = fract(x);
        // Wind drift accumulates over fall
        x += localT * wind;
        // Micro turbulence
        float turb = sin(localT * (4.0 + h2 * 6.0) + fi * 2.1) * 0.0015;
        turb += sin(localT * (7.0 + h4 * 3.0) + fi) * 0.0008;
        x += turb;

        vec2 diff = uv - vec2(fract(x), y);
        diff.x *= aspect;
        // Tilt with wind
        diff = vec2(diff.x * ca - diff.y * sa, diff.x * sa + diff.y * ca);

        // Varied drop geometry
        float dropLen = 0.022 + h2 * 0.02 + h4 * 0.01;
        float dropWidth = 0.0007 + h4 * 0.0005;

        // Speed increases slightly as drop falls (acceleration)
        float accelStretch = 1.0 + localT * 0.1;
        dropLen *= accelStretch;

        float streak = 0.0;
        if (diff.y > 0.0 && diff.y < dropLen) {
            // Tapered tail, bright head
            float taper = pow(1.0 - diff.y / dropLen, 0.5);
            float head = exp(-diff.y * 60.0) * 1.2;
            streak = exp(-abs(diff.x) / dropWidth) * taper
                   + head * exp(-abs(diff.x) / (dropWidth * 2.5));
        }

        float brightness = 0.3 + h3 * 0.2;
        vec3 dropCol = vec3(0.6 + h4 * 0.1, 0.68 + h4 * 0.08, 0.82 + h2 * 0.06);
        effect += dropCol * streak * brightness * alive;
    }

    // --- Mid layer ---
    for (int i = 0; i < 35; i++)
    {
        float fi = float(i);
        float h1 = hash(fi * 11.17 + 200.0);
        float h2 = hash(fi * 29.53 + 300.0);
        float h3 = hash(fi * 67.31 + 400.0);
        float h4 = hash(fi * 83.71 + 500.0);

        float cycle = 1.5 + h2 * 1.8;
        float birth = h1 * 35.0 + h4 * 13.0;
        float localT = mod(t - birth, cycle);

        float speed = 0.38 + h3 * 0.22;
        float fallTime = (1.1 - waveEdge) / speed;
        float alive = step(localT, fallTime);

        float x = h1 + (h2 - 0.5) * 0.18;
        float y = 1.1 - localT * speed;

        x += localT * wind * 0.85;
        x += sin(localT * (5.0 + h4 * 4.0) + fi * 1.7) * 0.001;

        vec2 diff = uv - vec2(fract(x), y);
        diff.x *= aspect;
        diff = vec2(diff.x * ca - diff.y * sa, diff.x * sa + diff.y * ca);

        float dropLen = 0.01 + h2 * 0.012;
        float dropWidth = 0.00045;

        float streak = 0.0;
        if (diff.y > 0.0 && diff.y < dropLen) {
            float taper = pow(1.0 - diff.y / dropLen, 0.6);
            streak = exp(-abs(diff.x) / dropWidth) * taper;
        }

        float brightness = 0.1 + h4 * 0.12;
        effect += vec3(0.5, 0.58, 0.72) * streak * brightness * alive;
    }

    // --- Fine drizzle background ---
    for (int i = 0; i < 50; i++)
    {
        float fi = float(i);
        float h1 = hash(fi * 7.13 + 600.0);
        float h2 = hash(fi * 23.97 + 700.0);
        float h3 = hash(fi * 51.31 + 800.0);
        float h4 = hash(fi * 89.17 + 900.0);

        float cycle = 0.8 + h2 * 0.8;
        float birth = h1 * 50.0 + h3 * 17.0;
        float localT = mod(t - birth, cycle);

        float speed = 0.45 + h3 * 0.25;
        float alive = step(localT, (1.05 - waveEdge) / speed);

        float x = h1;
        float y = 1.05 - localT * speed;

        x += localT * wind * 0.6;

        vec2 diff = uv - vec2(fract(x), y);
        diff.x *= aspect;

        float dropLen = 0.004 + h2 * 0.005;
        float dropWidth = 0.00035;

        float streak = 0.0;
        if (diff.y > 0.0 && diff.y < dropLen) {
            streak = exp(-abs(diff.x) / dropWidth) * (1.0 - diff.y / dropLen);
        }

        effect += vec3(0.4, 0.45, 0.6) * streak * 0.06 * alive;
    }

    // ========== WATER BODY ==========

    if (uv.y < waveEdge + 0.02)
    {
        // Water surface
        float waterDepth = max(0.0, waveEdge - uv.y);
        float waterMask = smoothstep(0.0, 0.008, waterDepth);

        // Animated water surface texture
        vec2 waterUV = vec2(uv.x * 8.0, uv.y * 3.0);
        float surface = fbm(waterUV + vec2(t * 0.15, t * 0.05));
        float surface2 = fbm(waterUV * 1.5 + vec2(-t * 0.1, t * 0.08) + 50.0);
        float surfaceDetail = (surface + surface2 * 0.6) * 0.5;

        // Water color - dark with subtle variation
        vec3 waterDeep = vec3(0.04, 0.07, 0.14);
        vec3 waterShallow = vec3(0.08, 0.13, 0.22);
        vec3 waterCol = mix(waterShallow, waterDeep, waterDepth / waterLevel);

        // Surface light caustics
        float caustic = pow(surfaceDetail, 3.0) * 2.0;
        waterCol += vec3(0.1, 0.15, 0.25) * caustic;

        // Gentle surface shimmer
        float shimmer = sin(uv.x * 60.0 + t * 2.0 + surface * 5.0) * 0.5 + 0.5;
        shimmer *= sin(uv.x * 35.0 - t * 1.5 + surface2 * 3.0) * 0.5 + 0.5;
        waterCol += vec3(0.06, 0.08, 0.12) * shimmer * exp(-waterDepth * 15.0);

        // ========== RIPPLES from rain hitting water ==========
        float ripples = 0.0;
        for (int i = 0; i < 15; i++)
        {
            float fi = float(i);
            float rh1 = hash(fi * 31.17 + 1000.0);
            float rh2 = hash(fi * 57.31 + 1100.0);
            float rh3 = hash(fi * 79.53 + 1200.0);

            // Ripple spawn position on water surface
            vec2 rippleCenter = vec2(rh1, waterLevel * 0.5 + rh2 * waterLevel * 0.4);

            // Staggered ripple births
            float rippleCycle = 2.0 + rh3 * 2.0;
            float rippleBirth = floor((t + rh1 * rippleCycle) / rippleCycle) * rippleCycle - rh1 * rippleCycle;

            vec2 ruv = vec2(uv.x, uv.y);
            ruv.x *= aspect;
            rippleCenter.x *= aspect;

            ripples += ripple(ruv, rippleCenter, rippleBirth, t);
        }

        waterCol += vec3(0.15, 0.2, 0.3) * ripples;

        // Reflection hint - subtle vertical smear of terminal content above
        vec2 reflUV = vec2(uv.x, waveEdge + (waveEdge - uv.y) * 0.3);
        reflUV.x += sin(uv.y * 30.0 + t * 1.5) * 0.008; // wavy reflection
        reflUV.x += surface * 0.01;
        if (reflUV.y > waveEdge && reflUV.y < 1.0) {
            vec4 reflected = texture(iChannel0, reflUV);
            waterCol += reflected.rgb * 0.06 * exp(-waterDepth * 8.0);
        }

        // Blend water over terminal
        vec4 terminal = texture(iChannel0, uv);
        fragColor = vec4(mix(terminal.rgb, waterCol, waterMask * 0.85) + effect * 0.2, terminal.a);
    }
    else
    {
        // Atmospheric mist - more near water, fades up
        float distToWater = uv.y - waveEdge;
        float mist = exp(-distToWater * 5.0) * 0.02;
        // Breathing mist
        mist *= 0.8 + 0.2 * sin(t * 0.15 + uv.x * 3.0);

        // Very faint top haze
        mist += exp(-(1.0 - uv.y) * 6.0) * 0.008;

        effect += vec3(0.35, 0.42, 0.55) * mist;

        vec4 terminal = texture(iChannel0, uv);
        fragColor = vec4(terminal.rgb + effect * 0.2, terminal.a);
    }
}
