import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/ai_dialog.dart';
import 'package:osint_fire/flags.dart';
import 'package:osint_fire/l10n.dart';
import 'package:osint_fire/api.dart';
import 'package:osint_fire/backend.dart';
import 'package:osint_fire/settings_dialog.dart';
import 'package:osint_fire/theme.dart';

Settings _settings() => Settings({
      'default_depth': 2, 'default_max_entities': 300, 'cache_ttl_hours': 24, 'fetch_avatars': true, 'passive_only': false, 'auto_username_from_email': true, 'auto_username_from_name': false,
      'disabled_collectors': <String>[], 'ignored_domains': <String>['gmail.com', 'outlook.com'], 'concurrency': 8, 'http_timeout': 15, 'user_agent': 'OSINT-Fire/0.1', 'proxy': '',
      'maigret_top_sites': 300, 'maigret_timeout': 8, 'group_min': 6, 'ai_provider': 'anthropic', 'ai_base_url': '',
      'ai_model': 'claude-sonnet-5-5', 'ai_send_notes': false, 'ai_max_entities': 400,
    }, {'github_token': '••••1234', 'virustotal_key': '', 'shodan_key': '', 'hunter_key': '', 'hibp_key': '', 'securitytrails_key': '', 'abuseipdb_key': '', 'ai_key': ''});

final _collectors = [
  CollectorInfo('dns', ['Dominio'], false, null, 'ok'),
  CollectorInfo('web_page', ['Dominio'], true, null, 'ok'),
  CollectorInfo('virustotal_domain', ['Dominio'], false, 'virustotal_key', 'nokey'),
  CollectorInfo('github_user', ['Username'], false, null, 'ok'),
];

Future<void> _open(WidgetTester tester, Widget dialog) async {
  tester.view.physicalSize = const Size(1280, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: Scaffold(body: Builder(builder: (c) => TextButton(onPressed: () => showDialog(context: c, builder: (_) => dialog), child: const Text('apri'))))));
  await tester.tap(find.text('apri'));
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() => appLang.value = 'it');
  testWidgets('settings: language selector offers the four languages with flags', (tester) async {
    await _open(tester, SettingsDialog(backend: Backend(), initial: _settings(), initialCollectors: _collectors, initialStats: const {'size': 1, 'investigations': 0}));
    for (final n in ['Italiano', 'English', 'Español', 'Deutsch']) {
      expect(find.widgetWithText(ChoiceChip, n), findsOneWidget);
    }
    expect(find.byType(FlagIcon), findsNWidgets(4));
    expect(tester.widget<ChoiceChip>(find.widgetWithText(ChoiceChip, 'Italiano')).selected, isTrue);
  });

  testWidgets('settings: edits are collected, sources can be toggled, secrets are masked', (tester) async {
    await _open(tester, SettingsDialog(backend: Backend(), initial: _settings(), initialCollectors: _collectors, initialStats: const {'size': 2500000, 'investigations': 3}));
    expect(find.text('IMPOSTAZIONI'), findsOneWidget);
    expect(find.text('SALVA'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull); // nothing to save yet

    await tester.tap(find.widgetWithText(SwitchListTile, 'Solo fonti passive'));
    await tester.pump();
    expect(find.text('1 modifiche non salvate'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNotNull);

    await tester.dragUntilVisible(find.text('Domini da non tracciare'), find.byType(ListView).last, const Offset(0, -150));
    expect(find.text('gmail.com\noutlook.com'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextFormField, 'gmail.com\noutlook.com'), 'gmail.com, @Corp.com\nmail.test');
    await tester.pump();
    expect(find.text('2 modifiche non salvate'), findsOneWidget); // passive_only + ignored_domains

    await tester.tap(find.text('Fonti'));
    await tester.pumpAndSettle();
    expect(find.text('3 attive su 4'), findsNothing); // 4 enabled, none disabled yet
    expect(find.text('4 attive su 4'), findsOneWidget);
    expect(find.text('contatta il bersaglio'), findsOneWidget); // web_page is active
    expect(find.text('richiede chiave'), findsOneWidget);
    await tester.tap(find.widgetWithText(SwitchListTile, 'dns'));
    await tester.pump();
    expect(find.text('3 attive su 4'), findsOneWidget);
    expect(find.text('3 modifiche non salvate'), findsOneWidget);
    await tester.enterText(find.byType(TextField).first, 'username'); // filter by seed type
    await tester.pump();
    expect(find.widgetWithText(SwitchListTile, 'github_user'), findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'dns'), findsNothing);

    await tester.tap(find.text('Chiavi API'));
    await tester.pumpAndSettle();
    expect(find.text('impostata ••••1234'), findsOneWidget);
    expect(find.textContaining('ghp_'), findsNothing);
    expect(find.text('Account collegati'.toUpperCase()), findsOneWidget);
    expect(find.text('Reddit'), findsOneWidget);
    expect(find.textContaining('vietano l\'accesso automatico'), findsOneWidget); // why Facebook/Instagram/LinkedIn are not connectors
    // "PROVA" needs saved credentials: with unsaved edits every test button is disabled
    expect(tester.widget<TextButton>(find.widgetWithText(TextButton, 'PROVA').first).onPressed, isNull);

    await tester.tap(find.text('AI'));
    await tester.pumpAndSettle();
    await tester.dragUntilVisible(find.textContaining('osint.mcp_server'), find.byType(ListView).last, const Offset(0, -200));
    expect(find.textContaining('osint.mcp_server'), findsOneWidget); // MCP config snippet
    await tester.tap(find.text('Dati'));
    await tester.pumpAndSettle();
    expect(find.text('2.5 MB'), findsOneWidget);
    await tester.dragUntilVisible(find.text('ELIMINA TUTTO'), find.byType(ListView).last, const Offset(0, -200));
    expect(tester.widget<OutlinedButton>(find.widgetWithText(OutlinedButton, 'ELIMINA TUTTO')).onPressed, isNull);
    await tester.enterText(find.widgetWithText(TextField, '').last, 'ELIMINA');
    await tester.pump();
    expect(tester.widget<OutlinedButton>(find.widgetWithText(OutlinedButton, 'ELIMINA TUTTO')).onPressed, isNotNull);
  });

  testWidgets('AI dialog: not configured points to settings, configured enables the tasks', (tester) async {
    await _open(tester, AiDialog(inv: 1, initialStatus: AiStatus(false, 'chiave API non impostata', 'anthropic', 'm')));
    expect(find.textContaining('chiave API non impostata'), findsOneWidget);
    expect(find.text('CONFIGURA'), findsOneWidget);
    expect(tester.widget<OutlinedButton>(find.widgetWithText(OutlinedButton, 'RIASSUNTO')).onPressed, isNull);

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    await tester.tap(find.text('apri'));
    await tester.pumpAndSettle();
  });

  testWidgets('AI dialog configured', (tester) async {
    await _open(tester, AiDialog(inv: 1, initialStatus: AiStatus(true, '', 'anthropic', 'claude-sonnet-5-5')));
    expect(find.textContaining('anthropic · claude-sonnet-5-5'), findsOneWidget);
    expect(find.text('CONFIGURA'), findsNothing);
    expect(tester.widget<OutlinedButton>(find.widgetWithText(OutlinedButton, 'RIASSUNTO')).onPressed, isNotNull);
    expect(find.textContaining('scegli un\'analisi'), findsOneWidget);
  });
}
