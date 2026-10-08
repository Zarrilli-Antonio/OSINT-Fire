"""Translation tables added by the extra source modules (same format as the tables in ../i18n.py)."""
# Italian canonical text -> (English, Spanish, German); '{}' copies a value through. Merged into the tables of osint/i18n.py.
TYPES: dict = {}
RELS: dict = {
    "autore_di": ("author of", "autor de", "Autor von"), "collaboratore": ("collaborator", "colaborador", "Mitarbeiter"), "affiliato_a": ("affiliated with", "afiliado a", "angehörig bei"),
}
_N = ("name match (possible namesake)", "coincidencia de nombre (posible homónimo)", "Namensübereinstimmung (möglicher Namensvetter)")
REASONS: dict = {
    "autore su {}: corrispondenza sul nome (omonimia possibile)": ("author on {}: name match (possible namesake)", "autor en {}: coincidencia de nombre (posible homónimo)", "Autor bei {}: Namensübereinstimmung (möglicher Namensvetter)"),
    "coautore su {}: corrispondenza sul nome (omonimia possibile)": ("co-author on {}: name match (possible namesake)", "coautor en {}: coincidencia de nombre (posible homónimo)", "Koautor bei {}: Namensübereinstimmung (möglicher Namensvetter)"),
    "affiliazione su {}: corrispondenza sul nome (omonimia possibile)": ("affiliation on {}: name match (possible namesake)", "afiliación en {}: coincidencia de nombre (posible homónimo)", "Zugehörigkeit bei {}: Namensübereinstimmung (möglicher Namensvetter)"),
    "ORCID iD indicato su {} (Crossref): corrispondenza sul nome (omonimia possibile)": ("ORCID iD given on {} (Crossref): name match (possible namesake)", "ORCID iD indicado en {} (Crossref): coincidencia de nombre (posible homónimo)", "ORCID iD angegeben bei {} (Crossref): Namensübereinstimmung (möglicher Namensvetter)"),
    "ORCID iD indicato su Zenodo: corrispondenza sul nome (omonimia possibile)": ("ORCID iD given on Zenodo: name match (possible namesake)", "ORCID iD indicado en Zenodo: coincidencia de nombre (posible homónimo)", "ORCID iD bei Zenodo angegeben: Namensübereinstimmung (möglicher Namensvetter)"),
    "ORCID indicato nel profilo INSPIRE-HEP": ("ORCID given in the INSPIRE-HEP profile", "ORCID indicado en el perfil de INSPIRE-HEP", "ORCID im INSPIRE-HEP-Profil angegeben"),
    "identificativo DBLP indicato da Semantic Scholar": ("DBLP identifier given by Semantic Scholar", "identificador DBLP indicado por Semantic Scholar", "DBLP-Kennung von Semantic Scholar angegeben"),
    "pagina personale indicata su Semantic Scholar": ("personal page given on Semantic Scholar", "página personal indicada en Semantic Scholar", "persönliche Seite bei Semantic Scholar angegeben"),
    "repository di codice sorgente archiviato in Software Heritage (stesso nome utente)": ("source-code repository archived in Software Heritage (same username)", "repositorio de código fuente archivado en Software Heritage (mismo nombre de usuario)", "in Software Heritage archiviertes Quellcode-Repository (gleicher Benutzername)"),
}
VALUES: dict = {}
