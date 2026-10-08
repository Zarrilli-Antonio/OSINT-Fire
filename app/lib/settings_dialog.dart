import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'backend.dart';
import 'flags.dart';
import 'l10n.dart';
import 'platform.dart';
import 'theme.dart';

/// Settings in five tabs. Edits are collected in a patch and sent together with "Save"; the backend validates
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
      if (mounted) setState(() => error = t('Could not read settings: {0}', [e]));
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
        notice = t('Settings saved');
      });
    } catch (e) {
      if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
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
                      Expanded(child: Text(t('SETTINGS'), style: TextStyle(fontSize: 12, letterSpacing: 2, fontWeight: FontWeight.w700))),
                      IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context, saved)),
                    ]),
                  ),
                  TabBar(
                    isScrollable: true,
                    tabAlignment: TabAlignment.start,
                    dividerColor: line,
                    indicatorColor: accent,
                    labelColor: fg,
                    unselectedLabelColor: dim,
                    labelStyle: const TextStyle(fontSize: 12, fontFamily: mono),
                    tabs: [Tab(text: t('General')), Tab(text: t('Sources')), Tab(text: t('API keys')), const Tab(text: 'AI'), Tab(text: t('Data'))],
                  ),
                  Expanded(
                    child: TabBarView(children: [_general(), _sources(), _keys(), _ai(), _data()]),
                  ),
                  const Divider(),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 8, 20, 14),
                    child: Row(children: [
                      Expanded(
                        child: Text(error ?? notice ?? (patch.isEmpty ? '' : t('{0} unsaved changes', [patch.length])),
                            maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 11.5, color: error != null ? accent : dim)),
                      ),
                      TextButton(onPressed: () => Navigator.pop(context, saved), child: Text(t('Close'))),
                      const SizedBox(width: 8),
                      SizedBox(
                        width: 120,
                        child: FilledButton(onPressed: patch.isEmpty || saving ? null : _save, child: Text(saving ? '…' : t('SAVE'))),
                      ),
                    ]),
                  ),
                ]),
        ),
      ),
    );
  }

  // ---------------- building blocks ----------------

  Widget _section(String title) => Padding(
        padding: const EdgeInsets.only(top: 20, bottom: 4),
        child: Text(title.toUpperCase(), style: const TextStyle(fontSize: 10, letterSpacing: 1.6, color: dim)),
      );

  Widget _switch(String key, String title, String help) => SwitchListTile(
        dense: true,
        contentPadding: EdgeInsets.zero,
        title: Text(title, style: const TextStyle(fontSize: 12.5)),
        subtitle: Text(help, style: const TextStyle(fontSize: 11, color: dim)),
        value: v(key) != false, // a missing value counts as on (new settings default to on)
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
          Text(removing ? t('will be removed') : (hint.isEmpty ? t('not set') : t('set {0}', [hint])),
              style: TextStyle(fontSize: 11, color: removing ? accent : (hint.isEmpty ? dim : const Color(0xFF7EE787)))),
          if (hint.isNotEmpty && !removing)
            TextButton(
              onPressed: () {
                ctl.clear();
                set(key, '');
              },
              child: Text(t('remove'), style: TextStyle(fontSize: 11)),
            ),
        ]),
        Text(help, style: const TextStyle(fontSize: 11, color: dim)),
        TextField(
          controller: ctl,
          obscureText: true,
          style: const TextStyle(fontSize: 12),
          decoration: InputDecoration(hintText: hint.isEmpty ? t('paste the key') : t('paste to replace it')),
          onChanged: (x) => x.isEmpty ? setState(() => patch.remove(key)) : set(key, x),
        ),
      ]),
    );
  }

  Widget _page(List<Widget> children) => ListView(padding: const EdgeInsets.fromLTRB(24, 4, 24, 16), children: children);

  // ---------------- tabs ----------------

  Future<void> _pickLang(String code) async {
    final before = appLang.value;
    appLang.value = code; // immediate: the whole interface switches now
    try {
      await saveSettings({'language': code});
      saved = true;
    } catch (e) {
      appLang.value = before;
      if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    }
  }

  Widget _languagePicker() => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Wrap(spacing: 8, runSpacing: 8, children: [
          for (final code in supportedLangs)
            ChoiceChip(
              key: ValueKey('lang-$code'),
              avatar: FlagIcon(code, width: 20),
              label: Text(langNames[code]!, style: const TextStyle(fontSize: 12)),
              selected: appLang.value == code,
              showCheckmark: false,
              onSelected: (_) => _pickLang(code),
            ),
        ]),
      );

  Widget _general() => _page([
        _section(t('Language')),
        _languagePicker(),
        _section(t('New searches')),
        _num('default_depth', t('Default depth'), t('How many steps to follow the data found (0-4).')),
        _num('default_max_entities', t('Entity limit per search'), t('The search stops following new data beyond this number.')),
        _section(t('Data handling')),
        _switch('passive_only', t('Passive sources only'), t('Do not contact the target\'s servers: skips website, TLS port and DNS name guessing. Other sources stay active.')),
        _switch('fetch_avatars', t('Download profile images'), t('Used to compare photos across profiles. When off, no images are downloaded or saved.')),
        _num('cache_ttl_hours', t('Cache validity'), t('For how many hours to reuse a result already obtained (0 = always repeat the requests).'), suffix: t('hours')),
        _lines('ignored_domains', t('Domains not to track'), t('Public mail providers and the like (gmail.com, outlook.com…): their addresses are searched, but the domain is not analysed. A domain chosen as seed is always searched.')),
        _switch('monitoring', t('Monitor investigations'), t('Re-runs investigations on the schedule you set for each one and raises an alert when something new appears. Only while the app is open.')),
        _num('group_min', t('Group nodes from'), t('Minimum number of similar nodes the graph merges into one group.')),
        _section(t('Network')),
        _num('concurrency', t('Parallel requests'), t('Higher is faster but makes it easier for sites to block you.')),
        _num('http_timeout', t('Request timeout'), t('Maximum wait for a response.'), suffix: t('sec')),
        _text('user_agent', 'User-Agent', t('Identity sent to the sites queried.')),
        _text('proxy', 'Proxy', t('For example socks5://127.0.0.1:9050 (Tor) or http://host:port. Applies to web sources and Maigret; DNS queries do not go through the proxy.'),
            hint: t('empty = direct connection')),
        _section(t('Social media search')),
        _switch('auto_username_from_email', t('From an email, look up the username'), t('Follows the part before the @ (if it looks personal, for example john.smith) and checks hundreds of sites and social networks with Maigret.')),
        _switch('auto_username_from_name', t('From a name, try likely usernames'), t('For “Mario Rossi” it tries mariorossi, mario.rossi, mrossi… Gives many false positives and each attempt takes about a minute.')),
        _section(t('Username scan (Maigret)')),
        _num('maigret_top_sites', t('Sites checked'), t('More sites = more results and more time.')),
        _num('maigret_timeout', t('Timeout per site'), '', suffix: t('sec')),
      ]);

  Widget _sources() {
    final disabled = <String>{...(v('disabled_collectors') as List).cast<String>()};
    final q = filter.toLowerCase();
    final rows = collectors.where((c) => q.isEmpty || c.name.contains(q) || c.accepts.any((a) => a.toLowerCase().contains(q))).toList()
      ..sort((a, b) => a.name.compareTo(b.name));
    Widget chip(String label, Color c) => Container(
          margin: const EdgeInsets.only(left: 6),
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(border: Border.all(color: c.withValues(alpha: 0.6)), borderRadius: BorderRadius.circular(3)),
          child: Text(label, style: TextStyle(fontSize: 9.5, color: c)),
        );
    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(24, 12, 24, 4),
        child: Row(children: [
          Expanded(child: TextField(decoration: InputDecoration(hintText: t('search source or type'), prefixIcon: const Icon(Icons.search, size: 16)), onChanged: (x) => setState(() => filter = x))),
          const SizedBox(width: 12),
          Text(t('{0} active of {1}', [collectors.length - disabled.length, collectors.length]), style: const TextStyle(fontSize: 11, color: dim)),
          TextButton(onPressed: () => set('disabled_collectors', <String>[]), child: Text(t('enable all'), style: TextStyle(fontSize: 11))),
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
                if (c.active) chip(t('contacts the target'), accent),
                if (c.key != null) chip(t('requires key'), c.status == 'nokey' ? dim : const Color(0xFF7EE787)),
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
    final res = tests[id];
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
              child: Text(t('TEST'), style: TextStyle(fontSize: 11, letterSpacing: 1)),
            ),
        ]),
        Text(help, style: const TextStyle(fontSize: 11, color: dim, height: 1.4)),
        for (final k in keys) _secret(k.$1, k.$2, ''),
        if (res != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(res.$1 ? '✓ ${res.$2}' : '✗ ${res.$2}', style: TextStyle(fontSize: 11, color: res.$1 ? const Color(0xFF7EE787) : accent)),
          ),
      ]),
    );
  }

  Widget _keys() => _page([
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(
              t('Here you connect your accounts to the platforms\' official APIs: searches are made on your behalf, within the limits and terms of the service. '
                  'Facebook, Instagram and LinkedIn do not offer an API to search for people and forbid automated access with an account, so for those use the '
                  'SEARCH ON buttons in the detail panel: they open the search in your browser, where you are already signed in.'),
              style: const TextStyle(fontSize: 11.5, color: dim, height: 1.45)),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(t('Credentials stay on your computer, in the local database, unencrypted.'), style: const TextStyle(fontSize: 11.5, color: dim)),
        ),
        _section(t('Connected accounts')),
        _provider('github', 'GitHub', t('Personal token with no permissions: raises the limit from 60 to 5000 requests an hour.'), [('github_token', 'token')]),
        _provider('reddit', 'Reddit', t('Create a “script” app at reddit.com/prefs/apps. Profile, account age, karma and communities where it is active.'),
            [('reddit_client_id', 'client id'), ('reddit_client_secret', 'client secret')]),
        _provider('twitch', 'Twitch', t('App at dev.twitch.tv/console. Profile, description, creation date, channel type.'),
            [('twitch_client_id', 'client id'), ('twitch_client_secret', 'client secret')]),
        _provider('youtube', 'YouTube', t('Google Cloud API key (YouTube Data API v3, free quota). Channel by handle: country, description, creation date.'), [('youtube_key', t('api key'))]),
        _provider('spotify', 'Spotify', t('App at developer.spotify.com. Public profile of a user by id.'),
            [('spotify_client_id', 'client id'), ('spotify_client_secret', 'client secret')]),
        _provider('x', 'X (Twitter)', t('API v2 bearer token (requires a paid plan). Profile, bio, location, website, creation date.'), [('x_bearer', 'bearer token')]),
        _section(t('Sources with a key')),
        _provider('virustotal', 'VirusTotal', t('Subdomains, historical resolutions and reputation of domains and IPs (free plan).'), [('virustotal_key', t('key'))]),
        _provider('shodan', 'Shodan', t('Ports, banners and vulnerabilities of IPs, beyond the free InternetDB data.'), [('shodan_key', t('key'))]),
        _provider('hunter', 'Hunter.io', t('Emails and address format of a domain.'), [('hunter_key', t('key'))]),
        _provider('hibp', 'Have I Been Pwned', t('Breaches with date and type of data exposed for each email.'), [('hibp_key', t('key'))]),
        _provider('securitytrails', 'SecurityTrails', t('Subdomain list.'), [('securitytrails_key', t('key'))]),
        _provider('abuseipdb', 'AbuseIPDB', t('Reputation and reports of an IP.'), [('abuseipdb_key', t('key'))]),
        _provider('greynoise', 'GreyNoise (community)', t('Tells whether an IP does mass scanning or is a known, benign service.'), [('greynoise_key', t('key'))]),
        _provider('otx', 'AlienVault OTX', t('Historical passive DNS of domains and IPs (free account).'), [('otx_key', t('key'))]),
        _provider('abusech', 'abuse.ch (URLhaus)', t('Malicious URLs linked to a domain or IP (free account).'), [('abusech_key', t('key'))]),
        _provider('opencorporates', 'OpenCorporates', t('Companies and officers from company registers worldwide (optional key: raises the limits).'), [('opencorporates_key', t('key'))]),
        _provider('companieshouse', 'Companies House (UK)', t('Companies and directors from the UK business register (free key).'), [('companieshouse_key', t('key'))]),
      ]);

  Widget _ai() {
    final exe = Backend.bundled();
    final dirPath = widget.backend.dir()?.path ?? t('<path>/backend');
    final server = exe != null
        ? {'command': exe.path, 'args': ['--mcp']} // packaged app: the bundled executable doubles as the MCP server
        : {'command': 'uv', 'args': ['run', '--directory', dirPath, '--extra', 'mcp', 'python', '-m', 'osint.mcp_server']};
    final snippet = const JsonEncoder.withIndent('  ').convert({'mcpServers': {'osint-fire': server}});
    final provider = v('ai_provider') as String;
    return _page([
      _section(t('Built-in AI connector')),
      Text(
          t('The investigation graph (entities, relations, links) is sent to the chosen provider for summaries, checks and suggestions. '
              'With a local model (for example Ollama) the data does not leave your computer.'),
          style: const TextStyle(fontSize: 11.5, color: dim, height: 1.4)),
      const SizedBox(height: 10),
      DropdownButtonFormField<String>(
        initialValue: provider,
        dropdownColor: const Color(0xFF131316),
        decoration: InputDecoration(labelText: t('Provider')),
        items: [
          DropdownMenuItem(value: 'anthropic', child: Text('Anthropic (Claude)', style: TextStyle(fontSize: 12))),
          DropdownMenuItem(value: 'openai', child: Text(t('OpenAI-compatible (OpenAI, Ollama, LM Studio, OpenRouter…)'), style: const TextStyle(fontSize: 12))),
        ],
        onChanged: (x) => set('ai_provider', x),
      ),
      _text('ai_model', t('Model'), provider == 'anthropic' ? t('For example claude-sonnet-5-5.') : t('For example gpt-4o-mini or llama3.1.')),
      _text('ai_base_url', t('Service address'), provider == 'anthropic' ? t('Leave empty for the Anthropic service.') : t('Empty = OpenAI. For Ollama: http://localhost:11434/v1'),
          hint: t('optional')),
      _secret('ai_key', t('API key'), provider == 'openai' ? t('With a local service it can stay empty.') : t('Required for Anthropic.')),
      Align(
        alignment: Alignment.centerLeft,
        child: Row(children: [
          TextButton(onPressed: patch.isEmpty && !testing.contains('ai') ? () => _test('ai') : null, child: Text(t('TEST THE CONNECTION'), style: const TextStyle(fontSize: 11, letterSpacing: 1))),
          if (tests['ai'] != null)
            Expanded(child: Text(tests['ai']!.$1 ? '✓ ${tests['ai']!.$2}' : '✗ ${tests['ai']!.$2}', style: TextStyle(fontSize: 11, color: tests['ai']!.$1 ? const Color(0xFF7EE787) : accent))),
        ]),
      ),
      _switch('ai_send_notes', t('Send my private notes'), t('The notes and stars you put on nodes are included in the context.')),
      _num('ai_max_entities', t('Maximum entities sent'), t('Beyond this number the graph is reduced to the most connected (and favourite) ones.')),
      _section(t('MCP connector (for Claude Desktop and other agents)')),
      Text(
          t('Lets an AI assistant start and read OSINT-Fire investigations while the app is open. '
              'Add this block to your client\'s MCP configuration.'),
          style: const TextStyle(fontSize: 11.5, color: dim, height: 1.4)),
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
          label: Text(t('Copy configuration'), style: const TextStyle(fontSize: 11.5)),
          onPressed: () async {
            await Clipboard.setData(ClipboardData(text: snippet));
            if (mounted) setState(() => notice = t('MCP configuration copied'));
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
      _section(t('Local storage')),
      stat(t('Path'), stats['path']),
      stat(t('Size'), size(stats['size'] ?? 0)),
      stat(t('Searches'), stats['investigations']),
      stat(t('Entities'), stats['entities']),
      stat(t('Evidence'), stats['evidence']),
      stat(t('Cached results'), stats['cache_entries']),
      stat(t('Images'), stats['images']),
      stat(t('Notes'), stats['notes']),
      _section(t('Maintenance')),
      action(t('Clear the cache'), t('Deletes reusable results: the next search repeats all requests.'), t('CLEAR'),
          () => run(() async => t('Cache cleared ({0} entries)', [await clearCache()]))),
      action(t('Compact the database'), t('Frees the space left by deleted data.'), t('COMPACT'), () => run(() async {
            await vacuumDb();
            return t('Database compacted');
          })),
      action(t('Full backup'), t('Saves a copy of searches, notes and settings (including API keys) to Downloads.'), t('SAVE COPY'), () => run(() async {
            final path = '${downloadsDir()}/osint-fire-backup-${DateTime.now().millisecondsSinceEpoch ~/ 1000}.db';
            await File(path).writeAsBytes(await backupBytes());
            return t('Backup saved: {0}', [path]);
          })),
      _section(t('Danger zone')),
      Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(border: Border.all(color: accent.withValues(alpha: 0.5)), borderRadius: BorderRadius.circular(6)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(t('Delete all searches'), style: const TextStyle(fontSize: 12.5, color: accent)),
          Text(t('Deletes searches, graphs, evidence, notes, images and cache. Settings are kept. This cannot be undone.'), style: const TextStyle(fontSize: 11, color: dim)),
          Row(children: [
            Expanded(child: TextField(decoration: InputDecoration(hintText: t('type {0} to confirm', [t('DELETE')])), onChanged: (x) => setState(() => wipeWord = x))),
            const SizedBox(width: 12),
            OutlinedButton(
              style: OutlinedButton.styleFrom(foregroundColor: accent, side: const BorderSide(color: accent)),
              onPressed: wipeWord == t('DELETE')
                  ? () => run(() async {
                        final n = await wipeAll(wipeWord);
                        wipeWord = '';
                        saved = true;
                        return t('Deleted {0} searches', [n]);
                      })
                  : null,
              child: Text(t('DELETE EVERYTHING'), style: const TextStyle(fontSize: 11.5)),
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
