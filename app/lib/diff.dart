import 'package:flutter/material.dart';

import 'l10n.dart';
import 'theme.dart';

class GraphDiff {
  const GraphDiff({this.since = 0, this.firstRun = false, this.runs = const [], this.nodes = const {}, this.edges = const {}, this.entities = 0, this.relations = 0});
  final double since;
  final bool firstRun;
  final List<double> runs;
  final Set<int> nodes, edges; // ids of new entities / relations
  final int entities, relations;

  bool get isEmpty => entities == 0 && relations == 0;
  bool isNewNode(int id) => nodes.contains(id);
  bool isNewEdge(int id) => edges.contains(id);

  static GraphDiff fromJson(Map<String, dynamic> j) {
    final s = (j['summary'] as Map?) ?? const {};
    return GraphDiff(
      since: ((j['since'] ?? 0) as num).toDouble(),
      firstRun: j['first_run'] == true,
      runs: [for (final r in (j['runs'] ?? const []) as List) (r as num).toDouble()],
      nodes: {for (final i in (j['nodes'] ?? const []) as List) i as int},
      edges: {for (final i in (j['edges'] ?? const []) as List) i as int},
      entities: (s['entities'] ?? 0) as int,
      relations: (s['relations'] ?? 0) as int,
    );
  }
}

/// "Since the last run: +N entities, +M relations", with a toggle to show only the new ones.
class DiffBanner extends StatelessWidget {
  const DiffBanner({super.key, required this.diff, required this.onlyNew, required this.onToggle, required this.onDismiss});
  final GraphDiff diff;
  final bool onlyNew; // current state of the toggle
  final VoidCallback onToggle, onDismiss;

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    final text = diff.firstRun ? t('First run: everything is new') : t('Since the last run: +{0} entities, +{1} relations', [diff.entities, diff.relations]);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(8), border: Border.all(color: line)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.fiber_new_outlined, size: 18, color: accent),
        const SizedBox(width: 8),
        Flexible(child: Text(text, style: const TextStyle(fontSize: 12))),
        const SizedBox(width: 12),
        TextButton(onPressed: onToggle, child: Text(onlyNew ? t('SHOW ALL') : t('SHOW ONLY NEW'))),
        TextButton(onPressed: onDismiss, style: TextButton.styleFrom(foregroundColor: dim), child: Text(t('DISMISS'))),
      ]),
    );
  }
}
