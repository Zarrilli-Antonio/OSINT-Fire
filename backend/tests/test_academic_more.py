import json
import pathlib

from osint.collectors import COLLECTORS, more_academic as m

FX = pathlib.Path(__file__).parent / "fixtures"
C = {c.name: c for c in COLLECTORS}
J = lambda n: json.loads((FX / n).read_text())


def check(out, rel_min=1):
    assert out and all(f.conf <= 0.5 and not f.pivot for f in out)
    assert any(f.rel == "autore_di" for f in out)


def test_registration():
    for n in ("arxiv", "crossref", "europepmc", "pubmed", "inspirehep", "semanticscholar", "zenodo", "openaire"):
        assert C[n].accepts == {"Persona"} and C[n].key == ()
    assert C["softwareheritage"].accepts == {"Username"}


def test_same_person():
    assert m.same_person("Yann LeCun", "LeCun, Yann") and m.same_person("Yann LeCun", "Yann A. LeCun") and not m.same_person("Yann LeCun", "Marie LeCun")
    assert not m.same_person("Yann", "Yann")


def test_arxiv_papers_and_coauthors():
    out = m.parse_arxiv("Yann LeCun", (FX / "arxiv_author.xml").read_text())
    check(out)
    assert any(f.rel == "collaboratore" and f.dst == ("Persona", "Camille Couprie") for f in out)
    assert not any(f.dst == ("Persona", "Yann LeCun") for f in out) and all("omonimia possibile" in f.reason for f in out)


def test_crossref_orcid():
    out = m.parse_crossref("Yann LeCun", J("crossref_author.json"))
    check(out)
    assert any(f.dst == ("Account", "https://orcid.org/0000-0002-1992-2684") for f in out)


def test_europepmc_and_pubmed():
    out = m.parse_europepmc("Yann LeCun", J("europepmc.json"))
    check(out)
    assert any(f.dst == ("Persona", "Bojanowski P") for f in out)
    out = m.parse_pubmed("Yann LeCun", J("pubmed_esummary.json"))
    check(out)
    assert any("10.3390/e26030252" in f.dst[1] for f in out)


def test_inspire_orcid_and_affiliation():
    out = m.parse_inspire("Edward Witten", J("inspire_authors.json"))
    assert any(f.rel == "affiliato_a" and f.dst == ("Azienda", "Princeton, Inst. Advanced Study") for f in out)
    assert m.parse_inspire("Somebody Else", J("inspire_authors.json")) == []


def test_semanticscholar_dblp():
    out = m.parse_semanticscholar("Yann LeCun", J("semanticscholar_author.json"))
    assert out and all(f.conf <= 0.4 for f in out) and any("dblp.org" in f.dst[1] for f in out)


def test_zenodo_and_openaire():
    check(m.parse_zenodo("Yann LeCun", J("zenodo.json")))
    out = m.parse_openaire("Yann LeCun", J("openaire_author.json"))
    check(out)
    assert any("10.1080/08956308.2018.1516928" in f.dst[1] for f in out)


def test_software_heritage_only_exact_owner():
    out = m.parse_swh("torvalds", J("swh_origin.json"))
    assert len(out) == 4 and all(f.src == ("Username", "torvalds") and f.dst[1].startswith("github.com/torvalds/") for f in out)


def test_empty_and_garbage():
    for fn in (m.parse_crossref, m.parse_europepmc, m.parse_pubmed, m.parse_inspire, m.parse_semanticscholar, m.parse_zenodo, m.parse_openaire):
        assert fn("Yann LeCun", {}) == []
    assert m.parse_arxiv("Yann LeCun", "not xml") == [] and m.parse_swh("x", [None, {}]) == []
