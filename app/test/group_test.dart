import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api.dart';
import 'package:osint_fire/l10n.dart';

void main() {
  setUpAll(() => appLang.value = 'it');
  test('leaf groups collapse, small ones and linked ones stay, ids are stable', () {
    final nodes = [
      GNode(1, 'Account', 'hub'),
      for (var i = 0; i < 7; i++) GNode(10 + i, 'Immagine', 'hash$i'), // 7 leaf images -> group
      for (var i = 0; i < 3; i++) GNode(30 + i, 'Breach', 'b$i'), // too few -> stay
      for (var i = 0; i < 6; i++) GNode(40 + i, 'Servizio', 's$i'), // 6 leaves, but one is linked -> only 5 collapse -> stay
    ];
    final edges = [
      for (var i = 0; i < 7; i++) GEdge(1, 10 + i, 'immagine_profilo', 0.9, 'r', 'c', ''),
      for (var i = 0; i < 3; i++) GEdge(1, 30 + i, 'presente_in_breach', 0.7, 'r', 'c', ''),
      for (var i = 0; i < 6; i++) GEdge(1, 40 + i, 'usa', 0.9, 'r', 'c', ''),
    ];
    final g = Graph(nodes, edges, [GLink(1, 40, 41, 0.5, ['s'], 'review')]);
    final c1 = collapseGroups(g), c2 = collapseGroups(g);

    final group = c1.nodes.singleWhere((n) => n.members.isNotEmpty);
    expect(group.type, 'Immagine');
    expect(group.value, '7 immagine');
    expect(group.members, hasLength(7));
    expect(group.id, lessThan(0));
    expect(group.id, c2.nodes.singleWhere((n) => n.members.isNotEmpty).id);
    expect(c1.nodes.where((n) => n.type == 'Breach'), hasLength(3));
    expect(c1.nodes.where((n) => n.type == 'Servizio'), hasLength(6));
    expect(c1.edges.where((e) => e.dst == group.id), hasLength(1));
    expect(c1.nodes.where((n) => n.type == 'Immagine' && n.members.isEmpty), isEmpty);
  });

  test('annotated or starred leaves are never folded into a group', () {
    final nodes = [GNode(1, 'Account', 'hub'), for (var i = 0; i < 7; i++) GNode(10 + i, 'Breach', 'b$i')];
    final edges = [for (var i = 0; i < 7; i++) GEdge(1, 10 + i, 'presente_in_breach', 0.7, 'r', 'c', '')];
    final notes = {12: GNote('importante', true)};
    final g = collapseGroups(Graph(nodes, edges, const [], notes));
    // 6 remaining leaves still meet the threshold, but the annotated one stays out
    final group = g.nodes.singleWhere((n) => n.members.isNotEmpty);
    expect(group.members, hasLength(6));
    expect(g.nodes.any((n) => n.id == 12), isTrue);
    expect(g.notes, same(notes)); // shared map: UI edits stay visible
  });

  test('user-made and hidden nodes are never folded; groups know their member ids; withoutHidden drops nodes, edges, links', () {
    final nodes = [GNode(1, 'Account', 'hub'), for (var i = 0; i < 8; i++) GNode(10 + i, 'Servizio', 's$i', const [], 0, i == 0)];
    final edges = [for (var i = 0; i < 8; i++) GEdge(1, 10 + i, 'usa', 0.9, 'r', 'c', '')];
    final g = Graph(nodes, edges, const [], null, {11});
    final c = collapseGroups(g);
    final group = c.nodes.singleWhere((n) => n.members.isNotEmpty);
    expect(group.members, hasLength(6)); // 8 leaves minus the manual one (10) and the hidden one (11)
    expect(group.memberIds.toSet(), {12, 13, 14, 15, 16, 17});
    expect(c.nodes.map((n) => n.id), containsAll([10, 11]));
    expect(c.hidden, {11});

    final clean = withoutHidden(g);
    expect(clean.nodes.map((n) => n.id), isNot(contains(11)));
    expect(clean.edges.any((e) => e.dst == 11), isFalse);
    expect(clean.hidden, isEmpty);
    expect(identical(withoutHidden(Graph(nodes, edges)).nodes, nodes), isTrue); // nothing hidden: same graph back
  });
}
