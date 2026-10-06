from xml.sax.saxutils import escape


def to_graphml(g: dict) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
           '<key id="type" for="node" attr.name="type" attr.type="string"/>',
           '<key id="label" for="node" attr.name="label" attr.type="string"/>',
           '<key id="rel" for="edge" attr.name="rel" attr.type="string"/>',
           '<key id="conf" for="edge" attr.name="conf" attr.type="double"/>',
           '<key id="source" for="edge" attr.name="source" attr.type="string"/>',
           '<graph edgedefault="directed">']
    for n in g["nodes"]:
        out.append(f'<node id="n{n["id"]}"><data key="type">{_t(n["type"])}</data><data key="label">{_t(n["value"])}</data></node>')
    for e in g["edges"]:
        out.append(f'<edge source="n{e["src"]}" target="n{e["dst"]}"><data key="rel">{_t(e["rel"])}</data>'
                   f'<data key="conf">{e["conf"]}</data><data key="source">{_t(e["url"] or e["collector"])}</data></edge>')
    for l in g.get("links", []):
        out.append(f'<edge source="n{l["a"]}" target="n{l["b"]}"><data key="rel">stesso_soggetto ({l["status"]})</data>'
                   f'<data key="conf">{l["score"]}</data></edge>')
    return "\n".join(out + ["</graph>", "</graphml>"])


def _t(s: str) -> str:
    return escape(s)
