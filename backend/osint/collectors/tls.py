import asyncio
import socket
import ssl

import certifi

from ..models import Finding
from . import collector

MAX_SAN = 50


def _fetch(domain: str) -> dict:
    ctx = ssl.create_default_context(cafile=certifi.where())  # a frozen Python has no system CA path
    with socket.create_connection((domain, 443), timeout=8) as s, ctx.wrap_socket(s, server_hostname=domain) as t:
        return t.getpeercert()


def parse_cert(domain: str, cert: dict) -> list[Finding]:
    me, out = ("Dominio", domain), []
    subj = {k: v for rdn in cert.get("subject", ()) for k, v in rdn}
    issuer = {k: v for rdn in cert.get("issuer", ()) for k, v in rdn}
    if subj.get("organizationName"):  # only OV/EV certificates carry the organisation
        out.append(Finding(me, "organizzazione_certificato", ("Azienda", subj["organizationName"]), 0.85, "campo O del certificato TLS", pivot=False))
    if subj.get("localityName") or subj.get("countryName"):
        place = ", ".join(x for x in (subj.get("localityName"), subj.get("stateOrProvinceName"), subj.get("countryName")) if x)
        out.append(Finding(me, "luogo_certificato", ("Luogo", place), 0.7, "luogo nel certificato TLS", pivot=False))
    if issuer.get("organizationName"):
        out.append(Finding(me, "emesso_da", ("Servizio", f"CA: {issuer['organizationName']}"), 0.9, "emittente del certificato", pivot=False))
    sans = sorted({v.lstrip("*.").lower() for k, v in cert.get("subjectAltName", ()) if k == "DNS"} - {domain})
    shared = len(sans) > MAX_SAN // 2  # large SAN lists are CDN/shared certificates: list them but do not follow
    for san in sans[:MAX_SAN]:
        out.append(Finding(me, "stesso_certificato", ("Dominio", san), 0.8, "SAN dello stesso certificato TLS", pivot=not shared))
    return out


@collector("tls_cert", "Dominio", active=True)
async def tls_cert(domain: str) -> list[Finding]:
    try:
        cert = await asyncio.to_thread(_fetch, domain)
    except (OSError, ssl.SSLError):
        return []  # no HTTPS, or a certificate that does not validate
    return parse_cert(domain, cert)
