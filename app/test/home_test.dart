import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/main.dart';
import 'package:osint_fire/theme.dart';

void main() {
  testWidgets('home renders with theme, no layout errors, seed chips work', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(),
      builder: (context, child) => Backdrop(child: child!),
      home: const Home(autostart: false),
    ));
    expect(find.text('OSINT/FIRE'), findsOneWidget);
    expect(find.textContaining('nessun grafo'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, '').at(2), 'example.com'); // seed value field
    await tester.tap(find.byTooltip('Aggiungi seed'));
    await tester.pump();
    expect(find.textContaining('Dominio · example.com'), findsOneWidget);

    // sidebar collapses and reopens, via button and via cmd+B
    await tester.tap(find.byTooltip('Riduci pannello (⌘/Ctrl+B)'));
    await tester.pumpAndSettle();
    expect(find.text('OSINT/FIRE'), findsNothing);
    await tester.tap(find.byTooltip('Apri pannello (⌘/Ctrl+B)'));
    await tester.pumpAndSettle();
    expect(find.text('OSINT/FIRE'), findsOneWidget);
    await tester.sendKeyDownEvent(LogicalKeyboardKey.metaLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyB);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.metaLeft);
    await tester.pumpAndSettle();
    expect(find.text('OSINT/FIRE'), findsNothing);
  });
}
