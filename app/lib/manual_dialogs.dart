import 'package:flutter/material.dart';

import 'theme.dart';

const nodeTypes = ['Persona', 'Azienda', 'Email', 'Username', 'Dominio', 'IP', 'Telefono', 'Account', 'Luogo', 'Evento', 'Oggetto', 'Documento', 'Nota'];
const bridgeLabels = ['collegato a', 'stessa persona', 'lavora per', 'possiede', 'familiare di', 'contatto di', 'usa', 'sospetto legato a', 'si trova a'];

Widget _chips(List<String> items, String current, void Function(String) onTap) => Wrap(spacing: 6, runSpacing: 6, children: [
      for (final t in items)
        InkWell(
          onTap: () => onTap(t),
          borderRadius: BorderRadius.circular(4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              border: Border.all(color: t == current ? accent : line),
              borderRadius: BorderRadius.circular(4),
              color: t == current ? accent.withValues(alpha: 0.15) : null,
            ),
            child: Text(t, style: TextStyle(fontSize: 11, color: t == current ? fg : dim)),
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
  late final type = TextEditingController(text: widget.type ?? 'Persona');
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
        title: Text(widget.editing ? 'Modifica nodo' : 'Nuovo nodo', style: const TextStyle(fontSize: 14)),
        content: SizedBox(
          width: 440,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('TIPO', style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            TextField(controller: type, onChanged: (_) => setState(() {}), decoration: const InputDecoration(hintText: 'scegli o scrivi il tuo')),
            const SizedBox(height: 8),
            _chips(nodeTypes, type.text.trim(), (t) => setState(() => type.text = t)),
            const SizedBox(height: 16),
            const Text('VALORE', style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            TextField(
              controller: value,
              autofocus: true,
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) => ok ? Navigator.pop(context, (type.text.trim(), value.text.trim())) : null,
              decoration: const InputDecoration(hintText: 'nome, indirizzo, descrizione…'),
            ),
            const SizedBox(height: 10),
            const Text('Un nodo creato a mano si riconosce dal rombo dorato. Puoi collegarlo, annotarlo, nasconderlo, modificarlo o eliminarlo.',
                style: TextStyle(fontSize: 11, color: dim, height: 1.4)),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annulla')),
          FilledButton(onPressed: ok ? () => Navigator.pop(context, (type.text.trim(), value.text.trim())) : null, child: Text(widget.editing ? 'SALVA' : 'CREA')),
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
  final label = TextEditingController(text: 'collegato a');
  final reason = TextEditingController();

  @override
  void dispose() {
    label.dispose();
    reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Nuovo ponte', style: TextStyle(fontSize: 14)),
        content: SizedBox(
          width: 460,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${widget.from}  →  ${widget.to}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
            const SizedBox(height: 14),
            const Text('RELAZIONE', style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            TextField(controller: label, autofocus: true, onChanged: (_) => setState(() {}), decoration: const InputDecoration(hintText: 'per esempio: lavora per')),
            const SizedBox(height: 8),
            _chips(bridgeLabels, label.text.trim(), (t) => setState(() => label.text = t)),
            const SizedBox(height: 14),
            const Text('NOTA (FACOLTATIVA)', style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
            TextField(controller: reason, decoration: const InputDecoration(hintText: 'perché li colleghi')),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annulla')),
          FilledButton(onPressed: label.text.trim().isEmpty ? null : () => Navigator.pop(context, (label.text.trim(), reason.text.trim())), child: const Text('CREA PONTE')),
        ],
      );
}
