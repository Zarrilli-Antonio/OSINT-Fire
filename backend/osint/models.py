import re
from dataclasses import dataclass, field

# Entity types. PIVOT = types that are re-queried by other collectors.
PIVOT = {"Dominio", "Email", "Username", "IP", "Telefono", "Portafoglio", "Vulnerabilità"}


_ETH = re.compile(r"^0x[0-9a-fA-F]{40}$")


def wallet_kind(v: str) -> str | None:
    """'btc' | 'eth' | None. Bitcoin base58 is case-sensitive, so the legacy form is matched exactly; bech32 is all one case."""
    if _ETH.match(v):
        return "eth"
    if re.match(r"^[13][1-9A-HJ-NP-Za-km-z]{25,34}$", v) or re.match(r"^bc1[ac-hj-np-z02-9]{11,87}$", v.lower()):
        return "btc"
    return None


def norm(type_: str, value: str) -> str:
    v = value.strip()
    if type_ in {"Dominio", "Email", "Username"}:
        v = v.lower()
    if type_ == "Portafoglio" and _ETH.match(v) or type_ == "Portafoglio" and v.lower().startswith("bc1"):
        v = v.lower()
    if type_ == "Vulnerabilità":
        v = v.upper()
    if type_ == "Dominio":
        v = v.rstrip(".")
    if type_ == "Telefono":
        v = re.sub(r"[^\d+]", "", v)
        v = "+" + v[2:] if v.startswith("00") else v
    return v


@dataclass
class Finding:
    """One edge src --rel--> dst with its evidence. Entities are derived from it."""
    src: tuple[str, str]
    rel: str
    dst: tuple[str, str]
    conf: float
    reason: str
    url: str = ""
    raw: dict = field(default_factory=dict)
    pivot: bool = True  # False = infrastructure of a third party, do not follow
