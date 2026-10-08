import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api.dart';
import 'package:osint_fire/filters.dart';

Graph g() => Graph(
      [GNode(1, 'Dominio', 'a.it'), GNode(2, 'IP', '1.1.1.1'), GNode(3, 'Email', 'x@a.it'), GNode(4, 'Persona', 'Bob', const [], 0, true), GNode(5, 'Luogo', 'Rome'), GNode(6, 'Username', 'solo')],
      [
        GEdge(1, 2, 'risolve_a', 0.9, '', 'dns', '', 1),
        GEdge(1, 3, 'ha_email', 0.4, '', 'whois', '', 2),
        GEdge(1, 5, 'sede', 0.3, '', 'whois', '', 3),
        GEdge(1, 4, 'bridge', 0.1, '', 'manual', '', 4, true),
      ],
      [GLink(1, 2, 3, 0.8, [], 'auto'), GLink(2, 1, 2, 0.8, [], 'auto')],
      {3: GNote('n', false), 5: GNote('s', true)},
    );

Set<int> ids(Graph x) => {for (final n in x.nodes) n.id};

void main() {
  final cases = <(String, GraphFilters, Set<int>)>[
    ('conf 0.5 drops weak-only nodes, keeps manual and isolated', const GraphFilters(minConfidence: 0.5), {1, 2, 4, 6}),
    ('source whois', const GraphFilters(sources: {'whois'}), {1, 3, 4, 5, 6}),
    ('only notes', const GraphFilters(onlyNotes: true), {3, 4, 5}),
    ('only starred', const GraphFilters(onlyStarred: true), {4, 5}),
    ('only new', const GraphFilters(onlyNew: true), {2, 4}),
    ('tags', const GraphFilters(tags: {'Sus'}), {1, 4}),
  ];
  for (final (name, f, want) in cases) {
    test(name, () => expect(ids(applyFilters(g(), f, newNodes: {2}, tags: {1: ['sus']})), want));
  }

  test('empty filters return same graph', () {
    final x = g();
    expect(applyFilters(x, const GraphFilters()), same(x));
  });
  test('links only between survivors; edges too', () {
    final r = applyFilters(g(), const GraphFilters(minConfidence: 0.5));
    expect(r.links.map((l) => l.id), [2]);
    expect(r.edges.map((e) => e.id), [1, 4]);
    expect(r.notes, same(r.notes));
  });
  test('equality and isActive', () {
    expect(const GraphFilters().isActive, isFalse);
    expect(const GraphFilters(sources: {'a'}), const GraphFilters(sources: {'a'}));
    expect(const GraphFilters().copyWith(onlyNew: true).isActive, isTrue);
  });

  testWidgets('panel emits changes', (tester) async {
    GraphFilters f = const GraphFilters();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: StatefulBuilder(builder: (c, set) => FilterPanel(graph: g(), filters: f, tags: const ['sus'], onChanged: (v) => set(() => f = v))))));
    await tester.tap(find.byKey(const Key('src-whois')));
    await tester.pump();
    expect(f.sources, {'whois'});
    await tester.tap(find.byKey(const Key('tag-sus')));
    await tester.pump();
    expect(f.tags, {'sus'});
    await tester.tap(find.byType(Switch).first);
    await tester.pump();
    expect(f.onlyNotes, isTrue);
  });
}
