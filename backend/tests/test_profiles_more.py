import asyncio
import json
import pathlib

import pytest

from osint.collectors import COLLECTORS, more_profiles as mp
from osint.i18n import VALUES

FX = pathlib.Path(__file__).parent / "fixtures"
J = lambda n: json.loads((FX / n).read_text())
T = lambda n: (FX / n).read_text()


def rels(fs):
    return {(f.rel, f.dst[0]): f.dst[1] for f in fs}


def run(src, payload, user):
    p = src.parse(payload, user)
    return mp.findings(user, src.label, src.name, p) if p else []


S = {s.name: s for s in mp.SOURCES}

CASES = [  # source, fixture, username, expected (rel, type) -> value
    ("lobsters", "pf_lobsters.json", "jcs", {("creato_il", "Data"): "account Lobsters creato: 2012-06-30", ("profilo_collegato", "Account"): "https://github.com/jcs"}),
    ("scratch", "pf_scratch.json", "griffpatch", {("creato_il", "Data"): "account Scratch creato: 2012-10-24"}),
    ("wikipedia_user_en", "pf_mw.json", "Jimbo Wales", {("creato_il", "Data"): "account Wikipedia creato: 2001-03-27"}),
    ("duolingo", "pf_duolingo.json", "Luis", {("nome_profilo", "Persona"): "Luis", ("luogo_dichiarato", "Luogo"): "Guatemala"}),
    ("matrix", "pf_matrix.json", "matthew", {("nome_profilo", "Persona"): "Matthew"}),
    ("hexpm", "pf_hex.json", "josevalim", {("email_pubblica", "Email"): "jose.valim@gmail.com", ("creato_il", "Data"): "account Hex.pm creato: 2014-04-23"}),
    ("lemmy_lemmy_ml", "pf_lemmy.json", "nutomic", {("profilo_collegato", "Account"): "https://matrix.to/#/@nutomic:matrix.org", ("nome_profilo", "Persona"): "Nutomic"}),
    ("openlibrary_user", "pf_openlibrary.json", "george08", {("sito_dichiarato", "Dominio"): "abitofgeorge.com", ("creato_il", "Data"): "account Open Library creato: 2009-04-28"}),
    ("mixcloud", "pf_mixcloud.json", "spartacus", {("luogo_dichiarato", "Luogo"): "London, United Kingdom"}),
    ("dailymotion", "pf_dailymotion.json", "dailymotion", {("profilo_collegato", "Account"): "https://instagram.com/dailymotion", ("creato_il", "Data"): "account Dailymotion creato: 2007-05-16"}),
    ("substack", "pf_substack.json", "ben", {("nome_profilo", "Persona"): "Benjamin Murphy", ("sito_dichiarato", "Dominio"): "benjaminmurphy.me"}),
    ("bitbucket", "pf_bitbucket.json", "atlassian", {("creato_il", "Data"): "account Bitbucket creato: 2018-11-29"}),
    ("gitea_com", "pf_gitea.json", "lunny", {("luogo_dichiarato", "Luogo"): "Silicon Valley", ("creato_il", "Data"): "account Gitea creato: 2018-11-27"}),
    ("framagit", "pf_gitlab.json", "ycollet", {("account", "Account"): "https://framagit.org/ycollet"}),
    ("kitsu", "pf_kitsu.json", "josh", {("luogo_dichiarato", "Luogo"): "Pittsburgh, PA", ("creato_il", "Data"): "account Kitsu creato: 2013-02-21"}),
    ("modrinth", "pf_modrinth.json", "Prospector", {("creato_il", "Data"): "account Modrinth creato: 2020-11-06"}),
    ("misskey_io", "pf_misskey.json", "syuilo", {("luogo_dichiarato", "Luogo"): "Japan", ("nome_profilo", "Persona"): "しゅいろ(本物)"}),
    ("sourceforge", "pf_sourceforge.json", "torvalds", {("creato_il", "Data"): "account SourceForge creato: 2000-06-12"}),
    ("tumblr", "pf_tumblr.js", "staff", {("account", "Account"): "https://staff.tumblr.com"}),
    ("livejournal", "pf_livejournal.xml", "brad", {("nome_profilo", "Persona"): "Brad Fitzpatrick", ("luogo_dichiarato", "Luogo"): "San Francisco, US",
                                                    ("sito_dichiarato", "Dominio"): "bradfitz.com", ("creato_il", "Data"): "account LiveJournal creato: 1999-05-03"}),
    ("neocities", "pf_neocities.json", "neocities", {("creato_il", "Data"): "account Neocities creato: 2013-06-21"}),
    ("packagist", "pf_packagist.json", "symfony", {("account", "Account"): "https://packagist.org/packages/symfony/"}),
    ("wikimedia_commons_user", "pf_mw_commons.json", "Jimbo Wales", {("account", "Account"): "https://commons.wikimedia.org/wiki/User:Jimbo_Wales"}),
]


@pytest.mark.parametrize("name,fx,user,expected", CASES)
def test_parse_real_fixtures(name, fx, user, expected):
    src = S[name]
    payload = T(fx) if src.raw else J(fx)
    got = rels(run(src, payload, user))
    for k, v in expected.items():
        assert k in got and (v is None or got[k] == v), (k, got)
    assert all(f.conf <= 0.9 for f in run(src, payload, user))
    acc = [f for f in run(src, payload, user) if f.rel == "account"][0]
    assert acc.src == ("Username", user) and acc.conf <= 0.6 and not acc.pivot


def test_missing_garbage_and_empty_inputs():
    assert run(S["wikipedia_user_en"], {"query": {"users": [{"name": "Zz", "missing": ""}]}}, "zz") == []
    assert run(S["duolingo"], {"users": []}, "zz") == []
    assert run(S["kitsu"], {"data": []}, "zz") == []
    assert run(S["kitsu"], J("pf_kitsu.json"), "someoneelse") == []  # fuzzy filter hit is not the exact name
    assert run(S["framagit"], [], "zz") == [] and run(S["packagist"], {"packageNames": []}, "zz") == []
    assert run(S["mixcloud"], {"error": {"type": "ResourceNotFoundException"}}, "zz") == []
    assert run(S["tumblr"], "garbage", "zz") == [] and run(S["livejournal"], "<html/>", "zz") == []
    assert run(S["lemmy_lemmy_ml"], {"person_view": {"person": {"deleted": True}}}, "zz") == []


def test_bsky_search_only_exact_display_name_and_low_confidence():
    out = mp.parse_bsky_search("Jay", J("pf_bsky_search.json"))
    assert out and all(f.conf <= 0.3 and f.src == ("Persona", "Jay") and "omonimi" in f.reason for f in out)
    assert mp.parse_bsky_search("Nobody Special", J("pf_bsky_search.json")) == [] and mp.parse_bsky_search("x", {}) == []


def test_osm_parse():
    out = mp.parse_osm("Steve", T("pf_osm_changesets.xml"), J("pf_osm_user.json"))
    assert rels(out)[("creato_il", "Data")] == "account OpenStreetMap creato: 2005-09-13"
    assert mp.parse_osm("x", "", {}) == []


def test_registration_and_translations():
    names = {c.name: c for c in COLLECTORS}
    for s in mp.SOURCES:
        assert names[s.name].accepts == {"Username"} and not names[s.name].key and not names[s.name].active
    assert names["bluesky_search"].accepts == {"Persona"} and names["openstreetmap"].accepts == {"Username"}
    assert len([n for n in names if n in {s.name for s in mp.SOURCES}]) + 2 >= 25
    for s in mp.SOURCES:
        assert f"account {s.label} creato: {{}}" in VALUES, s.label


def test_invalid_username_is_not_requested():
    assert asyncio.run(mp.make(S["lobsters"])("../../x?y")) == []
    assert asyncio.run(mp.openstreetmap("a b/c")) == []
