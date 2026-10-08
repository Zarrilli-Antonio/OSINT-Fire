import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api_ops.dart';
import 'package:osint_fire/proofs_dialog.dart';
import 'package:osint_fire/theme.dart';

final _hash = 'ab12cd34ef56' * 5 + 'abcd';
Proof _p(int id, {String wayback = ''}) => Proof(id, 'https://example.com/p$id', 1700000000, _hash, 2048, 200, 'text/html', wayback, false, '', null);

Future<void> _show(WidgetTester tester, Widget d) async {
  await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: Scaffold(body: Builder(builder: (c) => TextButton(onPressed: () => showDialog(context: c, builder: (_) => d), child: const Text('go'))))));
  await tester.tap(find.text('go'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('save dialog: warning visible, archive off by default, returns the choice', (tester) async {
    bool? saved;
    await _show(tester, SaveProofDialog(url: 'https://example.com', save: (a) async => saved = a));
    expect(find.textContaining('sends the address to archive.org'), findsOneWidget);
    expect(tester.widget<CheckboxListTile>(find.byType(CheckboxListTile)).value, isFalse);
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pump();
    await tester.tap(find.text('SAVE PROOF'));
    await tester.pumpAndSettle();
    expect(saved, isTrue);
    expect(find.byType(SaveProofDialog), findsNothing);
  });

  testWidgets('save dialog: an error keeps the dialog open', (tester) async {
    await _show(tester, SaveProofDialog(url: 'https://example.com', save: (a) async => throw Exception('blocked')));
    await tester.tap(find.text('SAVE PROOF'));
    await tester.pumpAndSettle();
    expect(find.text('blocked'), findsOneWidget);
    expect(find.byType(SaveProofDialog), findsOneWidget);
  });

  testWidgets('list shows rows, copies the full hash, deletes after confirmation, opens links', (tester) async {
    String? copied;
    final opened = <String>[];
    final deleted = <int>[];
    await _show(
        tester,
        ProofsDialog(
          inv: 4,
          fetch: (inv, {entity}) async => [_p(1, wayback: 'https://web.archive.org/web/1/x'), _p(2)],
          delete: (i, id) async => deleted.add(id),
          open: (u) async => opened.add(u),
          copy: (s) async => copied = s,
        ));
    expect(find.text('https://example.com/p1'), findsOneWidget);
    expect(find.textContaining('HTTP 200'), findsNWidgets(2));
    expect(find.text('SHA-256 ab12cd34ef56…'), findsNWidgets(2));
    expect(find.text('WAYBACK COPY'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.copy).first);
    await tester.pump();
    expect(copied, _hash);

    await tester.tap(find.text('OPEN SNAPSHOT').first);
    await tester.tap(find.text('WAYBACK COPY'));
    expect(opened, [proofSnapshotUrl(4, 1), 'https://web.archive.org/web/1/x']);

    await tester.tap(find.text('DELETE').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(deleted, isEmpty);
    await tester.tap(find.text('DELETE').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('DELETE').last);
    await tester.pumpAndSettle();
    expect(deleted, [1]);
    expect(find.text('https://example.com/p1'), findsNothing);
  });

  testWidgets('empty state', (tester) async {
    await _show(tester, ProofsDialog(inv: 4, fetch: (inv, {entity}) async => []));
    expect(find.text('No proofs saved yet.'), findsOneWidget);
  });
}
