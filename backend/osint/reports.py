"""Human-readable exports of an investigation graph: Markdown report, PDF, Obsidian vault."""
import io
import json
import re
from collections import defaultdict
from datetime import datetime
from xml.sax.saxutils import escape

from . import i18n
from .settings import lang as _current_lang


class _L:
    """Language helpers for one report: headings, entity types, relation names, values and signals in the chosen language."""

    def __init__(self, lang: str | None):
        self.lang = lang or _current_lang()

    def ui(self, key: str) -> str:
        return i18n.ui(key, self.lang)

    def type(self, t: str) -> str:
        return i18n.label("type", t, self.lang)

    def rel(self, r: str) -> str:
        return i18n.label("rel", r, self.lang)

    def signal(self, s: str) -> str:
        return i18n.label("reason", s, self.lang)

    def value(self, n: dict) -> str:
        return i18n.label_value(n["value"], self.lang) if n["type"] in ("Servizio", "Data") else n["value"]

    def status(self, st: str) -> str:
        return self.ui({"auto": "auto", "review": "review", "confirmed": "confirmed"}[st])


def _prep(g: dict):
    nodes = {n["id"]: n for n in g["nodes"]}
    out, inc = defaultdict(list), defaultdict(list)  # id -> [(edge, other_node)]
    for e in g["edges"]:
        out[e["src"]].append((e, nodes[e["dst"]]))
        inc[e["dst"]].append((e, nodes[e["src"]]))
    by_type = defaultdict(list)
    for n in sorted(g["nodes"], key=lambda n: (n["type"], n["value"].lower())):
        by_type[n["type"]].append(n)
    return nodes, out, inc, by_type


def _notes(g: dict) -> dict[int, dict]:
    return {n["entity"]: n for n in g.get("notes", [])}


def _date(meta: dict) -> str:
    return datetime.fromtimestamp(meta["created"]).strftime("%Y-%m-%d %H:%M")


def _src(e: dict) -> str:
    return e["url"] or e["collector"]


def markdown(g: dict, meta: dict, lang: str | None = None) -> str:
    T = _L(lang)
    nodes, out, _, by_type = _prep(g)
    L = [f"# {meta['name']}", "", f"- **{T.ui('investigation')}:** #{meta['id']}"] + ([f"- **{T.ui('purpose')}:** {meta['purpose']}"] if meta["purpose"] else []) + [
         f"- **{T.ui('date')}:** {_date(meta)}", f"- **{T.ui('entities')}:** {len(g['nodes'])} · **{T.ui('relations')}:** {len(g['edges'])}", "", f"## {T.ui('summary')}", ""]
    L += [f"- {T.type(t)}: {len(ns)}" for t, ns in by_type.items()]
    notes = _notes(g)
    if any(n["starred"] for n in notes.values()):
        L += ["", f"## {T.ui('favourites')}", ""]
        for n in g["nodes"]:
            if notes.get(n["id"], {}).get("starred"):
                L.append(f"- **{_md(T.value(n))}** ({T.type(n['type'])})" + (f": {_md(notes[n['id']]['text'])}" if notes[n["id"]]["text"] else ""))
    if g["links"]:
        L += ["", f"## {T.ui('links')}", "", f"| {T.ui('status')} | {T.ui('score')} | {T.ui('entities')} | {T.ui('signals')} |", "|---|---|---|---|"]
        for l in sorted(g["links"], key=lambda l: -l["score"]):
            sig = ", ".join(T.signal(s[0]) for s in l["signals"]) or T.ui("confirmed_manually")
            L.append(f"| {T.status(l['status'])} | {l['score']:.0%} | {_md(T.value(nodes[l['a']]))} ↔ {_md(T.value(nodes[l['b']]))} | {sig} |")
    L += ["", f"## {T.ui('entities')}", ""]
    for t, ns in by_type.items():
        L += [f"### {T.type(t)}", ""]
        for n in ns:
            L.append(f"- **{_md(T.value(n))}**" + (" ★" if notes.get(n["id"], {}).get("starred") else ""))
            if notes.get(n["id"], {}).get("text"):
                L.append(f"  - {T.ui('note')}: {_md(notes[n['id']]['text'])}")
            for e, o in out[n["id"]]:
                L.append(f"  - {T.rel(e['rel'])} → {_md(T.value(o))} ({e['conf']:.0%}, {_md(_src(e))})")
        L.append("")
    return "\n".join(L)


def _md(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


# ---------- Obsidian ----------

def _fname(n: dict) -> str:
    v = re.sub(r"^https?://(www\.)?", "", n["value"])
    v = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", v).strip(" .")[:80] or str(n["id"])
    return v


def obsidian(g: dict, meta: dict, lang: str | None = None) -> dict[str, str]:
    """{relative path: file content}. Each entity is a note; relations are [[wikilinks]]."""
    T = _L(lang)
    nodes, out, inc, by_type = _prep(g)
    path, used = {}, set()
    for n in sorted(g["nodes"], key=lambda n: n["id"]):
        p = f"{T.type(n['type'])}/{_fname({**n, 'value': T.value(n)})}"
        if p.lower() in used:
            p += f" ({n['id']})"
        used.add(p.lower())
        path[n["id"]] = p

    def link(i: int) -> str:
        return f"[[{path[i]}|{T.value(nodes[i]).replace('|', '/').replace(']', ')')[:80]}]]"

    notes = _notes(g)
    links_of = defaultdict(list)
    for l in g["links"]:
        links_of[l["a"]].append((l, l["b"]))
        links_of[l["b"]].append((l, l["a"]))

    files = {}
    for n in g["nodes"]:
        L = ["---", f"{T.ui('type')}: {json.dumps(T.type(n['type']), ensure_ascii=False)}", f"{T.ui('value')}: {json.dumps(T.value(n), ensure_ascii=False)}",
             f"{T.ui('investigation_key')}: {meta['id']}", f"tags: [osint/{re.sub(r'[^a-z0-9]', '', n['type'].lower())}]"]
        if notes.get(n["id"], {}).get("starred"):
            L.append(f"{T.ui('favourite_key')}: true")
        L += ["---", "", f"# {T.value(n)}", ""]
        if notes.get(n["id"], {}).get("text"):
            L += [f"## {T.ui('notes')}", notes[n["id"]]["text"], ""]
        if out[n["id"]] or inc[n["id"]]:
            L.append(f"## {T.ui('relations')}")
            for e, o in out[n["id"]]:
                L.append(f"- {T.rel(e['rel'])} → {link(o['id'])} · {e['conf']:.0%} · {_src(e)}")
            for e, o in inc[n["id"]]:
                L.append(f"- ← {T.rel(e['rel'])} · {link(o['id'])} · {e['conf']:.0%} · {_src(e)}")
            L.append("")
        if links_of[n["id"]]:
            L.append(f"## {T.ui('links')}")
            for l, other in sorted(links_of[n["id"]], key=lambda x: -x[0]["score"]):
                L.append(f"- {link(other)} · {l['score']:.0%} · {T.status(l['status'])} · {', '.join(T.signal(s[0]) for s in l['signals'])}")
            L.append("")
        files[path[n["id"]] + ".md"] = "\n".join(L)

    idx = [f"# {meta['name']}", "", f"- **{T.ui('investigation')}:** #{meta['id']}"] + ([f"- **{T.ui('purpose')}:** {meta['purpose']}"] if meta["purpose"] else []) + [
        f"- **{T.ui('date')}:** {_date(meta)}", ""]
    starred = [n for n in g["nodes"] if notes.get(n["id"], {}).get("starred")]
    if starred:
        idx += [f"## {T.ui('favourites')}", ""] + [f"- {link(n['id'])}" for n in starred] + [""]
    for t, ns in by_type.items():
        idx += [f"## {T.type(t)} ({len(ns)})", ""] + [f"- {link(n['id'])}" for n in ns] + [""]
    files[f"{T.ui('investigation')}.md"] = "\n".join(idx)
    return files


# ---------- PDF ----------

def pdf(g: dict, meta: dict, lang: str | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    T = _L(lang)
    nodes, out, _, by_type = _prep(g)

    def t(s) -> str:  # base-14 fonts are latin-1 only: unsupported characters become '?'
        return escape(str(s).replace("→", "->").replace("↔", "<->")).encode("latin-1", "replace").decode("latin-1")

    st = getSampleStyleSheet()
    small = st["BodyText"].clone("small", fontSize=8, leading=10, leftIndent=14)
    doc = []
    doc += [Paragraph(t(meta["name"]), st["Title"])]
    if meta["purpose"]:
        doc.append(Paragraph(f"<b>{t(T.ui('purpose'))}:</b> {t(meta['purpose'])}", st["BodyText"]))
    doc += [Paragraph(f"<b>{t(T.ui('date'))}:</b> {_date(meta)} &nbsp; <b>{t(T.ui('entities'))}:</b> {len(g['nodes'])} &nbsp; <b>{t(T.ui('relations'))}:</b> {len(g['edges'])}", st["BodyText"]),
            Spacer(1, 10), Paragraph(t(T.ui("summary")), st["Heading2"])]
    rows = [[t(T.type(k)), str(len(v))] for k, v in by_type.items()]
    if rows:
        tb = Table(rows, hAlign="LEFT", colWidths=[160, 50])
        tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
        doc.append(tb)
    notes = _notes(g)
    starred = [n for n in g["nodes"] if notes.get(n["id"], {}).get("starred")]
    if starred:
        doc += [Spacer(1, 10), Paragraph(t(T.ui("favourites")), st["Heading2"])]
        for n in starred:
            doc.append(Paragraph(f"<b>{t(T.value(n))[:150]}</b> ({t(T.type(n['type']))})" + (f": {t(notes[n['id']]['text'])}" if notes[n["id"]]["text"] else ""), st["BodyText"]))
    if g["links"]:
        doc += [Spacer(1, 10), Paragraph(t(T.ui("links")), st["Heading2"])]
        cell = st["BodyText"].clone("cell", fontSize=8, leading=10)
        rows = [[t(T.ui("status")), t(T.ui("pt")), t(T.ui("entity_col")), t(T.ui("signals"))]] + [
            [t(T.status(l["status"])), f"{l['score']:.0%}", Paragraph(t(f"{T.value(nodes[l['a']])} <-> {T.value(nodes[l['b']])}"), cell),
             Paragraph(t(", ".join(T.signal(s[0]) for s in l["signals"]) or T.ui("confirmed_manually")), cell)]
            for l in sorted(g["links"], key=lambda l: -l["score"])]
        tb = Table(rows, hAlign="LEFT", colWidths=[70, 40, 230, 150], repeatRows=1)
        tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        doc.append(tb)
    doc.append(Paragraph(t(T.ui("entities")), st["Heading2"]))
    for typ, ns in by_type.items():
        doc.append(Paragraph(f"{t(T.type(typ))} ({len(ns)})", st["Heading3"]))
        for n in ns:
            doc.append(Paragraph(f"<b>{t(T.value(n))[:150]}</b>" + (" *" if notes.get(n["id"], {}).get("starred") else ""), st["BodyText"]))
            if notes.get(n["id"], {}).get("text"):
                doc.append(Paragraph(f"<i>{t(T.ui('note'))}: {t(notes[n['id']]['text'])}</i>", small))
            for e, o in out[n["id"]]:
                doc.append(Paragraph(t(f"{T.rel(e['rel'])} -> {T.value(o)[:100]} ({e['conf']:.0%}, {_src(e)[:90]})"), small))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=meta["name"], leftMargin=40, rightMargin=40,
                      topMargin=40, bottomMargin=40).build(doc)
    return buf.getvalue()
