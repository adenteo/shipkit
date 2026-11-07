local json = require('json')

type Mesh = { pos: GPUBuffer, nrm: GPUBuffer, idx: GPUBuffer, count: number }
type Toon = {
    context: Context,
    mesh: Mesh?,
    toon: GPUPipeline?,
    outline: GPUPipeline?,
    ubo: GPUBuffer?,
    bind: GPUBindGroup?,
    canvas: GPUCanvas?,
    msaa: GPUTexture?,
    msaaView: GPUTextureView?,
    depth: GPUTexture?,
    depthView: GPUTextureView?,
    staging: buffer,
    size: Vector,
    scale: number,
    t: number,
    sampler: ImageSampler,
}

-- Read a .glb blob: header, JSON chunk, BIN chunk; first primitive's POSITION, NORMAL, indices
local function loadGlb(data: buffer): Mesh
    local jsonLen = buffer.readu32(data, 12)
    local gl = json.decode(buffer.readstring(data, 20, jsonLen))
    local binStart = 20 + jsonLen + 8
    local prim = gl.meshes[1].primitives[1]
    local function slice(accessorIndex: number, usage: BufferUsage): (GPUBuffer, number)
        local acc = gl.accessors[accessorIndex + 1]
        local view = gl.bufferViews[acc.bufferView + 1]
        local len = view.byteLength
        local bytes = buffer.create(len)
        buffer.copy(bytes, 0, data, binStart + (view.byteOffset or 0) + (acc.byteOffset or 0), len)
        return GPUBuffer.new({ size = len, usage = usage, data = bytes, immutable = true }), acc.count
    end
    local pos = slice(prim.attributes.POSITION, 'vertex')
    local nrm = slice(prim.attributes.NORMAL, 'vertex')
    local idx, count = slice(prim.indices, 'index')
    return { pos = pos, nrm = nrm, idx = idx, count = count }
end

local function rgb(r: number, g: number, b: number): (number, number, number) return r / 255, g / 255, b / 255 end

function init(self: Toon, context: Context): boolean
    local blob = context:blob('heart')
    local shader = context:shader('toon')
    if not blob or not shader then
        print('missing asset', blob, shader)
        return false
    end
    self.mesh = loadGlb(blob.data)
    local layouts: { VertexBufferLayout } = {
        { stride = 12, attributes = { { format = 'float32x3', slot = 0 } } },
        { stride = 12, attributes = { { format = 'float32x3', slot = 1 } } },
    }
    local depth: DepthStencilState = { format = 'depth32float', compare = 'less', write = true }
    self.toon = GPUPipeline.new({
        vertex = { module = shader, entryPoint = 'vs_toon' },
        fragment = { module = shader, entryPoint = 'fs_toon' },
        vertexLayout = layouts, colorTargets = { { format = 'rgba8unorm' } },
        depthStencil = depth, cullMode = 'back', sampleCount = 4,
    })
    self.outline = GPUPipeline.new({
        vertex = { module = shader, entryPoint = 'vs_outline' },
        fragment = { module = shader, entryPoint = 'fs_outline' },
        vertexLayout = layouts, colorTargets = { { format = 'rgba8unorm' } },
        depthStencil = depth, cullMode = 'front', sampleCount = 4,
    })
    self.ubo = GPUBuffer.new({ size = 224, usage = 'uniform' })
    self.bind = GPUBindGroup.new({
        layout = (self.toon :: GPUPipeline):getBindGroupLayout(0),
        ubos = { { slot = 0, buffer = self.ubo :: GPUBuffer } },
    })
    self.canvas = context:gpuCanvas()
    return true
end

function resize(self: Toon, size: Vector, scale: number)
    self.size = size
    self.scale = scale
    local w, h = math.max(1, math.floor(size.x * scale)), math.max(1, math.floor(size.y * scale))
    local canvas = self.canvas :: GPUCanvas
    canvas:resize(w, h)
    self.msaa = GPUTexture.new({ width = w, height = h, format = canvas.format, renderTarget = true, sampleCount = 4 })
    self.msaaView = (self.msaa :: GPUTexture):view()
    self.depth = GPUTexture.new({ width = w, height = h, format = 'depth32float', renderTarget = true, sampleCount = 4 })
    self.depthView = (self.depth :: GPUTexture):view()
end

function advance(self: Toon, seconds: number): boolean
    self.t += seconds
    return true
end

local function writeUniforms(self: Toon)
    local b = self.staging
    local aspect = self.size.x / math.max(1, self.size.y)
    local proj = Mat4.perspective(math.rad(32), aspect, 0.1, 50)
    local view = Mat4.lookAt(Vector.xyz(0, 0.35, 5.2), Vector.xyz(0, 0.05, 0), Vector.xyz(0, 1, 0))
    local model = Mat4.fromRotationY(0.55 + self.t * 0.8) * Mat4.fromRotationX(-0.12)
    ;(proj * view * model):writeToBuffer(b, 0)
    model:writeToBuffer(b, 64)
    local function v4(off: number, x: number, y: number, z: number, w: number)
        buffer.writef32(b, off, x); buffer.writef32(b, off + 4, y)
        buffer.writef32(b, off + 8, z); buffer.writef32(b, off + 12, w)
    end
    v4(128, -0.5, 0.8, 0.6, 0)                -- light direction (world)
    local r, g, bl = rgb(214, 86, 112); v4(144, r, g, bl, 1)   -- shadow
    r, g, bl = rgb(242, 154, 166); v4(160, r, g, bl, 1)        -- mid
    r, g, bl = rgb(255, 214, 220); v4(176, r, g, bl, 1)        -- lit
    r, g, bl = rgb(62, 42, 34); v4(192, r, g, bl, 1)           -- ink
    v4(208, 0.035, 0, 0, 0)                                    -- outline width
    ;(self.ubo :: GPUBuffer):write(b)
end

function draw(self: Toon, renderer: Renderer)
    local canvas = self.canvas
    local mesh = self.mesh
    if not canvas or not mesh or canvas.width == 0 then return end
    writeUniforms(self)
    local pass = canvas:beginRenderPass({
        color = { {
            view = self.msaaView, resolveTarget = canvas:colorView(),
            loadOp = 'clear', storeOp = 'discard', clearColor = { 0, 0, 0, 0 },
        } },
        depthStencil = { view = self.depthView :: GPUTextureView, depthLoadOp = 'clear', depthStoreOp = 'discard', depthClearValue = 1 },
    })
    for _, pipe in { self.outline, self.toon } do
        pass:setPipeline(pipe :: GPUPipeline)
        pass:setBindGroup(0, self.bind :: GPUBindGroup)
        pass:setVertexBuffer(0, mesh.pos)
        pass:setVertexBuffer(1, mesh.nrm)
        pass:setIndexBuffer(mesh.idx, 'uint16')
        pass:drawIndexed(mesh.count)
    end
    pass:finish()
    renderer:save()
    renderer:transform(Mat2D.withScale(1 / self.scale))
    renderer:drawImage(canvas.image, self.sampler, 'srcOver', 1)
    renderer:restore()
end

return function(context: Context): Layout<Toon>
    return {
        context = context,
        mesh = nil, toon = nil, outline = nil, ubo = nil, bind = nil, canvas = nil,
        msaa = nil, msaaView = nil, depth = nil, depthView = nil,
        staging = buffer.create(224),
        size = Vector.xy(0, 0), scale = 1, t = 0,
        sampler = ImageSampler('clamp', 'clamp', 'bilinear'),
        init = init, resize = resize, advance = advance, draw = draw,
    }
end
