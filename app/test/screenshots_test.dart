// Renders the README pictures from fictional data (reserved domains only): no real person, no network.
//   SCREENSHOTS=1 flutter test --update-goldens test/screenshots_test.dart
// The pictures land in docs/images. Skipped in normal runs, so UI changes never break the suite because of them.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/ai_dialog.dart';
import 'package:osint_fire/api.dart';
import 'package:osint_fire/backend.dart';
import 'package:osint_fire/graph_view.dart';
import 'package:osint_fire/l10n.dart';
import 'package:osint_fire/main.dart';
import 'package:osint_fire/settings_dialog.dart';
import 'package:osint_fire/theme.dart';

const _out = '../../docs/images';
final _on = Platform.environment.containsKey('SCREENSHOTS');

Graph _demo() {
  final n = <GNode>[];
  final e = <GEdge>[];
  int id = 0;
  GNode add(String type, String value, {bool manual = false}) {
    final x = GNode(++id, type, value, const [], 1.0, manual);
    n.add(x);
    return x;
  }

  void link(GNode a, GNode b, String rel, double conf, String why, String collector, {bool manual = false}) =>
      e.add(GEdge(a.id, b.id, rel, conf, why, collector, '', e.length + 1, manual));

  final user = add('Username', 'mrossi_demo');
  final mail = add('Email', 'mario.rossi@acme-demo.test');
  final dom = add('Dominio', 'acme-demo.test');
  final pers = add('Persona', 'Mario Rossi');
  final org = add('Azienda', 'Acme Demo S.r.l.');
  link(user, mail, 'possibile_username', 0.4, 'parte locale dell\'indirizzo', 'email_username');
  link(mail, dom, 'dominio_email', 1, 'parte dopo @', 'email_domain');
  link(mail, pers, 'intestata_a', 0.6, 'nome nel profilo Gravatar', 'gravatar');
  link(dom, org, 'organizzazione_certificato', 0.85, 'campo O del certificato TLS', 'tls_cert');
  for (final (host, ip) in [('www', '203.0.113.10'), ('mail', '203.0.113.11'), ('vpn', '203.0.113.12'), ('dev', '203.0.113.13'), ('shop', '203.0.113.14')]) {
    final s = add('Dominio', '$host.acme-demo.test');
    final a = add('IP', ip);
    link(dom, s, 'sottodominio', 0.9, 'certificato TLS pubblico', 'crtsh');
    link(s, a, 'risolve_a', 0.95, 'record DNS A', 'dns');
  }
  for (final (site, url) in [('github', 'https://github.com/mrossi-demo'), ('x', 'https://x.com/mrossi_demo'), ('reddit', 'https://www.reddit.com/user/mrossi_demo'),
      ('gitlab', 'https://gitlab.com/mrossi_demo'), ('keybase', 'https://keybase.io/mrossi_demo'), ('mastodon', 'https://mastodon.social/@mrossi_demo')]) {
    final a = add('Account', url);
    link(user, a, 'account', 0.85, 'profilo su $site', site == 'x' ? 'maigret' : site);
    if (site == 'github') link(a, pers, 'nome_profilo', 0.5, 'nome nel profilo GitHub', 'github_user');
  }
  final loc = add('Luogo', 'Milano, IT');
  link(pers, loc, 'luogo_dichiarato', 0.4, 'luogo nel profilo GitHub', 'github_user');
  link(dom, add('Servizio', 'Google Workspace'), 'usa_servizio_email', 0.9, 'record SPF include', 'dns_mail');
  link(dom, add('Servizio', 'CA: Let\'s Encrypt'), 'emesso_da', 0.9, 'emittente del certificato', 'tls_cert');
  link(dom, add('Data', 'registrazione: 2014-05-12'), 'evento_dominio', 0.95, 'evento nel registro RDAP', 'rdap');
  link(dom, add('ID tracciamento', 'Google Analytics UA-0000000-1'), 'usa_tracciamento', 0.9, 'identificativo nel codice della pagina', 'web_deep');
  link(mail, add('Chiave PGP', '6AFDDB6B447170715E61'), 'chiave_pgp', 0.8, 'chiave pubblica su keyserver', 'pgp_keyserver');
  link(org, add('Telefono', '+390212345678'), 'telefono_sul_sito', 0.8, 'schema.org telephone', 'web_page');
  for (final b in ['ExampleForum 2016', 'DemoShop 2019', 'SampleCloud 2021']) {
    link(mail, add('Breach', b), 'presente_in_breach', 0.7, 'indicata in database di breach pubblico', 'xposedornot');
  }
  final ev = add('Evento', 'Meeting on 12 May', manual: true);
  link(pers, ev, 'ha partecipato a', 1, 'aggiunto manualmente', 'manuale', manual: true);

  final notes = {pers.id: GNote('Owner of the company: check the other related companies.', true)};
  final hidden = {n.firstWhere((x) => x.value == 'vpn.acme-demo.test').id, n.firstWhere((x) => x.value == '203.0.113.12').id};
  final links = [GLink(1, user.id, mail.id, 0.6, ['parte locale email uguale all\'username'], 'review'), GLink(2, pers.id, org.id, 0.78, ['stesso nome persona', 'stessa azienda'], 'auto')];
  return _english(Graph(n, e, links, notes, hidden));
}

// What the backend sends as display labels when the language is English (the stored names stay Italian).
const _types = {'Dominio': 'Domain', 'Persona': 'Person', 'Azienda': 'Company', 'Luogo': 'Place', 'Telefono': 'Phone', 'Evento': 'Event', 'Servizio': 'Service', 'Data': 'Date', 'ID tracciamento': 'Tracking ID', 'Chiave PGP': 'PGP key'};
const _rels = {
  'usa_tracciamento': 'uses tracking', 'chiave_pgp': 'PGP key', 'organizzazione_certificato': 'organisation in the certificate', 'dominio_email': 'email domain', 'presente_in_breach': 'present in breach',
  'risolve_a': 'resolves to', 'usa_servizio_email': 'uses email service', 'emesso_da': 'issued by', 'evento_dominio': 'domain event', 'ha partecipato a': 'took part in', 'telefono_sul_sito': 'phone on the website',
  'possibile_username': 'possible username', 'intestata_a': 'registered to', 'sottodominio': 'subdomain', 'luogo_dichiarato': 'declared place', 'nome_profilo': 'profile name',
};
const _why = {
  'parte dopo @': 'part after @', "parte locale dell'indirizzo": 'local part of the address', 'certificato TLS pubblico': 'public TLS certificate', 'evento nel registro RDAP': 'event in the RDAP registry',
  'identificativo nel codice della pagina': 'identifier in the page code', 'chiave pubblica su keyserver': 'public key on a keyserver', 'indicata in database di breach pubblico': 'listed in a public breach database',
  'nome nel profilo GitHub': 'name in the GitHub profile', 'record SPF include': 'SPF include record', 'campo O del certificato TLS': 'O field of the TLS certificate', 'aggiunto manualmente': 'added manually',
  'record DNS A': 'DNS A record', 'nome nel profilo Gravatar': 'name in the Gravatar profile', 'emittente del certificato': 'certificate issuer', 'luogo nel profilo GitHub': 'place in the GitHub profile',
  'schema.org telephone': 'schema.org telephone', "parte locale email uguale all'username": 'email local part equals the username', 'stesso nome persona': 'same person name', 'stessa azienda': 'same company',
};

String _w(String s) => _why[s] ?? (s.startsWith('profilo su ') ? 'profile on ${s.substring(11)}' : s);

Graph _english(Graph g) => Graph(
      [for (final x in g.nodes) GNode(x.id, x.type, x.value, x.members, x.added, x.manual, x.memberIds, x.value.startsWith('registrazione: ') ? 'registered: ${x.value.substring(15)}' : null)],
      [for (final x in g.edges) GEdge(x.src, x.dst, x.rel, x.conf, x.reason, x.collector, x.url, x.id, x.manual, _rels[x.rel] ?? x.rel, _w(x.reason))],
      [for (final l in g.links) GLink(l.id, l.a, l.b, l.score, l.signals, l.status, [for (final x in l.signals) _w(x)])],
      g.notes,
      g.hidden,
      {for (final x in g.nodes) x.type: _types[x.type] ?? x.type},
    );

Settings _settings() => Settings({
      'default_depth': 2, 'default_max_entities': 300, 'cache_ttl_hours': 24, 'fetch_avatars': true, 'passive_only': false,
      'auto_username_from_email': true, 'auto_username_from_name': false, 'disabled_collectors': <String>['wayback'],
      'ignored_domains': <String>['gmail.com', 'outlook.com'], 'concurrency': 8, 'http_timeout': 15, 'user_agent': 'OSINT-Fire/0.1', 'proxy': '',
      'maigret_top_sites': 300, 'maigret_timeout': 8, 'group_min': 6, 'ai_provider': 'anthropic', 'ai_base_url': '', 'ai_model': 'claude-sonnet-5-5',
      'ai_send_notes': false, 'ai_max_entities': 400,
    }, {for (final k in ['github_token', 'virustotal_key', 'shodan_key', 'hunter_key', 'hibp_key', 'securitytrails_key', 'abuseipdb_key', 'ai_key']) k: ''}..['github_token'] = '••••9f2a');

final _collectors = [
  for (final (name, types, active, key, status) in [
    ('dns', ['Dominio'], false, null, 'ok'), ('crtsh', ['Dominio'], false, null, 'ok'), ('wayback', ['Dominio'], false, null, 'disabled'),
    ('web_page', ['Dominio'], true, null, 'ok'), ('tls_cert', ['Dominio'], true, null, 'ok'), ('virustotal_domain', ['Dominio'], false, 'virustotal_key', 'nokey'),
    ('gravatar', ['Email'], false, null, 'ok'), ('pgp_keyserver', ['Email'], false, null, 'ok'), ('hibp', ['Email'], false, 'hibp_key', 'nokey'),
    ('maigret', ['Username'], false, null, 'ok'), ('github_user', ['Username'], false, null, 'ok'), ('keybase', ['Username'], false, null, 'ok'),
    ('reddit', ['Username'], false, 'reddit_client_id', 'nokey'), ('internetdb', ['IP'], false, null, 'ok'), ('wikidata', ['Persona', 'Azienda'], false, null, 'ok'),
  ])
    CollectorInfo(name, types, active, key, status),
];

Future<void> _loadFont(String family, List<String> candidates) async {
  for (final path in candidates) {
    final f = File(path);
    if (f.existsSync()) {
      final loader = FontLoader(family)..addFont(Future.value(ByteData.view(f.readAsBytesSync().buffer)));
      await loader.load();
      return;
    }
  }
}

/// Flutter's test environment draws every glyph as a box. Load real fonts: the machine's monospace face for the text,
/// the Material icon font from the SDK, and a wide-coverage face as the first fallback (arrows and the like).
Future<void> _fonts() async {
  final root = Platform.environment['FLUTTER_ROOT'] ?? '';
  await _loadFont('Menlo', ['/System/Library/Fonts/Monaco.ttf', r'C:\Windows\Fonts\consola.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']);
  await _loadFont('SF Mono', ['/System/Library/Fonts/Supplemental/Arial Unicode.ttf', r'C:\Windows\Fonts\arialuni.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']);
  await _loadFont('MaterialIcons', ['$root/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf']);
}

Future<void> _shoot(WidgetTester tester, Widget home, String file, {Size size = const Size(1440, 900)}) async {
  tester.view.physicalSize = size * 1.5;
  tester.view.devicePixelRatio = 1.5;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), builder: (c, child) => Backdrop(child: child!), home: home));
  await tester.runAsync(() => precacheImage(const AssetImage('assets/icon.png'), tester.element(find.byType(MaterialApp)))); // decoding happens off the fake clock
  await tester.pump();
  for (var i = 0; i < 400; i++) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  await expectLater(find.byType(MaterialApp), matchesGoldenFile('$_out/$file'));
}

void main() {
  setUpAll(() {
    appLang.value = 'en';
    return _fonts();
  });
  final skip = _on ? null : 'set SCREENSHOTS=1 to regenerate the README pictures';

  testWidgets('graph with detail panel', (tester) async {
    await _shoot(tester, Home(autostart: false, initialGraph: _demo(), initialInv: 1, initialName: 'Acme Demo', initialSeeds: const [('Username', 'mrossi_demo'), ('Dominio', 'acme-demo.test')], backendReadyForTests: true), 'graph.png');
    // pick a node the way a user would, then frame everything
    await tester.enterText(find.byWidgetPredicate((w) => w is TextField && w.decoration?.hintText == 'search the graph (⌘/Ctrl+F)'), 'Mario Rossi');
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    final gv = tester.state(find.byType(GraphView)) as dynamic;
    gv.fit();
    await tester.pump(const Duration(milliseconds: 200));
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('$_out/graph-detail.png'));
  }, skip: skip != null);

  testWidgets('split view with and without hidden nodes', (tester) async {
    await _shoot(tester, Home(autostart: false, initialGraph: _demo(), initialInv: 1, initialName: 'Acme Demo', initialSeeds: const [('Username', 'mrossi_demo'), ('Dominio', 'acme-demo.test')], backendReadyForTests: true), 'tmp.png');
    await tester.tap(find.text('SIDE BY SIDE'));
    for (var i = 0; i < 300; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('$_out/split-view.png'));
  }, skip: skip != null);

  testWidgets('settings', (tester) async {
    await _shoot(tester, SettingsDialog(backend: Backend(), initialTab: 1, initial: _settings(), initialCollectors: _collectors, initialStats: const {}), 'settings.png', size: const Size(1100, 760));
  }, skip: skip != null);

  testWidgets('AI analyst', (tester) async {
    final result = AiResult(
        'L\'indagine ruota attorno a «Mario Rossi» [4], titolare di Acme Demo S.r.l. [5].\n\n'
        '• Forte (0.85): il certificato TLS di acme-demo.test [3] riporta l\'organizzazione [5]; il dominio è collegato all\'email [2].\n'
        '• Debole (0.40): lo username mrossi_demo [1] coincide con la parte locale dell\'email [2], ma è un\'ipotesi: va verificata.\n'
        '• Esposizione: 3 breach pubblici sull\'indirizzo email; il servizio di posta è Google Workspace.\n\n'
        'Lacune: nessun profilo LinkedIn trovato e nessun dato sul telefono +390212345678 [oltre al prefisso].',
        [AiPivot('Persona', 'Mario Rossi', 'Owner of the company: look for other related companies'), AiPivot('Dominio', 'shop.acme-demo.test', 'Subdomain with an online shop, not analysed yet')]);
    await _shoot(tester, AiDialog(inv: 1, initialStatus: AiStatus(true, '', 'anthropic', 'claude-sonnet-5-5'), initialResult: result, initialTask: 'summary'), 'ai.png', size: const Size(1100, 800));
  }, skip: skip != null);
}
