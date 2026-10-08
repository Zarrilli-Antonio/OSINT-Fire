import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api_archive.dart';
import 'package:osint_fire/import_archive_dialog.dart';
import 'package:osint_fire/l10n.dart';

void main() {
  late Directory dir;
  setUpAll(() => appLang.value = 'en');
  tearDownAll(() => appLang.value = 'en');
  setUp(() {
    dir = Directory.systemTemp.createTempSync('imp');
    File('${dir.path}/osint-old.json').writeAsStringSync('{"old":1}');
    File('${dir.path}/osint-old.json').setLastModifiedSync(DateTime(2020));
    File('${dir.path}/case.osint.json').writeAsStringSync('{"new":1}');
    File('${dir.path}/photo.jpg').writeAsStringSync('x');
  });
  tearDown(() => dir.deleteSync(recursive: true));

  test('findArchives lists export files newest first', () {
    expect(findArchives(dir).map((f) => f.uri.pathSegments.last), ['case.osint.json', 'osint-old.json']);
  });

  Future<void> open(WidgetTester tester, Future<ImportResult> Function(String) imp, List<Object?> out) async {
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (c) => TextButton(onPressed: () async => out.add(await showDialog(context: c, builder: (_) => ImportArchiveDialog(import: imp, downloads: dir))), child: const Text('go')),
      ),
    ));
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();
  }

  testWidgets('select a candidate, import, show result and pop the id', (tester) async {
    final out = <Object?>[], got = <String>[];
    await open(tester, (s) async {
      got.add(s);
      return ImportResult(7, 'Case', 3, 2, ['skipped one']);
    }, out);
    expect(find.text('photo.jpg'), findsNothing);
    await tester.tap(find.text('case.osint.json'));
    await tester.pump();
    await tester.tap(find.text('IMPORT'));
    await tester.pumpAndSettle();
    expect(got, ['{"new":1}']);
    expect(find.text('Imported «Case»: 3 entities, 2 relations'), findsOneWidget);
    expect(find.text('skipped one'), findsOneWidget);
    await tester.tap(find.text('OPEN'));
    await tester.pumpAndSettle();
    expect(out.single, 7);
  });

  testWidgets('a bad path and a failing import show errors in the dialog', (tester) async {
    await open(tester, (_) async => throw Exception('bad archive'), []);
    await tester.enterText(find.byType(TextField), '${dir.path}/missing.json');
    await tester.pump();
    await tester.tap(find.text('IMPORT'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Could not read the file'), findsOneWidget);
    await tester.enterText(find.byType(TextField), '${dir.path}/osint-old.json');
    await tester.pump();
    await tester.tap(find.text('IMPORT'));
    await tester.pumpAndSettle();
    expect(find.text('bad archive'), findsOneWidget);
    expect(find.text('OPEN'), findsNothing);
  });

  testWidgets('Italian labels', (tester) async {
    appLang.value = 'it';
    addTearDown(() => appLang.value = 'en');
    await open(tester, (_) async => ImportResult(1, '', 0, 0, []), []);
    expect(find.text('Importa un\'indagine'), findsOneWidget);
    expect(find.text('IMPORTA'), findsOneWidget);
  });
}
