import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api_ops.dart';
import 'package:osint_fire/monitor_control.dart';
import 'package:osint_fire/theme.dart';

void main() {
  test('Alert.fromJson reads the contract', () {
    final a = Alert.fromJson({
      'id': 3, 'inv': 7, 'name': 'Acme', 'ts': 1700000000.5, 'entities': 4, 'relations': 2, 'seen': false,
      'summary': [{'type': 'Dominio', 'value': 'a.it', 'type_label': 'Domain', 'label': 'a.it'}],
    });
    expect((a.id, a.inv, a.name, a.entities, a.relations, a.seen), (3, 7, 'Acme', 4, 2, false));
    expect(a.summary.single.type, 'Domain');
    expect(a.summary.single.label, 'a.it');
  });

  testWidgets('selector offers the intervals and reports the choice', (tester) async {
    final saved = <(int, int)>[];
    int? changed;
    await tester.pumpWidget(MaterialApp(
        theme: buildTheme(),
        home: Scaffold(body: MonitorSelector(inv: 5, initialDays: 0, save: (i, d) async => saved.add((i, d)), onChanged: (d) => changed = d))));
    expect(find.text('Off'), findsOneWidget);
    expect(find.text('Only runs while the app is open'), findsOneWidget);
    await tester.tap(find.text('Off'));
    await tester.pumpAndSettle();
    for (final l in ['every day', 'every 3 days', 'every 7 days', 'every 14 days', 'every 30 days']) {
      expect(find.text(l), findsOneWidget);
    }
    await tester.tap(find.text('every 7 days').last);
    await tester.pumpAndSettle();
    expect(saved, [(5, 7)]);
    expect(changed, 7);
  });

  testWidgets('selector reverts and shows the error when saving fails', (tester) async {
    await tester.pumpWidget(MaterialApp(
        theme: buildTheme(), home: Scaffold(body: MonitorSelector(inv: 5, initialDays: 3, save: (i, d) async => throw Exception('boom')))));
    await tester.tap(find.text('every 3 days'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('every 30 days').last);
    await tester.pumpAndSettle();
    expect(find.text('boom'), findsOneWidget);
    expect(find.text('every 3 days'), findsOneWidget);
  });
}
