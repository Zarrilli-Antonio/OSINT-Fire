import asyncio
import re
from urllib.parse import urlparse

import dns.asyncresolver
import dns.exception
import httpx

from ..models import Finding
from . import collector

HTTP = {"timeout": 15, "headers": {"User-Agent": "OSINT-Fire/0.1"}}
MAX_SUBDOMAINS = 200


@collector("dns", "Dominio")
async def dns_records(domain: str) -> list[Finding]:
    out = []
    for rtype, rel, dst_type in (("A", "risolve_a", "IP"), ("AAAA", "risolve_a", "IP"),
                                 ("NS", "nameserver", "Dominio"), ("MX", "mail_server", "Dominio")):
        try:
            answer = await dns.asyncresolver.resolve(domain, rtype, lifetime=8)
        except (dns.exception.DNSException, OSError):
            continue
        for r in answer:
            val = r.exchange.to_text() if rtype == "MX" else r.to_text()
            if val in ("", "."):  # null MX
                continue
            out.append(Finding(("Dominio", domain), rel, (dst_type, val), 0.95, f"record DNS {rtype}",
                               raw={"type": rtype, "value": val}, pivot=dst_type == "IP"))
    return out


@collector("crtsh", "Dominio")
async def crtsh(domain: str) -> list[Finding]:
    # wildcard query is often overloaded (404/502); fall back to the exact-name query, whose SANs often list subdomains
    async with httpx.AsyncClient(**{**HTTP, "timeout": 60}) as c:
        for q in (f"%.{domain}", domain):
            url = f"https://crt.sh/?q={q}&output=json"
            r = await c.get(url)
            if r.status_code == 200:
                break
        else:
            r.raise_for_status()
            return []
    names = set()
    for row in r.json():
        for n in row["name_value"].splitlines():
            n = n.strip().lower().lstrip("*.")
            if n.endswith("." + domain):
                names.add(n)
    return [Finding(("Dominio", domain), "sottodominio", ("Dominio", n), 0.9, "certificato TLS pubblico", url=url)
            for n in sorted(names)[:MAX_SUBDOMAINS]]


EVENTS = {"registration": "registrazione", "expiration": "scadenza", "last changed": "ultima modifica", "transfer": "trasferimento"}


def parse_rdap_domain(domain: str, d: dict, url: str) -> list[Finding]:
    me, out = ("Dominio", domain), []
    for ent in d.get("entities", []):
        roles = ",".join(ent.get("roles", []))
        for item in ent.get("vcardArray", [None, []])[1]:
            if item[0] == "email" and "@" in str(item[3]):
                out.append(Finding(me, "contatto_registrazione", ("Email", item[3]), 0.8, f"RDAP ruolo {roles}", url=url))
            elif item[0] == "fn" and item[3] and "registrar" in ent.get("roles", []):
                out.append(Finding(me, "registrar", ("Azienda", item[3]), 0.95, "registrar nel registro RDAP", url=url, pivot=False))
            elif item[0] == "org" and item[3] and "registrant" in ent.get("roles", []):
                org = item[3][0] if isinstance(item[3], list) else item[3]
                if org and "redacted" not in str(org).lower():
                    out.append(Finding(me, "intestatario", ("Azienda", org), 0.85, "organizzazione intestataria (RDAP)", url=url, pivot=False))
    for ev in d.get("events", []):
        if (what := EVENTS.get(ev.get("eventAction", ""))) and ev.get("eventDate"):
            out.append(Finding(me, "evento_dominio", ("Data", f"{what}: {ev['eventDate'][:10]}"), 0.95, "evento nel registro RDAP", url=url, pivot=False))
    for st in d.get("status", []):
        out.append(Finding(me, "stato_dominio", ("Servizio", f"stato dominio: {st}"), 0.9, "stato EPP nel registro RDAP", url=url, pivot=False))
    return out


@collector("rdap", "Dominio")
async def rdap(domain: str) -> list[Finding]:
    url = f"https://rdap.org/domain/{domain}"
    async with httpx.AsyncClient(follow_redirects=True, **HTTP) as c:
        r = await c.get(url)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_rdap_domain(domain, r.json(), url)


def wayback_hosts(rows: list, domain: str) -> set[str]:
    hosts = set()
    for (original,) in rows[1:]:  # first row is the header
        host = (urlparse(original).hostname or "").lower().rstrip(".")
        if host.endswith("." + domain):
            hosts.add(host)
    return hosts


@collector("wayback", "Dominio")
async def wayback(domain: str) -> list[Finding]:
    params = {"url": domain, "matchType": "domain", "output": "json", "fl": "original", "collapse": "urlkey",
              "limit": 3000, "filter": "original:^https?://[^/:]+\\." + re.escape(domain) + "[:/].*"}  # subdomains only
    async with httpx.AsyncClient(**{**HTTP, "timeout": 45}) as c:
        r = await c.get("https://web.archive.org/cdx/search/cdx", params=params)
    r.raise_for_status()
    rows = r.json() if r.text.strip() else []
    return [Finding(("Dominio", domain), "sottodominio", ("Dominio", h), 0.7, "URL archiviato su Wayback Machine",
                    url=str(r.url)) for h in sorted(wayback_hosts(rows, domain))[:MAX_SUBDOMAINS]]


def parse_mail_dns(domain: str, spf: list[str], dmarc: list[str]) -> list[Finding]:
    """SPF -> mail providers and sender IPs; DMARC report addresses -> contact emails."""
    out = []
    for txt in spf:
        if not txt.lower().startswith("v=spf1"):
            continue
        for tok in txt.split()[1:]:
            tok = tok.lstrip("+")
            if tok.startswith("include:"):
                out.append(Finding(("Dominio", domain), "usa_servizio_email", ("Servizio", tok[8:].lower()), 0.9,
                                   "record SPF include", raw={"spf": txt}, pivot=False))
            elif tok.startswith(("ip4:", "ip6:")) and "/" not in tok:
                out.append(Finding(("Dominio", domain), "ip_autorizzato_mail", ("IP", tok[4:]), 0.8, "record SPF",
                                   raw={"spf": txt}))
    for txt in dmarc:
        if not txt.lower().startswith("v=dmarc1"):
            continue
        for tag in re.findall(r"\b(?:rua|ruf)=([^;]+)", txt, flags=re.I):
            for m in re.findall(r"mailto:([^,;\s!]+)", tag, flags=re.I):
                out.append(Finding(("Dominio", domain), "contatto_dmarc", ("Email", m), 0.85, "indirizzo report DMARC",
                                   raw={"dmarc": txt}))
    return out


async def _txt(name: str) -> list[str]:
    try:
        answer = await dns.asyncresolver.resolve(name, "TXT", lifetime=8)
    except (dns.exception.DNSException, OSError):
        return []
    return [b"".join(r.strings).decode(errors="ignore") for r in answer]


@collector("dns_mail", "Dominio")
async def dns_mail(domain: str) -> list[Finding]:
    return parse_mail_dns(domain, await _txt(domain), await _txt(f"_dmarc.{domain}"))


# TXT prefix -> service the domain owner verified/uses
TXT_SERVICES = {
    "google-site-verification=": "Google (Search Console / Workspace)", "ms=": "Microsoft 365",
    "facebook-domain-verification=": "Meta Business", "atlassian-domain-verification=": "Atlassian",
    "docusign=": "DocuSign", "stripe-verification=": "Stripe", "zoom-domain-verification=": "Zoom",
    "adobe-idp-site-verification=": "Adobe", "apple-domain-verification=": "Apple Business",
    "have-i-been-pwned-verification=": "Have I Been Pwned", "onetrust-domain-verification=": "OneTrust",
    "mongodb-site-verification=": "MongoDB Atlas", "globalsign-domain-verification=": "GlobalSign",
    "slack-domain-verification=": "Slack", "dropbox-domain-verification=": "Dropbox",
    "shopify-verification-code=": "Shopify", "hubspot-developer-verification=": "HubSpot",
    "cisco-ci-domain-verification=": "Cisco", "miro-verification=": "Miro", "figma-domain-verification=": "Figma",
}


def parse_dns_extra(domain: str, soa: list[str], caa: list[str], txt: list[str]) -> list[Finding]:
    me, out = ("Dominio", domain), []
    for rec in soa:  # "ns1.x.com. hostmaster.x.com. serial ..." -> responsible mailbox
        parts = rec.split()
        if len(parts) >= 2 and "." in parts[1].rstrip("."):
            local, _, host = parts[1].rstrip(".").partition(".")
            out.append(Finding(me, "contatto_soa", ("Email", f"{local}@{host}".lower()), 0.55, "campo RNAME del record SOA"))
    for rec in caa:
        if m := re.search(r'issue(?:wild)?\s+"?([^";\s]+)', rec):
            out.append(Finding(me, "autorita_certificati", ("Servizio", f"CA: {m.group(1).lower()}"), 0.9, "record CAA", pivot=False))
    for t in txt:
        for prefix, service in TXT_SERVICES.items():
            if t.lower().startswith(prefix):
                out.append(Finding(me, "usa_servizio", ("Servizio", service), 0.85, f"record TXT di verifica ({prefix.rstrip('=')})",
                                   pivot=False))
    return out


async def _records(name: str, rtype: str) -> list[str]:
    try:
        return [r.to_text() for r in await dns.asyncresolver.resolve(name, rtype, lifetime=8)]
    except (dns.exception.DNSException, OSError):
        return []


@collector("dns_extra", "Dominio")
async def dns_extra(domain: str) -> list[Finding]:
    return parse_dns_extra(domain, await _records(domain, "SOA"), await _records(domain, "CAA"), await _txt(domain))


# substring of a DNS target -> technology/provider it reveals
MX_PROVIDERS = {"google.com": "Google Workspace", "googlemail.com": "Google Workspace", "outlook.com": "Microsoft 365",
                "protonmail.ch": "Proton Mail", "zoho.": "Zoho Mail", "mimecast": "Mimecast (sicurezza email)",
                "pphosted": "Proofpoint (sicurezza email)", "yahoodns": "Yahoo Mail", "secureserver.net": "GoDaddy Email",
                "ovh.net": "OVH Email", "aruba": "Aruba Email", "register.it": "Register.it Email", "mailgun": "Mailgun",
                "icloud.com": "iCloud Mail", "fastmail": "Fastmail", "ionos": "IONOS Email", "libero.it": "Libero Mail"}
NS_PROVIDERS = {"cloudflare.com": "Cloudflare", "awsdns": "AWS Route 53", "azure-dns": "Azure DNS", "googledomains": "Google Domains",
                "domaincontrol.com": "GoDaddy DNS", "registrar-servers.com": "Namecheap DNS", "ovh.net": "OVH DNS",
                "aruba": "Aruba DNS", "ui-dns": "IONOS DNS", "nsone.net": "NS1", "akam.net": "Akamai DNS", "dnsimple": "DNSimple",
                "godaddy": "GoDaddy DNS", "register.it": "Register.it DNS", "gandi.net": "Gandi", "hetzner": "Hetzner DNS"}
WEB_PROVIDERS = {"cloudfront.net": "AWS CloudFront", "github.io": "GitHub Pages", "herokuapp.com": "Heroku", "herokudns.com": "Heroku",
                 "netlify": "Netlify", "vercel": "Vercel", "azurewebsites.net": "Azure App Service", "fastly.net": "Fastly",
                 "pages.dev": "Cloudflare Pages", "wixdns.net": "Wix", "squarespace": "Squarespace", "myshopify.com": "Shopify",
                 "wordpress.com": "WordPress.com", "ghost.io": "Ghost", "readme.io": "ReadMe", "pantheonsite.io": "Pantheon",
                 "elb.amazonaws.com": "AWS Load Balancer", "trafficmanager.net": "Azure Traffic Manager"}


def fingerprint(domain: str, mx: list[str], ns: list[str], cname: list[str]) -> list[Finding]:
    out = []
    for kind, targets, table in (("email", mx, MX_PROVIDERS), ("dns", ns, NS_PROVIDERS), ("hosting", cname, WEB_PROVIDERS)):
        found = {name for t in targets for key, name in table.items() if key in t.lower()}
        for name in sorted(found):
            out.append(Finding(("Dominio", domain), f"usa_{kind}", ("Tecnologia", name), 0.85, f"dedotto dai record DNS ({kind})", pivot=False))
    return out


@collector("infra_fingerprint", "Dominio")
async def infra_fingerprint(domain: str) -> list[Finding]:
    mx, ns = await _records(domain, "MX"), await _records(domain, "NS")
    cname = await _records(f"www.{domain}", "CNAME") + await _records(domain, "CNAME")
    return fingerprint(domain, mx, ns, cname)


WORDLIST = ("www mail webmail smtp imap pop pop3 ftp sftp vpn remote portal intranet extranet dev test staging stage beta demo "
            "api app apps admin cpanel panel dashboard login sso auth id accounts shop store blog news forum support help docs wiki "
            "status monitor git gitlab jenkins ci cdn static assets media img images files download downloads upload backup db sql "
            "mysql ns1 ns2 mx mx1 autodiscover owa exchange crm erp m mobile secure office cloud proxy gateway uat prod").split()


@collector("dns_wordlist", "Dominio", active=True)
async def dns_wordlist(domain: str) -> list[Finding]:
    """Active but light: ~100 A-record lookups of common subdomain names. Skipped if the zone has a wildcard."""
    import uuid
    if await _records(f"zz-{uuid.uuid4().hex[:12]}.{domain}", "A"):
        return []  # wildcard DNS: every name resolves, results would be noise
    sem = asyncio.Semaphore(20)

    async def one(label: str):
        async with sem:
            return label, await _records(f"{label}.{domain}", "A")

    out = []
    for label, ips in await asyncio.gather(*(one(w) for w in WORDLIST)):
        if ips:
            host = f"{label}.{domain}"
            out.append(Finding(("Dominio", domain), "sottodominio", ("Dominio", host), 0.85, "nome comune che risolve (wordlist DNS)"))
            out += [Finding(("Dominio", host), "risolve_a", ("IP", ip), 0.9, "record DNS A", pivot=False) for ip in ips[:3]]
    return out


# DKIM selector -> email sending service. A published selector means the domain sends mail through that service.
DKIM_SELECTORS = {"google": "Google Workspace", "selector1": "Microsoft 365", "selector2": "Microsoft 365", "k1": "Mailchimp", "k2": "Mailchimp",
                  "k3": "Mailchimp", "mandrill": "Mandrill", "s1": "SendGrid", "s2": "SendGrid", "smtpapi": "SendGrid", "pm": "Postmark",
                  "mailjet": "Mailjet", "zendesk1": "Zendesk", "zendesk2": "Zendesk", "sig1": "iCloud Mail", "protonmail": "Proton Mail",
                  "mxvault": "MX Vault", "amazonses": "Amazon SES", "cm": "Campaign Monitor", "krs": "Klaviyo", "hs1": "HubSpot", "hs2": "HubSpot"}


def parse_mail_services(domain: str, dkim: dict[str, list[str]], tlsrpt: list[str], mtasts: list[str]) -> list[Finding]:
    me, out = ("Dominio", domain), []
    for sel in sorted(s for s, recs in dkim.items() if recs):
        out.append(Finding(me, "usa_servizio_email", ("Servizio", DKIM_SELECTORS[sel]), 0.8, f"selettore DKIM '{sel}' pubblicato", pivot=False))
    for txt in tlsrpt:
        for m in re.findall(r"mailto:([^,;\s]+)", txt, flags=re.I):
            out.append(Finding(me, "contatto_tlsrpt", ("Email", m.lower()), 0.8, "indirizzo report TLS-RPT"))
    if any(t.lower().startswith("v=stsv1") for t in mtasts):
        out.append(Finding(me, "usa_mta_sts", ("Servizio", "MTA-STS attivo"), 0.8, "record _mta-sts", pivot=False))
    return out


@collector("dns_mail_services", "Dominio")
async def dns_mail_services(domain: str) -> list[Finding]:
    async def sel(s):
        return s, await _records(f"{s}._domainkey.{domain}", "TXT") or await _records(f"{s}._domainkey.{domain}", "CNAME")

    dkim = dict(await asyncio.gather(*(sel(s) for s in DKIM_SELECTORS)))
    return parse_mail_services(domain, dkim, await _txt(f"_smtp._tls.{domain}"), await _txt(f"_mta-sts.{domain}"))
