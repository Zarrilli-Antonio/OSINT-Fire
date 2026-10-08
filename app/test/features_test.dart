import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api.dart';
import 'package:osint_fire/l10n.dart';
import 'package:osint_fire/graph_view.dart';
import 'package:osint_fire/main.dart';
import 'package:osint_fire/manual_dialogs.dart';
import 'package:osint_fire/theme.dart';

Graph _graph({Set<int>? hidden}) => Graph(
      [GNode(1, 'Email', 'bob@example.com'), GNode(2, 'Username', 'bob'), GNode(3, 'Dominio', 'example.com'), GNode(4, 'Account', 'https://github.com/bob')],
      [GEdge(1, 2, 'possibile_username', 0.4, 'r', 'c', ''), GEdge(1, 3, 'dominio_email', 1, 'r', 'c', ''), GEdge(2, 4, 'account', 0.9, 'r', 'c', '')],
      const [],
      null,
      hidden,
    );

final _search = find.byWidgetPredicate((w) => w is TextField && w.decoration?.hintText == 'cerca nel grafo (⌘/Ctrl+F)');

Future<void> _pump(WidgetTester tester, {Set<int>? hidden, Graph? graph}) async {
  tester.view.physicalSize = const Size(1280, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: buildTheme(),
    builder: (context, child) => Backdrop(child: child!),
    home: Home(autostart: false, initialGraph: graph ?? _graph(hidden: hidden), initialInv: 1),
  ));
  await tester.pump();
}

void main() {
  setUpAll(() => appLang.value = 'it');
  testWidgets('search counts matches, Enter selects the first, Escape clears', (tester) async {
    await _pump(tester);
    await tester.enterText(_search, 'bob');
    await tester.pump();
    expect(find.text('3 trovati'), findsOneWidget); // email, username, account all contain "bob"
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(find.text('ESPANDI · Email «bob@example.com»'), findsOneWidget); // first match (lowest id) is selected, detail panel open
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump();
    expect(find.textContaining('trovati'), findsNothing);

    await tester.enterText(_search, 'zzz');
    await tester.pump();
    expect(find.text('0 trovati'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('starring a node lists it under Preferiti', (tester) async {
    await _pump(tester);
    expect(find.text('PREFERITI'), findsNothing);
    await tester.enterText(_search, 'example.com');
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    await tester.tap(find.byTooltip('Aggiungi ai preferiti'));
    await tester.pump();
    expect(find.text('PREFERITI'), findsOneWidget);
    expect(find.byTooltip('Rimuovi dai preferiti'), findsOneWidget);
    await tester.tap(find.byTooltip('Rimuovi dai preferiti'));
    await tester.pump();
    expect(find.text('PREFERITI'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('new search clears graph, seeds and form', (tester) async {
    await _pump(tester);
    expect(find.textContaining('nessun grafo'), findsNothing);
    await tester.tap(find.byTooltip('Nuova ricerca (⌘/Ctrl+N)').first);
    await tester.pump();
    expect(find.textContaining('nessun grafo'), findsOneWidget);
    expect(find.textContaining('0 nodi'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('open investigation offers AGGIORNA; a new search offers AVVIA; FERMA only while running', (tester) async {
    await _pump(tester);
    expect(find.text('AGGIORNA'), findsOneWidget);
    expect(find.text('AVVIA'), findsNothing);
    expect(find.text('FERMA'), findsNothing);
    await tester.tap(find.byTooltip('Nuova ricerca (⌘/Ctrl+N)').first);
    await tester.pump();
    expect(find.text('AVVIA'), findsOneWidget);
    expect(find.text('AGGIORNA'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('hidden nodes: clean view omits them, full view keeps them, split shows both; hide/show from the detail panel', (tester) async {
    await _pump(tester, hidden: {3});
    expect(find.text('3 nodi · 2 archi'), findsOneWidget); // clean (default): node 3 and its edge are out
    expect(find.text('PULITA'), findsOneWidget);
    expect(find.text('1 nascosti'), findsOneWidget);

    await tester.tap(find.text('COMPLETA'));
    await tester.pump();
    expect(find.text('4 nodi · 3 archi'), findsOneWidget);

    await tester.tap(find.text('AFFIANCATE'));
    await tester.pump();
    expect(find.text('CON I NASCOSTI'), findsOneWidget);
    expect(find.text('SENZA I NASCOSTI'), findsOneWidget);

    await tester.tap(find.text('PULITA'));
    await tester.pump();
    await tester.enterText(_search, 'bob@example.com');
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(find.text('NASCONDI'), findsOneWidget); // detail panel of a visible node
    expect(find.text('ELIMINA'), findsOneWidget); // collected nodes can be deleted too
    await tester.tap(find.text('NASCONDI'));
    await tester.pump();
    expect(find.text('2 nodi · 1 archi'), findsOneWidget);
    expect(find.text('2 nascosti'), findsOneWidget);
    expect(find.text('ESPANDI · Email «bob@example.com»'), findsNothing); // selection dropped with the node

    await tester.tap(find.text('MOSTRA TUTTI'));
    await tester.pump();
    expect(find.text('4 nodi · 3 archi'), findsOneWidget); // clean view again, nothing hidden: all four are in
    expect(find.text('PULITA'), findsNothing); // the view bar only exists while something is hidden
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('user-made nodes can be edited, any node deleted; bridges show the delete cross', (tester) async {
    final g = Graph(
      [GNode(1, 'Persona', 'Mario Rossi', const [], 0, true), GNode(2, 'Email', 'mario@example.com')],
      [GEdge(1, 2, 'ha scritto da', 1, 'aggiunto manualmente', 'manuale', '', 7, true)],
    );
    await _pump(tester, graph: g);
    await tester.enterText(_search, 'mario rossi');
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(find.text('MODIFICA'), findsOneWidget);
    expect(find.text('ELIMINA'), findsOneWidget);
    expect(find.text('COLLEGA A…'), findsOneWidget);
    expect(find.byTooltip('Elimina questo ponte'), findsOneWidget);

    await tester.enterText(_search, 'mario@example');
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(find.text('MODIFICA'), findsNothing); // only user-made nodes can be renamed
    expect(find.text('ELIMINA'), findsOneWidget);
    expect(find.byTooltip('Elimina questo ponte'), findsOneWidget); // the bridge is user-made, the node is not

    await tester.tap(find.text('COLLEGA A…'));
    await tester.pump();
    expect(find.textContaining('clicca il nodo di partenza'), findsNothing); // starts from the selected node: asks only for the destination
    expect(find.textContaining('clicca la destinazione'), findsOneWidget);
    expect(find.text('COLLEGA A…'), findsNothing); // the description panel is closed while choosing

    // clicking the destination opens the bridge dialog, not the node's description
    for (var i = 0; i < 200; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    final gv = tester.state(find.byType(GraphView)) as dynamic;
    gv.fit();
    await tester.pump();
    await tester.tapAt(tester.getTopLeft(find.byType(GraphView)) + (gv.toScreen(gv.pos[1]) as Offset)); // node 1 (Mario Rossi) is the destination
    await tester.pumpAndSettle();
    expect(find.text('Nuovo ponte'), findsOneWidget);
    expect(find.text('MODIFICA'), findsNothing);
    await tester.tap(find.text('Annulla'));
    await tester.pumpAndSettle();
    expect(find.text('Nuovo ponte'), findsNothing);
    expect(find.text('NASCONDI'), findsNothing); // still no description panel
    expect(find.textContaining('clicca la destinazione'), findsNothing); // cancelling the dialog leaves bridge mode
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('node and bridge dialogs return what was typed; chips fill the fields', (tester) async {
    (String, String)? node, bridge;
    tester.view.physicalSize = const Size(1000, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(),
      home: Builder(
        builder: (c) => Column(children: [
          TextButton(onPressed: () async => node = await showDialog(context: c, builder: (_) => const NodeDialog()), child: const Text('n')),
          TextButton(onPressed: () async => bridge = await showDialog(context: c, builder: (_) => const BridgeDialog(from: 'A', to: 'B')), child: const Text('b')),
        ]),
      ),
    ));
    await tester.tap(find.text('n'));
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull); // value is required
    await tester.tap(find.text('Evento'));
    await tester.enterText(find.widgetWithText(TextField, '').last, '  Incontro a Roma ');
    await tester.pump();
    await tester.tap(find.text('CREA'));
    await tester.pumpAndSettle();
    expect(node, ('Evento', 'Incontro a Roma'));

    await tester.tap(find.text('b'));
    await tester.pumpAndSettle();
    expect(find.text('A  →  B'), findsOneWidget);
    await tester.tap(find.text('lavora per'));
    await tester.enterText(find.widgetWithText(TextField, '').last, 'visto il 3 maggio');
    await tester.pump();
    await tester.tap(find.text('CREA PONTE'));
    await tester.pumpAndSettle();
    expect(bridge, ('lavora per', 'visto il 3 maggio'));
  });

  testWidgets('deleting a collected node asks first and explains what happens to what hung from it', (tester) async {
    await _pump(tester);
    await tester.enterText(_search, 'example.com');
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    await tester.tap(find.text('ELIMINA'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Eliminare il nodo'), findsOneWidget);
    expect(find.textContaining('non lo ricreerà'), findsOneWidget); // a refresh will not bring it back
    expect(find.textContaining('nascosti (potrai rimostrarli)'), findsOneWidget); // dependents are hidden, not destroyed
    await tester.tap(find.text('Annulla'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Eliminare il nodo'), findsNothing);
    expect(find.text('4 nodi · 3 archi'), findsOneWidget); // cancelled: nothing changed
    await tester.pumpWidget(const SizedBox());
  });
}
