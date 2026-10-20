"""Cutting terminal text (with colour codes) to a width, the way a terminal would show it."""
import re
import unicodedata

# CSI and other escapes | OSC (e.g. OSC 8 hyperlinks), ended by BEL or ESC \\ | a visible character
TOKEN = re.compile(r"(\x1b\[[0-9;:?<=>]*[ -/]*[@-~]|\x1b[()][0-9A-Za-z]|\x1b[^\[\]])"
                   r"|(\x1b\][^\x07\x1b]*(?:\x07|\x1b\\))|(.)", re.S)


def cell_width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def visible_width(text):
    return sum(cell_width(m.group(3)) for m in TOKEN.finditer(text) if m.group(3))


def clip(text, width, pad=True):
    """The first `width` cells of `text`, colour codes kept, ending in a reset.

    A double-width character that would straddle the edge is replaced by a
    space; with pad, the result is filled with spaces to exactly `width` cells.
    """
    out, used = [], 0
    for m in TOKEN.finditer(text):
        seq, osc, ch = m.groups()
        if seq:
            if seq.endswith("m"):  # colours only; cursor moves etc. would break the layout
                out.append(seq)
            continue
        if osc or ch in ("\r", "\n"):
            continue
        w = cell_width(ch)
        if used + w > width:
            if w == 2 and used < width:
                out.append(" ")
                used += 1
            break
        out.append(ch)
        used += w
    if pad and used < width:
        out.append("\x1b[0m" + " " * (width - used))
    return "".join(out) + "\x1b[0m"


def plain(text):
    return "".join(m.group(3) for m in TOKEN.finditer(text) if m.group(3))


def cells(text):
    """[(char, style)]: each visible character with the colour codes in force for it."""
    out, style = [], ""
    for m in TOKEN.finditer(text):
        seq, osc, ch = m.groups()
        if seq:
            if seq.endswith("m"):
                style = "" if seq in ("\x1b[0m", "\x1b[m") else style + seq
            continue
        if osc or ch in ("\r", "\n"):
            continue
        out.append((ch, style))
    return out


def join(cs):
    parts, style = [], ""
    for ch, st in cs:
        if st != style:
            parts.append("\x1b[0m" + st)
            style = st
        parts.append(ch)
    return "".join(parts) + ("\x1b[0m" if style else "")


def wrap(text, width):
    """Word-wrap coloured text to `width` cells; continuation lines keep a hanging indent.

    The indent lines up under the text after a bullet ("● ", "- ", "1. "), the
    way Claude's own output does.
    """
    cs = cells(text)
    lead = len(re.match(r"\s*(?:[●•\-*✶└]|\d+[.)])?\s*", "".join(c for c, _ in cs)).group())
    lead = lead if lead < width // 3 else 0
    lines = []
    while True:
        widths = [cell_width(c) for c, _ in cs]
        if sum(widths) <= width:
            lines.append(join(cs))
            return lines
        used, cut = 0, 0
        for k, w in enumerate(widths):
            if used + w > width:
                break
            used, cut = used + w, k + 1
        # a space right after the last fitting cell is the best break of all
        space = max((k for k in range(min(cut + 1, len(cs))) if cs[k][0] == " " and k > lead), default=-1)
        if space > width // 3:  # break at the last space; else split the long word
            head, rest = cs[:space], cs[space + 1:]
        else:
            head, rest = cs[:cut], cs[cut:]
        lines.append(join(head))
        while rest and rest[0][0] == " ":
            rest = rest[1:]
        if not rest:
            return lines
        cs = [(" ", "")] * lead + rest


def unwrap(lines, width):
    """Joins lines the terminal broke because they reached `width` cells."""
    out = []
    for line in lines:
        if out and visible_width(out[-1]) >= width - 1 and plain(line).strip():
            out[-1] = join(cells(out[-1]) + [(" ", "")] + cells(line.lstrip(" ")))
        else:
            out.append(line)
    return out
