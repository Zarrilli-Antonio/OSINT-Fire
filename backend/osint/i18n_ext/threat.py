# Italian canonical text -> (English, Spanish, German); '{}' copies a value through. Merged into the tables of osint/i18n.py.
TYPES: dict = {}
RELS: dict = {
    "listato_in": ("listed_in", "listado_en", "gelistet_in"),
    "punteggio_cvss": ("cvss_score", "puntuación_cvss", "cvss_bewertung"),
    "pubblicata_il": ("published_on", "publicada_el", "veröffentlicht_am"),
    "debolezza": ("weakness", "debilidad", "schwäche"),
    "riferimento": ("reference", "referencia", "referenz"),
    "stato_sfruttamento": ("exploitation_status", "estado_de_explotación", "ausnutzungsstatus"),
    "colpisce_prodotto": ("affects_product", "afecta_al_producto", "betrifft_produkt"),
    "aggiunta_al_catalogo_il": ("added_to_catalogue_on", "añadida_al_catálogo_el", "zum_katalog_hinzugefügt_am"),
    "probabilità_sfruttamento": ("exploitation_probability", "probabilidad_de_explotación", "ausnutzungswahrscheinlichkeit"),
}
REASONS: dict = {
    "presente nella lista pubblica {}": ("present in the public list {}", "presente en la lista pública {}", "in der öffentlichen Liste {} enthalten"),
    "punteggio CVSS pubblicato da NVD": ("CVSS score published by NVD", "puntuación CVSS publicada por NVD", "von NVD veröffentlichte CVSS-Bewertung"),
    "data di pubblicazione in NVD": ("publication date in NVD", "fecha de publicación en NVD", "Veröffentlichungsdatum in NVD"),
    "debolezza (CWE) indicata in NVD": ("weakness (CWE) listed in NVD", "debilidad (CWE) indicada en NVD", "in NVD genannte Schwäche (CWE)"),
    "riferimento nella scheda NVD": ("reference in the NVD entry", "referencia en la ficha de NVD", "Referenz im NVD-Eintrag"),
    "presente nel catalogo CISA Known Exploited Vulnerabilities": ("listed in the CISA Known Exploited Vulnerabilities catalogue", "presente en el catálogo CISA Known Exploited Vulnerabilities", "im CISA-Katalog Known Exploited Vulnerabilities enthalten"),
    "prodotto indicato nel catalogo CISA KEV": ("product named in the CISA KEV catalogue", "producto indicado en el catálogo CISA KEV", "im CISA-KEV-Katalog genanntes Produkt"),
    "riferimento nel catalogo CISA KEV": ("reference in the CISA KEV catalogue", "referencia en el catálogo CISA KEV", "Referenz im CISA-KEV-Katalog"),
    "probabilità di sfruttamento stimata da EPSS (FIRST)": ("exploitation probability estimated by EPSS (FIRST)", "probabilidad de explotación estimada por EPSS (FIRST)", "von EPSS (FIRST) geschätzte Ausnutzungswahrscheinlichkeit"),
}
VALUES: dict = {
    "feed: {}": ("feed: {}", "feed: {}", "Feed: {}"),
    "CVSS {}: {}": ("CVSS {}: {}", "CVSS {}: {}", "CVSS {}: {}"),
    "critica": ("critical", "crítica", "kritisch"), "alta": ("high", "alta", "hoch"), "media": ("medium", "media", "mittel"),
    "bassa": ("low", "baja", "niedrig"), "nessuna": ("none", "ninguna", "keine"),
    "sfruttata attivamente (CISA KEV)": ("actively exploited (CISA KEV)", "explotada activamente (CISA KEV)", "aktiv ausgenutzt (CISA KEV)"),
    "usata in campagne ransomware (CISA KEV)": ("used in ransomware campaigns (CISA KEV)", "usada en campañas de ransomware (CISA KEV)", "in Ransomware-Kampagnen genutzt (CISA KEV)"),
    "EPSS {}% (percentile {})": ("EPSS {}% (percentile {})", "EPSS {}% (percentil {})", "EPSS {}% (Perzentil {})"),
}
