import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api_tools.dart';
import 'l10n.dart';
import 'theme.dart';

/// Paste a list or CSV, preview the detected seeds, pop the checked ones as (canonical type, value).
class ImportSeedsDialog extends StatefulWidget {
  const ImportSeedsDialog({super.key, this.parse = parseSeeds});
  final Future<ParsedSeeds> Function(String text) parse;

  @override
  State<ImportSeedsDialog> createState() => _ImportSeedsDialogState();
}

class _ImportSeedsDialogState extends State<ImportSeedsDialog> {
  final text = TextEditingController();
  ParsedSeeds? parsed;
  Set<int> checked = {};
  bool busy = false;
  String? error;

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final d = await Clipboard.getData(Clipboard.kTextPlain);
    if (d?.text != null) setState(() => text.text = d!.text!);
  }

  Future<void> _analyse() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final p = await widget.parse(text.text);
      if (!mounted) return;
      setState(() {
        parsed = p;
        checked = {for (var i = 0; i < p.seeds.length; i++) i};
      });
    } catch (e) {
      if (mounted) setState(() => error = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = parsed;
    return AlertDialog(
      title: Text(t('Import seeds'), style: const TextStyle(fontSize: 14)),
      content: SizedBox(
        width: 520,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(t('Paste a list or CSV: emails, domains, IPs, phones, @handles'), style: TextStyle(fontSize: 11, color: dim))),
            TextButton(onPressed: _paste, child: Text(t('PASTE'))),
          ]),
          TextField(
            controller: text,
            minLines: 5,
            maxLines: 8,
            onChanged: (_) => setState(() => parsed = null),
            style: const TextStyle(fontSize: 12),
            decoration: const InputDecoration(border: OutlineInputBorder(borderSide: BorderSide(color: line))),
          ),
          if (error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(error!, style: const TextStyle(fontSize: 11, color: accent))),
          if (p != null) ...[
            const SizedBox(height: 10),
            Text(t('{0} seeds detected', [p.seeds.length]), style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            Flexible(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 220),
                child: ListView(shrinkWrap: true, children: [
                  for (var i = 0; i < p.seeds.length; i++)
                    CheckboxListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      value: checked.contains(i),
                      onChanged: (v) => setState(() => v == true ? checked.add(i) : checked.remove(i)),
                      title: Text(p.seeds[i].$2, style: const TextStyle(fontSize: 12)),
                      secondary: Text(typeLabel(p.seeds[i].$1), style: TextStyle(fontSize: 11, color: dim)),
                    ),
                  if (p.skipped.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(t('{0} lines skipped', [p.skipped.length]), style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
                    for (final s in p.skipped) Text(s, style: TextStyle(fontSize: 11, color: dim)),
                  ],
                ]),
              ),
            ),
          ],
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(t('Cancel'))),
        if (p == null)
          FilledButton(onPressed: busy || text.text.trim().isEmpty ? null : _analyse, child: Text(t('ANALYSE')))
        else
          FilledButton(
            onPressed: checked.isEmpty ? null : () => Navigator.pop(context, [for (final i in (checked.toList()..sort())) p.seeds[i]]),
            child: Text(t('IMPORT')),
          ),
      ],
    );
  }
}
