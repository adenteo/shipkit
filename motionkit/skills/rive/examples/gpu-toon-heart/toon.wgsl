struct U {
    mvp: mat4x4<f32>,
    model: mat4x4<f32>,
    light: vec4<f32>,
    shadow: vec4<f32>,
    mid: vec4<f32>,
    lit: vec4<f32>,
    ink: vec4<f32>,
    params: vec4<f32>,   // x = outline width (model units)
};
@group(0) @binding(0) var<uniform> u: U;

struct VIn { @location(0) pos: vec3<f32>, @location(1) nrm: vec3<f32> };
struct VOut { @builtin(position) p: vec4<f32>, @location(0) n: vec3<f32> };

@vertex fn vs_toon(v: VIn) -> VOut {
    var o: VOut;
    o.p = u.mvp * vec4<f32>(v.pos, 1.0);
    o.n = (u.model * vec4<f32>(v.nrm, 0.0)).xyz;
    return o;
}

// Inverted hull: push every vertex out along its normal; drawn with front faces culled
@vertex fn vs_outline(v: VIn) -> VOut {
    var o: VOut;
    o.p = u.mvp * vec4<f32>(v.pos + normalize(v.nrm) * u.params.x, 1.0);
    o.n = v.nrm;
    return o;
}

@fragment fn fs_toon(i: VOut) -> @location(0) vec4<f32> {
    let n = normalize(i.n);
    let d = dot(n, normalize(u.light.xyz));
    // three tones, band edges softened by one pixel of fwidth so they never stair-step
    let w = max(fwidth(d), 0.001);
    let toLit = smoothstep(0.45 - w, 0.45 + w, d);
    let toShadow = smoothstep(-0.05 + w, -0.05 - w, d);
    var c = mix(u.mid.rgb, u.lit.rgb, toLit);
    c = mix(c, u.shadow.rgb, toShadow);
    return vec4<f32>(c, 1.0);
}

@fragment fn fs_outline(i: VOut) -> @location(0) vec4<f32> {
    return vec4<f32>(u.ink.rgb, 1.0);
}
