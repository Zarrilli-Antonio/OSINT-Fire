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


def _tags(g: dict, n: dict) -> list[str]:
    return next((t["tags"] for t in g.get("tags", []) if t["entity"] == n["id"]), [])


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
            L.append(f"- **{_md(T.value(n))}**" + (" ★" if notes.get(n["id"], {}).get("starred") else "") + (f" [{_md(', '.join(_tags(g, n)))}]" if _tags(g, n) else ""))
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
        tags = [f"osint/{re.sub(r'[^a-z0-9]', '', n['type'].lower())}"] + [json.dumps(re.sub(r"[\s#,\[\]]+", "_", x), ensure_ascii=False) for x in _tags(g, n)]
        L = ["---", f"{T.ui('type')}: {json.dumps(T.type(n['type']), ensure_ascii=False)}", f"{T.ui('value')}: {json.dumps(T.value(n), ensure_ascii=False)}",
             f"{T.ui('investigation_key')}: {meta['id']}", f"tags: [{', '.join(tags)}]"]
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
            doc.append(Paragraph(f"<b>{t(T.value(n))[:150]}</b>" + (" *" if notes.get(n["id"], {}).get("starred") else "") + (f" [{t(', '.join(_tags(g, n)))}]" if _tags(g, n) else ""), st["BodyText"]))
            if notes.get(n["id"], {}).get("text"):
                doc.append(Paragraph(f"<i>{t(T.ui('note'))}: {t(notes[n['id']]['text'])}</i>", small))
            for e, o in out[n["id"]]:
                doc.append(Paragraph(t(f"{T.rel(e['rel'])} -> {T.value(o)[:100]} ({e['conf']:.0%}, {_src(e)[:90]})"), small))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=meta["name"], leftMargin=40, rightMargin=40,
                      topMargin=40, bottomMargin=40).build(doc)
    return buf.getvalue()


# ---------- Customizable reports (md / pdf / html with chosen sections) ----------

SECTIONS = ("summary", "entities", "relations", "links", "notes", "tags", "proofs", "timeline")
LOGO_MAX = 1_000_000
_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")


def decode_logo(b64: str | None) -> tuple[bytes, str] | None:
    """(bytes, mime) of a base64 PNG/JPEG up to 1 MB; ValueError otherwise."""
    if not b64:
        return None
    import base64
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError("logo: invalid base64")
    if len(raw) > LOGO_MAX:
        raise ValueError("logo: larger than 1 MB")
    if raw.startswith(_MAGIC[0]):
        return raw, "image/png"
    if raw.startswith(_MAGIC[1]):
        return raw, "image/jpeg"
    raise ValueError("logo: only PNG or JPEG")


def _ts(x) -> str:
    try:
        return datetime.fromtimestamp(float(x)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _data(g: dict, T: _L, extras: dict | None) -> dict:
    """Section contents as plain rows, shared by the three formats."""
    nodes, out, _, by_type = _prep(g)
    notes = _notes(g)
    tags = {t["entity"]: t["tags"] for t in g.get("tags", [])}
    ex = extras or {}
    v = lambda i: T.value(nodes[i])
    d = {
        "summary": [(T.type(t), len(ns)) for t, ns in by_type.items()],
        "entities": [(T.type(t), [(T.value(n), bool(notes.get(n["id"], {}).get("starred"))) for n in ns]) for t, ns in by_type.items()],
        "relations": [(v(e["src"]), T.rel(e["rel"]), v(e["dst"]), f"{e['conf']:.0%}", _src(e)) for e in sorted(g["edges"], key=lambda e: e["id"])],
        "links": [(T.status(l["status"]), f"{l['score']:.0%}", f"{v(l['a'])} <-> {v(l['b'])}",
                   ", ".join(T.signal(s[0]) for s in l["signals"]) or T.ui("confirmed_manually")) for l in sorted(g["links"], key=lambda l: -l["score"])],
        "notes": [(T.value(n), notes[n["id"]]["text"]) for n in g["nodes"] if notes.get(n["id"], {}).get("text")],
        "tags": [(v(i), ", ".join(ts)) for i, ts in tags.items() if i in nodes and ts],
        "proofs": [(_ts(p.get("ts")), str(p.get("url", "")), str(p.get("sha256", "")), str(p.get("wayback") or "")) for p in ex.get("proofs", [])],
        "timeline": [(str(e.get("date", "")), str(e.get("label", ""))) for e in ex.get("timeline", [])],
    }
    return d


def _heads(T: _L) -> dict:
    return {s: T.ui(s) for s in SECTIONS}


def _cols(T: _L) -> dict:
    return {"relations": ("", T.ui("relations"), "", "%", ""), "links": (T.ui("status"), T.ui("pt"), T.ui("entity_col"), T.ui("signals")),
            "proofs": (T.ui("date"), "URL", "SHA-256", T.ui("archive")), "tags": (T.ui("entity_col"), T.ui("tags")),
            "notes": (T.ui("entity_col"), T.ui("note")), "timeline": (T.ui("date"), "")}


def _custom_md(g, meta, sections, title, header, footer, T, extras) -> str:
    d, H = _data(g, T, extras), _heads(T)
    L = [f"# {title or meta['name']}", ""] + ([header, ""] if header else [])
    if "summary" in sections:
        L += [f"## {H['summary']}", "", f"- **{T.ui('entities')}:** {len(g['nodes'])} · **{T.ui('relations')}:** {len(g['edges'])}"] + [f"- {k}: {n}" for k, n in d["summary"]] + [""]
    if "entities" in sections:
        L += [f"## {H['entities']}", ""]
        for t, vs in d["entities"]:
            L += [f"### {t}", ""] + [f"- **{_md(x)}**" + (" ★" if s else "") for x, s in vs] + [""]
    tables = {"relations": d["relations"], "links": d["links"], "proofs": d["proofs"], "tags": d["tags"], "notes": d["notes"], "timeline": d["timeline"]}
    cols = _cols(T)
    for s in SECTIONS:
        if s in tables and s in sections and tables[s]:
            c = cols[s] if s != "relations" else (T.ui("entity_col"), T.ui("relations"), T.ui("entity_col"), T.ui("pt"), T.ui("signals"))
            L += [f"## {H[s]}", "", "| " + " | ".join(c) + " |", "|" + "---|" * len(c)]
            L += ["| " + " | ".join(_md(str(x)) for x in row) + " |" for row in tables[s]] + [""]
    if footer:
        L += ["---", footer, ""]
    return "\n".join(L)


def _custom_html(g, meta, sections, title, header, footer, T, extras, logo) -> str:
    import base64
    from html import escape as h
    d, H, cols = _data(g, T, extras), _heads(T), _cols(T)
    cols["relations"] = (T.ui("entity_col"), T.ui("relations"), T.ui("entity_col"), T.ui("pt"), T.ui("signals"))
    P = [f"<h1>{h(title or meta['name'])}</h1>"]
    if logo:
        P.insert(0, f'<img class="logo" alt="" src="data:{logo[1]};base64,{base64.b64encode(logo[0]).decode()}">')
    if header:
        P.append(f'<p class="hdr">{h(header)}</p>')
    P.append('<input id="q" type="search" placeholder="%s" aria-label="%s">' % (h(T.ui("filter")), h(T.ui("filter"))))
    if "summary" in sections:
        P.append(f"<h2>{h(H['summary'])}</h2><p>{h(T.ui('entities'))}: {len(g['nodes'])} · {h(T.ui('relations'))}: {len(g['edges'])}</p><ul>"
                 + "".join(f"<li>{h(k)}: {n}</li>" for k, n in d["summary"]) + "</ul>")
    if "entities" in sections:
        P.append(f"<h2>{h(H['entities'])}</h2>")
        for t, vs in d["entities"]:
            P.append(f"<details open><summary>{h(t)} ({len(vs)})</summary><ul>"
                     + "".join(f'<li class="f">{h(x)}{" ★" if s else ""}</li>' for x, s in vs) + "</ul></details>")
    for s in SECTIONS:
        if s in ("summary", "entities") or s not in sections or not d[s]:
            continue
        P.append(f"<h2>{h(H[s])}</h2><table><thead><tr>" + "".join(f"<th>{h(c)}</th>" for c in cols[s]) + "</tr></thead><tbody>"
                 + "".join('<tr class="f">' + "".join(f"<td>{h(str(x))}</td>" for x in row) + "</tr>" for row in d[s]) + "</tbody></table>")
    if footer:
        P.append(f'<footer>{h(footer)}</footer>')
    css = ("body{font:15px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;background:#fff;color:#1b1b1b}"
           "@media(prefers-color-scheme:dark){body{background:#16181c;color:#e6e6e6}th{background:#2a2d33}}"
           "table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #8886;padding:3px 6px;text-align:left;word-break:break-all}th{background:#eee}"
           ".logo{max-height:80px}input{width:100%;padding:6px;margin:1rem 0}summary{cursor:pointer;font-weight:600}footer{margin-top:2rem;border-top:1px solid #8886;padding-top:.5rem;font-size:13px}"
           "@media print{input{display:none}body{background:#fff;color:#000;margin:0}details>*{display:block}}")
    js = ("document.getElementById('q').oninput=function(){var s=this.value.toLowerCase();"
          "document.querySelectorAll('.f').forEach(function(e){e.hidden=e.textContent.toLowerCase().indexOf(s)<0})};")
    return (f'<!doctype html><html lang="{h(T.lang)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{h(title or meta["name"])}</title><style>{css}</style></head><body>{"".join(P)}<script>{js}</script></body></html>')


def _custom_pdf(g, meta, sections, title, header, footer, T, extras, logo) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def t(s) -> str:
        return escape(str(s).replace("→", "->").replace("↔", "<->")).encode("latin-1", "replace").decode("latin-1")

    d, H, cols = _data(g, T, extras), _heads(T), _cols(T)
    cols["relations"] = (T.ui("entity_col"), T.ui("relations"), T.ui("entity_col"), T.ui("pt"), T.ui("signals"))
    st = getSampleStyleSheet()
    cell = st["BodyText"].clone("cell", fontSize=7, leading=9)
    doc = []
    if logo:
        try:
            w, hh = ImageReader(io.BytesIO(logo[0])).getSize()
        except Exception:
            raise ValueError("logo: not a readable image")
        k = min(1.0, 140 / w, 60 / hh)
        doc.append(Image(io.BytesIO(logo[0]), width=w * k, height=hh * k, hAlign="LEFT"))
    doc.append(Paragraph(t(title or meta["name"]), st["Title"]))
    if header:
        doc.append(Paragraph(t(header), st["BodyText"]))
    if "summary" in sections:
        doc += [Paragraph(t(H["summary"]), st["Heading2"]), Paragraph(f"{t(T.ui('entities'))}: {len(g['nodes'])} &nbsp; {t(T.ui('relations'))}: {len(g['edges'])}", st["BodyText"])]
        doc += [Paragraph(f"{t(k)}: {n}", st["BodyText"]) for k, n in d["summary"]]
    if "entities" in sections:
        doc.append(Paragraph(t(H["entities"]), st["Heading2"]))
        for typ, vs in d["entities"]:
            doc.append(Paragraph(f"{t(typ)} ({len(vs)})", st["Heading3"]))
            doc += [Paragraph(f"<b>{t(x)[:150]}</b>" + (" *" if s else ""), st["BodyText"]) for x, s in vs]
    for s in SECTIONS:
        if s in ("summary", "entities") or s not in sections or not d[s]:
            continue
        doc += [Spacer(1, 8), Paragraph(t(H[s]), st["Heading2"])]
        rows = [[Paragraph(f"<b>{t(c)}</b>", cell) for c in cols[s]]] + [[Paragraph(t(x)[:300], cell) for x in row] for row in d[s]]
        tb = Table(rows, hAlign="LEFT", repeatRows=1)
        tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        doc.append(tb)

    def page(c, _):
        c.setFont("Helvetica", 8)
        if footer:
            c.drawString(40, 22, t(footer).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")[:120])
        c.drawRightString(A4[0] - 40, 22, str(c.getPageNumber()))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=title or meta["name"], leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40).build(doc, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()


def render(g: dict, meta: dict, fmt: str, *, sections=SECTIONS, title: str = "", header: str = "", footer: str = "",
           logo: str | None = None, lang: str | None = None, extras: dict | None = None) -> bytes:
    """Custom report as bytes. fmt md|pdf|html; ValueError on unknown format/section or bad logo. extras = {"proofs": [...], "timeline": [...]}."""
    bad = [s for s in sections if s not in SECTIONS]
    if bad or fmt not in ("md", "pdf", "html"):
        raise ValueError(f"unknown {'section ' + str(bad) if bad else 'format ' + fmt}")
    lg, T, sec = decode_logo(logo), _L(lang), set(sections)
    if fmt == "md":
        return _custom_md(g, meta, sec, title, header, footer, T, extras).encode()
    if fmt == "html":
        return _custom_html(g, meta, sec, title, header, footer, T, extras, lg).encode()
    return _custom_pdf(g, meta, sec, title, header, footer, T, extras, lg)
