"""Human-readable exports of an investigation graph: Markdown report, PDF, Obsidian vault."""
import io
import json
import re
from collections import defaultdict
from datetime import datetime
from xml.sax.saxutils import escape

STATUS = {"auto": "automatico", "review": "da verificare", "confirmed": "confermato"}


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


def markdown(g: dict, meta: dict) -> str:
    nodes, out, _, by_type = _prep(g)
    L = [f"# {meta['name']}", "", f"- **Indagine:** #{meta['id']}"] + ([f"- **Scopo:** {meta['purpose']}"] if meta["purpose"] else []) + [
         f"- **Data:** {_date(meta)}", f"- **Entità:** {len(g['nodes'])} · **Relazioni:** {len(g['edges'])}", "", "## Riepilogo", ""]
    L += [f"- {t}: {len(ns)}" for t, ns in by_type.items()]
    notes = _notes(g)
    if any(n["starred"] for n in notes.values()):
        L += ["", "## Preferiti", ""]
        for n in g["nodes"]:
            if notes.get(n["id"], {}).get("starred"):
                L.append(f"- **{_md(n['value'])}** ({n['type']})" + (f": {_md(notes[n['id']]['text'])}" if notes[n["id"]]["text"] else ""))
    if g["links"]:
        L += ["", "## Collegamenti ipotizzati", "", "| Stato | Punteggio | Entità | Segnali |", "|---|---|---|---|"]
        for l in sorted(g["links"], key=lambda l: -l["score"]):
            sig = ", ".join(s[0] for s in l["signals"]) or "confermato manualmente"
            L.append(f"| {STATUS[l['status']]} | {l['score']:.0%} | {_md(nodes[l['a']]['value'])} ↔ {_md(nodes[l['b']]['value'])} | {sig} |")
    L += ["", "## Entità", ""]
    for t, ns in by_type.items():
        L += [f"### {t}", ""]
        for n in ns:
            L.append(f"- **{_md(n['value'])}**" + (" ★" if notes.get(n["id"], {}).get("starred") else ""))
            if notes.get(n["id"], {}).get("text"):
                L.append(f"  - nota: {_md(notes[n['id']]['text'])}")
            for e, o in out[n["id"]]:
                L.append(f"  - {e['rel']} → {_md(o['value'])} ({e['conf']:.0%}, {_md(_src(e))})")
        L.append("")
    return "\n".join(L)


def _md(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


# ---------- Obsidian ----------

def _fname(n: dict) -> str:
    v = re.sub(r"^https?://(www\.)?", "", n["value"])
    v = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", v).strip(" .")[:80] or str(n["id"])
    return v


def obsidian(g: dict, meta: dict) -> dict[str, str]:
    """{relative path: file content}. Each entity is a note; relations are [[wikilinks]]."""
    nodes, out, inc, by_type = _prep(g)
    path, used = {}, set()
    for n in sorted(g["nodes"], key=lambda n: n["id"]):
        p = f"{n['type']}/{_fname(n)}"
        if p.lower() in used:
            p += f" ({n['id']})"
        used.add(p.lower())
        path[n["id"]] = p

    def link(i: int) -> str:
        return f"[[{path[i]}|{nodes[i]['value'].replace('|', '/').replace(']', ')')[:80]}]]"

    notes = _notes(g)
    links_of = defaultdict(list)
    for l in g["links"]:
        links_of[l["a"]].append((l, l["b"]))
        links_of[l["b"]].append((l, l["a"]))

    files = {}
    for n in g["nodes"]:
        L = ["---", f"tipo: {json.dumps(n['type'], ensure_ascii=False)}", f"valore: {json.dumps(n['value'], ensure_ascii=False)}",
             f"indagine: {meta['id']}", f"tags: [osint/{re.sub(r'[^a-z0-9]', '', n['type'].lower())}]"]
        if notes.get(n["id"], {}).get("starred"):
            L.append("preferito: true")
        L += ["---", "", f"# {n['value']}", ""]
        if notes.get(n["id"], {}).get("text"):
            L += ["## Note", notes[n["id"]]["text"], ""]
        if out[n["id"]] or inc[n["id"]]:
            L.append("## Relazioni")
            for e, o in out[n["id"]]:
                L.append(f"- {e['rel']} → {link(o['id'])} · {e['conf']:.0%} · {_src(e)}")
            for e, o in inc[n["id"]]:
                L.append(f"- ← {e['rel']} da {link(o['id'])} · {e['conf']:.0%} · {_src(e)}")
            L.append("")
        if links_of[n["id"]]:
            L.append("## Collegamenti ipotizzati")
            for l, other in sorted(links_of[n["id"]], key=lambda x: -x[0]["score"]):
                L.append(f"- {link(other)} · {l['score']:.0%} · {STATUS[l['status']]} · {', '.join(s[0] for s in l['signals'])}")
            L.append("")
        files[path[n["id"]] + ".md"] = "\n".join(L)

    idx = [f"# {meta['name']}", "", f"- **Indagine:** #{meta['id']}"] + ([f"- **Scopo:** {meta['purpose']}"] if meta["purpose"] else []) + [
        f"- **Data:** {_date(meta)}", ""]
    starred = [n for n in g["nodes"] if notes.get(n["id"], {}).get("starred")]
    if starred:
        idx += ["## Preferiti", ""] + [f"- {link(n['id'])}" for n in starred] + [""]
    for t, ns in by_type.items():
        idx += [f"## {t} ({len(ns)})", ""] + [f"- {link(n['id'])}" for n in ns] + [""]
    files["Indagine.md"] = "\n".join(idx)
    return files


# ---------- PDF ----------

def pdf(g: dict, meta: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    nodes, out, _, by_type = _prep(g)

    def t(s) -> str:  # base-14 fonts are latin-1 only: unsupported characters become '?'
        return escape(str(s).replace("→", "->").replace("↔", "<->")).encode("latin-1", "replace").decode("latin-1")

    st = getSampleStyleSheet()
    small = st["BodyText"].clone("small", fontSize=8, leading=10, leftIndent=14)
    doc = []
    doc += [Paragraph(t(meta["name"]), st["Title"])]
    if meta["purpose"]:
        doc.append(Paragraph(f"<b>Scopo:</b> {t(meta['purpose'])}", st["BodyText"]))
    doc += [Paragraph(f"<b>Data:</b> {_date(meta)} &nbsp; <b>Entita:</b> {len(g['nodes'])} &nbsp; <b>Relazioni:</b> {len(g['edges'])}", st["BodyText"]),
            Spacer(1, 10), Paragraph("Riepilogo", st["Heading2"])]
    rows = [[t(k), str(len(v))] for k, v in by_type.items()]
    if rows:
        tb = Table(rows, hAlign="LEFT", colWidths=[160, 50])
        tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
        doc.append(tb)
    notes = _notes(g)
    starred = [n for n in g["nodes"] if notes.get(n["id"], {}).get("starred")]
    if starred:
        doc += [Spacer(1, 10), Paragraph("Preferiti", st["Heading2"])]
        for n in starred:
            doc.append(Paragraph(f"<b>{t(n['value'])[:150]}</b> ({t(n['type'])})" + (f": {t(notes[n['id']]['text'])}" if notes[n["id"]]["text"] else ""), st["BodyText"]))
    if g["links"]:
        doc += [Spacer(1, 10), Paragraph("Collegamenti ipotizzati", st["Heading2"])]
        cell = st["BodyText"].clone("cell", fontSize=8, leading=10)
        rows = [["Stato", "Punt.", "Entita", "Segnali"]] + [
            [t(STATUS[l["status"]]), f"{l['score']:.0%}", Paragraph(t(f"{nodes[l['a']]['value']} <-> {nodes[l['b']]['value']}"), cell),
             Paragraph(t(", ".join(s[0] for s in l["signals"]) or "confermato manualmente"), cell)]
            for l in sorted(g["links"], key=lambda l: -l["score"])]
        tb = Table(rows, hAlign="LEFT", colWidths=[70, 40, 230, 150], repeatRows=1)
        tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        doc.append(tb)
    doc.append(Paragraph("Entita", st["Heading2"]))
    for typ, ns in by_type.items():
        doc.append(Paragraph(f"{t(typ)} ({len(ns)})", st["Heading3"]))
        for n in ns:
            doc.append(Paragraph(f"<b>{t(n['value'])[:150]}</b>" + (" *" if notes.get(n["id"], {}).get("starred") else ""), st["BodyText"]))
            if notes.get(n["id"], {}).get("text"):
                doc.append(Paragraph(f"<i>nota: {t(notes[n['id']]['text'])}</i>", small))
            for e, o in out[n["id"]]:
                doc.append(Paragraph(t(f"{e['rel']} -> {o['value'][:100]} ({e['conf']:.0%}, {_src(e)[:90]})"), small))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=meta["name"], leftMargin=40, rightMargin=40,
                      topMargin=40, bottomMargin=40).build(doc)
    return buf.getvalue()
