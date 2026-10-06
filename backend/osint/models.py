import re
from dataclasses import dataclass, field

# Entity types. PIVOT = types that are re-queried by other collectors.
PIVOT = {"Dominio", "Email", "Username", "IP", "Telefono"}


def norm(type_: str, value: str) -> str:
    v = value.strip()
    if type_ in {"Dominio", "Email", "Username"}:
        v = v.lower()
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
