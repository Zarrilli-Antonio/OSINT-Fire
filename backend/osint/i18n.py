"""Display translations for data that collectors store in Italian: entity types, relation names, reasons, and a few
entity values. Stored data keeps its Italian canonical form (it is part of an entity's identity); everything shown to
the user goes through label()/localize_graph(). Unknown text is shown as stored.

Tables map the Italian text to (English, Spanish, German). '{}' marks a value that is copied through, in order.
"""
import re

LANGS = ("it", "en", "es", "de")
LANG_NAMES = {"it": "Italian", "en": "English", "es": "Spanish", "de": "German"}  # for "reply in ..." instructions
_IDX = {"en": 0, "es": 1, "de": 2}

TYPES = {
    "Account": ("Account", "Cuenta", "Konto"), "App": ("App", "App", "App"), "Azienda": ("Company", "Empresa", "Unternehmen"),
    "Breach": ("Breach", "Filtración", "Datenleck"), "Chiave SSH": ("SSH key", "Clave SSH", "SSH-Schlüssel"),
    "Chiave PGP": ("PGP key", "Clave PGP", "PGP-Schlüssel"), "Data": ("Date", "Fecha", "Datum"), "Dominio": ("Domain", "Dominio", "Domain"),
    "Email": ("Email", "Correo electrónico", "E-Mail"), "ID tracciamento": ("Tracking ID", "ID de seguimiento", "Tracking-ID"),
    "IP": ("IP", "IP", "IP"), "Immagine": ("Image", "Imagen", "Bild"), "Interesse": ("Interest", "Interés", "Interesse"),
    "Luogo": ("Place", "Lugar", "Ort"), "Persona": ("Person", "Persona", "Person"), "Registrazione": ("Registration", "Registro", "Registrierung"),
    "Rete": ("Network", "Red", "Netzwerk"), "Servizio": ("Service", "Servicio", "Dienst"), "Tecnologia": ("Technology", "Tecnología", "Technologie"),
    "Telefono": ("Phone", "Teléfono", "Telefon"), "Username": ("Username", "Nombre de usuario", "Benutzername"),
    "Vulnerabilità": ("Vulnerability", "Vulnerabilidad", "Schwachstelle"), "Wikidata": ("Wikidata", "Wikidata", "Wikidata"),
    "Wikipedia": ("Wikipedia", "Wikipedia", "Wikipedia"),
    # types people create by hand
    "Evento": ("Event", "Evento", "Ereignis"), "Oggetto": ("Object", "Objeto", "Objekt"), "Documento": ("Document", "Documento", "Dokument"),
    "Nota": ("Note", "Nota", "Notiz"),
}

RELS = {
    "account": ("account", "cuenta", "Konto"), "account_pubblicitario": ("advertising account", "cuenta publicitaria", "Werbekonto"),
    "affiliazione": ("affiliation", "afiliación", "Zugehörigkeit"), "amministratore_registrato": ("registered officer", "administrador registrado", "eingetragener Geschäftsführer"),
    "anonimizzatore": ("anonymiser", "anonimizador", "Anonymisierer"), "app_android": ("Android app", "app de Android", "Android-App"),
    "app_ios": ("iOS app", "app de iOS", "iOS-App"), "area_geografica": ("geographic area", "área geográfica", "Region"),
    "attivita": ("activity", "actividad", "Aktivität"), "attivo_in": ("active in", "activo en", "aktiv in"),
    "autore_nel_feed": ("author in the feed", "autor en el feed", "Autor im Feed"), "autore_nel_pacchetto": ("package author", "autor del paquete", "Paketautor"),
    "autore_wordpress": ("WordPress author", "autor de WordPress", "WordPress-Autor"), "autorita_certificati": ("certificate authority", "autoridad de certificación", "Zertifizierungsstelle"),
    "azienda_dichiarata": ("declared company", "empresa declarada", "angegebenes Unternehmen"), "categoria": ("category", "categoría", "Kategorie"),
    "chiave_pgp": ("PGP key", "clave PGP", "PGP-Schlüssel"), "chiave_ssh": ("SSH key", "clave SSH", "SSH-Schlüssel"),
    "classificazione": ("classification", "clasificación", "Einstufung"), "codice_lei": ("LEI code", "código LEI", "LEI-Code"),
    "contatto_dmarc": ("DMARC contact", "contacto DMARC", "DMARC-Kontakt"), "contatto_registrazione": ("registration contact", "contacto de registro", "Registrierungskontakt"),
    "contatto_sicurezza": ("security contact", "contacto de seguridad", "Sicherheitskontakt"), "contatto_soa": ("SOA contact", "contacto SOA", "SOA-Kontakt"),
    "contatto_tlsrpt": ("TLS-RPT contact", "contacto TLS-RPT", "TLS-RPT-Kontakt"), "costituita": ("incorporated", "constituida", "gegründet"),
    "creato_il": ("created on", "creado el", "erstellt am"), "dettaglio": ("detail", "detalle", "Detail"),
    "dominio_associato": ("associated domain", "dominio asociado", "zugehörige Domain"), "dominio_email": ("email domain", "dominio del correo", "E-Mail-Domain"),
    "dominio_ospitato": ("hosted domain", "dominio alojado", "gehostete Domain"), "dominio_provider": ("provider domain", "dominio del proveedor", "Provider-Domain"),
    "dominio_verificato": ("verified domain", "dominio verificado", "verifizierte Domain"), "email_nei_commit": ("email in commits", "correo en los commits", "E-Mail in Commits"),
    "email_nel_feed": ("email in the feed", "correo en el feed", "E-Mail im Feed"), "email_nella_bio": ("email in the bio", "correo en la bio", "E-Mail in der Bio"),
    "email_nella_chiave": ("email in the key", "correo en la clave", "E-Mail im Schlüssel"), "email_pubblica": ("public email", "correo público", "öffentliche E-Mail"),
    "email_registry": ("registry email", "correo del registro", "Registry-E-Mail"), "email_sul_sito": ("email on the website", "correo en el sitio web", "E-Mail auf der Website"),
    "email_trovata": ("email found", "correo encontrado", "gefundene E-Mail"), "emesso_da": ("issued by", "emitido por", "ausgestellt von"),
    "entita_legale": ("legal entity", "entidad legal", "juristische Person"), "evento_dominio": ("domain event", "evento del dominio", "Domain-Ereignis"),
    "forma_internazionale": ("international form", "forma internacional", "internationale Form"), "formato_email": ("email format", "formato de correo", "E-Mail-Format"),
    "geolocalizzato": ("geolocated", "geolocalizado", "geolokalisiert"), "hostname": ("hostname", "nombre de host", "Hostname"),
    "identita_nella_chiave": ("identity in the key", "identidad en la clave", "Identität im Schlüssel"), "immagine_profilo": ("profile picture", "imagen de perfil", "Profilbild"),
    "indirizzo_registrato": ("registered address", "dirección registrada", "eingetragene Adresse"), "intestata_a": ("registered to", "a nombre de", "ausgestellt auf"),
    "intestatario": ("registrant", "titular", "Inhaber"), "ip_autorizzato_mail": ("IP allowed to send mail", "IP autorizada para enviar correo", "für E-Mail zugelassene IP"),
    "luogo_certificato": ("place in the certificate", "lugar en el certificado", "Ort im Zertifikat"), "luogo_dichiarato": ("declared place", "lugar declarado", "angegebener Ort"),
    "membro_di": ("member of", "miembro de", "Mitglied von"), "membro_pubblico": ("public member", "miembro público", "öffentliches Mitglied"),
    "nome_canale": ("channel name", "nombre del canal", "Kanalname"), "nome_nei_commit": ("name in commits", "nombre en los commits", "Name in Commits"),
    "nome_organizzazione": ("organisation name", "nombre de la organización", "Organisationsname"), "nome_profilo": ("profile name", "nombre del perfil", "Profilname"),
    "numero_registro": ("registry number", "número de registro", "Registernummer"), "operatore_originario": ("original carrier", "operador original", "ursprünglicher Anbieter"),
    "organizzazione": ("organisation", "organización", "Organisation"), "organizzazione_certificato": ("organisation in the certificate", "organización en el certificado", "Organisation im Zertifikat"),
    "organizzazione_github": ("GitHub organisation", "organización de GitHub", "GitHub-Organisation"), "ospita_dominio": ("hosts domain", "aloja el dominio", "hostet Domain"),
    "paese": ("country", "país", "Land"), "pagina_autore": ("author page", "página del autor", "Autorenseite"), "parte_di_rete": ("part of network", "parte de la red", "Teil des Netzwerks"),
    "porta_aperta": ("open port", "puerto abierto", "offener Port"), "possibile_profilo": ("possible profile", "posible perfil", "mögliches Profil"),
    "possibile_username": ("possible username", "posible nombre de usuario", "möglicher Benutzername"), "presente_in_breach": ("present in breach", "presente en filtración", "in Datenleck enthalten"),
    "profilo_accademico": ("academic profile", "perfil académico", "akademisches Profil"), "profilo_collegato": ("linked profile", "perfil vinculado", "verknüpftes Profil"),
    "profilo_orcid": ("ORCID profile", "perfil ORCID", "ORCID-Profil"), "profilo_social": ("social profile", "perfil social", "Social-Profil"),
    "profilo_verificato": ("verified profile", "perfil verificado", "verifiziertes Profil"), "provider_email": ("email provider", "proveedor de correo", "E-Mail-Anbieter"),
    "pubblica_pacchetto": ("publishes package", "publica el paquete", "veröffentlicht Paket"), "registrar": ("registrar", "registrador", "Registrar"),
    "registrato_in": ("registered in", "registrado en", "registriert in"), "registrazione_locale": ("local registration", "registro local", "lokale Registrierung"),
    "reputazione": ("reputation", "reputación", "Reputation"), "rete_di": ("network of", "red de", "Netz von"), "reverse_dns": ("reverse DNS", "DNS inverso", "Reverse-DNS"),
    "risolve_a": ("resolves to", "resuelve a", "löst auf"), "sede": ("office", "sede", "Standort"), "sede_legale": ("registered office", "domicilio social", "Firmensitz"),
    "servizio_esposto": ("exposed service", "servicio expuesto", "exponierter Dienst"), "sito_dichiarato": ("declared website", "sitio web declarado", "angegebene Website"),
    "sito_nel_pacchetto": ("website in the package", "sitio web en el paquete", "Website im Paket"), "societa_registrata": ("registered company", "sociedad registrada", "eingetragene Gesellschaft"),
    "sottodominio": ("subdomain", "subdominio", "Subdomain"), "stato_dominio": ("domain status", "estado del dominio", "Domain-Status"),
    "stesso_certificato": ("same certificate", "mismo certificado", "gleiches Zertifikat"), "tecnologia": ("technology", "tecnología", "Technologie"),
    "telefono_sul_sito": ("phone on the website", "teléfono en el sitio web", "Telefon auf der Website"), "tipo_account": ("account type", "tipo de cuenta", "Kontotyp"),
    "tipo_indirizzo": ("address type", "tipo de dirección", "Adresstyp"), "tipo_linea": ("line type", "tipo de línea", "Anschlussart"), "tipo_uso": ("type of use", "tipo de uso", "Nutzungsart"),
    "url_malevolo": ("malicious URL", "URL maliciosa", "schädliche URL"), "usa_mta_sts": ("uses MTA-STS", "usa MTA-STS", "nutzt MTA-STS"), "usa_servizio": ("uses service", "usa el servicio", "nutzt Dienst"),
    "usa_servizio_email": ("uses email service", "usa servicio de correo", "nutzt E-Mail-Dienst"), "usa_tracciamento": ("uses tracking", "usa seguimiento", "nutzt Tracking"),
    "usa_username": ("uses username", "usa el nombre de usuario", "nutzt Benutzernamen"), "usa_email": ("uses email provider", "usa proveedor de correo", "nutzt E-Mail-Anbieter"),
    "usa_dns": ("uses DNS provider", "usa proveedor de DNS", "nutzt DNS-Anbieter"), "usa_hosting": ("uses hosting", "usa alojamiento", "nutzt Hosting"),
    "username_ipotetico": ("guessed username", "nombre de usuario supuesto", "vermuteter Benutzername"), "username_wordpress": ("WordPress username", "usuario de WordPress", "WordPress-Benutzername"),
    "validita": ("validity", "validez", "Gültigkeit"), "voce_wikidata": ("Wikidata entry", "entrada de Wikidata", "Wikidata-Eintrag"),
    "voce_wikipedia": ("Wikipedia article", "artículo de Wikipedia", "Wikipedia-Artikel"), "vulnerabilità_nota": ("known vulnerability", "vulnerabilidad conocida", "bekannte Schwachstelle"),
    "nameserver": ("nameserver", "servidor de nombres", "Nameserver"), "mail_server": ("mail server", "servidor de correo", "Mailserver"),
    # relations that are not collected but made by hand or derived
    "collegato a": ("linked to", "vinculado a", "verknüpft mit"), "ha partecipato a": ("took part in", "participó en", "nahm teil an"),
}

REASONS = {
    "ASN (ipinfo.io)": ("ASN (ipinfo.io)", "ASN (ipinfo.io)", "ASN (ipinfo.io)"), "ASN (ipwho.is)": ("ASN (ipwho.is)", "ASN (ipwho.is)", "ASN (ipwho.is)"),
    "AbuseIPDB": ("AbuseIPDB", "AbuseIPDB", "AbuseIPDB"), "AbuseIPDB (ultimi 90 giorni)": ("AbuseIPDB (last 90 days)", "AbuseIPDB (últimos 90 días)", "AbuseIPDB (letzte 90 Tage)"),
    "CVE associata da Shodan (non verificata)": ("CVE linked by Shodan (unverified)", "CVE asociada por Shodan (sin verificar)", "CVE von Shodan zugeordnet (nicht verifiziert)"),
    "Companies House": ("Companies House", "Companies House", "Companies House"), "Companies House, stato {}": ("Companies House, status {}", "Companies House, estado {}", "Companies House, Status {}"),
    "HIBP, {}, dati esposti: {}": ("HIBP, {}, exposed data: {}", "HIBP, {}, datos expuestos: {}", "HIBP, {}, offengelegte Daten: {}"),
    "Hunter.io": ("Hunter.io", "Hunter.io", "Hunter.io"), "Hunter.io{}": ("Hunter.io{}", "Hunter.io{}", "Hunter.io{}"),
    "IP noto a HackerTarget": ("IP known to HackerTarget", "IP conocida por HackerTarget", "IP bei HackerTarget bekannt"), "IP rilevato da urlscan.io": ("IP seen by urlscan.io", "IP detectada por urlscan.io", "von urlscan.io erkannte IP"),
    "ISP secondo AbuseIPDB": ("ISP according to AbuseIPDB", "ISP según AbuseIPDB", "ISP laut AbuseIPDB"), "LeakCheck, database pubblico di breach": ("LeakCheck, public breach database", "LeakCheck, base de datos pública de filtraciones", "LeakCheck, öffentliche Datenleck-Datenbank"),
    "ORCID collegato in OpenAlex": ("ORCID linked in OpenAlex", "ORCID vinculado en OpenAlex", "ORCID in OpenAlex verknüpft"), "RDAP": ("RDAP", "RDAP", "RDAP"), "RDAP ruolo {}": ("RDAP role {}", "RDAP, rol {}", "RDAP, Rolle {}"),
    "SAN dello stesso certificato TLS": ("SAN of the same TLS certificate", "SAN del mismo certificado TLS", "SAN desselben TLS-Zertifikats"), "SecurityTrails": ("SecurityTrails", "SecurityTrails", "SecurityTrails"),
    "Team Cymru IP-to-ASN": ("Team Cymru IP-to-ASN", "Team Cymru IP-to-ASN", "Team Cymru IP-to-ASN"), "URL archiviato su Wayback Machine": ("URL archived on the Wayback Machine", "URL archivada en Wayback Machine", "URL in der Wayback Machine archiviert"),
    "abuse.ch URLhaus": ("abuse.ch URLhaus", "abuse.ch URLhaus", "abuse.ch URLhaus"), "ads.txt, venditore DIRECT": ("ads.txt, DIRECT seller", "ads.txt, vendedor DIRECT", "ads.txt, DIRECT-Verkäufer"),
    "affiliazione dichiarata su ORCID": ("affiliation declared on ORCID", "afiliación declarada en ORCID", "auf ORCID angegebene Zugehörigkeit"), "altro indirizzo nello UID della chiave PGP": ("another address in the PGP key UID", "otra dirección en el UID de la clave PGP", "weitere Adresse in der UID des PGP-Schlüssels"),
    "analisi VirusTotal": ("VirusTotal analysis", "análisis de VirusTotal", "VirusTotal-Analyse"), "apple-app-site-association": ("apple-app-site-association", "apple-app-site-association", "apple-app-site-association"),
    "assetlinks.json": ("assetlinks.json", "assetlinks.json", "assetlinks.json"), "autore di commit in {}": ("commit author in {}", "autor de commits en {}", "Commit-Autor in {}"),
    "autore di commit pubblici (può essere un co-autore)": ("author of public commits (may be a co-author)", "autor de commits públicos (puede ser coautor)", "Autor öffentlicher Commits (kann Mitautor sein)"),
    "autore nel feed RSS/Atom": ("author in the RSS/Atom feed", "autor en el feed RSS/Atom", "Autor im RSS/Atom-Feed"), "autore su OpenAlex ({} opere, omonimia possibile)": ("author on OpenAlex ({} works, namesake possible)", "autor en OpenAlex ({} obras, posible homonimia)", "Autor bei OpenAlex ({} Werke, Namensvetter möglich)"),
    "avatar GitHub": ("GitHub avatar", "avatar de GitHub", "GitHub-Avatar"), "avatar Gravatar": ("Gravatar avatar", "avatar de Gravatar", "Gravatar-Avatar"), "avatar Libravatar": ("Libravatar avatar", "avatar de Libravatar", "Libravatar-Avatar"),
    "avatar del profilo": ("profile avatar", "avatar del perfil", "Profil-Avatar"), "avatar su {}": ("avatar on {}", "avatar en {}", "Avatar auf {}"), "azienda nel profilo {}": ("company in the {} profile", "empresa en el perfil de {}", "Unternehmen im {}-Profil"),
    "banner raccolto da Shodan": ("banner collected by Shodan", "banner recogido por Shodan", "von Shodan erfasstes Banner"), "campo O del certificato TLS": ("O field of the TLS certificate", "campo O del certificado TLS", "O-Feld des TLS-Zertifikats"),
    "campo RNAME del record SOA": ("RNAME field of the SOA record", "campo RNAME del registro SOA", "RNAME-Feld des SOA-Eintrags"), "campo authors di un suo pacchetto": ("authors field of one of their packages", "campo authors de uno de sus paquetes", "Authors-Feld eines ihrer Pakete"),
    "campo blog GitHub": ("GitHub blog field", "campo blog de GitHub", "GitHub-Blogfeld"), "campo blog dell'organizzazione": ("organisation blog field", "campo blog de la organización", "Blogfeld der Organisation"),
    "campo company GitHub": ("GitHub company field", "campo company de GitHub", "GitHub-Firmenfeld"), "campo location GitHub": ("GitHub location field", "campo location de GitHub", "GitHub-Ortsfeld"),
    "campo location dell'organizzazione": ("organisation location field", "campo location de la organización", "Ortsfeld der Organisation"), "campo twitter GitHub": ("GitHub twitter field", "campo twitter de GitHub", "GitHub-Twitterfeld"),
    "campo twitter dell'organizzazione": ("organisation twitter field", "campo twitter de la organización", "Twitterfeld der Organisation"), "canale YouTube": ("YouTube channel", "canal de YouTube", "YouTube-Kanal"),
    "certificato TLS (Cert Spotter)": ("TLS certificate (Cert Spotter)", "certificado TLS (Cert Spotter)", "TLS-Zertifikat (Cert Spotter)"), "certificato TLS pubblico": ("public TLS certificate", "certificado TLS público", "öffentliches TLS-Zertifikat"),
    "chiave SSH pubblica su {}": ("public SSH key on {}", "clave SSH pública en {}", "öffentlicher SSH-Schlüssel auf {}"), "chiave pubblica su keyserver": ("public key on a keyserver", "clave pública en un servidor de claves", "öffentlicher Schlüssel auf einem Keyserver"),
    "classificazione VirusTotal": ("VirusTotal classification", "clasificación de VirusTotal", "VirusTotal-Einstufung"), "classificazione del numero": ("number classification", "clasificación del número", "Einstufung der Nummer"),
    "collegato in Gravatar ({})": ("linked in Gravatar ({})", "vinculado en Gravatar ({})", "in Gravatar verknüpft ({})"), "combinazione nome e cognome (ipotesi)": ("first and last name combination (guess)", "combinación de nombre y apellido (hipótesis)", "Kombination aus Vor- und Nachname (Vermutung)"),
    "corrispondenza per nome su Wikidata (omonimi possibili)": ("name match on Wikidata (namesakes possible)", "coincidencia por nombre en Wikidata (posibles homónimos)", "Namensübereinstimmung bei Wikidata (Namensvetter möglich)"),
    "dati strutturati schema.org": ("schema.org structured data", "datos estructurados de schema.org", "strukturierte schema.org-Daten"), "dato Wikidata {} ({})": ("Wikidata data {} ({})", "dato de Wikidata {} ({})", "Wikidata-Angabe {} ({})"),
    "dedotto dai record DNS ({})": ("inferred from DNS records ({})", "deducido de los registros DNS ({})", "aus DNS-Einträgen abgeleitet ({})"), "dominio del provider": ("provider's domain", "dominio del proveedor", "Domain des Providers"),
    "dominio dell'ISP": ("ISP's domain", "dominio del ISP", "Domain des ISP"), "dominio nell'elenco dei provider pubblici": ("domain in the list of public providers", "dominio de la lista de proveedores públicos", "Domain aus der Liste öffentlicher Anbieter"),
    "dominio noto a Shodan": ("domain known to Shodan", "dominio conocido por Shodan", "Shodan bekannte Domain"), "elenco pubblico di domini temporanei": ("public list of temporary domains", "lista pública de dominios temporales", "öffentliche Liste temporärer Domains"),
    "elenco ufficiale dei nodi di uscita Tor": ("official list of Tor exit nodes", "lista oficial de nodos de salida de Tor", "offizielle Liste der Tor-Exit-Knoten"), "email dell'organizzazione": ("organisation email", "correo de la organización", "E-Mail der Organisation"),
    "email nel profilo GitHub": ("email in the GitHub profile", "correo en el perfil de GitHub", "E-Mail im GitHub-Profil"), "email nel profilo {}": ("email in the {} profile", "correo en el perfil de {}", "E-Mail im {}-Profil"),
    "email pubblica nel profilo GitHub": ("public email in the GitHub profile", "correo público en el perfil de GitHub", "öffentliche E-Mail im GitHub-Profil"), "emittente del certificato": ("certificate issuer", "emisor del certificado", "Aussteller des Zertifikats"),
    "evento nel registro RDAP": ("event in the RDAP registry", "evento en el registro RDAP", "Ereignis im RDAP-Register"), "gem Ruby di cui è owner": ("Ruby gem they own", "gem de Ruby de la que es propietario", "Ruby-Gem, dessen Eigentümer er ist"),
    "geolocalizzazione IP (approssimativa)": ("IP geolocation (approximate)", "geolocalización de IP (aproximada)", "IP-Geolokalisierung (ungefähr)"), "geolocalizzazione Shodan (approssimativa)": ("Shodan geolocation (approximate)", "geolocalización de Shodan (aproximada)", "Shodan-Geolokalisierung (ungefähr)"),
    "handle in humans.txt": ("handle in humans.txt", "usuario en humans.txt", "Handle in humans.txt"), "header HTTP Server": ("HTTP Server header", "cabecera HTTP Server", "HTTP-Server-Header"),
    "hostname (ipinfo.io)": ("hostname (ipinfo.io)", "nombre de host (ipinfo.io)", "Hostname (ipinfo.io)"), "hostname noto a Shodan": ("hostname known to Shodan", "nombre de host conocido por Shodan", "Shodan bekannter Hostname"),
    "hostsearch pubblico (HackerTarget)": ("public hostsearch (HackerTarget)", "hostsearch público (HackerTarget)", "öffentliche Hostsuche (HackerTarget)"), "humans.txt": ("humans.txt", "humans.txt", "humans.txt"),
    "identificativo nel codice della pagina": ("identifier in the page code", "identificador en el código de la página", "Kennung im Seitencode"), "indicata in database di breach pubblico": ("listed in a public breach database", "figura en una base de datos pública de filtraciones", "in öffentlicher Datenleck-Datenbank aufgeführt"),
    "indirizzo legale nel registro LEI": ("legal address in the LEI register", "dirección legal en el registro LEI", "Rechtsadresse im LEI-Register"), "indirizzo nel feed RSS/Atom": ("address in the RSS/Atom feed", "dirección en el feed RSS/Atom", "Adresse im RSS/Atom-Feed"),
    "indirizzo nel registro pubblico": ("address in the public registry", "dirección en el registro público", "Adresse im öffentlichen Register"), "indirizzo nella bio su {}": ("address in the bio on {}", "dirección en la bio de {}", "Adresse in der Bio auf {}"),
    "indirizzo noreply di GitHub": ("GitHub noreply address", "dirección noreply de GitHub", "GitHub-noreply-Adresse"), "indirizzo registrato": ("registered address", "dirección registrada", "eingetragene Adresse"),
    "indirizzo report DMARC": ("DMARC report address", "dirección de informes DMARC", "DMARC-Berichtsadresse"), "indirizzo report TLS-RPT": ("TLS-RPT report address", "dirección de informes TLS-RPT", "TLS-RPT-Berichtsadresse"),
    "indirizzo schema.org": ("schema.org address", "dirección de schema.org", "schema.org-Adresse"), "link a profilo social nella home page": ("link to a social profile on the home page", "enlace a un perfil social en la página de inicio", "Link zu einem Social-Profil auf der Startseite"),
    "link a un altro profilo su {}": ("link to another profile on {}", "enlace a otro perfil en {}", "Link zu einem anderen Profil auf {}"), 'link rel="me" nella pagina': ('rel="me" link on the page', 'enlace rel="me" en la página', 'rel="me"-Link auf der Seite'),
    "link tel: nella home page": ("tel: link on the home page", "enlace tel: en la página de inicio", "tel:-Link auf der Startseite"), "luogo nel certificato TLS": ("place in the TLS certificate", "lugar en el certificado TLS", "Ort im TLS-Zertifikat"),
    "luogo nel profilo Keybase": ("place in the Keybase profile", "lugar en el perfil de Keybase", "Ort im Keybase-Profil"), "luogo nel profilo {}": ("place in the {} profile", "lugar en el perfil de {}", "Ort im {}-Profil"),
    "membro pubblico dell'organizzazione": ("public member of the organisation", "miembro público de la organización", "öffentliches Mitglied der Organisation"), "meta generator": ("meta generator", "meta generator", "Meta-Generator"),
    "meta twitter:site": ("meta twitter:site", "meta twitter:site", "Meta twitter:site"), "metadato pubblico del registry npm": ("public metadata of the npm registry", "metadato público del registro npm", "öffentliche Metadaten der npm-Registry"),
    "nessun record MX/A": ("no MX/A record", "ningún registro MX/A", "kein MX/A-Eintrag"), "nome ASN (Team Cymru)": ("ASN name (Team Cymru)", "nombre del ASN (Team Cymru)", "ASN-Name (Team Cymru)"),
    "nome associato da Hunter.io": ("name linked by Hunter.io", "nombre asociado por Hunter.io", "von Hunter.io zugeordneter Name"), "nome comune che risolve (wordlist DNS)": ("common name that resolves (DNS wordlist)", "nombre común que resuelve (lista de palabras DNS)", "gängiger Name, der aufgelöst wird (DNS-Wortliste)"),
    "nome dell'autore nei commit": ("author name in commits", "nombre del autor en los commits", "Autorenname in Commits"), "nome nel profilo GitHub": ("name in the GitHub profile", "nombre en el perfil de GitHub", "Name im GitHub-Profil"),
    "nome nel profilo Gravatar": ("name in the Gravatar profile", "nombre en el perfil de Gravatar", "Name im Gravatar-Profil"), "nome nel profilo Keybase": ("name in the Keybase profile", "nombre en el perfil de Keybase", "Name im Keybase-Profil"),
    "nome nel profilo {}": ("name in the {} profile", "nombre en el perfil de {}", "Name im {}-Profil"), "nome nello UID della chiave PGP": ("name in the PGP key UID", "nombre en el UID de la clave PGP", "Name in der UID des PGP-Schlüssels"),
    "normalizzazione E.164": ("E.164 normalisation", "normalización E.164", "E.164-Normalisierung"), "numero di registro delle imprese": ("company registry number", "número del registro mercantil", "Handelsregisternummer"),
    "omonimia possibile (ORCID)": ("namesake possible (ORCID)", "posible homonimia (ORCID)", "Namensvetter möglich (ORCID)"), "omonimia possibile, {} incarichi (Companies House)": ("namesake possible, {} appointments (Companies House)", "posible homonimia, {} cargos (Companies House)", "Namensvetter möglich, {} Ämter (Companies House)"),
    "operatore del prefisso: la portabilità può averlo cambiato": ("carrier of the prefix: number portability may have changed it", "operador del prefijo: la portabilidad puede haberlo cambiado", "Anbieter der Vorwahl: Nummernportierung kann ihn geändert haben"),
    "organizzazione GitHub con lo stesso nome": ("GitHub organisation with the same name", "organización de GitHub con el mismo nombre", "GitHub-Organisation mit gleichem Namen"), "organizzazione GitHub pubblica": ("public GitHub organisation", "organización pública de GitHub", "öffentliche GitHub-Organisation"),
    "organizzazione dell'ASN": ("ASN organisation", "organización del ASN", "Organisation des ASN"), "organizzazione intestataria (RDAP)": ("registrant organisation (RDAP)", "organización titular (RDAP)", "Inhaber-Organisation (RDAP)"),
    "organizzazione secondo Shodan": ("organisation according to Shodan", "organización según Shodan", "Organisation laut Shodan"), "pacchetto npm di cui è maintainer": ("npm package they maintain", "paquete npm que mantiene", "npm-Paket, das er betreut"),
    "paese nel registro RDAP": ("country in the RDAP registry", "país en el registro RDAP", "Land im RDAP-Register"), "paese secondo AbuseIPDB": ("country according to AbuseIPDB", "país según AbuseIPDB", "Land laut AbuseIPDB"),
    "paese secondo VirusTotal": ("country according to VirusTotal", "país según VirusTotal", "Land laut VirusTotal"), "pagina autore WordPress": ("WordPress author page", "página de autor de WordPress", "WordPress-Autorenseite"),
    "parte dopo @": ("part after @", "parte después de @", "Teil nach @"), "parte locale dell'indirizzo": ("local part of the address", "parte local de la dirección", "lokaler Teil der Adresse"),
    "passive DNS (OTX)": ("passive DNS (OTX)", "DNS pasivo (OTX)", "passives DNS (OTX)"), "pattern rilevato da Hunter.io": ("pattern detected by Hunter.io", "patrón detectado por Hunter.io", "von Hunter.io erkanntes Muster"),
    "porta rilevata da Shodan": ("port detected by Shodan", "puerto detectado por Shodan", "von Shodan erkannter Port"), "prefisso internazionale": ("international prefix", "prefijo internacional", "internationale Vorwahl"),
    "prefisso telefonico": ("dialling prefix", "prefijo telefónico", "Telefonvorwahl"), "profilo GitHub": ("GitHub profile", "perfil de GitHub", "GitHub-Profil"), "profilo Gravatar": ("Gravatar profile", "perfil de Gravatar", "Gravatar-Profil"),
    "profilo Keybase": ("Keybase profile", "perfil de Keybase", "Keybase-Profil"), "profilo Reddit": ("Reddit profile", "perfil de Reddit", "Reddit-Profil"), "profilo Roblox": ("Roblox profile", "perfil de Roblox", "Roblox-Profil"),
    "profilo Twitch": ("Twitch profile", "perfil de Twitch", "Twitch-Profil"), "profilo X": ("X profile", "perfil de X", "X-Profil"), "proprietario ASN (VirusTotal)": ("ASN owner (VirusTotal)", "propietario del ASN (VirusTotal)", "ASN-Inhaber (VirusTotal)"),
    "prova crittografica Keybase (DNS)": ("Keybase cryptographic proof (DNS)", "prueba criptográfica de Keybase (DNS)", "kryptografischer Keybase-Nachweis (DNS)"), "prova crittografica Keybase ({})": ("Keybase cryptographic proof ({})", "prueba criptográfica de Keybase ({})", "kryptografischer Keybase-Nachweis ({})"),
    "record CAA": ("CAA record", "registro CAA", "CAA-Eintrag"), "record DNS A": ("DNS A record", "registro DNS A", "DNS-A-Eintrag"), "record DNS {}": ("DNS {} record", "registro DNS {}", "DNS-{}-Eintrag"), "record PTR": ("PTR record", "registro PTR", "PTR-Eintrag"),
    "record SPF": ("SPF record", "registro SPF", "SPF-Eintrag"), "record SPF include": ("SPF include record", "registro SPF include", "SPF-include-Eintrag"), "record TXT di verifica ({})": ("TXT verification record ({})", "registro TXT de verificación ({})", "TXT-Verifizierungseintrag ({})"),
    "record _mta-sts": ("_mta-sts record", "registro _mta-sts", "_mta-sts-Eintrag"), "registrar nel registro RDAP": ("registrar in the RDAP registry", "registrador en el registro RDAP", "Registrar im RDAP-Register"), "registrar secondo VirusTotal": ("registrar according to VirusTotal", "registrador según VirusTotal", "Registrar laut VirusTotal"),
    "registro LEI (GLEIF)": ("LEI register (GLEIF)", "registro LEI (GLEIF)", "LEI-Register (GLEIF)"), "registro pubblico": ("public registry", "registro público", "öffentliches Register"),
    "reverse IP (HackerTarget), può essere hosting condiviso": ("reverse IP (HackerTarget), may be shared hosting", "IP inversa (HackerTarget), puede ser alojamiento compartido", "Reverse-IP (HackerTarget), kann Shared Hosting sein"),
    "risoluzione storica (OTX)": ("historical resolution (OTX)", "resolución histórica (OTX)", "historische Auflösung (OTX)"), "risoluzione storica (VirusTotal)": ("historical resolution (VirusTotal)", "resolución histórica (VirusTotal)", "historische Auflösung (VirusTotal)"),
    "scansione pubblica su urlscan.io": ("public scan on urlscan.io", "escaneo público en urlscan.io", "öffentlicher Scan auf urlscan.io"), "schema.org email": ("schema.org email", "correo de schema.org", "schema.org-E-Mail"),
    "schema.org sameAs": ("schema.org sameAs", "schema.org sameAs", "schema.org sameAs"), "schema.org telephone": ("schema.org telephone", "teléfono de schema.org", "schema.org-Telefon"), "security.txt": ("security.txt", "security.txt", "security.txt"),
    "selettore DKIM '{}' pubblicato": ("DKIM selector '{}' published", "selector DKIM '{}' publicado", "DKIM-Selektor '{}' veröffentlicht"), "sito nel profilo {}": ("website in the {} profile", "sitio web en el perfil de {}", "Website im {}-Profil"),
    "slug dell'autore su WordPress (spesso lo username)": ("author slug on WordPress (often the username)", "slug del autor en WordPress (a menudo el nombre de usuario)", "Autoren-Slug in WordPress (oft der Benutzername)"), "sottodominio noto a VirusTotal": ("subdomain known to VirusTotal", "subdominio conocido por VirusTotal", "VirusTotal bekannte Subdomain"),
    "stato EPP nel registro RDAP": ("EPP status in the RDAP registry", "estado EPP en el registro RDAP", "EPP-Status im RDAP-Register"), "stato {}": ("status {}", "estado {}", "Status {}"),
    "titolo del canale (può essere un marchio o un soprannome)": ("channel title (may be a brand or a nickname)", "título del canal (puede ser una marca o un apodo)", "Kanaltitel (kann eine Marke oder ein Spitzname sein)"), "ultima affiliazione nota": ("last known affiliation", "última afiliación conocida", "letzte bekannte Zugehörigkeit"),
    "username presente su {}": ("username present on {}", "nombre de usuario presente en {}", "Benutzername auf {} vorhanden"), "utente pubblico dell'API REST di WordPress": ("public user of the WordPress REST API", "usuario público de la API REST de WordPress", "öffentlicher Benutzer der WordPress-REST-API"),
    "voce enciclopedica con questo titolo (omonimi possibili)": ("encyclopedia article with this title (namesakes possible)", "artículo enciclopédico con este título (posibles homónimos)", "Lexikonartikel mit diesem Titel (Namensvetter möglich)"), "{} contributi recenti": ("{} recent contributions", "{} contribuciones recientes", "{} aktuelle Beiträge"),
    "{} di un suo pacchetto": ("{} of one of their packages", "{} de uno de sus paquetes", "{} eines ihrer Pakete"), "{} pubblica chiavi per questo username": ("{} publishes keys for this username", "{} publica claves para este nombre de usuario", "{} veröffentlicht Schlüssel für diesen Benutzernamen"),
    "profilo su {}": ("profile on {}", "perfil en {}", "Profil auf {}"), "mailto nella home page": ("mailto on the home page", "mailto en la página de inicio", "mailto auf der Startseite"),
    "indirizzo nel testo della home page": ("address in the home page text", "dirección en el texto de la página de inicio", "Adresse im Text der Startseite"),
    "scansioni di massa osservate": ("mass scanning observed", "escaneos masivos observados", "Massenscans beobachtet"),
    "servizio noto e benigno (RIOT)": ("known benign service (RIOT)", "servicio conocido y benigno (RIOT)", "bekannter harmloser Dienst (RIOT)"),
    # reasons written by hand or by the correlation engine
    "aggiunto manualmente": ("added manually", "añadido manualmente", "manuell hinzugefügt"),
}

# entity values (Servizio / Data) with Italian wording
VALUES = {
    "MTA-STS attivo": ("MTA-STS enabled", "MTA-STS activo", "MTA-STS aktiv"), "dominio di posta usa-e-getta": ("disposable email domain", "dominio de correo desechable", "Wegwerf-E-Mail-Domain"),
    "il dominio non riceve posta (nessun MX)": ("the domain does not receive mail (no MX)", "el dominio no recibe correo (sin MX)", "Die Domain empfängt keine E-Mails (kein MX)"),
    "nodo Tor": ("Tor node", "nodo Tor", "Tor-Knoten"), "nodo di uscita Tor": ("Tor exit node", "nodo de salida de Tor", "Tor-Exit-Knoten"),
    "AbuseIPDB: punteggio {}%, {} segnalazioni": ("AbuseIPDB: score {}%, {} reports", "AbuseIPDB: puntuación {}%, {} informes", "AbuseIPDB: Bewertung {}%, {} Meldungen"),
    "Reddit: karma {} post, {} commenti": ("Reddit: karma {} posts, {} comments", "Reddit: karma {} publicaciones, {} comentarios", "Reddit: Karma {} Beiträge, {} Kommentare"),
    "URL malevolo: {} ({})": ("malicious URL: {} ({})", "URL maliciosa: {} ({})", "schädliche URL: {} ({})"),
    "URLhaus: {} URL malevoli segnalati ({} online)": ("URLhaus: {} malicious URLs reported ({} online)", "URLhaus: {} URL maliciosas notificadas ({} en línea)", "URLhaus: {} schädliche URLs gemeldet ({} online)"),
    "VirusTotal: {} motori lo segnalano come malevolo": ("VirusTotal: {} engines flag it as malicious", "VirusTotal: {} motores lo marcan como malicioso", "VirusTotal: {} Engines stufen es als schädlich ein"),
    "X: {} follower, {} post": ("X: {} followers, {} posts", "X: {} seguidores, {} publicaciones", "X: {} Follower, {} Beiträge"), "categoria: {}": ("category: {}", "categoría: {}", "Kategorie: {}"),
    "formato email: {}": ("email format: {}", "formato de correo: {}", "E-Mail-Format: {}"), "provider email pubblico: {}": ("public email provider: {}", "proveedor de correo público: {}", "öffentlicher E-Mail-Anbieter: {}"),
    "stato dominio: {}": ("domain status: {}", "estado del dominio: {}", "Domain-Status: {}"), "tipo linea: {}": ("line type: {}", "tipo de línea: {}", "Anschlussart: {}"), "uso: {}": ("usage: {}", "uso: {}", "Nutzung: {}"),
    "account Reddit creato: {}": ("Reddit account created: {}", "cuenta de Reddit creada: {}", "Reddit-Konto erstellt: {}"), "account Roblox creato: {}": ("Roblox account created: {}", "cuenta de Roblox creada: {}", "Roblox-Konto erstellt: {}"),
    "account Twitch creato: {}": ("Twitch account created: {}", "cuenta de Twitch creada: {}", "Twitch-Konto erstellt: {}"), "account X creato: {}": ("X account created: {}", "cuenta de X creada: {}", "X-Konto erstellt: {}"),
    "canale YouTube creato: {}": ("YouTube channel created: {}", "canal de YouTube creado: {}", "YouTube-Kanal erstellt: {}"), "costituzione: {}": ("incorporation: {}", "constitución: {}", "Gründung: {}"),
    "registrazione: {}": ("registered: {}", "registro: {}", "Registrierung: {}"), "scadenza: {}": ("expires: {}", "caducidad: {}", "Ablauf: {}"), "ultima modifica: {}": ("last changed: {}", "última modificación: {}", "letzte Änderung: {}"),
    "trasferimento: {}": ("transferred: {}", "transferencia: {}", "Übertragung: {}"),
    # inner values of "tipo linea: {}"
    "linea fissa": ("landline", "línea fija", "Festnetz"), "cellulare": ("mobile", "móvil", "Mobilfunk"), "fisso o cellulare": ("landline or mobile", "fija o móvil", "Festnetz oder Mobilfunk"),
    "numero verde": ("toll-free number", "número gratuito", "gebührenfreie Nummer"), "tariffa premium": ("premium rate", "tarifa premium", "Premium-Tarif"),
}

_tables = {"type": TYPES, "rel": RELS, "reason": REASONS, "value": VALUES}


def _compile(table: dict) -> list[tuple[re.Pattern, tuple]]:
    out = []
    for it, tr in table.items():
        if "{}" in it:
            out.append((re.compile("^" + re.escape(it).replace(r"\{\}", "(.+?)") + "$", re.S), tr))
    return out


_templates = {k: _compile(t) for k, t in _tables.items() if k in ("reason", "value")}


def _fill(template: str, groups: tuple, lang: str) -> str:
    parts = template.split("{}")
    return parts[0] + "".join(g + p for g, p in zip((label_value(g, lang) if g in VALUES else g for g in groups), parts[1:]))


def label(kind: str, text: str, lang: str) -> str:
    """Localised form of [text] for kind in type|rel|reason|value. Italian and unknown text come back unchanged."""
    if lang not in _IDX:
        return text
    i, table = _IDX[lang], _tables[kind]
    if text in table:
        return table[text][i]
    for rx, tr in _templates.get(kind, ()):
        if m := rx.match(text):
            return _fill(tr[i], m.groups(), lang)
    if kind == "rel":  # generic fallback: usa_{x} and unknown names read as words
        return text.replace("_", " ")
    return text


def label_value(text: str, lang: str) -> str:
    return label("value", text, lang)


def localize_graph(g: dict, lang: str) -> dict:
    """The graph payload with display labels next to the canonical fields (which stay as they are: they are identities)."""
    types = {n["type"] for n in g["nodes"]}
    return {**g,
            "type_labels": {t: label("type", t, lang) for t in types},
            "nodes": [{**n, "label": label_value(n["value"], lang) if n["type"] in ("Servizio", "Data") else n["value"]} for n in g["nodes"]],
            "edges": [{**e, "rel_label": label("rel", e["rel"], lang), "reason_label": label("reason", e["reason"], lang)} for e in g["edges"]],
            "links": [{**l, "signal_labels": [label("reason", sig[0], lang) for sig in l["signals"]]} for l in g["links"]]}


# ---- report and message strings ----
UI = {
    "investigation": ("Indagine", "Investigation", "Investigación", "Untersuchung"), "purpose": ("Scopo", "Purpose", "Propósito", "Zweck"),
    "date": ("Data", "Date", "Fecha", "Datum"), "entities": ("Entità", "Entities", "Entidades", "Entitäten"), "relations": ("Relazioni", "Relations", "Relaciones", "Beziehungen"),
    "summary": ("Riepilogo", "Summary", "Resumen", "Zusammenfassung"), "favourites": ("Preferiti", "Favourites", "Favoritos", "Favoriten"),
    "links": ("Collegamenti ipotizzati", "Suspected links", "Vínculos supuestos", "Vermutete Verknüpfungen"), "status": ("Stato", "Status", "Estado", "Status"),
    "score": ("Punteggio", "Score", "Puntuación", "Bewertung"), "signals": ("Segnali", "Signals", "Señales", "Signale"),
    "confirmed_manually": ("confermato manualmente", "confirmed manually", "confirmado manualmente", "manuell bestätigt"), "note": ("nota", "note", "nota", "Notiz"),
    "notes": ("Note", "Notes", "Notas", "Notizen"), "auto": ("automatico", "automatic", "automático", "automatisch"), "review": ("da verificare", "to review", "por verificar", "zu prüfen"),
    "confirmed": ("confermato", "confirmed", "confirmado", "bestätigt"), "type": ("tipo", "type", "tipo", "typ"), "value": ("valore", "value", "valor", "wert"),
    "investigation_key": ("indagine", "investigation", "investigacion", "untersuchung"), "favourite_key": ("preferito", "favourite", "favorito", "favorit"),
    "entities_title": ("Entità", "Entities", "Entidades", "Entitäten"), "pt": ("Pt.", "Score", "Punt.", "Wert"), "entity_col": ("Entità", "Entity", "Entidad", "Entität"),
}


def ui(key: str, lang: str) -> str:
    row = UI[key]
    return row[LANGS.index(lang)] if lang in LANGS else row[1]
