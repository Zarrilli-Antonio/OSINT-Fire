import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api.dart';
import 'package:osint_fire/graph_view.dart';
import 'package:osint_fire/theme.dart';

Graph _graph() => Graph(
      [for (var i = 1; i <= 20; i++) GNode(i, i.isEven ? 'Dominio' : 'Email', 'n$i.example.com')],
      [for (var i = 1; i < 20; i++) GEdge(i, i + 1, 'rel', 0.8, 'r', 'c', '')],
      [GLink(1, 1, 5, 0.5, ['s'], 'review')],
    );

void main() {
  testWidgets('drag node pins it, background drag pans, scroll zooms', (tester) async {
    tester.view.physicalSize = const Size(900, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    GNode? selected;
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(),
      home: Scaffold(body: GraphView(graph: _graph(), onSelect: (n) => selected = n)),
    ));
    for (var i = 0; i < 400; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    final s = tester.state(find.byType(GraphView)) as dynamic;
    s.fit(); // auto-fit may have run already; make it deterministic
    await tester.pump();

    final before = s.pos[7] as Offset;
    final at = s.toScreen(before) as Offset;
    await tester.dragFrom(at, const Offset(120, 60));
    await tester.pump();
    final after = s.pos[7] as Offset;
    expect(s.pinned.contains(7), isTrue);
    expect((after - before).dx, greaterThan(40));
    expect(selected, isNull); // dragging a node moves it, it does not open its description

    // pinned node stays put while the simulation keeps running
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(s.pos[7], after);

    final pan0 = s.pan as Offset;
    await tester.dragFrom(const Offset(8, 8), const Offset(50, 30));
    expect((s.pan as Offset) != pan0, isTrue);

    final scale0 = s.scale as double;
    final mouse = TestPointer(1, PointerDeviceKind.mouse);
    await tester.sendEventToBinding(mouse.hover(const Offset(450, 350)));
    await tester.sendEventToBinding(mouse.scroll(const Offset(0, -150)));
    expect(s.scale as double, greaterThan(scale0));

    // double click releases the pin
    final p = s.toScreen(s.pos[7]) as Offset;
    await tester.tapAt(p);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tapAt(p);
    await tester.pump();
    expect(s.pinned.contains(7), isFalse);
  });

  testWidgets('legend toggles a node type off and on', (tester) async {
    tester.view.physicalSize = const Size(900, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(),
      home: Scaffold(body: GraphView(graph: _graph(), onSelect: (_) {})),
    ));
    final s = tester.state(find.byType(GraphView)) as dynamic;
    await tester.tap(find.text('Email  10'));
    await tester.pump();
    expect(s.hidden.contains('Email'), isTrue);
    // a hidden node cannot be picked up
    final at = s.toScreen(s.pos[1]) as Offset; // node 1 is an Email
    expect(s.hidden.contains('Email') && (s.hit(at) == null || s.byId[s.hit(at)].type != 'Email'), isTrue);
    await tester.tap(find.text('Email  10'));
    await tester.pump();
    expect(s.hidden.isEmpty, isTrue);
    await tester.pumpWidget(const SizedBox()); // dispose the ticker before the test ends
  });

  testWidgets('saved layout is restored as it was and changes are saved back for the right investigation', (tester) async {
    tester.view.physicalSize = const Size(900, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final saved = SavedLayout(
      {for (var i = 1; i <= 20; i++) i: Offset(i * 12.0, (i % 5) * 20.0)},
      {3},
      {'scale': 1.5, 'pan': [10.0, 20.0], 'hidden': ['Email']},
    );
    final calls = <(int, List<Map<String, dynamic>>, Map<String, dynamic>)>[];
    Widget build(int id, SavedLayout lay) => MaterialApp(
          theme: buildTheme(),
          home: Scaffold(body: GraphView(graph: _graph(), layout: lay, layoutId: id, onSelect: (_) {}, onLayoutChanged: (i, n, v) => calls.add((i, n, v)))),
        );
    await tester.pumpWidget(build(7, saved));
    await tester.pump(const Duration(milliseconds: 50));
    final s = tester.state(find.byType(GraphView)) as dynamic;
    expect(s.pos[5], const Offset(60, 0));
    expect(s.pinned, {3});
    expect(s.scale, 1.5);
    expect(s.pan, const Offset(10, 20));
    expect(s.hidden, {'Email'});
    expect(s.ticker.isActive, isFalse); // same picture as last time: nothing to settle, nothing moves
    expect(calls, isEmpty);

    // moving a node schedules one save, delivered with the investigation id and the new position
    final p = s.toScreen(s.pos[2]) as Offset; // node 2 is a Dominio (visible: only Email is hidden)
    await tester.dragFrom(p, const Offset(60, 40));
    await tester.pump(const Duration(seconds: 2));
    expect(calls, hasLength(1));
    final (id, nodes, view) = calls.single;
    expect(id, 7);
    expect(nodes, hasLength(20));
    expect(nodes.firstWhere((n) => n['id'] == 2)['pinned'], isTrue);
    expect((nodes.firstWhere((n) => n['id'] == 2)['x'] as double) > 24, isTrue);
    expect(view['scale'], 1.5);
    expect(view['hidden'], ['Email']);

    // switching to another investigation flushes a pending save to the old one, then shows the new layout
    await tester.dragFrom(s.toScreen(s.pos[4]) as Offset, const Offset(30, 30));
    await tester.pumpWidget(build(8, SavedLayout({1: const Offset(500, 500)}, {}, {})));
    expect(calls.last.$1, 7);
    expect(s.pos[1], const Offset(500, 500));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a node that leaves the graph (hidden) comes back where it was; link mode only pans', (tester) async {
    tester.view.physicalSize = const Size(900, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final full = _graph();
    final without5 = Graph([for (final n in full.nodes) if (n.id != 5) n], [for (final e in full.edges) if (e.src != 5 && e.dst != 5) e]);
    final taps = <int?>[];
    Widget build(Graph g, {bool link = false, Set<int>? ghosts}) => MaterialApp(
          theme: buildTheme(),
          home: Scaffold(body: GraphView(graph: g, linkMode: link, ghostIds: ghosts, onSelect: (n) => taps.add(n?.id), onAddNode: () {}, onToggleLink: () {})),
        );
    await tester.pumpWidget(build(full));
    for (var i = 0; i < 300; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    final s = tester.state(find.byType(GraphView)) as dynamic;
    final before = s.pos[5] as Offset;
    await tester.pumpWidget(build(without5));
    expect(s.pos.containsKey(5), isFalse);
    for (var i = 0; i < 100; i++) {
      await tester.pump(const Duration(milliseconds: 16)); // the rest keeps settling while 5 is away
    }
    await tester.pumpWidget(build(full, ghosts: {5}));
    expect(((s.pos[5] as Offset) - before).distance, lessThan(3)); // not respawned at random: restored from the stash

    // link mode: dragging a node must not move or pin it, a tap still reports it
    await tester.pumpWidget(build(full, link: true));
    for (var i = 0; i < 200; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    s.fit();
    await tester.pump();
    final p = s.toScreen(s.pos[7]) as Offset;
    final start = s.pos[7] as Offset;
    await tester.dragFrom(p, const Offset(80, 0));
    expect(s.pinned.contains(7), isFalse);
    expect(s.pos[7], start);
    await tester.tapAt(s.toScreen(s.pos[7]) as Offset);
    await tester.pump(const Duration(milliseconds: 400));
    expect(taps.last, 7);
    expect(find.byTooltip('Annulla il collegamento'), findsOneWidget);
    expect(find.byTooltip('Aggiungi un nodo'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a click selects, a press-and-hold does not', (tester) async {
    tester.view.physicalSize = const Size(900, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final taps = <int?>[];
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: Scaffold(body: GraphView(graph: _graph(), onSelect: (n) => taps.add(n?.id)))));
    for (var i = 0; i < 300; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    final s = tester.state(find.byType(GraphView)) as dynamic;
    s.fit();
    await tester.pump();
    final p = s.toScreen(s.pos[9]) as Offset;
    await tester.longPressAt(p); // hold for 500 ms and release without moving
    await tester.pump(const Duration(milliseconds: 400));
    expect(taps, isEmpty);
    await tester.tapAt(p);
    await tester.pump(const Duration(milliseconds: 400));
    expect(taps, [9]);
    await tester.pumpWidget(const SizedBox());
  });
}
