-- Float a cat sticker over the Rex window that holds a Claude pane, sized to the card.
--   rex do -s SESSION rex-cat-layer.lua block=BLOCK_ID mood=done label=NAME [seconds=4]
-- Called detached by rex-agent-status.sh on done / blocked / error.
--
-- 1. Render the card first (rex-cat.py --prepare), so the box never opens empty.
-- 2. Open a floating box exactly the card's size: the window's pixel size comes from the
--    Claude pane (its cells x cell px / its share of the window), and the box's padding
--    is measured from the cells Rex actually gives it, then corrected once.
-- 3. Own the box's terminal and set it to the card's cells: otherwise a second, narrow
--    Rex window can own it and shrink it (then the cat got ~6 columns).
local a = rex.args
local T = "com.superlogical.terminal"
local home = os.getenv("HOME")
local py = os.getenv("REX_CAT_PYTHON") or "python3"
local script = home .. "/.claude/hooks/rex-cat.py"
local seconds = tonumber(a.seconds or 4)
local CARD_COLS = 18  -- the Ghostty tmux sticker is 18 cells wide

local view, err = rex.session.view{}
if not view then return "view failed: " .. tostring(err) end

-- the window holding the Claude pane, and that pane's rect in the window
local function find_rect(node)
  if not node then return nil end
  if node.block_id == a.block then return node.rect end
  local s = node.split
  if s then return find_rect(s.before) or find_rect(s.after) end
end
local window_id, rect
for _, w in ipairs(view.windows or {}) do
  for _, l in ipairs(w.layers or {}) do
    local r = l.layout and find_rect(l.layout)
    if r then window_id, rect = w.window_id, r end
  end
end
local pane = rex.block.call(T, "size", { block_id = a.block })
if not (window_id and rect and pane and pane.columns) then return "pane not found" end
local cw, ch = pane.cell_width_px, pane.cell_height_px
local W = pane.columns * cw / rect[3]
local H = pane.rows * ch / rect[4]
local viewer = pane.owner  -- the client showing the Claude pane: size the box for it

-- 1. the card, rendered (or read from cache) before anything is shown
local p = rex.exec{ py, script, "--prepare", a.mood or "done", a.label or "claude",
                    tostring(cw), tostring(ch), tostring(CARD_COLS), "--bare" }
if not (p and p.ok) then return "prepare failed: " .. tostring(p and p.stderr) end
local dir, cols, rows = p.stdout:match("^(%S+)%s+(%d+)%s+(%d+)")
cols, rows = tonumber(cols), tonumber(rows)
if not dir then return "prepare said: " .. tostring(p.stdout) end

-- 2. a box the card's size, top right
local padx, pady = 48, 48  -- first guess; measured below
local function bounds()
  local w = math.min(0.9, (cols * cw + padx) / W)
  local h = math.min(0.9, (rows * ch + pady) / H)
  return { math.max(0, 1 - w - 12 / W * 2), math.max(0, 0.03), w, h }
end
local r, e = rex.session.new_layer{
  window_id = window_id,
  bounds = bounds(),
  focus = false,
  layout = { block = { flavor = "com.superlogical.terminal.shell", label = "cat",
    options = { shell = "none", login = false,
      command = { py, script, "--show", dir, tostring(cols), tostring(rows),
                  "--seconds", tostring(seconds) } } } },
}
if not r then return e end
local id = r.block_ids and r.block_ids[1]
if not id then return r end

-- the box is the card: its background (padding included) is the card colour, so Rex's
-- rounded box is the card's edge and its padding the card's margin (no frame in a frame)
rex.block.call(T, "set_theme", { block_id = id, background = "#1e1e1e", scheme = "dark" })

-- 3. own the terminal at exactly the card's cells
rex.session.own_block{ block_ids = { id }, mode = "take" }
rex.block.call(T, "resize", { block_id = id, columns = cols, rows = rows })

-- measure the box's padding from the cells the viewer's window asks for, and fix the box.
-- Each resize makes the viewer send a new request; wait for it (its updated_at changes)
-- instead of reading the previous one.
local function viewer_request(since)
  for _ = 1, 25 do
    local s = rex.block.call(T, "size", { block_id = id })
    for _, d in ipairs((s and s.desired) or {}) do
      if d.client_id == viewer and d.updated_at ~= since then return d end
    end
    rex.sleep(0.04)
  end
end
local got = viewer_request(nil)
for _ = 1, 4 do
  if not got or (got.columns == cols and got.rows == rows) then break end
  padx = padx + (cols - got.columns) * cw
  pady = pady + (rows - got.rows) * ch
  local stamp = got.updated_at
  rex.session.resize_layer{ layer_id = r.layer_id, bounds = bounds() }
  got = viewer_request(stamp)
end
rex.block.call(T, "resize", { block_id = id, columns = cols, rows = rows })

-- Let go so the viewer's window owns it (an owner other than the viewer makes Rex badge
-- the box "Sized by another client"). If another window grabs it instead (the narrow
-- second Rex window did, and squeezed the cat to 4x7), take it back and hold it: a
-- badge is better than a squashed cat.
rex.session.disown_block{ block_ids = { id } }
rex.sleep(0.25)
local after = rex.block.call(T, "size", { block_id = id })
local held = false
if after and after.owner and after.owner ~= viewer then
  rex.session.own_block{ block_ids = { id }, mode = "take" }
  rex.block.call(T, "resize", { block_id = id, columns = cols, rows = rows })
  held = true
  rex.sleep(seconds)
end
return { cols = cols, rows = rows, padx = padx, pady = pady, held = held,
         owner_after = after and after.owner or "none" }
