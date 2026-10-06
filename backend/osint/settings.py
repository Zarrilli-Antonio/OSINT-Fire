"""User settings. Stored in the DB (table `setting`), mirrored in CFG so synchronous code (collectors) can read them."""
import json

# key -> (default, kind, lo/hi or choices). kind: int | bool | str | list
# Public mail providers and ISPs: an address there says nothing about a domain owner, and tracing gmail.com is noise.
FREE_EMAIL_DOMAINS = (
    "gmail.com googlemail.com outlook.com outlook.it hotmail.com hotmail.it live.com live.it msn.com yahoo.com yahoo.it ymail.com "
    "icloud.com me.com mac.com aol.com proton.me protonmail.com pm.me gmx.com gmx.net gmx.de mail.com yandex.com yandex.ru mail.ru "
    "zoho.com libero.it virgilio.it tiscali.it alice.it tim.it fastwebnet.it email.it inwind.it iol.it tin.it pec.it legalmail.it "
    "arubapec.it postecert.it tutanota.com tuta.io fastmail.com hey.com qq.com 163.com naver.com web.de t-online.de orange.fr free.fr "
    "laposte.net wanadoo.fr btinternet.com comcast.net verizon.net att.net sbcglobal.net cox.net rediffmail.com duck.com"
).split()

SPEC = {
    # investigations
    "default_depth": (2, "int", (0, 4)),
    "default_max_entities": (300, "int", (10, 2000)),
    # data handling
    "cache_ttl_hours": (24, "int", (0, 24 * 90)),  # 0 = never reuse cached collector results
    "fetch_avatars": (True, "bool", None),  # download public avatars (needed for image matching)
    "passive_only": (False, "bool", None),  # skip collectors that contact the target's own servers
    "disabled_collectors": ([], "list", None),
    "ignored_domains": (FREE_EMAIL_DOMAINS, "list", None),  # never followed automatically (a domain given as a seed is still searched)
    # network
    "concurrency": (8, "int", (1, 32)),
    "http_timeout": (15, "int", (3, 120)),
    "user_agent": ("OSINT-Fire/0.1", "str", (1, 200)),
    "proxy": ("", "str", (0, 300)),  # http(s):// or socks5://, applied to HTTP collectors and Maigret (not to DNS)
    # social search from other seed types (each followed username triggers a Maigret scan: about a minute)
    "auto_username_from_email": (True, "bool", None),  # follow the part before @ when it looks personal
    "auto_username_from_name": (False, "bool", None),  # follow username guesses built from a person's name (many false positives)
    # username scan
    "maigret_top_sites": (300, "int", (20, 3000)),
    "maigret_timeout": (8, "int", (2, 60)),
    # display
    "group_min": (6, "int", (3, 50)),
    # optional API keys (secret)
    "github_token": ("", "secret", None),
    "virustotal_key": ("", "secret", None),
    "shodan_key": ("", "secret", None),
    "hunter_key": ("", "secret", None),
    "hibp_key": ("", "secret", None),
    "securitytrails_key": ("", "secret", None),
    "abuseipdb_key": ("", "secret", None),
    # connected accounts: official APIs of the platforms, with the user's own credentials
    "reddit_client_id": ("", "secret", None),
    "reddit_client_secret": ("", "secret", None),
    "twitch_client_id": ("", "secret", None),
    "twitch_client_secret": ("", "secret", None),
    "youtube_key": ("", "secret", None),
    "spotify_client_id": ("", "secret", None),
    "spotify_client_secret": ("", "secret", None),
    "x_bearer": ("", "secret", None),
    "companieshouse_key": ("", "secret", None),
    "greynoise_key": ("", "secret", None),
    "otx_key": ("", "secret", None),
    "abusech_key": ("", "secret", None),
    # AI connector
    "ai_provider": ("anthropic", "choice", ("anthropic", "openai")),
    "ai_base_url": ("", "str", (0, 300)),
    "ai_model": ("claude-sonnet-5-5", "str", (0, 100)),
    "ai_key": ("", "secret", None),
    "ai_send_notes": (False, "bool", None),
    "ai_max_entities": (400, "int", (20, 3000)),
}
SECRETS = {k for k, v in SPEC.items() if v[1] == "secret"}
CFG: dict = {k: (list(v[0]) if isinstance(v[0], list) else v[0]) for k, v in SPEC.items()}


def validate(key: str, value):
    if key not in SPEC:
        raise ValueError(f"impostazione sconosciuta: {key}")
    default, kind, rule = SPEC[key]
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{key}: atteso true/false")
    elif kind == "int":
        if isinstance(value, bool) or not isinstance(value, int) or not rule[0] <= value <= rule[1]:
            raise ValueError(f"{key}: atteso un intero tra {rule[0]} e {rule[1]}")
    elif kind in ("str", "secret"):
        if not isinstance(value, str) or (rule and len(value) > rule[1]):
            raise ValueError(f"{key}: testo non valido")
        value = value.strip()
        if key == "user_agent" and not value:
            raise ValueError("user_agent non può essere vuoto")
        if key == "proxy" and value and not value.startswith(("http://", "https://", "socks5://", "socks5h://")):
            raise ValueError("proxy deve iniziare con http://, https://, socks5:// o socks5h://")
        if key == "ai_base_url" and value and not value.startswith(("http://", "https://")):
            raise ValueError("ai_base_url deve iniziare con http:// o https://")
    elif kind == "choice":
        if value not in rule:
            raise ValueError(f"{key}: uno tra {', '.join(rule)}")
    elif kind == "list":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value) or len(value) > 1000:
            raise ValueError(f"{key}: atteso un elenco di nomi")
        if key == "ignored_domains":  # normalise: lower case, no '@', no blanks, no duplicates
            value = list(dict.fromkeys(x.strip().lstrip("@").lower().rstrip(".") for x in value if x.strip()))
    return value


def load(db) -> None:
    for k, raw in db.settings_rows():
        if k in SPEC:
            try:
                CFG[k] = validate(k, json.loads(raw))
            except ValueError:
                pass  # a stale/invalid stored value falls back to the default
    apply()


def update(db, patch: dict) -> None:
    clean = {k: validate(k, v) for k, v in patch.items()}  # all-or-nothing
    for k, v in clean.items():
        db.set_setting(k, json.dumps(v))
        CFG[k] = v
    apply()


def public() -> dict:
    """Settings for the UI: secrets are never sent back, only a hint that one is set."""
    return {
        "values": {k: v for k, v in CFG.items() if k not in SECRETS},
        "secrets": {k: ("••••" + CFG[k][-4:] if len(CFG[k]) > 4 else "••••") if CFG[k] else "" for k in SECRETS},
    }


def apply() -> None:
    """Push settings into the modules that cache them (shared HTTP kwargs, concurrency limit)."""
    from .collectors.domain import HTTP
    from . import runner
    HTTP["timeout"] = CFG["http_timeout"]
    HTTP["headers"] = {"User-Agent": CFG["user_agent"]}
    if CFG["proxy"]:
        HTTP["proxy"] = CFG["proxy"]
    else:
        HTTP.pop("proxy", None)
    runner.set_concurrency(CFG["concurrency"])


def is_ignored_domain(domain: str) -> bool:
    """True for a domain (or any subdomain of one) the user does not want traced automatically."""
    d = domain.lower().rstrip(".")
    return any(d == x or d.endswith("." + x) for x in CFG["ignored_domains"])
