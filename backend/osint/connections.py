"""'Test connection' for every credential the user can set: one cheap authenticated call, with a clear message."""
import httpx

from . import ai
from .collectors.connected import reddit_token, spotify_token, twitch_token
from .collectors.keyed import client
from .settings import CFG

# provider id -> settings keys it needs
PROVIDERS = {
    "github": ("github_token",), "reddit": ("reddit_client_id", "reddit_client_secret"), "twitch": ("twitch_client_id", "twitch_client_secret"),
    "youtube": ("youtube_key",), "spotify": ("spotify_client_id", "spotify_client_secret"), "x": ("x_bearer",),
    "companieshouse": ("companieshouse_key",), "greynoise": ("greynoise_key",), "otx": ("otx_key",), "abusech": ("abusech_key",),
    "virustotal": ("virustotal_key",), "shodan": ("shodan_key",), "hunter": ("hunter_key",), "hibp": ("hibp_key",),
    "securitytrails": ("securitytrails_key",), "abuseipdb": ("abuseipdb_key",), "ai": (),
}


def verdict(status: int, ok_codes=(200,), what: str = "") -> tuple[bool, str]:
    if status in ok_codes:
        return True, "collegato" + (f": {what}" if what else "")
    if status in (401, 403):
        return False, f"credenziali rifiutate ({status}) o piano senza accesso a questa API"
    if status == 429:
        return False, "limite di richieste raggiunto, riprova tra poco"
    return False, f"risposta inattesa ({status})"


async def test(provider: str) -> tuple[bool, str]:
    if provider not in PROVIDERS:
        raise KeyError(provider)
    if provider != "ai" and any(not CFG[k] for k in PROVIDERS[provider]):
        return False, "credenziali non impostate"
    try:
        return await _test(provider)
    except httpx.HTTPError as e:
        return False, f"connessione fallita: {e!r}"
    except Exception as e:  # token flows raise RuntimeError with the provider's message
        return False, str(e)


async def _test(p: str) -> tuple[bool, str]:
    if p == "ai":
        async with httpx.AsyncClient(timeout=60) as c:
            try:
                await ai.complete(c, "Rispondi solo con la parola ok.", "ping", 8)
            except ai.AIError as e:
                return False, str(e)
        return True, f"collegato: {CFG['ai_provider']} · {CFG['ai_model']}"
    if p == "reddit":
        await reddit_token()
        return True, "collegato (autenticazione app riuscita)"
    if p == "twitch":
        await twitch_token()
        return True, "collegato (autenticazione app riuscita)"
    if p == "spotify":
        await spotify_token()
        return True, "collegato (autenticazione app riuscita)"
    async with client({}) as c:
        if p == "github":
            r = await c.get("https://api.github.com/user", headers={"Authorization": f"Bearer {CFG['github_token']}"})
            return verdict(r.status_code, what=r.json().get("login", "") if r.status_code == 200 else "")
        if p == "youtube":
            r = await c.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "id", "forHandle": "@YouTube", "key": CFG["youtube_key"]})
            return verdict(r.status_code if r.status_code != 400 else 403)
        if p == "x":
            r = await c.get("https://api.x.com/2/users/by/username/x", headers={"Authorization": f"Bearer {CFG['x_bearer']}"})
            return verdict(r.status_code if r.status_code != 402 else 403)
        if p == "companieshouse":
            r = await c.get("https://api.company-information.service.gov.uk/search/companies", params={"q": "test", "items_per_page": 1}, auth=(CFG["companieshouse_key"], ""))
            return verdict(r.status_code)
        if p == "greynoise":
            r = await c.get("https://api.greynoise.io/v3/community/8.8.8.8", headers={"key": CFG["greynoise_key"]})
            return verdict(r.status_code, (200, 404))
        if p == "otx":
            r = await c.get("https://otx.alienvault.com/api/v1/users/me", headers={"X-OTX-API-KEY": CFG["otx_key"]})
            return verdict(r.status_code)
        if p == "abusech":
            r = await c.post("https://urlhaus-api.abuse.ch/v1/host/", data={"host": "example.com"}, headers={"Auth-Key": CFG["abusech_key"]})
            return verdict(r.status_code)
        if p == "virustotal":
            r = await c.get("https://www.virustotal.com/api/v3/domains/example.com", headers={"x-apikey": CFG["virustotal_key"]})
            return verdict(r.status_code)
        if p == "shodan":
            r = await c.get("https://api.shodan.io/api-info", params={"key": CFG["shodan_key"]})
            return verdict(r.status_code, what=f"{r.json().get('query_credits', '?')} crediti" if r.status_code == 200 else "")
        if p == "hunter":
            r = await c.get("https://api.hunter.io/v2/account", params={"api_key": CFG["hunter_key"]})
            return verdict(r.status_code)
        if p == "hibp":
            r = await c.get("https://haveibeenpwned.com/api/v3/subscription/status", headers={"hibp-api-key": CFG["hibp_key"]})
            return verdict(r.status_code)
        if p == "securitytrails":
            r = await c.get("https://api.securitytrails.com/v1/ping", headers={"APIKEY": CFG["securitytrails_key"]})
            return verdict(r.status_code)
        if p == "abuseipdb":
            r = await c.get("https://api.abuseipdb.com/api/v2/check", params={"ipAddress": "8.8.8.8"}, headers={"Key": CFG["abuseipdb_key"], "Accept": "application/json"})
            return verdict(r.status_code)
    return False, "provider sconosciuto"
