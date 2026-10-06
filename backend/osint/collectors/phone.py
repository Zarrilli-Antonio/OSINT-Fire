import phonenumbers
from phonenumbers import carrier, geocoder, number_type, PhoneNumberType

from ..models import Finding
from . import collector

DEFAULT_REGION = "IT"  # numbers without a +prefix are read as Italian
TYPES = {PhoneNumberType.MOBILE: "cellulare", PhoneNumberType.FIXED_LINE: "linea fissa", PhoneNumberType.FIXED_LINE_OR_MOBILE: "fisso o cellulare",
         PhoneNumberType.TOLL_FREE: "numero verde", PhoneNumberType.VOIP: "VoIP", PhoneNumberType.PREMIUM_RATE: "tariffa premium"}


def parse_phone(raw: str) -> list[Finding]:
    try:
        n = phonenumbers.parse(raw, DEFAULT_REGION)
    except phonenumbers.NumberParseException:
        return []
    if not phonenumbers.is_possible_number(n):
        return []
    me, out = ("Telefono", raw), []
    e164 = phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)
    if e164 != raw:
        out.append(Finding(me, "forma_internazionale", ("Telefono", e164), 1.0, "normalizzazione E.164", pivot=False))
    place = geocoder.description_for_number(n, "it")
    if place:
        out.append(Finding(me, "area_geografica", ("Luogo", place), 0.6, "prefisso telefonico", pivot=False))
    country = geocoder.region_code_for_number(n)
    if country and country != place:
        out.append(Finding(me, "paese", ("Luogo", country), 0.9, "prefisso internazionale", pivot=False))
    op = carrier.name_for_number(n, "it")
    if op:
        out.append(Finding(me, "operatore_originario", ("Azienda", op), 0.5, "operatore del prefisso: la portabilità può averlo cambiato", pivot=False))
    if (t := TYPES.get(number_type(n))):
        out.append(Finding(me, "tipo_linea", ("Servizio", f"tipo linea: {t}"), 0.8, "classificazione del numero", pivot=False))
    return out


@collector("phone_info", "Telefono")
async def phone_info(number: str) -> list[Finding]:
    return parse_phone(number)
