-- Minimal JSON decoder, enough for a glTF header chunk
local M = {}
local function skip(s: string, i: number): number
    local _, e = string.find(s, "^[ \n\r\t]*", i)
    return (e or i - 1) + 1
end
local parse: (string, number) -> (any, number)
local function parseString(s: string, i: number): (string, number)
    local out = {}
    i += 1
    while true do
        local ch = string.sub(s, i, i)
        if ch == '"' then return table.concat(out), i + 1 end
        if ch == "\\" then
            local nx = string.sub(s, i + 1, i + 1)
            local map = { n = "\n", t = "\t", r = "\r", b = "\b", f = "\f" }
            table.insert(out, map[nx] or nx)
            i += 2
        else
            table.insert(out, ch)
            i += 1
        end
    end
end
parse = function(s: string, i: number): (any, number)
    i = skip(s, i)
    local ch = string.sub(s, i, i)
    if ch == "{" then
        local obj = {}
        i = skip(s, i + 1)
        if string.sub(s, i, i) == "}" then return obj, i + 1 end
        while true do
            local k
            k, i = parseString(s, skip(s, i))
            i = skip(s, i) + 1 -- ':'
            local v
            v, i = parse(s, i)
            obj[k] = v
            i = skip(s, i)
            local c = string.sub(s, i, i)
            i += 1
            if c == "}" then return obj, i end
        end
    elseif ch == "[" then
        local arr = {}
        i = skip(s, i + 1)
        if string.sub(s, i, i) == "]" then return arr, i + 1 end
        while true do
            local v
            v, i = parse(s, i)
            table.insert(arr, v)
            i = skip(s, i)
            local c = string.sub(s, i, i)
            i += 1
            if c == "]" then return arr, i end
        end
    elseif ch == '"' then
        return parseString(s, i)
    elseif string.sub(s, i, i + 3) == "true" then return true, i + 4
    elseif string.sub(s, i, i + 4) == "false" then return false, i + 5
    elseif string.sub(s, i, i + 3) == "null" then return nil, i + 4
    else
        local _, e = string.find(s, "^-?[%d%.eE+-]+", i)
        return tonumber(string.sub(s, i, e)), (e :: number) + 1
    end
end
function M.decode(s: string): any
    local v = parse(s, 1)
    return v
end
return M
