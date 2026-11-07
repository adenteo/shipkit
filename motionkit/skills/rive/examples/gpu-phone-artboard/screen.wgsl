struct U { mvp: mat4x4<f32> };
@group(0) @binding(0) var<uniform> u: U;
@group(0) @binding(1) var tex: texture_2d<f32>;
@group(0) @binding(2) var samp: sampler;
struct VIn { @location(0) pos: vec3<f32>, @location(1) uv: vec2<f32> };
struct VOut { @builtin(position) p: vec4<f32>, @location(0) uv: vec2<f32> };
@vertex fn vs_main(v: VIn) -> VOut {
    var o: VOut;
    o.p = u.mvp * vec4<f32>(v.pos, 1.0);
    o.uv = v.uv;
    return o;
}
@fragment fn fs_main(i: VOut) -> @location(0) vec4<f32> {
    return textureSample(tex, samp, i.uv);
}
