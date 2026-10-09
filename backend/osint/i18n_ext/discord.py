# Discord invites (osint/collectors/more_discord.py). Italian canonical text -> (English, Spanish, German).
TYPES: dict = {}
RELS: dict = {
    "server_discord": ("Discord server", "servidor de Discord", "Discord-Server"),
    "evento_account": ("account event", "evento de la cuenta", "Konto-Ereignis"),
    "evento_server": ("server event", "evento del servidor", "Server-Ereignis"),
    "invito_creato_da": ("invite created by", "invitación creada por", "Einladung erstellt von"),
}
REASONS: dict = {
    "invito pubblico Discord": ("public Discord invite", "invitación pública de Discord", "öffentliche Discord-Einladung"),
    "invito pubblico Discord ({} membri)": ("public Discord invite ({} members)", "invitación pública de Discord ({} miembros)", "öffentliche Discord-Einladung ({} Mitglieder)"),
    "data codificata nell'ID del server": ("date encoded in the server ID", "fecha codificada en el ID del servidor", "im Server-ID kodiertes Datum"),
    "creatore dell'invito Discord": ("creator of the Discord invite", "creador de la invitación de Discord", "Ersteller der Discord-Einladung"),
    "nome visualizzato su Discord": ("display name on Discord", "nombre visible en Discord", "Anzeigename auf Discord"),
    "data codificata nell'ID dell'utente": ("date encoded in the user ID", "fecha codificada en el ID del usuario", "in der Benutzer-ID kodiertes Datum"),
}
VALUES: dict = {
    "server Discord creato: {}": ("Discord server created: {}", "servidor de Discord creado: {}", "Discord-Server erstellt: {}"),
    "account Discord creato: {}": ("Discord account created: {}", "cuenta de Discord creada: {}", "Discord-Konto erstellt: {}"),
}
