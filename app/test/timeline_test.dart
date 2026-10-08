import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/l10n.dart';
import 'package:osint_fire/timeline_view.dart';

TimelineEvent ev(String d, String kind, int? e, String label) => TimelineEvent.fromJson({'ts': DateTime.parse('${d}T00:00:00Z').millisecondsSinceEpoch / 1000, 'date': d, 'kind': kind, 'entity': e, 'related': null, 'label': label, 'collector': 'rdap'});

Widget app(List<TimelineEvent> evs, int undated, [void Function(int)? sel]) =>
    MaterialApp(home: Scaffold(body: TimelineView(events: evs, undated: undated, onSelect: sel ?? (_) {}, onClose: () {})));

void main() {
  setUpAll(() => appLang.value = 'it');
  tearDownAll(() => appLang.value = 'en');

  testWidgets('groups by year and month, taps select', (tester) async {
    int? got;
    await tester.pumpWidget(app([ev('2015-03-02', 'expiry', 2, 'second'), ev('2014-05-12', 'registration', 1, 'first'), ev('2014-05-20', 'change', 3, 'third')], 2, (i) => got = i));
    expect(find.byKey(const Key('year-2014')), findsOneWidget);
    expect(find.byKey(const Key('year-2015')), findsOneWidget);
    expect(find.byKey(const Key('month-2014-05')), findsOneWidget);
    expect(find.byKey(const Key('month-2015-03')), findsOneWidget);
    expect(tester.getTopLeft(find.text('first')).dy < tester.getTopLeft(find.text('second')).dy, isTrue);
    expect(find.text('2 fatti senza data'), findsOneWidget);
    await tester.tap(find.text('first'));
    expect(got, 1);
  });

  testWidgets('empty state in Italian, English after switch', (tester) async {
    await tester.pumpWidget(app([], 0));
    expect(find.text('Ancora nessun fatto datato'), findsOneWidget);
    expect(find.textContaining('senza data'), findsNothing);
    appLang.value = 'en';
    await tester.pumpWidget(app([], 0));
    expect(find.text('No dated facts yet'), findsOneWidget);
    appLang.value = 'it';
  });
}
