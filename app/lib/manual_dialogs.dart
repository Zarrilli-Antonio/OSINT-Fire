import 'package:flutter/material.dart';

import 'l10n.dart';
import 'theme.dart';

// canonical (stored) type names; shown through typeLabel()
const nodeTypes = ['Persona', 'Azienda', 'Email', 'Username', 'Dominio', 'IP', 'Telefono', 'Account', 'Luogo', 'Evento', 'Oggetto', 'Documento', 'Nota'];
// English source strings of the suggested relation names; shown through t(), stored as typed
const bridgeLabels = ['linked to', 'same person', 'works for', 'owns', 'family member of', 'contact of', 'uses', 'suspected link to', 'located in'];

/// Suggestion chips: [items] are (value, shown text); [current] is compared with the value.
Widget _chips(List<(String, String)> items, String current, void Function(String) onTap) => Wrap(spacing: 6, runSpacing: 6, children: [
      for (final (v, shown) in items)
        InkWell(
          onTap: () => onTap(v),
          borderRadius: BorderRadius.circular(4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              border: Border.all(color: v == current ? accent : line),
              borderRadius: BorderRadius.circular(4),
              color: v == current ? accent.withValues(alpha: 0.15) : null,
            ),
            child: Text(shown, style: TextStyle(fontSize: 11, color: v == current ? fg : dim)),
          ),
        ),
    ]);

/// Create or edit a node made by hand: a type (pick one or type your own) and a value. Pops (type, value).
class NodeDialog extends StatefulWidget {
  const NodeDialog({super.key, this.type, this.value});
  final String? type, value; // set when editing
  bool get editing => value != null;

  @override
  State<NodeDialog> createState() => _NodeDialogState();
}

class _NodeDialogState extends State<NodeDialog> {
  late final type = TextEditingController(text: typeLabel(widget.type ?? 'Persona'));
  late final value = TextEditingController(text: widget.value ?? '');

  @override
  void dispose() {
    type.dispose();
    value.dispose();
    super.dispose();
  }

  bool get ok => type.text.trim().isNotEmpty && value.text.trim().isNotEmpty;

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.editing ? t('Edit node') : t('New node'), style: const TextStyle(fontSize: 14)),
        content: SizedBox(
          width: 440,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(t('TYPE'), style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            TextField(controller: type, onChanged: (_) => setState(() {}), decoration: InputDecoration(hintText: t('pick one or type your own'))),
            const SizedBox(height: 8),
            _chips([for (final c in nodeTypes) (c, typeLabel(c))], typeKey(type.text), (c) => setState(() => type.text = typeLabel(c))),
            const SizedBox(height: 16),
            Text(t('VALUE'), style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            TextField(
              controller: value,
              autofocus: true,
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) => ok ? Navigator.pop(context, (typeKey(type.text), value.text.trim())) : null,
              decoration: InputDecoration(hintText: t('name, address, description…')),
            ),
            const SizedBox(height: 10),
            Text(t('A hand-made node is marked by a golden diamond. You can link, annotate, hide, edit or delete it.'),
                style: TextStyle(fontSize: 11, color: dim, height: 1.4)),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(t('Cancel'))),
          FilledButton(onPressed: ok ? () => Navigator.pop(context, (typeKey(type.text), value.text.trim())) : null, child: Text(widget.editing ? t('SAVE') : t('CREATE'))),
        ],
      );
}

/// Name the bridge between two nodes: a label (pick one or type your own) and an optional note. Pops (label, reason).
class BridgeDialog extends StatefulWidget {
  const BridgeDialog({super.key, required this.from, required this.to});
  final String from, to;

  @override
  State<BridgeDialog> createState() => _BridgeDialogState();
}

class _BridgeDialogState extends State<BridgeDialog> {
  final label = TextEditingController(text: t('linked to'));
  final reason = TextEditingController();

  @override
  void dispose() {
    label.dispose();
    reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(t('New bridge'), style: TextStyle(fontSize: 14)),
        content: SizedBox(
          width: 460,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${widget.from}  →  ${widget.to}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
            const SizedBox(height: 14),
            Text(t('RELATION'), style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            TextField(controller: label, autofocus: true, onChanged: (_) => setState(() {}), decoration: InputDecoration(hintText: t('for example: works for'))),
            const SizedBox(height: 8),
            _chips([for (final b in bridgeLabels) (t(b), t(b))], label.text.trim(), (b) => setState(() => label.text = b)),
            const SizedBox(height: 14),
            Text(t('NOTE (OPTIONAL)'), style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            TextField(controller: reason, decoration: InputDecoration(hintText: t('why you link them'))),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(t('Cancel'))),
          FilledButton(onPressed: label.text.trim().isEmpty ? null : () => Navigator.pop(context, (label.text.trim(), reason.text.trim())), child: Text(t('CREATE BRIDGE'))),
        ],
      );
}
