"""Translation tables for more_crypto.py: Italian canonical text -> (English, Spanish, German); '{}' copies a value through."""
TYPES: dict = {"Portafoglio": ("Wallet", "Cartera", "Wallet")}
RELS: dict = {
    "controparte": ("counterparty", "contraparte", "Gegenpartei"),
    "transazioni": ("transactions", "transacciones", "Transaktionen"),
    "nome_ens": ("ENS name", "nombre ENS", "ENS-Name"),
    "etichetta": ("label", "etiqueta", "Label"),
    "creato_da": ("created by", "creado por", "erstellt von"),
    "segnalato": ("flagged", "señalado", "gemeldet"),
    "tipo_email": ("email type", "tipo de correo", "E-Mail-Typ"),
    "esposta_infostealer": ("exposed to infostealer", "expuesto a infostealer", "Infostealer-Exposition"),
    "caricato": ("uploaded", "subido", "hochgeladen"),
}
REASONS: dict = {
    "{} transazioni recenti in comune": ("{} recent transactions in common", "{} transacciones recientes en común", "{} gemeinsame aktuelle Transaktionen"),
    "dati della blockchain Bitcoin": ("Bitcoin blockchain data", "datos de la blockchain de Bitcoin", "Bitcoin-Blockchain-Daten"),
    "blockchain Bitcoin": ("Bitcoin blockchain", "blockchain de Bitcoin", "Bitcoin-Blockchain"),
    "blockchain Ethereum": ("Ethereum blockchain", "blockchain de Ethereum", "Ethereum-Blockchain"),
    "primo movimento sulla blockchain Bitcoin": ("first movement on the Bitcoin blockchain", "primer movimiento en la blockchain de Bitcoin", "erste Bewegung auf der Bitcoin-Blockchain"),
    "nome ENS del portafoglio": ("ENS name of the wallet", "nombre ENS de la cartera", "ENS-Name des Wallets"),
    "etichetta pubblica Blockscout (non verificata)": ("public Blockscout label (unverified)", "etiqueta pública de Blockscout (no verificada)", "öffentliches Blockscout-Label (ungeprüft)"),
    "creatore del contratto": ("contract creator", "creador del contrato", "Ersteller des Vertrags"),
    "etichetta di reputazione Blockscout": ("Blockscout reputation label", "etiqueta de reputación de Blockscout", "Blockscout-Reputationslabel"),
    "dominio nell'elenco dei servizi usa e getta": ("domain in the disposable-service list", "dominio en la lista de servicios desechables", "Domain in der Liste von Wegwerfdiensten"),
    "{} computer infettati da infostealer associati all'email (Hudson Rock)": ("{} computers infected by an infostealer linked to the email (Hudson Rock)", "{} equipos infectados por infostealer asociados al correo (Hudson Rock)", "{} mit Infostealer infizierte Computer zur E-Mail (Hudson Rock)"),
    "elemento caricato su Internet Archive con questa email come uploader": ("item uploaded to Internet Archive with this email as uploader", "elemento subido a Internet Archive con este correo como uploader", "bei Internet Archive mit dieser E-Mail als Uploader hochgeladenes Element"),
}
VALUES: dict = {
    "ultimo movimento: {}": ("last movement: {}", "último movimiento: {}", "letzte Bewegung: {}"),
    "portafoglio creato: {}": ("wallet created: {}", "cartera creada: {}", "Wallet erstellt: {}"),
    "Bitcoin: {} transazioni, ricevuti {} BTC": ("Bitcoin: {} transactions, {} BTC received", "Bitcoin: {} transacciones, {} BTC recibidos", "Bitcoin: {} Transaktionen, {} BTC empfangen"),
    "email usa e getta o alias: {}": ("disposable or alias email: {}", "correo desechable o alias: {}", "Wegwerf- oder Alias-E-Mail: {}"),
    "segnalato come truffa su Blockscout": ("flagged as scam on Blockscout", "señalado como estafa en Blockscout", "auf Blockscout als Betrug gemeldet"),
    "Hudson Rock infostealer ({})": ("Hudson Rock infostealer ({})", "Hudson Rock infostealer ({})", "Hudson Rock Infostealer ({})"),
}
