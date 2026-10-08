# Italian canonical text -> (English, Spanish, German); '{}' copies a value through. Merged into the tables of osint/i18n.py.
TYPES: dict = {}
RELS: dict = {}
REASONS: dict = {
    "ricerca per nome su Bluesky: possibili omonimi": ("name search on Bluesky: homonyms possible", "búsqueda por nombre en Bluesky: posibles homónimos", "Namenssuche auf Bluesky: Namensvettern möglich"),
}
# 'account <platform> creato: <date>' lines of osint/collectors/more_profiles.py
_PLATFORMS = ("Lobsters", "Scratch", "Packagist", "Matrix", "Tumblr", "Wikipedia", "Wikimedia Commons", "Wikidata", "Duolingo", "Hex.pm", "Lemmy (lemmy.ml)", "Lemmy (lemmy.world)",
              "Lemmy (sh.itjust.works)", "Lemmy (programming.dev)", "Open Library", "Mixcloud", "Dailymotion", "Substack", "Bitbucket", "Gitea", "Framagit",
              "KDE Invent", "Kitsu", "Modrinth", "Misskey", "SourceForge", "LiveJournal", "Neocities", "OpenStreetMap")
VALUES: dict = {f"account {p} creato: {{}}": (f"{p} account created: {{}}", f"cuenta de {p} creada: {{}}", f"{p}-Konto erstellt: {{}}") for p in _PLATFORMS}
