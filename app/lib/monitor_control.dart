import 'package:flutter/material.dart';

import 'api_ops.dart';
import 'l10n.dart';
import 'theme.dart';

const monitorChoices = [0, 1, 3, 7, 14, 30];

/// Compact "monitor this investigation" dropdown. Saves through [save] (default: the backend) and then calls [onChanged].
class MonitorSelector extends StatefulWidget {
  const MonitorSelector({super.key, required this.inv, required this.initialDays, this.onChanged, this.save});
  final int inv, initialDays;
  final void Function(int days)? onChanged;
  final Future<void> Function(int inv, int days)? save; // tests: replaces the backend call

  @override
  State<MonitorSelector> createState() => _MonitorSelectorState();
}

class _MonitorSelectorState extends State<MonitorSelector> {
  late int days = monitorChoices.contains(widget.initialDays) ? widget.initialDays : 0;
  String? error;

  Future<void> _pick(int? d) async {
    if (d == null) return;
    final before = days;
    setState(() {
      days = d;
      error = null;
    });
    try {
      await (widget.save ?? setMonitor)(widget.inv, d);
      widget.onChanged?.call(d);
    } catch (e) {
      if (mounted) {
        setState(() {
          days = before;
          error = e.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
      Row(children: [
        Text(t('Monitor'), style: const TextStyle(fontSize: 11.5, color: dim)),
        const SizedBox(width: 8),
        Expanded(child: DropdownButton<int>(
          value: days,
          isDense: true,
          isExpanded: true,
          dropdownColor: const Color(0xFF131316),
          style: const TextStyle(fontSize: 12, color: fg),
          items: [
            for (final d in monitorChoices)
              DropdownMenuItem(value: d, child: Text(d == 0 ? t('Off') : (d == 1 ? t('every day') : t('every {0} days', [d])))),
          ],
          onChanged: _pick,
        )),
      ]),
      Text(error ?? t('Only runs while the app is open'), style: TextStyle(fontSize: 10.5, color: error != null ? accent : dim)),
    ]);
  }
}
