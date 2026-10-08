import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api_report.dart';
import 'package:osint_fire/l10n.dart';
import 'package:osint_fire/report_dialog.dart';
import 'package:osint_fire/theme.dart';

final _png = Uint8List.fromList([0x89, 0x50, 0x4E, 0x47, 1, 2, 3]);

class _Rig {
  final requests = <ReportOptions>[];
  final saved = <String>[];
  Object? failWith;
  String? popped;

  Future<void> open(WidgetTester tester, {bool hasHidden = false}) async {
    tester.view.physicalSize = const Size(1280, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(),
      home: Scaffold(
        body: Builder(
          builder: (c) => TextButton(
            onPressed: () async => popped = await showDialog<String>(
              context: c,
              builder: (_) => ReportDialog(
                inv: 7,
                defaultTitle: 'Case 7',
                hasHidden: hasHidden,
                build: (inv, o) async {
                  requests.add(o);
                  if (failWith != null) throw failWith!;
                  return Uint8List.fromList([1]);
                },
                save: (name, bytes) async {
                  saved.add(name);
                  return '/x/$name';
                },
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
  }
}

Future<void> _logo(WidgetTester tester, String path) async {
  await tester.enterText(find.widgetWithText(TextField, 'Path of a PNG or JPEG file (max 1 MB)'), path);
  await tester.pump();
}

void main() {
  setUp(resetReportMemory);
  tearDown(() => appLang.value = 'en');

  test('ReportOptions.toJson', () {
    final j = ReportOptions(format: 'pdf', sections: ['summary', 'notes'], title: 'T', lang: 'de').toJson();
    expect(j['format'], 'pdf');
    expect(j['sections'], ['summary', 'notes']);
    expect(j['lang'], 'de');
    expect(j['include_hidden'], false);
    expect(j.containsKey('logo'), false);
    expect(ReportOptions(logoBase64: 'QQ==').toJson()['logo'], 'QQ==');
    expect(ReportOptions().toJson()['sections'], reportSections);
  });

  testWidgets('defaults, then a request with fewer sections and the saved name', (tester) async {
    final r = _Rig();
    await r.open(tester);
    expect(find.text('Include hidden items'), findsNothing);
    await tester.tap(find.text('Timeline'));
    await tester.tap(find.text('Markdown'));
    await tester.pump();
    await tester.tap(find.text('Create'));
    await tester.pumpAndSettle();
    final o = r.requests.single;
    expect(o.format, 'md');
    expect(o.sections, reportSections.where((s) => s != 'timeline'));
    expect(o.title, 'Case 7');
    expect(o.lang, 'en');
    expect(r.saved.single, 'Case 7.md');
    expect(r.popped, '/x/Case 7.md');
  });

  testWidgets('defaults are all sections and html', (tester) async {
    final r = _Rig();
    await r.open(tester, hasHidden: true);
    expect(find.text('Include hidden items'), findsOneWidget);
    await tester.tap(find.text('Create'));
    await tester.pumpAndSettle();
    expect(r.requests.single.sections, reportSections);
    expect(r.requests.single.format, 'html');
  });

  testWidgets('logo: wrong type, too big, valid', (tester) async {
    final r = _Rig();
    await r.open(tester);
    final dir = Directory.systemTemp.createTempSync();
    addTearDown(() => dir.deleteSync(recursive: true));
    final txt = File('${dir.path}/a.png')..writeAsBytesSync([1, 2, 3]);
    final big = File('${dir.path}/b.png')..writeAsBytesSync([..._png, ...List.filled(maxLogoBytes, 0)]);
    final ok = File('${dir.path}/c.png')..writeAsBytesSync(_png);
    await _logo(tester, txt.path);
    expect(find.text('The logo must be a PNG or JPEG image'), findsOneWidget);
    await _logo(tester, big.path);
    expect(find.text('The logo is larger than 1 MB'), findsOneWidget);
    await _logo(tester, ok.path);
    expect(find.textContaining('The logo'), findsNothing);
    await tester.tap(find.text('Create'));
    await tester.pumpAndSettle();
    expect(r.requests.single.logoBase64, base64Encode(_png));
  });

  testWidgets('build error is shown and the dialog stays open', (tester) async {
    final r = _Rig()..failWith = Exception('boom');
    await r.open(tester);
    await tester.tap(find.text('Create'));
    await tester.pumpAndSettle();
    expect(find.textContaining('boom'), findsOneWidget);
    expect(r.saved, isEmpty);
    expect(find.text('Custom report'), findsOneWidget);
  });

  group('italian', () {
    setUpAll(() => appLang.value = 'it');
    tearDownAll(() => appLang.value = 'en');

    testWidgets('dialog is translated and report language follows the app', (tester) async {
      final r = _Rig();
      await r.open(tester);
      expect(find.text('Report personalizzato'), findsOneWidget);
      expect(find.text('Crea'), findsOneWidget);
      await tester.tap(find.text('Crea'));
      await tester.pumpAndSettle();
      expect(r.requests.single.lang, 'it');
    });
  });
}
