import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api.dart';
import 'package:osint_fire/tags.dart';

void main() {
  test('tagColor is deterministic and case-insensitive', () {
    expect(tagColor('Suspect'), tagColor('suspect'));
    expect(tagColor('a'), isNot(tagColor('b')));
  });

  test('graphFromJson parses tags; allTags dedupes; they survive collapse and hide', () {
    final g = graphFromJson({
      'nodes': [
        {'id': 1, 'type': 'Email', 'value': 'a@b.it', 'added': 0},
        {'id': 2, 'type': 'Email', 'value': 'c@d.it', 'added': 0},
      ],
      'edges': [],
      'links': [],
      'tags': [
        {'entity': 1, 'tags': ['Suspect', 'verified']},
        {'entity': 2, 'tags': ['suspect']},
      ],
    });
    expect(g.tags[1], ['Suspect', 'verified']);
    expect(allTags(g), {'Suspect', 'verified'});
    expect(collapseGroups(g).tags, g.tags);
    g.hidden.add(2);
    expect(withoutHidden(g).tags, g.tags);
    expect(graphFromJson({'nodes': [], 'edges': [], 'links': []}).tags, isEmpty);
  });

  Future<List<List<String>>> pump(WidgetTester tester, {List<String> tags = const [], List<String> sugg = const []}) async {
    final calls = <List<String>>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: TagEditor(tags: tags, suggestions: sugg, onChanged: calls.add))));
    return calls;
  }

  testWidgets('add on Enter and comma, trim, dedupe, remove', (tester) async {
    final calls = await pump(tester);
    await tester.enterText(find.byType(TextField), '  Alpha ');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'alpha');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.enterText(find.byType(TextField), 'beta,');
    await tester.pump();
    expect(calls.last, ['Alpha', 'beta']);
    expect(calls.length, 2);
    await tester.tap(find.byIcon(Icons.close).first);
    await tester.pump();
    expect(calls.last, ['beta']);
  });

  testWidgets('length and count limits', (tester) async {
    final calls = await pump(tester, tags: [for (var i = 0; i < 11; i++) 't$i']);
    await tester.enterText(find.byType(TextField), 'x' * 40);
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(calls.last.last.length, 30);
    expect(calls.last.length, 12);
    await tester.enterText(find.byType(TextField), 'more');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    expect(calls.length, 1);
  });

  testWidgets('suggestions are tappable and hide used tags', (tester) async {
    final calls = await pump(tester, tags: ['one'], sugg: ['one', 'two']);
    expect(find.text('one'), findsOneWidget);
    await tester.tap(find.text('two'));
    await tester.pump();
    expect(calls.last, ['one', 'two']);
  });
}
