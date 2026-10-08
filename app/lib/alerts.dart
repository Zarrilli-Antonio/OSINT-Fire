import 'dart:async';

import 'package:flutter/material.dart';

import 'api_ops.dart';
import 'l10n.dart';
import 'theme.dart';

/// Bell with the number of unseen alerts. Polls while [enabled]; tapping opens [AlertsDialog]
/// and calls [onOpen] with the investigation id when the user picks one.
class AlertsButton extends StatefulWidget {
  const AlertsButton({
    super.key,
    this.enabled = true,
    this.interval = const Duration(seconds: 60),
    this.fetch,
    this.onOpen,
  });
  final bool enabled;
  final Duration interval;
  final Future<List<Alert>> Function()? fetch; // tests: replaces the backend call (returns the unseen alerts)
  final void Function(int inv)? onOpen;

  @override
  State<AlertsButton> createState() => _AlertsButtonState();
}

class _AlertsButtonState extends State<AlertsButton> {
  int unseen = 0;
  Timer? timer;

  Future<List<Alert>> _fetch() => (widget.fetch ?? () => fetchAlerts(unseenOnly: true))();

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void didUpdateWidget(AlertsButton old) {
    super.didUpdateWidget(old);
    if (old.enabled != widget.enabled || old.interval != widget.interval) _start();
  }

  void _start() {
    timer?.cancel();
    timer = null;
    if (!widget.enabled) return;
    _poll();
    timer = Timer.periodic(widget.interval, (_) => _poll());
  }

  Future<void> _poll() async {
    try {
      final a = await _fetch();
      if (mounted) setState(() => unseen = a.where((x) => !x.seen).length);
    } catch (_) {} // the backend may be restarting: keep the last count
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  Future<void> _open() async {
    final inv = await showDialog<int>(context: context, builder: (_) => AlertsDialog(fetch: widget.fetch == null ? null : () => widget.fetch!()));
    _poll();
    if (inv != null) widget.onOpen?.call(inv);
  }

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    return IconButton(
      tooltip: t('Alerts'),
      onPressed: _open,
      icon: Badge(
        isLabelVisible: unseen > 0,
        label: Text('$unseen'),
        backgroundColor: accent,
        child: const Icon(Icons.notifications_none),
      ),
    );
  }
}

/// List of monitoring alerts. Pops the investigation id when the user taps OPEN.
class AlertsDialog extends StatefulWidget {
  const AlertsDialog({super.key, this.fetch, this.markSeen, this.markAllSeen});
  // tests: replace the backend calls
  final Future<List<Alert>> Function()? fetch;
  final Future<void> Function(int id)? markSeen;
  final Future<void> Function()? markAllSeen;

  @override
  State<AlertsDialog> createState() => _AlertsDialogState();
}

class _AlertsDialogState extends State<AlertsDialog> {
  List<Alert>? alerts;
  String? error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final a = await (widget.fetch ?? fetchAlerts)();
      if (mounted) setState(() => alerts = a);
    } catch (e) {
      if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    }
  }

  Future<void> _markAll() async {
    try {
      await (widget.markAllSeen ?? markAllAlertsSeen)();
      if (mounted) setState(() => alerts = [for (final a in alerts!) Alert(a.id, a.inv, a.name, a.ts, a.entities, a.relations, a.summary, true)]);
    } catch (e) {
      if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    }
  }

  Future<void> _open(Alert a) async {
    try {
      if (!a.seen) await (widget.markSeen ?? markAlertSeen)(a.id);
    } catch (_) {} // opening still works if the flag could not be saved
    if (mounted) Navigator.pop(context, a.inv);
  }

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    final list = alerts;
    return Dialog(
      insetPadding: const EdgeInsets.all(24),
      child: SizedBox(
        width: 560,
        height: 520,
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 12, 0),
            child: Row(children: [
              Expanded(child: Text(t('ALERTS'), style: const TextStyle(fontSize: 12, letterSpacing: 2, fontWeight: FontWeight.w700))),
              TextButton(onPressed: list == null || list.every((a) => a.seen) ? null : _markAll, child: Text(t('MARK ALL SEEN'), style: const TextStyle(fontSize: 11, letterSpacing: 1))),
              IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context)),
            ]),
          ),
          const Divider(),
          Expanded(
            child: error != null
                ? Center(child: Text(error!, style: const TextStyle(color: accent)))
                : list == null
                    ? const Center(child: CircularProgressIndicator(strokeWidth: 2))
                    : list.isEmpty
                        ? Center(child: Text(t('No alerts yet.'), style: const TextStyle(color: dim)))
                        : ListView(padding: const EdgeInsets.symmetric(horizontal: 20), children: [for (final a in list) _card(a)]),
          ),
        ]),
      ),
    );
  }

  Widget _card(Alert a) => Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(border: Border.all(color: a.seen ? line : accent.withValues(alpha: 0.6)), borderRadius: BorderRadius.circular(6)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(a.name, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600))),
            Text(fmtDateTime(DateTime.fromMillisecondsSinceEpoch((a.ts * 1000).round())), style: const TextStyle(fontSize: 11, color: dim)),
          ]),
          const SizedBox(height: 4),
          Text(t('+{0} entities, +{1} relations', [a.entities, a.relations]), style: const TextStyle(fontSize: 11.5, fontFamily: mono, fontFamilyFallback: monoFallback)),
          const SizedBox(height: 4),
          for (final s in a.summary.take(10)) Text('${s.type}: ${s.label}', style: const TextStyle(fontSize: 11, color: dim), overflow: TextOverflow.ellipsis),
          Align(alignment: Alignment.centerRight, child: TextButton(onPressed: () => _open(a), child: Text(t('OPEN'), style: const TextStyle(fontSize: 11, letterSpacing: 1)))),
        ]),
      );
}
