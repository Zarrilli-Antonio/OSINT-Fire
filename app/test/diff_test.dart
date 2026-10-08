import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/diff.dart';
import 'package:osint_fire/l10n.dart';
import 'package:osint_fire/timeline_view.dart';

const sample = {'since': 100.5, 'first_run': false, 'runs': [50, 100.5], 'nodes': [1, 2], 'edges': [7], 'summary': {'entities': 2, 'relations': 1}};

Widget app(GraphDiff d, {bool only = false, VoidCallback? toggle, VoidCallback? dismiss}) =>
    MaterialApp(home: Scaffold(body: DiffBanner(diff: d, onlyNew: only, onToggle: toggle ?? () {}, onDismiss: dismiss ?? () {})));

void main() {
  tearDown(() => appLang.value = 'en');

  test('GraphDiff.fromJson', () {
    final d = GraphDiff.fromJson(sample);
    expect(d.since, 100.5);
    expect(d.runs, [50.0, 100.5]);
    expect(d.isNewNode(2), isTrue);
    expect(d.isNewNode(3), isFalse);
    expect(d.isNewEdge(7), isTrue);
    expect((d.entities, d.relations, d.firstRun), (2, 1, false));
  });

  test('TimelineEvent.fromJson with nulls', () {
    final e = TimelineEvent.fromJson({'ts': 1, 'date': '2014-05-12', 'kind': 'manual', 'entity': null, 'related': 4, 'label': 'x', 'collector': 'rdap'});
    expect((e.entity, e.related, e.ts), (null, 4, 1.0));
  });

  testWidgets('banner text, callbacks', (tester) async {
    var toggled = 0, dismissed = 0;
    await tester.pumpWidget(app(GraphDiff.fromJson(sample), toggle: () => toggled++, dismiss: () => dismissed++));
    expect(find.text('Since the last run: +2 entities, +1 relations'), findsOneWidget);
    await tester.tap(find.text('SHOW ONLY NEW'));
    await tester.tap(find.text('DISMISS'));
    expect((toggled, dismissed), (1, 1));
  });

  testWidgets('first run and Italian', (tester) async {
    appLang.value = 'it';
    await tester.pumpWidget(app(GraphDiff.fromJson({...sample, 'first_run': true}), only: true));
    expect(find.text('Prima ricerca: tutto è nuovo'), findsOneWidget);
    expect(find.text('MOSTRA TUTTI'), findsOneWidget);
  });
}
