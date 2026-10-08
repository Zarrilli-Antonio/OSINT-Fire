import 'package:flutter/material.dart';

import 'api.dart';
import 'l10n.dart';
import 'theme.dart';

/// What to keep in the graph. Empty/zero values mean "no filter".
class GraphFilters {
  const GraphFilters({this.minConfidence = 0, this.sources = const {}, this.onlyNotes = false, this.onlyStarred = false, this.onlyNew = false, this.tags = const {}});
  final double minConfidence;
  final Set<String> sources; // collector names to keep; empty = all
  final bool onlyNotes, onlyStarred, onlyNew;
  final Set<String> tags; // a node needs at least one of them

  bool get isActive => minConfidence > 0 || sources.isNotEmpty || onlyNotes || onlyStarred || onlyNew || tags.isNotEmpty;

  GraphFilters copyWith({double? minConfidence, Set<String>? sources, bool? onlyNotes, bool? onlyStarred, bool? onlyNew, Set<String>? tags}) => GraphFilters(
      minConfidence: minConfidence ?? this.minConfidence,
      sources: sources ?? this.sources,
      onlyNotes: onlyNotes ?? this.onlyNotes,
      onlyStarred: onlyStarred ?? this.onlyStarred,
      onlyNew: onlyNew ?? this.onlyNew,
      tags: tags ?? this.tags);

  @override
  bool operator ==(Object other) =>
      other is GraphFilters &&
      other.minConfidence == minConfidence &&
      other.onlyNotes == onlyNotes &&
      other.onlyStarred == onlyStarred &&
      other.onlyNew == onlyNew &&
      other.sources.length == sources.length &&
      other.sources.containsAll(sources) &&
      other.tags.length == tags.length &&
      other.tags.containsAll(tags);

  @override
  int get hashCode => Object.hash(minConfidence, onlyNotes, onlyStarred, onlyNew, Object.hashAllUnordered(sources), Object.hashAllUnordered(tags));
}

/// The graph reduced to what [f] asks for. Notes/typeLabels are shared with [g]; the hidden set is copied like in [withoutHidden].
Graph applyFilters(Graph g, GraphFilters f, {Set<int> newNodes = const {}, Map<int, List<String>> tags = const {}}) {
  if (!f.isActive) return g;
  final edgeFilter = f.minConfidence > 0 || f.sources.isNotEmpty;
  final edges = [
    for (final e in g.edges)
      if (e.manual || ((e.conf >= f.minConfidence) && (f.sources.isEmpty || f.sources.contains(e.collector)))) e
  ];
  final byEdge = {for (final e in edges) ...[e.src, e.dst]};
  final hadEdge = {for (final e in g.edges) ...[e.src, e.dst]};
  final lower = {for (final s in f.tags) s.toLowerCase()};
  final nodeFilter = f.onlyNotes || f.onlyStarred || f.onlyNew || f.tags.isNotEmpty;

  bool matches(GNode n) {
    final note = g.notes[n.id];
    return (f.onlyNotes && note != null) ||
        (f.onlyStarred && (note?.starred ?? false)) ||
        (f.onlyNew && newNodes.contains(n.id)) ||
        (tags[n.id] ?? const []).any((x) => lower.contains(x.toLowerCase()));
  }

  final nodes = [
    for (final n in g.nodes)
      if (n.manual || (nodeFilter ? matches(n) : (!edgeFilter || byEdge.contains(n.id) || !hadEdge.contains(n.id)))) n
  ];
  final ids = {for (final n in nodes) n.id};
  return Graph(nodes, [for (final e in edges) if (ids.contains(e.src) && ids.contains(e.dst)) e],
      [for (final l in g.links) if (ids.contains(l.a) && ids.contains(l.b)) l], g.notes, {...g.hidden}, g.typeLabels);
}

/// Compact button: filter icon, with a dot when a filter is on. Opens [FilterPanel] in a dialog.
class FilterButton extends StatelessWidget {
  const FilterButton({super.key, required this.graph, required this.filters, required this.tags, required this.onChanged});
  final Graph graph;
  final GraphFilters filters;
  final List<String> tags;
  final ValueChanged<GraphFilters> onChanged;

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    return IconButton(
      tooltip: t('Filters'),
      onPressed: () => showDialog<void>(
        context: context,
        builder: (_) => Dialog(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 380),
            child: Padding(padding: const EdgeInsets.all(16), child: _Live(graph: graph, initial: filters, tags: tags, onChanged: onChanged)),
          ),
        ),
      ),
      icon: Stack(clipBehavior: Clip.none, children: [
        Icon(Icons.filter_alt_outlined, color: filters.isActive ? accent : null),
        if (filters.isActive) Positioned(right: -2, top: -2, child: Container(key: const Key('filter-dot'), width: 7, height: 7, decoration: const BoxDecoration(color: accent, shape: BoxShape.circle))),
      ]),
    );
  }
}

// Keeps its own copy of the filters so the dialog reflects changes while it is open.
class _Live extends StatefulWidget {
  const _Live({required this.graph, required this.initial, required this.tags, required this.onChanged});
  final Graph graph;
  final GraphFilters initial;
  final List<String> tags;
  final ValueChanged<GraphFilters> onChanged;
  @override
  State<_Live> createState() => _LiveState();
}

class _LiveState extends State<_Live> {
  late GraphFilters f = widget.initial;
  @override
  Widget build(BuildContext context) => FilterPanel(graph: widget.graph, filters: f, tags: widget.tags, onChanged: (v) {
        setState(() => f = v);
        widget.onChanged(v);
      });
}

class FilterPanel extends StatelessWidget {
  const FilterPanel({super.key, required this.graph, required this.filters, required this.tags, required this.onChanged});
  final Graph graph;
  final GraphFilters filters;
  final List<String> tags; // every known tag name
  final ValueChanged<GraphFilters> onChanged;

  static Set<String> _toggle(Set<String> s, String v) => s.contains(v) ? ({...s}..remove(v)) : {...s, v};

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    final sources = ({for (final e in graph.edges) if (e.collector.isNotEmpty) e.collector}.toList()..sort());
    final small = Theme.of(context).textTheme.bodySmall!.copyWith(color: dim);
    Widget chips(List<String> all, Set<String> on, String keyPrefix, ValueChanged<Set<String>> set) => Wrap(spacing: 6, runSpacing: 6, children: [
          for (final s in all)
            FilterChip(
              key: Key('$keyPrefix$s'),
              label: Text(s),
              selected: on.contains(s),
              showCheckmark: false,
              selectedColor: accent.withValues(alpha: 0.25),
              onSelected: (_) => set(_toggle(on, s)),
            )
        ]);
    Widget sw(String label, bool v, ValueChanged<bool> set) =>
        SwitchListTile(dense: true, contentPadding: EdgeInsets.zero, title: Text(label), value: v, activeThumbColor: accent, onChanged: set);

    return SingleChildScrollView(
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(t('Filters'), style: Theme.of(context).textTheme.titleMedium)),
          TextButton(onPressed: filters.isActive ? () => onChanged(const GraphFilters()) : null, child: Text(t('Reset'))),
        ]),
        const SizedBox(height: 8),
        Text(t('Minimum confidence: {0}%', [(filters.minConfidence * 100).round()]), style: small),
        Slider(key: const Key('conf-slider'), value: filters.minConfidence, divisions: 20, onChanged: (v) => onChanged(filters.copyWith(minConfidence: v))),
        if (sources.isNotEmpty) ...[
          Text(t('Sources'), style: small),
          const SizedBox(height: 6),
          chips(sources, filters.sources, 'src-', (s) => onChanged(filters.copyWith(sources: s))),
          const SizedBox(height: 8),
        ],
        sw(t('Only with notes'), filters.onlyNotes, (v) => onChanged(filters.copyWith(onlyNotes: v))),
        sw(t('Only starred'), filters.onlyStarred, (v) => onChanged(filters.copyWith(onlyStarred: v))),
        sw(t('Only new'), filters.onlyNew, (v) => onChanged(filters.copyWith(onlyNew: v))),
        if (tags.isNotEmpty) ...[
          Text(t('Tags'), style: small),
          const SizedBox(height: 6),
          chips(tags, filters.tags, 'tag-', (s) => onChanged(filters.copyWith(tags: s))),
        ],
      ]),
    );
  }
}
