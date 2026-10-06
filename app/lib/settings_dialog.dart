import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'backend.dart';
import 'theme.dart';

String downloadsDir() => '${Platform.environment['HOME']!.split('/Library/Containers').first}/Downloads';

/// Settings in five tabs. Edits are collected in a patch and sent together with "Salva"; the backend validates
/// the whole patch or none of it. Pops `true` when something was saved so the caller can reload.
class SettingsDialog extends StatefulWidget {
  const SettingsDialog({super.key, required this.backend, this.initialTab = 0, this.initial, this.initialCollectors, this.initialStats});
  final Backend backend;
  final int initialTab;
  // tests only: skip the network load
  final Settings? initial;
  final List<CollectorInfo>? initialCollectors;
  final Map<String, dynamic>? initialStats;

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  Settings? s;
  List<CollectorInfo> collectors = [];
  Map<String, dynamic> stats = {};
  final patch = <String, dynamic>{};
  final secretCtl = <String, TextEditingController>{};
  String? error, notice;
  bool saving = false, saved = false;
  String filter = '';
  String wipeWord = '';
  final tests = <String, (bool, String)>{};
  final testing = <String>{};

  @override
  void initState() {
    super.initState();
    if (widget.initial != null) {
      s = widget.initial;
      collectors = widget.initialCollectors ?? [];
      stats = widget.initialStats ?? {};
    } else {
      _load();
    }
  }

  @override
  void dispose() {
    for (final c in secretCtl.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final r = await Future.wait([fetchSettings(), fetchCollectors(), maintenanceStats()]);
      if (!mounted) return;
      setState(() {
        s = r[0] as Settings;
        collectors = r[1] as List<CollectorInfo>;
        stats = r[2] as Map<String, dynamic>;
      });
    } catch (e) {
      if (mounted) setState(() => error = 'Impossibile leggere le impostazioni: $e');
    }
  }

  dynamic v(String k) => patch.containsKey(k) ? patch[k] : s!.values[k];
  void set(String k, dynamic value) => setState(() {
        patch[k] = value;
        error = notice = null;
      });

  Future<void> _save() async {
    setState(() {
      saving = true;
      error = notice = null;
    });
    try {
      final next = await saveSettings(patch);
      final cols = await fetchCollectors();
      if (!mounted) return;
      setState(() {
        s = next;
        collectors = cols;
        patch.clear();
        for (final c in secretCtl.values) {
          c.clear();
        }
        saved = true;
        notice = 'Impostazioni salvate';
      });
    } catch (e) {
      if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 5,
      initialIndex: widget.initialTab,
      child: Dialog(
        insetPadding: const EdgeInsets.all(24),
        child: SizedBox(
          width: 840,
          height: 660,
          child: s == null
              ? Center(child: error == null ? const CircularProgressIndicator(strokeWidth: 2) : Text(error!, style: const TextStyle(color: accent)))
              : Column(children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 16, 12, 0),
                    child: Row(children: [
                      const Expanded(child: Text('IMPOSTAZIONI', style: TextStyle(fontSize: 12, letterSpacing: 2, fontWeight: FontWeight.w700))),
                      IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context, saved)),
                    ]),
                  ),
                  const TabBar(
                    isScrollable: true,
                    tabAlignment: TabAlignment.start,
                    dividerColor: line,
                    indicatorColor: accent,
                    labelColor: fg,
                    unselectedLabelColor: dim,
                    labelStyle: TextStyle(fontSize: 12, fontFamily: mono),
                    tabs: [Tab(text: 'Generale'), Tab(text: 'Fonti'), Tab(text: 'Chiavi API'), Tab(text: 'AI'), Tab(text: 'Dati')],
                  ),
                  Expanded(
                    child: TabBarView(children: [_general(), _sources(), _keys(), _ai(), _data()]),
                  ),
                  const Divider(),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 8, 20, 14),
                    child: Row(children: [
                      Expanded(
                        child: Text(error ?? notice ?? (patch.isEmpty ? '' : '${patch.length} modifiche non salvate'),
                            maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 11.5, color: error != null ? accent : dim)),
                      ),
                      TextButton(onPressed: () => Navigator.pop(context, saved), child: const Text('Chiudi')),
                      const SizedBox(width: 8),
                      SizedBox(
                        width: 120,
                        child: FilledButton(onPressed: patch.isEmpty || saving ? null : _save, child: Text(saving ? '…' : 'SALVA')),
                      ),
                    ]),
                  ),
                ]),
        ),
      ),
    );
  }

  // ---------------- building blocks ----------------

  Widget _section(String t) => Padding(
        padding: const EdgeInsets.only(top: 20, bottom: 4),
        child: Text(t.toUpperCase(), style: const TextStyle(fontSize: 10, letterSpacing: 1.6, color: dim)),
      );

  Widget _switch(String key, String title, String help) => SwitchListTile(
        dense: true,
        contentPadding: EdgeInsets.zero,
        title: Text(title, style: const TextStyle(fontSize: 12.5)),
        subtitle: Text(help, style: const TextStyle(fontSize: 11, color: dim)),
        value: v(key) as bool,
        onChanged: (x) => set(key, x),
      );

  Widget _num(String key, String title, String help, {String? suffix}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: const TextStyle(fontSize: 12.5)),
              Text(help, style: const TextStyle(fontSize: 11, color: dim)),
            ]),
          ),
          SizedBox(
            width: 110,
            child: _NumField(
              key: ValueKey('$key-${s!.values[key]}'),
              initial: '${v(key)}',
              suffix: suffix,
              onChanged: (n) => n == null ? null : set(key, n),
            ),
          ),
        ]),
      );

  Widget _text(String key, String title, String help, {String? hint}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontSize: 12.5)),
          Text(help, style: const TextStyle(fontSize: 11, color: dim)),
          TextFormField(
            key: ValueKey('$key-${s!.values[key]}'),
            initialValue: v(key) as String,
            style: const TextStyle(fontSize: 12),
            decoration: InputDecoration(hintText: hint),
            onChanged: (x) => set(key, x),
          ),
        ]),
      );

  /// One value per line (commas and spaces also work); stored as a list.
  Widget _lines(String key, String title, String help) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontSize: 12.5)),
          Text(help, style: const TextStyle(fontSize: 11, color: dim)),
          TextFormField(
            key: ValueKey('$key-${(s!.values[key] as List).length}'),
            initialValue: (v(key) as List).join('\n'),
            minLines: 3,
            maxLines: 6,
            style: const TextStyle(fontSize: 11.5, height: 1.4),
            onChanged: (x) => set(key, x.split(RegExp(r'[\s,;]+')).where((e) => e.isNotEmpty).toList()),
          ),
        ]),
      );

  Widget _secret(String key, String title, String help) {
    final ctl = secretCtl.putIfAbsent(key, () => TextEditingController());
    final hint = s!.secrets[key] ?? '';
    final removing = patch[key] == '';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(title, style: const TextStyle(fontSize: 12.5))),
          Text(removing ? 'verrà rimossa' : (hint.isEmpty ? 'non impostata' : 'impostata $hint'),
              style: TextStyle(fontSize: 11, color: removing ? accent : (hint.isEmpty ? dim : const Color(0xFF7EE787)))),
          if (hint.isNotEmpty && !removing)
            TextButton(
              onPressed: () {
                ctl.clear();
                set(key, '');
              },
              child: const Text('rimuovi', style: TextStyle(fontSize: 11)),
            ),
        ]),
        Text(help, style: const TextStyle(fontSize: 11, color: dim)),
        TextField(
          controller: ctl,
          obscureText: true,
          style: const TextStyle(fontSize: 12),
          decoration: InputDecoration(hintText: hint.isEmpty ? 'incolla la chiave' : 'incolla per sostituirla'),
          onChanged: (x) => x.isEmpty ? setState(() => patch.remove(key)) : set(key, x),
        ),
      ]),
    );
  }

  Widget _page(List<Widget> children) => ListView(padding: const EdgeInsets.fromLTRB(24, 4, 24, 16), children: children);

  // ---------------- tabs ----------------

  Widget _general() => _page([
        _section('Nuove ricerche'),
        _num('default_depth', 'Profondità predefinita', 'Quanti passi seguire i dati trovati (0-4).'),
        _num('default_max_entities', 'Limite di entità per ricerca', 'La ricerca smette di seguire nuovi dati oltre questo numero.'),
        _section('Gestione dei dati'),
        _switch('passive_only', 'Solo fonti passive', 'Non contattare i server del bersaglio: salta sito web, porta TLS e prove di nomi DNS. Le altre fonti restano attive.'),
        _switch('fetch_avatars', 'Scarica le immagini profilo', 'Serve a confrontare le foto tra profili. Disattivandolo non vengono scaricate né salvate immagini.'),
        _num('cache_ttl_hours', 'Validità della cache', 'Per quante ore riusare un risultato già ottenuto (0 = rifai sempre le richieste).', suffix: 'ore'),
        _lines('ignored_domains', 'Domini da non tracciare', 'Provider di posta pubblici e simili (gmail.com, outlook.com…): i loro indirizzi vengono cercati, ma il dominio non viene analizzato. Un dominio scelto come seed viene sempre cercato.'),
        _num('group_min', 'Raggruppa nodi da', 'Numero minimo di nodi simili che il grafo unisce in un gruppo.'),
        _section('Rete'),
        _num('concurrency', 'Richieste in parallelo', 'Più alto è più veloce ma più facile essere bloccati dai siti.'),
        _num('http_timeout', 'Timeout richieste', 'Attesa massima per una risposta.', suffix: 'sec'),
        _text('user_agent', 'User-Agent', 'Identità inviata ai siti interrogati.'),
        _text('proxy', 'Proxy', 'Per esempio socks5://127.0.0.1:9050 (Tor) o http://host:porta. Vale per le fonti web e per Maigret; le query DNS non passano dal proxy.',
            hint: 'vuoto = connessione diretta'),
        _section('Ricerca sui social'),
        _switch('auto_username_from_email', 'Da un\'email, cerca lo username', 'Segue la parte prima della @ (se sembra personale, per esempio mario.rossi) e controlla centinaia di siti e social con Maigret.'),
        _switch('auto_username_from_name', 'Da un nome, prova gli username probabili', 'Per «Mario Rossi» prova mariorossi, mario.rossi, mrossi… Dà molti falsi positivi e ogni tentativo richiede circa un minuto.'),
        _section('Scansione username (Maigret)'),
        _num('maigret_top_sites', 'Siti controllati', 'Più siti = più risultati e più tempo.'),
        _num('maigret_timeout', 'Timeout per sito', '', suffix: 'sec'),
      ]);

  Widget _sources() {
    final disabled = <String>{...(v('disabled_collectors') as List).cast<String>()};
    final q = filter.toLowerCase();
    final rows = collectors.where((c) => q.isEmpty || c.name.contains(q) || c.accepts.any((t) => t.toLowerCase().contains(q))).toList()
      ..sort((a, b) => a.name.compareTo(b.name));
    Widget chip(String t, Color c) => Container(
          margin: const EdgeInsets.only(left: 6),
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(border: Border.all(color: c.withValues(alpha: 0.6)), borderRadius: BorderRadius.circular(3)),
          child: Text(t, style: TextStyle(fontSize: 9.5, color: c)),
        );
    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(24, 12, 24, 4),
        child: Row(children: [
          Expanded(child: TextField(decoration: const InputDecoration(hintText: 'cerca fonte o tipo', prefixIcon: Icon(Icons.search, size: 16)), onChanged: (x) => setState(() => filter = x))),
          const SizedBox(width: 12),
          Text('${collectors.length - disabled.length} attive su ${collectors.length}', style: const TextStyle(fontSize: 11, color: dim)),
          TextButton(onPressed: () => set('disabled_collectors', <String>[]), child: const Text('abilita tutte', style: TextStyle(fontSize: 11))),
        ]),
      ),
      Expanded(
        child: ListView(padding: const EdgeInsets.symmetric(horizontal: 24), children: [
          for (final c in rows)
            SwitchListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              value: !disabled.contains(c.name),
              onChanged: (on) => set('disabled_collectors', (on ? (disabled..remove(c.name)) : (disabled..add(c.name))).toList()..sort()),
              title: Row(children: [
                Text(c.name, style: const TextStyle(fontSize: 12.5)),
                if (c.active) chip('contatta il bersaglio', accent),
                if (c.key != null) chip('richiede chiave', c.status == 'nokey' ? dim : const Color(0xFF7EE787)),
              ]),
              subtitle: Text(c.accepts.join(' · '), style: const TextStyle(fontSize: 10.5, color: dim)),
            ),
        ]),
      ),
    ]);
  }

  Future<void> _test(String provider) async {
    setState(() {
      testing.add(provider);
      tests.remove(provider);
    });
    try {
      final r = await testConnection(provider);
      if (mounted) setState(() => tests[provider] = r);
    } catch (e) {
      if (mounted) setState(() => tests[provider] = (false, e.toString().replaceFirst('Exception: ', '')));
    } finally {
      if (mounted) setState(() => testing.remove(provider));
    }
  }

  /// One service: its credential fields, whether they are set, and a button that tries them for real.
  Widget _provider(String id, String title, String help, List<(String, String)> keys) {
    final set_ = keys.every((k) => (s!.secrets[k.$1] ?? '').isNotEmpty);
    final t = tests[id];
    return Container(
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
      decoration: BoxDecoration(border: Border.all(color: line), borderRadius: BorderRadius.circular(6)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(width: 7, height: 7, decoration: BoxDecoration(color: set_ ? const Color(0xFF7EE787) : dim, shape: BoxShape.circle)),
          const SizedBox(width: 8),
          Expanded(child: Text(title, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600))),
          if (testing.contains(id))
            const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
          else
            TextButton(
              onPressed: set_ && patch.isEmpty ? () => _test(id) : null,
              child: const Text('PROVA', style: TextStyle(fontSize: 11, letterSpacing: 1)),
            ),
        ]),
        Text(help, style: const TextStyle(fontSize: 11, color: dim, height: 1.4)),
        for (final k in keys) _secret(k.$1, k.$2, ''),
        if (t != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(t.$1 ? '✓ ${t.$2}' : '✗ ${t.$2}', style: TextStyle(fontSize: 11, color: t.$1 ? const Color(0xFF7EE787) : accent)),
          ),
      ]),
    );
  }

  Widget _keys() => _page([
        const Padding(
          padding: EdgeInsets.only(top: 12),
          child: Text(
              'Qui colleghi i tuoi account alle API ufficiali delle piattaforme: le ricerche vengono fatte a nome tuo, entro i limiti e i termini del servizio. '
              'Facebook, Instagram e LinkedIn non offrono un\'API per cercare persone e vietano l\'accesso automatico con un account, quindi per quelli usa i '
              'pulsanti CERCA SU del pannello dettaglio: aprono la ricerca nel tuo browser, dove sei già collegato.',
              style: TextStyle(fontSize: 11.5, color: dim, height: 1.45)),
        ),
        const Padding(
          padding: EdgeInsets.only(top: 6),
          child: Text('Le credenziali restano sul tuo computer, nel database locale, non cifrate.', style: TextStyle(fontSize: 11.5, color: dim)),
        ),
        _section('Account collegati'),
        _provider('github', 'GitHub', 'Token personale senza permessi: porta il limite da 60 a 5000 richieste l\'ora.', [('github_token', 'token')]),
        _provider('reddit', 'Reddit', 'Crea un\'app «script» su reddit.com/prefs/apps. Profilo, anzianità, karma e community in cui è attivo.',
            [('reddit_client_id', 'client id'), ('reddit_client_secret', 'client secret')]),
        _provider('twitch', 'Twitch', 'App su dev.twitch.tv/console. Profilo, descrizione, data di creazione, tipo di canale.',
            [('twitch_client_id', 'client id'), ('twitch_client_secret', 'client secret')]),
        _provider('youtube', 'YouTube', 'Chiave API di Google Cloud (YouTube Data API v3, quota gratuita). Canale per handle: paese, descrizione, data di creazione.', [('youtube_key', 'chiave API')]),
        _provider('spotify', 'Spotify', 'App su developer.spotify.com. Profilo pubblico di un utente per id.',
            [('spotify_client_id', 'client id'), ('spotify_client_secret', 'client secret')]),
        _provider('x', 'X (Twitter)', 'Bearer token dell\'API v2 (richiede un piano a pagamento). Profilo, bio, luogo, sito, data di creazione.', [('x_bearer', 'bearer token')]),
        _section('Fonti con chiave'),
        _provider('virustotal', 'VirusTotal', 'Sottodomini, risoluzioni storiche e reputazione di domini e IP (piano gratuito).', [('virustotal_key', 'chiave')]),
        _provider('shodan', 'Shodan', 'Porte, banner e vulnerabilità degli IP oltre ai dati gratuiti di InternetDB.', [('shodan_key', 'chiave')]),
        _provider('hunter', 'Hunter.io', 'Email e formato degli indirizzi di un dominio.', [('hunter_key', 'chiave')]),
        _provider('hibp', 'Have I Been Pwned', 'Breach con data e tipo di dati esposti per ogni email.', [('hibp_key', 'chiave')]),
        _provider('securitytrails', 'SecurityTrails', 'Elenco sottodomini.', [('securitytrails_key', 'chiave')]),
        _provider('abuseipdb', 'AbuseIPDB', 'Reputazione e segnalazioni di un IP.', [('abuseipdb_key', 'chiave')]),
        _provider('greynoise', 'GreyNoise (community)', 'Dice se un IP fa scansioni di massa o è un servizio noto e benigno.', [('greynoise_key', 'chiave')]),
        _provider('otx', 'AlienVault OTX', 'DNS passivo storico di domini e IP (account gratuito).', [('otx_key', 'chiave')]),
        _provider('abusech', 'abuse.ch (URLhaus)', 'URL malevoli associati a un dominio o IP (account gratuito).', [('abusech_key', 'chiave')]),
        _provider('companieshouse', 'Companies House (UK)', 'Società e amministratori del registro imprese britannico (chiave gratuita).', [('companieshouse_key', 'chiave')]),
      ]);

  Widget _ai() {
    final exe = Backend.bundled();
    final dirPath = widget.backend.dir()?.path ?? '<percorso>/backend';
    final server = exe != null
        ? {'command': exe.path, 'args': ['--mcp']} // packaged app: the bundled executable doubles as the MCP server
        : {'command': 'uv', 'args': ['run', '--directory', dirPath, '--extra', 'mcp', 'python', '-m', 'osint.mcp_server']};
    final snippet = const JsonEncoder.withIndent('  ').convert({'mcpServers': {'osint-fire': server}});
    final provider = v('ai_provider') as String;
    return _page([
      _section('Connettore AI integrato'),
      const Text(
          'Il grafo dell\'indagine (entità, relazioni, collegamenti) viene inviato al provider scelto per riassunti, verifiche e suggerimenti. '
          'Con un modello locale (per esempio Ollama) i dati non lasciano il computer.',
          style: TextStyle(fontSize: 11.5, color: dim, height: 1.4)),
      const SizedBox(height: 10),
      DropdownButtonFormField<String>(
        initialValue: provider,
        dropdownColor: const Color(0xFF131316),
        decoration: const InputDecoration(labelText: 'Provider'),
        items: const [
          DropdownMenuItem(value: 'anthropic', child: Text('Anthropic (Claude)', style: TextStyle(fontSize: 12))),
          DropdownMenuItem(value: 'openai', child: Text('Compatibile OpenAI (OpenAI, Ollama, LM Studio, OpenRouter…)', style: TextStyle(fontSize: 12))),
        ],
        onChanged: (x) => set('ai_provider', x),
      ),
      _text('ai_model', 'Modello', provider == 'anthropic' ? 'Per esempio claude-sonnet-5-5.' : 'Per esempio gpt-4o-mini o llama3.1.'),
      _text('ai_base_url', 'Indirizzo del servizio', provider == 'anthropic' ? 'Lascia vuoto per il servizio Anthropic.' : 'Vuoto = OpenAI. Per Ollama: http://localhost:11434/v1',
          hint: 'facoltativo'),
      _secret('ai_key', 'Chiave API', provider == 'openai' ? 'Con un servizio locale può restare vuota.' : 'Obbligatoria per Anthropic.'),
      Align(
        alignment: Alignment.centerLeft,
        child: Row(children: [
          TextButton(onPressed: patch.isEmpty && !testing.contains('ai') ? () => _test('ai') : null, child: const Text('PROVA LA CONNESSIONE', style: TextStyle(fontSize: 11, letterSpacing: 1))),
          if (tests['ai'] != null)
            Expanded(child: Text(tests['ai']!.$1 ? '✓ ${tests['ai']!.$2}' : '✗ ${tests['ai']!.$2}', style: TextStyle(fontSize: 11, color: tests['ai']!.$1 ? const Color(0xFF7EE787) : accent))),
        ]),
      ),
      _switch('ai_send_notes', 'Invia le mie note private', 'Le note e le stelle che hai messo ai nodi vengono incluse nel contesto.'),
      _num('ai_max_entities', 'Entità massime inviate', 'Il grafo viene ridotto alle più collegate (e ai preferiti) oltre questo numero.'),
      _section('Connettore MCP (per Claude Desktop e altri agenti)'),
      const Text(
          'Permette a un assistente AI di avviare e leggere le indagini di OSINT-Fire mentre l\'app è aperta. '
          'Aggiungi questo blocco alla configurazione MCP del tuo client.',
          style: TextStyle(fontSize: 11.5, color: dim, height: 1.4)),
      const SizedBox(height: 8),
      Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: const Color(0x66000000), border: Border.all(color: line), borderRadius: BorderRadius.circular(6)),
        child: SelectableText(snippet, style: const TextStyle(fontSize: 11, height: 1.4)),
      ),
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          icon: const Icon(Icons.copy, size: 14),
          label: const Text('Copia configurazione', style: TextStyle(fontSize: 11.5)),
          onPressed: () async {
            await Clipboard.setData(ClipboardData(text: snippet));
            if (mounted) setState(() => notice = 'Configurazione MCP copiata');
          },
        ),
      ),
    ]);
  }

  Widget _data() {
    String size(num b) => b > 1e6 ? '${(b / 1e6).toStringAsFixed(1)} MB' : '${(b / 1e3).toStringAsFixed(0)} kB';
    Future<void> run(Future<String> Function() f) async {
      try {
        final msg = await f();
        final st = await maintenanceStats();
        if (mounted) {
          setState(() {
            stats = st;
            notice = msg;
            error = null;
          });
        }
      } catch (e) {
        if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
      }
    }

    Widget stat(String l, Object? x) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(children: [Expanded(child: Text(l, style: const TextStyle(fontSize: 12, color: dim))), Text('$x', style: const TextStyle(fontSize: 12))]),
        );
    Widget action(String title, String help, String label, VoidCallback onTap) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: const TextStyle(fontSize: 12.5)),
                Text(help, style: const TextStyle(fontSize: 11, color: dim)),
              ]),
            ),
            OutlinedButton(onPressed: onTap, child: Text(label, style: const TextStyle(fontSize: 11.5))),
          ]),
        );

    return _page([
      _section('Archivio locale'),
      stat('Percorso', stats['path']),
      stat('Dimensione', size(stats['size'] ?? 0)),
      stat('Ricerche', stats['investigations']),
      stat('Entità', stats['entities']),
      stat('Evidenze', stats['evidence']),
      stat('Risultati in cache', stats['cache_entries']),
      stat('Immagini', stats['images']),
      stat('Note', stats['notes']),
      _section('Manutenzione'),
      action('Svuota la cache', 'Cancella i risultati riusabili: la prossima ricerca rifà tutte le richieste.', 'SVUOTA',
          () => run(() async => 'Cache svuotata (${await clearCache()} voci)')),
      action('Compatta il database', 'Libera lo spazio lasciato dai dati cancellati.', 'COMPATTA', () => run(() async {
            await vacuumDb();
            return 'Database compattato';
          })),
      action('Backup completo', 'Salva in Download una copia di ricerche, note e impostazioni (comprese le chiavi API).', 'SALVA COPIA', () => run(() async {
            final path = '${downloadsDir()}/osint-fire-backup-${DateTime.now().millisecondsSinceEpoch ~/ 1000}.db';
            await File(path).writeAsBytes(await backupBytes());
            return 'Backup salvato: $path';
          })),
      _section('Zona pericolosa'),
      Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(border: Border.all(color: accent.withValues(alpha: 0.5)), borderRadius: BorderRadius.circular(6)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Elimina tutte le ricerche', style: TextStyle(fontSize: 12.5, color: accent)),
          const Text('Cancella ricerche, grafi, evidenze, note, immagini e cache. Le impostazioni restano. Non si può annullare.', style: TextStyle(fontSize: 11, color: dim)),
          Row(children: [
            Expanded(child: TextField(decoration: const InputDecoration(hintText: 'scrivi ELIMINA per confermare'), onChanged: (x) => setState(() => wipeWord = x))),
            const SizedBox(width: 12),
            OutlinedButton(
              style: OutlinedButton.styleFrom(foregroundColor: accent, side: const BorderSide(color: accent)),
              onPressed: wipeWord == 'ELIMINA'
                  ? () => run(() async {
                        final n = await wipeAll(wipeWord);
                        wipeWord = '';
                        saved = true;
                        return 'Eliminate $n ricerche';
                      })
                  : null,
              child: const Text('ELIMINA TUTTO', style: TextStyle(fontSize: 11.5)),
            ),
          ]),
        ]),
      ),
    ]);
  }
}

class _NumField extends StatefulWidget {
  const _NumField({super.key, required this.initial, required this.onChanged, this.suffix});
  final String initial;
  final String? suffix;
  final void Function(int?) onChanged;

  @override
  State<_NumField> createState() => _NumFieldState();
}

class _NumFieldState extends State<_NumField> {
  late final ctl = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    ctl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(
        controller: ctl,
        keyboardType: TextInputType.number,
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        textAlign: TextAlign.end,
        style: const TextStyle(fontSize: 12.5),
        decoration: InputDecoration(suffixText: widget.suffix),
        onChanged: (x) => widget.onChanged(int.tryParse(x)),
      );
}
