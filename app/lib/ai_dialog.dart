import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'theme.dart';

/// Ask the configured AI about the current investigation. Pops an [AiPivot] when the user wants to expand a
/// suggestion, or the string 'settings' when they want to configure the connector.
class AiDialog extends StatefulWidget {
  const AiDialog({super.key, required this.inv, this.initialStatus, this.initialResult, this.initialTask});
  final int inv;
  final AiStatus? initialStatus; // tests/screenshots only: skip the network load
  final AiResult? initialResult;
  final String? initialTask;

  @override
  State<AiDialog> createState() => _AiDialogState();
}

class _AiDialogState extends State<AiDialog> {
  AiStatus? status;
  String? text, error, lastTask;
  List<AiPivot> pivots = [];
  bool busy = false;
  final question = TextEditingController();

  static const tasks = [
    ('summary', 'Riassunto', 'Cosa emerge, identità probabili, lacune'),
    ('review', 'Verifica', 'Incongruenze e probabili falsi positivi'),
    ('pivots', 'Cosa cercare ora', 'Dati da cui estendere la ricerca'),
    ('report', 'Bozza di rapporto', 'Rapporto in Markdown'),
  ];

  @override
  void initState() {
    super.initState();
    if (widget.initialStatus != null) {
      status = widget.initialStatus;
      text = widget.initialResult?.text;
      pivots = widget.initialResult?.pivots ?? [];
      lastTask = widget.initialTask;
      return;
    }
    fetchAiStatus().then((s) {
      if (mounted) setState(() => status = s);
    }).catchError((Object e) {
      if (mounted) setState(() => error = 'Backend non raggiungibile: $e');
    });
  }

  @override
  void dispose() {
    question.dispose();
    super.dispose();
  }

  Future<void> _run(String task, {String q = ''}) async {
    if (busy) return;
    setState(() {
      busy = true;
      error = null;
      text = null;
      pivots = [];
      lastTask = task;
    });
    try {
      final r = await runAi(widget.inv, task, question: q);
      if (mounted) {
        setState(() {
          text = r.text;
          pivots = r.pivots;
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ok = status?.configured ?? false;
    return Dialog(
      insetPadding: const EdgeInsets.all(24),
      child: SizedBox(
        width: 780,
        height: 640,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 16, 22, 16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              const Icon(Icons.auto_awesome, size: 16, color: accent),
              const SizedBox(width: 10),
              const Expanded(child: Text('ANALISI AI', style: TextStyle(fontSize: 12, letterSpacing: 2, fontWeight: FontWeight.w700))),
              IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context)),
            ]),
            if (status != null && !ok)
              Container(
                margin: const EdgeInsets.only(top: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(border: Border.all(color: accent.withValues(alpha: 0.5)), borderRadius: BorderRadius.circular(6)),
                child: Row(children: [
                  Expanded(child: Text('Connettore non configurato: ${status!.reason}.', style: const TextStyle(fontSize: 12))),
                  TextButton(onPressed: () => Navigator.pop(context, 'settings'), child: const Text('CONFIGURA')),
                ]),
              )
            else if (status != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text('${status!.provider} · ${status!.model}  —  i dati dell\'indagine vengono inviati a questo servizio',
                    style: const TextStyle(fontSize: 11, color: dim)),
              ),
            const SizedBox(height: 14),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final (id, label, help) in tasks)
                Tooltip(
                  message: help,
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: lastTask == id ? accent : fg,
                      side: BorderSide(color: lastTask == id ? accent : line),
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    ),
                    onPressed: ok && !busy ? () => _run(id) : null,
                    child: Text(label.toUpperCase(), style: const TextStyle(fontSize: 11, letterSpacing: 1)),
                  ),
                ),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(
                child: TextField(
                  controller: question,
                  enabled: ok && !busy,
                  style: const TextStyle(fontSize: 12.5),
                  decoration: const InputDecoration(hintText: 'fai una domanda sull\'indagine…'),
                  onSubmitted: (q) => q.trim().isEmpty ? null : _run('ask', q: q),
                ),
              ),
              IconButton(
                tooltip: 'Chiedi',
                icon: const Icon(Icons.send, size: 18),
                onPressed: ok && !busy && question.text.trim().isNotEmpty ? () => _run('ask', q: question.text) : null,
              ),
            ]),
            const Divider(height: 28),
            Expanded(child: _output()),
            if (text != null)
              Align(
                alignment: Alignment.centerRight,
                child: TextButton.icon(
                  icon: const Icon(Icons.copy, size: 14),
                  label: const Text('Copia', style: TextStyle(fontSize: 11.5)),
                  onPressed: () => Clipboard.setData(ClipboardData(text: text!)),
                ),
              ),
          ]),
        ),
      ),
    );
  }

  Widget _output() {
    if (busy) {
      return const Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2)),
          SizedBox(height: 12),
          Text('il modello sta analizzando il grafo…', style: TextStyle(fontSize: 11.5, color: dim)),
        ]),
      );
    }
    if (error != null) return SingleChildScrollView(child: SelectableText(error!, style: const TextStyle(fontSize: 12, color: accent, height: 1.5)));
    if (text == null) {
      return const Center(child: Text('scegli un\'analisi o scrivi una domanda', style: TextStyle(fontSize: 12, color: dim)));
    }
    return ListView(children: [
      if (pivots.isNotEmpty) ...[
        const Text('SUGGERIMENTI', style: TextStyle(fontSize: 10, letterSpacing: 1.6, color: dim)),
        const SizedBox(height: 6),
        for (final p in pivots)
          Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(border: Border.all(color: line), borderRadius: BorderRadius.circular(6)),
            child: Row(children: [
              Container(width: 8, height: 8, decoration: BoxDecoration(color: typeColor(p.type), shape: BoxShape.circle)),
              const SizedBox(width: 10),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${p.type} · ${p.value}', style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                  if (p.reason.isNotEmpty) Text(p.reason, style: const TextStyle(fontSize: 11.5, color: dim, height: 1.4)),
                ]),
              ),
              TextButton(onPressed: () => Navigator.pop(context, p), child: const Text('ESPANDI')),
            ]),
          ),
        const SizedBox(height: 8),
      ],
      SelectableText(text!, style: const TextStyle(fontSize: 12.5, height: 1.55)),
    ]);
  }
}
