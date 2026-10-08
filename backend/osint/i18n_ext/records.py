# Italian canonical text -> (English, Spanish, German); '{}' copies a value through. Merged into the tables of osint/i18n.py.
TYPES: dict = {}
RELS: dict = {
    "deposito_sec": ("SEC filing", "documento presentado a la SEC", "SEC-Einreichung"),
    "ticker": ("ticker symbol", "símbolo bursátil", "Börsenkürzel"),
    "citato_in_inchiesta": ("named in investigation", "citado en investigación", "in Recherche genannt"),
    "in_lista_sanzioni": ("on sanctions list", "en lista de sanciones", "auf Sanktionsliste"),
    "voce_dbpedia": ("DBpedia entry", "entrada de DBpedia", "DBpedia-Eintrag"),
    "indirizzo_normalizzato": ("normalised address", "dirección normalizada", "normalisierte Adresse"),
    "coordinate": ("coordinates", "coordenadas", "Koordinaten"),
    "opera_nota": ("best-known work", "obra más conocida", "bekanntestes Werk"),
}
REASONS: dict = {
    "iscrizione alla SEC (EDGAR)": ("SEC registration (EDGAR)", "inscripción en la SEC (EDGAR)", "SEC-Registrierung (EDGAR)"),
    "indirizzo commerciale in EDGAR": ("business address in EDGAR", "dirección comercial en EDGAR", "Geschäftsadresse in EDGAR"),
    "sito indicato in EDGAR": ("website listed in EDGAR", "sitio indicado en EDGAR", "in EDGAR angegebene Website"),
    "documento depositato presso la SEC": ("document filed with the SEC", "documento presentado ante la SEC", "bei der SEC eingereichtes Dokument"),
    "beneficiario di fondi federali USA (USAspending)": ("recipient of US federal funds (USAspending)", "beneficiario de fondos federales de EE. UU. (USAspending)", "Empfänger von US-Bundesmitteln (USAspending)"),
    "corrispondenza sul nome, non verificata": ("name match, not verified", "coincidencia de nombre, no verificada", "Namensübereinstimmung, nicht verifiziert"),
    "partita IVA valida nel sistema VIES": ("VAT number valid in the VIES system", "NIF-IVA válido en el sistema VIES", "USt-IdNr. im VIES-System gültig"),
    "ragione sociale in VIES": ("company name in VIES", "razón social en VIES", "Firmenname in VIES"),
    "indirizzo in VIES": ("address in VIES", "dirección en VIES", "Adresse in VIES"),
    "voce DBpedia con lo stesso nome": ("DBpedia entry with the same name", "entrada de DBpedia con el mismo nombre", "DBpedia-Eintrag mit demselben Namen"),
    "indirizzo normalizzato da OpenStreetMap": ("address normalised by OpenStreetMap", "dirección normalizada por OpenStreetMap", "von OpenStreetMap normalisierte Adresse"),
    "coordinate da OpenStreetMap": ("coordinates from OpenStreetMap", "coordenadas de OpenStreetMap", "Koordinaten von OpenStreetMap"),
    "paese da OpenStreetMap": ("country from OpenStreetMap", "país de OpenStreetMap", "Land von OpenStreetMap"),
    "il nome compare in una sentenza USA, solo corrispondenza sul nome": ("the name appears in a US court opinion, name match only", "el nombre aparece en una sentencia de EE. UU., solo coincidencia de nombre", "der Name erscheint in einem US-Urteil, nur Namensübereinstimmung"),
}
VALUES: dict = {
    "sanzioni {}: {}": ("sanctions {}: {}", "sanciones {}: {}", "Sanktionen {}: {}"),
    "ticker {}": ("ticker {}", "símbolo {}", "Kürzel {}"),
}
