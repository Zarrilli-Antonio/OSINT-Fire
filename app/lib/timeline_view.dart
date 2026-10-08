import 'package:flutter/material.dart';

import 'l10n.dart';
import 'theme.dart';

class TimelineEvent {
  const TimelineEvent({required this.ts, required this.date, required this.kind, this.entity, this.related, required this.label, this.collector = ''});
  final double ts;
  final String date; // YYYY-MM-DD
  final String kind, label, collector;
  final int? entity, related;

  static TimelineEvent fromJson(Map<String, dynamic> j) => TimelineEvent(
      ts: (j['ts'] as num).toDouble(),
      date: j['date'] as String,
      kind: j['kind'] as String,
      entity: j['entity'] as int?,
      related: j['related'] as int?,
      label: j['label'] as String,
      collector: (j['collector'] ?? '') as String);
}

const _kinds = <String, (IconData, Color)>{
  'registration': (Icons.app_registration, Color(0xFF6EA8FE)),
  'expiry': (Icons.event_busy, Color(0xFFFFB454)),
  'change': (Icons.edit_calendar, Color(0xFFD2A8FF)),
  'certificate': (Icons.verified_outlined, Color(0xFF7EE787)),
  'breach': (Icons.warning_amber_rounded, Color(0xFFFF7EB6)),
  'first_seen': (Icons.visibility_outlined, Color(0xFF56D4DD)),
  'manual': (Icons.edit_note, gold),
  'run': (Icons.play_circle_outline, dim),
};

class TimelineView extends StatelessWidget {
  const TimelineView({super.key, required this.events, required this.undated, required this.onSelect, required this.onClose});
  final List<TimelineEvent> events;
  final int undated;
  final ValueChanged<int> onSelect; // entity id
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    final sorted = [...events]..sort((a, b) => a.ts.compareTo(b.ts));
    final rows = <Widget>[];
    String? year, month;
    for (final e in sorted) {
      final p = e.date.split('-');
      final y = p[0], m = p.length > 1 ? '${p[0]}-${p[1]}' : p[0];
      if (y != year) {
        year = y;
        month = null;
        rows.add(Padding(padding: const EdgeInsets.only(top: 18, bottom: 4), child: Text(y, key: Key('year-$y'), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: accent))));
      }
      if (m != month) {
        month = m;
        rows.add(Padding(padding: const EdgeInsets.only(top: 8, bottom: 2, left: 4), child: Text(m, key: Key('month-$m'), style: const TextStyle(fontSize: 12, color: dim))));
      }
      rows.add(_row(e));
    }
    return Container(
      color: bg,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 8, 0),
          child: Row(children: [
            Expanded(child: Text(t('Timeline'), style: Theme.of(context).textTheme.titleLarge)),
            IconButton(tooltip: t('Close'), onPressed: onClose, icon: const Icon(Icons.close)),
          ]),
        ),
        if (undated > 0) Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Align(alignment: Alignment.centerLeft, child: Text(t('{0} undated facts', [undated]), style: const TextStyle(fontSize: 11, color: dim)))),
        Expanded(
          child: sorted.isEmpty
              ? Center(child: Text(t('No dated facts yet'), style: const TextStyle(color: dim)))
              : ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: rows),
        ),
      ]),
    );
  }

  Widget _row(TimelineEvent e) {
    final (icon, color) = _kinds[e.kind] ?? (Icons.circle_outlined, dim);
    final id = e.entity ?? e.related;
    return InkWell(
      onTap: id == null ? null : () => onSelect(id),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 4),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 10),
          SizedBox(width: 84, child: Text(e.date, style: const TextStyle(fontSize: 11, color: dim))),
          Expanded(child: Text(e.label, style: const TextStyle(fontSize: 12))),
          if (e.collector.isNotEmpty) Text(e.collector, style: const TextStyle(fontSize: 10, color: dim)),
        ]),
      ),
    );
  }
}
