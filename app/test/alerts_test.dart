import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/alerts.dart';
import 'package:osint_fire/api_ops.dart';
import 'package:osint_fire/theme.dart';

Alert _a(int id, {bool seen = false}) => Alert(id, 10 + id, 'Case $id', 1700000000, 3, 1, [(type: 'Domain', label: 'x$id.it')], seen);

Widget _app(Widget w) => MaterialApp(theme: buildTheme(), home: Scaffold(body: Center(child: w)));

void main() {
  testWidgets('badge shows unseen count and polls on the interval', (tester) async {
    var calls = 0;
    var data = [_a(1), _a(2)];
    await tester.pumpWidget(_app(AlertsButton(interval: const Duration(seconds: 5), fetch: () async {
      calls++;
      return data;
    })));
    await tester.pump();
    expect(calls, 1);
    expect(find.text('2'), findsOneWidget);
    data = [_a(1), _a(2), _a(3)];
    await tester.pump(const Duration(seconds: 5));
    expect(calls, 2);
    expect(find.text('3'), findsOneWidget);
    await tester.pumpWidget(const SizedBox()); // dispose cancels the timer
  });

  testWidgets('no polling and no badge when disabled', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_app(AlertsButton(enabled: false, interval: const Duration(seconds: 1), fetch: () async {
      calls++;
      return [_a(1)];
    })));
    await tester.pump(const Duration(seconds: 3));
    expect(calls, 0);
    expect(find.text('1'), findsNothing);
  });

  testWidgets('dialog lists the alert, OPEN calls back with the investigation', (tester) async {
    int? opened;
    await tester.pumpWidget(_app(AlertsButton(interval: const Duration(hours: 1), fetch: () async => [_a(1)], onOpen: (i) => opened = i)));
    await tester.pump();
    await tester.tap(find.byType(IconButton));
    await tester.pumpAndSettle();
    expect(find.text('Case 1'), findsOneWidget);
    expect(find.text('+3 entities, +1 relations'), findsOneWidget);
    expect(find.text('Domain: x1.it'), findsOneWidget);
    await tester.tap(find.text('OPEN'));
    await tester.pumpAndSettle();
    expect(opened, 11);
  });

  testWidgets('MARK ALL SEEN calls the backend and disables itself', (tester) async {
    var marked = 0;
    await tester.pumpWidget(_app(Builder(
        builder: (c) => TextButton(
            onPressed: () => showDialog(context: c, builder: (_) => AlertsDialog(fetch: () async => [_a(1), _a(2)], markAllSeen: () async => marked++)),
            child: const Text('go')))));
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('MARK ALL SEEN'));
    await tester.pumpAndSettle();
    expect(marked, 1);
    expect(tester.widget<TextButton>(find.widgetWithText(TextButton, 'MARK ALL SEEN')).onPressed, isNull);
  });
}
