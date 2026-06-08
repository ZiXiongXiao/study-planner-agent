"""
本地结构图渲染：把 AI 规划出的结构内容渲染成 SVG 图片（纯 Python 标准库，无外部依赖）。

用于学习辅助图：knowledge_map / skill_map / workflow / practice_loop / learning_path /
deliverables。结构图零 MINIMAX_API_KEY、零网络——打开 Markdown 即见图，且文字/箭头/
层级由代码精确绘制，规避扩散模型乱码。

所有渲染函数对异常宽容：空/非法输入或任何异常都返回 None（绝不抛），调用方可回退到
Mermaid 代码块。SVG 在 VSCode 预览/浏览器可渲染（本项目本地查看场景）。
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

# ---- 度量参数 ----
_FS = 14            # 字号
_CH_CJK = 15.0      # 全宽字符（中日韩等）宽度估计
_CH_ASCII = 8.0     # ASCII 半宽
_PAD_X = 14         # 盒子左右内边距
_BOX_H = 38         # 盒子高度
_ROW_H = 50         # 知识地图每行高（含间距）

# ---- 配色（浅底深字，清爽）----
_FILL_ROOT = "#dbeafe"
_FILL_MOD = "#e0e7ff"
_FILL_TOPIC = "#f1f5f9"
_FILL_STEP = "#dcfce7"
_FILL_DELIV = "#fef9c3"

_DEFS = (
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
    'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    '<path d="M0,0 L10,5 L0,10 z" fill="#94a3b8"/></marker></defs>'
)


# --------------------------------------------------------------------------- #
# 基础件
# --------------------------------------------------------------------------- #
def _clean(text, maxlen: int = 22) -> str:
    """折叠空白/换行、去方括号、超长截断。不做 XML 转义（转义在 _label 里做）。"""
    s = " ".join(str(text if text is not None else "").split())
    s = s.replace("[", "(").replace("]", ")")
    if len(s) > maxlen:
        s = s[: maxlen - 1].rstrip() + "…"
    return s


def _is_wide(ch: str) -> bool:
    o = ord(ch)
    return o >= 0x1100 and (
        o <= 0x115F or 0x2E80 <= o <= 0xA4CF or 0xAC00 <= o <= 0xD7A3
        or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE4F
        or 0xFF00 <= o <= 0xFF60 or 0xFFE0 <= o <= 0xFFE6
        or 0x20000 <= o <= 0x3FFFD
    )


def _text_w(text: str) -> float:
    return sum(_CH_CJK if _is_wide(c) else _CH_ASCII for c in text)


def _box_w(label: str) -> float:
    return max(72.0, _text_w(label) + 2 * _PAD_X)


def _rect(x, y, w, h, fill, stroke="#94a3b8", rx=8) -> str:
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')


def _label(cx, cy, text, *, fill="#0f172a", anchor="middle", weight="normal") -> str:
    return (f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="Segoe UI, Microsoft YaHei, '
            f'PingFang SC, sans-serif" font-size="{_FS}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" dominant-baseline="central">'
            f'{escape(text)}</text>')


def _node(x, y, w, label, fill) -> str:
    return _rect(x, y, w, _BOX_H, fill) + _label(x + w / 2, y + _BOX_H / 2, label)


def _line(x1, y1, x2, y2, marker=True) -> str:
    end = ' marker-end="url(#arrow)"' if marker else ""
    return (f'<path d="M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}" fill="none" '
            f'stroke="#94a3b8" stroke-width="1.5"{end}/>')


def _svg(width, height, body) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
            f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">'
            f'<rect width="100%" height="100%" fill="#ffffff"/>{_DEFS}{body}</svg>')


def _write(svg: str, dest_dir, name: str) -> str | None:
    try:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{name}.svg").write_text(svg, encoding="utf-8")
        return f"assets/{name}.svg"
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 渲染器
# --------------------------------------------------------------------------- #
def render_chain(steps, dest_dir, name, *, cyclic: bool = False, title: str = "") -> str | None:
    """水平盒子+箭头链；cyclic=True 加回流箭头（练习/备考循环）。

    复用于 skill_map / workflow / practice_loop / learning_path。<2 步返回 None。
    """
    try:
        items = [_clean(s, 18) for s in (steps or []) if str(s).strip()][:8]
        if len(items) < 2:
            return None
        margin, gap = 24, 46
        title = _clean(title, 40)
        y0 = margin + (28 if title else 0)
        widths = [_box_w(s) for s in items]
        xs, x = [], margin
        for w in widths:
            xs.append(x)
            x += w + gap
        total_w = x - gap + margin
        height = y0 + _BOX_H + (64 if cyclic else margin)

        body = []
        if title:
            body.append(_label(total_w / 2, margin + 6, title, fill="#334155", weight="bold"))
        for s, bx, w in zip(items, xs, widths):
            body.append(_node(bx, y0, w, s, _FILL_STEP))
        yc = y0 + _BOX_H / 2
        for i in range(len(items) - 1):
            body.append(_line(xs[i] + widths[i], yc, xs[i + 1], yc))
        if cyclic:
            lx = xs[-1] + widths[-1] / 2
            fx = xs[0] + widths[0] / 2
            by = y0 + _BOX_H
            dip = by + 40
            body.append(
                f'<path d="M{lx:.1f},{by:.1f} C{lx:.1f},{dip:.1f} {fx:.1f},{dip:.1f} '
                f'{fx:.1f},{by:.1f}" fill="none" stroke="#94a3b8" stroke-width="1.5" '
                f'stroke-dasharray="5 4" marker-end="url(#arrow)"/>'
            )
            body.append(_label((lx + fx) / 2, dip, "循环", fill="#64748b"))
        return _write(_svg(total_w, height, "".join(body)), dest_dir, name)
    except Exception:
        return None


def render_knowledge_map(root, modules, dest_dir, name) -> str | None:
    """三列分层：根 → 模块（竖排）→ 每模块要点（右侧竖排）。无模块返回 None。"""
    try:
        root = _clean(root, 18) or "知识体系"
        mods = []
        for m in (modules or []):
            if not isinstance(m, dict):
                continue
            mname = _clean(m.get("name", ""), 16)
            if not mname:
                continue
            topics = [_clean(t, 16) for t in (m.get("topics") or []) if str(t).strip()][:5]
            mods.append((mname, topics))
            if len(mods) >= 6:
                break
        if not mods:
            return None

        margin, col_gap = 24, 70
        w_root = _box_w(root)
        w_mod = max(_box_w(n) for n, _ in mods)
        all_topics = [t for _, ts in mods for t in ts]
        w_topic = max([_box_w(t) for t in all_topics] or [120.0])
        x_root = margin
        x_mod = x_root + w_root + col_gap
        x_topic = x_mod + w_mod + col_gap

        y = margin
        mod_centers = []                       # (name, center_y)
        topic_nodes = []                       # (x, box_y, w, label, mod_cy, conn_y)
        for mname, topics in mods:
            band_h = max(1, len(topics)) * _ROW_H
            mod_cy = y + band_h / 2
            mod_centers.append((mname, mod_cy))
            ty = y
            for t in topics:
                topic_nodes.append(
                    (x_topic, ty + (_ROW_H - _BOX_H) / 2, _box_w(t), t, mod_cy, ty + _ROW_H / 2)
                )
                ty += _ROW_H
            y += band_h

        total_h = y + margin
        total_w = x_topic + w_topic + margin
        root_cy = total_h / 2

        body = [_node(x_root, root_cy - _BOX_H / 2, w_root, root, _FILL_ROOT)]
        for mname, mod_cy in mod_centers:
            body.append(_line(x_root + w_root, root_cy, x_mod, mod_cy))
            body.append(_node(x_mod, mod_cy - _BOX_H / 2, w_mod, mname, _FILL_MOD))
        for tx, tyb, tw, tlabel, mod_cy, tcy in topic_nodes:
            body.append(_line(x_mod + w_mod, mod_cy, tx, tcy))
            body.append(_node(tx, tyb, tw, tlabel, _FILL_TOPIC))
        return _write(_svg(total_w, total_h, "".join(body)), dest_dir, name)
    except Exception:
        return None


def render_deliverables(items, dest_dir, name, title="产出物清单") -> str | None:
    """竖排「☐ 项」清单图。空返回 None。"""
    try:
        rows = [_clean(s, 30) for s in (items or []) if str(s).strip()][:8]
        if not rows:
            return None
        margin, row_h = 20, 40
        title = _clean(title, 30)
        y0 = margin + (26 if title else 0)
        text_w = max(_text_w(r) for r in rows)
        width = max(280.0, text_w + 60 + 2 * margin)
        height = y0 + len(rows) * row_h + margin

        body = []
        if title:
            body.append(_label(margin, margin + 6, title, fill="#334155", anchor="start", weight="bold"))
        y = y0
        for r in rows:
            body.append(_rect(margin, y + (row_h - 18) / 2, 18, 18, _FILL_DELIV, rx=4))
            body.append(_label(margin + 30, y + row_h / 2, r, anchor="start"))
            y += row_h
        return _write(_svg(width, height, "".join(body)), dest_dir, name)
    except Exception:
        return None
