local json = require('json')

type Prim = { attrs: { [string]: GPUBuffer }, idx: GPUBuffer, count: number }
type Phone = {
    screen: Input<Artboard>,
    board: Artboard?,
    body: Prim?, glass: Prim?,
    toon: GPUPipeline?, outline: GPUPipeline?, tex: GPUPipeline?,
    toonUbo: GPUBuffer?, texUbo: GPUBuffer?,
    toonBind: GPUBindGroup?, texBind: GPUBindGroup?,
    gpu: GPUCanvas?, screenCanvas: Canvas?,
    msaaView: GPUTextureView?, depthView: GPUTextureView?,
    toonBytes: buffer, texBytes: buffer,
    size: Vector, scale: number, t: number,
    sampler: ImageSampler,
    mvp: Mat4?,
    model: Mat4?,
}

-- glTF binary: every mesh's first primitive, attributes uploaded as their own vertex buffers
local function loadGlb(data: buffer): { [string]: Prim }
    local jsonLen = buffer.readu32(data, 12)
    local gl = json.decode(buffer.readstring(data, 20, jsonLen))
    local binStart = 20 + jsonLen + 8
    local function upload(accessorIndex: number, usage: BufferUsage): (GPUBuffer, number)
        local acc = gl.accessors[accessorIndex + 1]
        local view = gl.bufferViews[acc.bufferView + 1]
        local bytes = buffer.create(view.byteLength)
        buffer.copy(bytes, 0, data, binStart + (view.byteOffset or 0) + (acc.byteOffset or 0), view.byteLength)
        return GPUBuffer.new({ size = view.byteLength, usage = usage, data = bytes, immutable = true }), acc.count
    end
    local out = {}
    for _, mesh in gl.meshes do
        local p = mesh.primitives[1]
        local attrs = {}
        for name, index in p.attributes do attrs[name] = (upload(index, 'vertex')) end
        local idx, count = upload(p.indices, 'index')
        out[mesh.name] = { attrs = attrs, idx = idx, count = count }
    end
    return out
end

function init(self: Phone, context: Context): boolean
    local blob = context:blob('phone')
    local toonShader = context:shader('toon')
    local texShader = context:shader('screen')
    if not blob or not toonShader or not texShader then
        print('missing asset')
        return false
    end
    local meshes = loadGlb(blob.data)
    self.body, self.glass = meshes.Body, meshes.Screen
    self.board = self.screen:instance()

    local v3: { VertexBufferLayout } = {
        { stride = 12, attributes = { { format = 'float32x3', slot = 0 } } },
        { stride = 12, attributes = { { format = 'float32x3', slot = 1 } } },
    }
    local v3uv: { VertexBufferLayout } = {
        { stride = 12, attributes = { { format = 'float32x3', slot = 0 } } },
        { stride = 8, attributes = { { format = 'float32x2', slot = 1 } } },
    }
    local depth: DepthStencilState = { format = 'depth32float', compare = 'less', write = true }
    local function pipe(shader: Shader, vs: string, fs: string, layout: { VertexBufferLayout }, cull: CullMode): GPUPipeline
        return GPUPipeline.new({
            vertex = { module = shader, entryPoint = vs }, fragment = { module = shader, entryPoint = fs },
            vertexLayout = layout, colorTargets = { { format = 'rgba8unorm' } },
            depthStencil = depth, cullMode = cull, sampleCount = 4,
        })
    end
    self.toon = pipe(toonShader, 'vs_toon', 'fs_toon', v3, 'back')
    self.outline = pipe(toonShader, 'vs_outline', 'fs_outline', v3, 'front')
    self.tex = pipe(texShader, 'vs_main', 'fs_main', v3uv, 'none')

    self.toonUbo = GPUBuffer.new({ size = 224, usage = 'uniform' })
    self.texUbo = GPUBuffer.new({ size = 64, usage = 'uniform' })
    self.toonBind = GPUBindGroup.new({
        layout = (self.toon :: GPUPipeline):getBindGroupLayout(0),
        ubos = { { slot = 0, buffer = self.toonUbo :: GPUBuffer } },
    })
    -- The live artboard is drawn into a 2D canvas each frame; its image is a texture view
    local sc = context:canvas({ width = 720, height = 1480 })
    self.screenCanvas = sc
    self.texBind = GPUBindGroup.new({
        layout = (self.tex :: GPUPipeline):getBindGroupLayout(0),
        ubos = { { slot = 0, buffer = self.texUbo :: GPUBuffer } },
        textures = { { slot = 1, view = sc.image:view() } },
        samplers = { { slot = 2, sampler = GPUSampler.new({ min = 'linear', mag = 'linear' }) } },
    })
    self.gpu = context:gpuCanvas()
    return true
end

function resize(self: Phone, size: Vector, scale: number)
    self.size, self.scale = size, scale
    local w, h = math.max(1, math.floor(size.x * scale)), math.max(1, math.floor(size.y * scale))
    local gpu = self.gpu :: GPUCanvas
    gpu:resize(w, h)
    self.msaaView = GPUTexture.new({ width = w, height = h, format = gpu.format, renderTarget = true, sampleCount = 4 }):view()
    self.depthView = GPUTexture.new({ width = w, height = h, format = 'depth32float', renderTarget = true, sampleCount = 4 }):view()
end

function advance(self: Phone, seconds: number): boolean
    self.t += seconds
    if self.board then (self.board :: Artboard):advance(seconds) end
    local aspect = self.size.x / math.max(1, self.size.y)
    local proj = Mat4.perspective(math.rad(30), aspect, 0.1, 50)
    local view = Mat4.lookAt(Vector.xyz(0, 0, 7.6), Vector.xyz(0, 0, 0), Vector.xyz(0, 1, 0))
    self.model = Mat4.fromRotationY(-0.5 + math.sin(self.t * 0.8) * 0.25) * Mat4.fromRotationX(-0.18)
    self.mvp = proj * view * (self.model :: Mat4)
    return true
end

local function v4(b: buffer, off: number, x: number, y: number, z: number, w: number)
    buffer.writef32(b, off, x); buffer.writef32(b, off + 4, y)
    buffer.writef32(b, off + 8, z); buffer.writef32(b, off + 12, w)
end
local function hex(b: buffer, off: number, c: number)
    v4(b, off, bit32.extract(c, 16, 8) / 255, bit32.extract(c, 8, 8) / 255, bit32.extract(c, 0, 8) / 255, 1)
end

function draw(self: Phone, renderer: Renderer)
    local gpu, sc, body, glass = self.gpu, self.screenCanvas, self.body, self.glass
    if not gpu or not sc or not body or not glass or gpu.width == 0 or not self.mvp then return end

    -- 1. the 2D artboard, rendered by the Rive renderer into its canvas
    local r2 = sc:beginFrame({ clearColor = 0xFFFFFFFF })
    r2:transform(Mat2D.withScale(2))
    if self.board then (self.board :: Artboard):draw(r2) end
    sc:endFrame()

    -- 2. uniforms (matrices are computed in advance, so pointer handlers can use them before any draw)
    local mvp, model = self.mvp :: Mat4, self.model :: Mat4
    local tb = self.toonBytes
    mvp:writeToBuffer(tb, 0); model:writeToBuffer(tb, 64)
    v4(tb, 128, -0.6, 0.7, 0.5, 0)
    hex(tb, 144, 0x5B6FA8); hex(tb, 160, 0x8FA3D9); hex(tb, 176, 0xC9D6F5); hex(tb, 192, 0x3E2A22)
    v4(tb, 208, 0.025, 0, 0, 0)
    ;(self.toonUbo :: GPUBuffer):write(tb)
    mvp:writeToBuffer(self.texBytes, 0)
    ;(self.texUbo :: GPUBuffer):write(self.texBytes)

    -- 3. one MSAA pass: outline hull, toon body, textured screen
    local pass = gpu:beginRenderPass({
        color = { { view = self.msaaView, resolveTarget = gpu:colorView(), loadOp = 'clear', storeOp = 'discard', clearColor = { 0, 0, 0, 0 } } },
        depthStencil = { view = self.depthView :: GPUTextureView, depthLoadOp = 'clear', depthStoreOp = 'discard', depthClearValue = 1 },
    })
    for _, p in { self.outline, self.toon } do
        pass:setPipeline(p :: GPUPipeline)
        pass:setBindGroup(0, self.toonBind :: GPUBindGroup)
        pass:setVertexBuffer(0, body.attrs.POSITION)
        pass:setVertexBuffer(1, body.attrs.NORMAL)
        pass:setIndexBuffer(body.idx, 'uint16')
        pass:drawIndexed(body.count)
    end
    pass:setPipeline(self.tex :: GPUPipeline)
    pass:setBindGroup(0, self.texBind :: GPUBindGroup)
    pass:setVertexBuffer(0, glass.attrs.POSITION)
    pass:setVertexBuffer(1, glass.attrs.TEXCOORD_0)
    pass:setIndexBuffer(glass.idx, 'uint16')
    pass:drawIndexed(glass.count)
    pass:finish()

    renderer:save()
    renderer:transform(Mat2D.withScale(1 / self.scale))
    renderer:drawImage(gpu.image, self.sampler, 'srcOver', 1)
    renderer:restore()
end

-- A pointer on the 3D view: unproject into model space, hit the screen plane, turn the hit into
-- artboard coordinates and hand the artboard a real PointerEvent, so its listeners fire.
local SW, SH, SZ = 0.71, 1.53, 0.092
local function toScreen(self: Phone, event: PointerEvent): PointerEvent?
    local mvp = self.mvp
    if not mvp then return nil end
    local inv = mvp:invert()
    if not inv then return nil end
    local x = event.position.x / self.size.x * 2 - 1
    local y = 1 - event.position.y / self.size.y * 2
    local n = inv:transformPoint(x, y, 0)
    local f = inv:transformPoint(x, y, 1)
    if math.abs(f.z - n.z) < 1e-6 then return nil end
    local t = (SZ - n.z) / (f.z - n.z)
    local hx, hy = n.x + (f.x - n.x) * t, n.y + (f.y - n.y) * t
    local u, v = (hx + SW) / (2 * SW), 1 - (hy + SH) / (2 * SH)
    if u < 0 or u > 1 or v < 0 or v > 1 then return nil end
    return PointerEvent.new(event.id, Vector.xy(u * 360, v * 740))
end
local function forward(kind: string)
    return function(self: Phone, event: PointerEvent)
        local board, e = self.board, toScreen(self, event)
        if not board or not e then return end
        if kind == 'down' then (board :: Artboard):pointerDown(e)
        elseif kind == 'up' then (board :: Artboard):pointerUp(e)
        else (board :: Artboard):pointerMove(e) end
    end
end

return function(context: Context): Layout<Phone>
    return {
        screen = late(), board = nil, body = nil, glass = nil,
        toon = nil, outline = nil, tex = nil, toonUbo = nil, texUbo = nil, toonBind = nil, texBind = nil,
        gpu = nil, screenCanvas = nil, msaaView = nil, depthView = nil,
        toonBytes = buffer.create(224), texBytes = buffer.create(64),
        size = Vector.xy(0, 0), scale = 1, t = 0,
        sampler = ImageSampler('clamp', 'clamp', 'bilinear'), mvp = nil, model = nil,
        pointerDown = forward('down'), pointerUp = forward('up'), pointerMove = forward('move'),
        init = init, resize = resize, advance = advance, draw = draw,
    }
end
