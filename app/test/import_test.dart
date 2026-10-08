import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api_tools.dart';
import 'package:osint_fire/import_dialog.dart';

void main() {
  Future<void> open(WidgetTester tester, Future<ParsedSeeds> Function(String) parse, List<Object?> out) async {
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (c) => TextButton(onPressed: () async => out.add(await showDialog(context: c, builder: (_) => ImportSeedsDialog(parse: parse))), child: const Text('go')),
      ),
    ));
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();
  }

  testWidgets('analyse, uncheck one, import the rest', (tester) async {
    final out = <Object?>[];
    await open(tester, (_) async => ParsedSeeds([('Email', 'a@b.it'), ('Dominio', 'b.it')], ['???']), out);
    await tester.enterText(find.byType(TextField), 'a@b.it\nb.it\n???');
    await tester.pump();
    await tester.tap(find.text('ANALYSE'));
    await tester.pumpAndSettle();
    expect(find.text('a@b.it'), findsOneWidget);
    expect(find.text('???'), findsOneWidget);
    await tester.tap(find.text('a@b.it'));
    await tester.pump();
    await tester.tap(find.text('IMPORT'));
    await tester.pumpAndSettle();
    expect(out.single, [('Dominio', 'b.it')]);
  });

  testWidgets('a failing parse shows the message', (tester) async {
    await open(tester, (_) async => throw Exception('boom'), []);
    await tester.enterText(find.byType(TextField), 'x');
    await tester.pump();
    await tester.tap(find.text('ANALYSE'));
    await tester.pumpAndSettle();
    expect(find.text('boom'), findsOneWidget);
    expect(find.text('IMPORT'), findsNothing);
  });
}
