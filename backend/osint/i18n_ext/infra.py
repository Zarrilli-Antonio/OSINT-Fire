# Italian canonical text -> (English, Spanish, German); '{}' copies a value through. Merged into the tables of osint/i18n.py.
TYPES: dict = {}
RELS: dict = {
    "menzionato_in": ("mentioned in", "mencionado en", "erwähnt in"), "contatto_abuso": ("abuse contact", "contacto de abusos", "Abuse-Kontakt"),
    "annuncia_prefisso": ("announces prefix", "anuncia el prefijo", "kündigt Präfix an"), "contatto_noc": ("NOC contact", "contacto NOC", "NOC-Kontakt"),
    "popolarita": ("popularity", "popularidad", "Beliebtheit"), "valutazione_sicurezza_web": ("web security grade", "calificación de seguridad web", "Web-Sicherheitsbewertung"),
    "in_blocklist": ("listed in blocklist", "en lista de bloqueo", "auf Sperrliste"), "usa_nameserver": ("uses nameserver", "usa servidor de nombres", "nutzt Nameserver"),
    "server_posta": ("mail server", "servidor de correo", "Mailserver"),
}
_PDNS = ("Robtex passive DNS (may be historical)", "DNS pasivo de Robtex (puede ser histórico)", "Robtex-Passiv-DNS (möglicherweise historisch)")
REASONS: dict = {
    "indicatore in un report AlienVault OTX": ("indicator in an AlienVault OTX report", "indicador en un informe de AlienVault OTX", "Indikator in einem AlienVault-OTX-Bericht"),
    "DNS passivo Robtex (può essere storico)": _PDNS,
    "DNS passivo Robtex (può essere storico o hosting condiviso)": ("Robtex passive DNS (may be historical or shared hosting)", "DNS pasivo de Robtex (puede ser histórico o alojamiento compartido)", "Robtex-Passiv-DNS (möglicherweise historisch oder Shared Hosting)"),
    "contatto abuse nel registro RIR (RIPEstat)": ("abuse contact in the RIR registry (RIPEstat)", "contacto de abusos en el registro RIR (RIPEstat)", "Abuse-Kontakt im RIR-Register (RIPEstat)"),
    "prefisso annunciato in BGP (RIPEstat)": ("prefix announced in BGP (RIPEstat)", "prefijo anunciado en BGP (RIPEstat)", "in BGP angekündigtes Präfix (RIPEstat)"),
    "titolare dell'ASN (RIPEstat)": ("ASN holder (RIPEstat)", "titular del ASN (RIPEstat)", "ASN-Inhaber (RIPEstat)"),
    "scheda PeeringDB": ("PeeringDB record", "ficha de PeeringDB", "PeeringDB-Eintrag"),
    "sito web nella scheda PeeringDB": ("website in the PeeringDB record", "sitio web en la ficha de PeeringDB", "Website im PeeringDB-Eintrag"),
    "contatto nelle note PeeringDB": ("contact in the PeeringDB notes", "contacto en las notas de PeeringDB", "Kontakt in den PeeringDB-Notizen"),
    "posizione {} nella classifica Tranco": ("rank {} in the Tranco list", "posición {} en la lista Tranco", "Rang {} in der Tranco-Liste"),
    "intestazioni di sicurezza HTTP, punteggio {}": ("HTTP security headers, score {}", "cabeceras de seguridad HTTP, puntuación {}", "HTTP-Sicherheitsheader, Punktzahl {}"),
    "presente in {}": ("listed in {}", "presente en {}", "gelistet in {}"),
    "hash del favicon (cercabile su Shodan: http.favicon.hash)": ("favicon hash (searchable on Shodan: http.favicon.hash)", "hash del favicon (buscable en Shodan: http.favicon.hash)", "Favicon-Hash (bei Shodan suchbar: http.favicon.hash)"),
}
VALUES: dict = {}
