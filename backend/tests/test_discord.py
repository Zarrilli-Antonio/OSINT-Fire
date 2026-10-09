import json
import pathlib

from osint import i18n
from osint.collectors import COLLECTORS
from osint.collectors.more_discord import invite_code, parse_invite, snowflake_date

FIX = pathlib.Path(__file__).parent / "fixtures" / "discord_invite_python.json"


def test_invite_code_forms():
    assert invite_code("https://discord.gg/python") == "python"
    assert invite_code("https://discord.com/invite/py-thon/") == "py-thon"
    assert invite_code("https://discordapp.com/invite/abc") == "abc"
    assert invite_code("https://example.com/invite/abc") is None
    assert invite_code("https://discord.gg/") is None


def test_snowflake_date():
    assert snowflake_date("267624335836053506") == "2017-01-08"


def test_parse_real_invite():
    out = parse_invite("https://discord.gg/python", json.loads(FIX.read_text()))
    assert [f.rel for f in out] == ["server_discord", "evento_server"]
    assert out[0].dst == ("Servizio", "Discord: Python (267624335836053506)") and out[0].pivot is False
    assert out[1].dst == ("Data", "server Discord creato: 2017-01-08")


def test_parse_inviter_shape_from_docs():  # the real fixture has no inviter; this field set is the documented one
    d = {**json.loads(FIX.read_text()), "inviter": {"id": "80351110224678912", "username": "nelly", "global_name": "Nelly"}}
    out = parse_invite("https://discord.gg/python", d)
    assert ("Username", "nelly") in [f.dst for f in out] and ("Persona", "Nelly") in [f.dst for f in out]
    assert any(f.dst == ("Data", "account Discord creato: 2015-08-10") for f in out)


def test_garbage_and_registration():
    assert parse_invite("u", {}) == [] and parse_invite("u", {"guild": {"name": "x"}, "guild_id": "abc"}) == []
    assert [c.accepts for c in COLLECTORS if c.name == "discord_invite"] == [{"Account"}]
    assert i18n.label("value", "server Discord creato: 2017-01-08", "de") == "Discord-Server erstellt: 2017-01-08"
