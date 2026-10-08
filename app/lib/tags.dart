import 'package:flutter/material.dart';

import 'api.dart';
import 'l10n.dart';

const maxTags = 12, maxTagLen = 30;

/// Stable colour per tag name, bright enough for the dark theme.
Color tagColor(String name) {
  var h = 0;
  for (final c in name.toLowerCase().codeUnits) {
    h = (h * 31 + c) & 0x7fffffff;
  }
  return HSLColor.fromAHSL(1, (h % 360).toDouble(), 0.6, 0.65).toColor();
}

/// Every tag used in the investigation, case-insensitively unique, sorted.
Set<String> allTags(Graph g) {
  final seen = <String, String>{};
  for (final l in g.tags.values) {
    for (final s in l) {
      seen.putIfAbsent(s.toLowerCase(), () => s);
    }
  }
  return (seen.values.toList()..sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()))).toSet();
}

Widget _chip(String name, {VoidCallback? onTap, VoidCallback? onRemove}) {
  final c = tagColor(name);
  return InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(10),
    child: Container(
      padding: EdgeInsets.fromLTRB(8, 2, onRemove == null ? 8 : 4, 2),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.15), border: Border.all(color: c.withValues(alpha: 0.5)), borderRadius: BorderRadius.circular(10)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(name, style: TextStyle(fontSize: 10, color: c)),
        if (onRemove != null)
          InkWell(onTap: onRemove, child: Padding(padding: const EdgeInsets.only(left: 2), child: Icon(Icons.close, size: 12, color: c))),
      ]),
    ),
  );
}

/// Read-only coloured chips.
class TagChips extends StatelessWidget {
  const TagChips(this.tags, {super.key});
  final List<String> tags;

  @override
  Widget build(BuildContext context) => Wrap(spacing: 4, runSpacing: 4, children: [for (final s in tags) _chip(s)]);
}

/// Edit the tags of one entity: chips with ×, an input (Enter or comma adds) and tappable suggestions.
class TagEditor extends StatefulWidget {
  const TagEditor({super.key, required this.tags, this.suggestions = const {}, required this.onChanged});
  final List<String> tags;
  final Iterable<String> suggestions;
  final ValueChanged<List<String>> onChanged;

  @override
  State<TagEditor> createState() => _TagEditorState();
}

class _TagEditorState extends State<TagEditor> {
  final input = TextEditingController();
  late List<String> tags = [...widget.tags];

  @override
  void dispose() {
    input.dispose();
    super.dispose();
  }

  void _add(String raw) {
    var s = raw.trim();
    if (s.length > maxTagLen) s = s.substring(0, maxTagLen);
    if (s.isEmpty || tags.length >= maxTags || tags.any((x) => x.toLowerCase() == s.toLowerCase())) return;
    setState(() => tags = [...tags, s]);
    widget.onChanged(tags);
  }

  void _remove(String s) {
    setState(() => tags = [for (final x in tags) if (x != s) x]);
    widget.onChanged(tags);
  }

  void _changed(String v) {
    if (!v.contains(',')) return setState(() {});
    final parts = v.split(',');
    for (final p in parts.take(parts.length - 1)) {
      _add(p);
    }
    input.text = parts.last;
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final q = input.text.trim().toLowerCase();
    final sugg = [
      for (final s in widget.suggestions)
        if (!tags.any((x) => x.toLowerCase() == s.toLowerCase()) && (q.isEmpty || s.toLowerCase().contains(q))) s
    ].take(8);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
      if (tags.isNotEmpty) Wrap(spacing: 4, runSpacing: 4, children: [for (final s in tags) _chip(s, onRemove: () => _remove(s))]),
      TextField(
        controller: input,
        enabled: tags.length < maxTags,
        onChanged: _changed,
        onSubmitted: (v) {
          _add(v);
          input.clear();
          setState(() {});
        },
        style: const TextStyle(fontSize: 12),
        decoration: InputDecoration(hintText: t('add a tag…')),
      ),
      if (sugg.isNotEmpty) ...[
        const SizedBox(height: 6),
        Wrap(spacing: 4, runSpacing: 4, children: [for (final s in sugg) _chip(s, onTap: () => _add(s))]),
      ],
    ]);
  }
}
