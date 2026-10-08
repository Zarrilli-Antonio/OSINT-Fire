import 'dart:async';

import 'package:flutter/material.dart';

import 'l10n.dart';

/// Multi-line private note with debounced autosave. Pending text is flushed when the editor goes away
/// (selecting another node), so nothing typed is lost.
class NoteEditor extends StatefulWidget {
  const NoteEditor({super.key, required this.initial, required this.onChanged});
  final String initial;
  final void Function(String) onChanged;

  @override
  State<NoteEditor> createState() => _NoteEditorState();
}

class _NoteEditorState extends State<NoteEditor> {
  late final ctl = TextEditingController(text: widget.initial);
  Timer? _debounce;
  bool _dirty = false;

  void _flush() {
    _debounce?.cancel();
    if (_dirty) {
      _dirty = false;
      widget.onChanged(ctl.text);
    }
  }

  @override
  void dispose() {
    _flush();
    ctl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(
        controller: ctl,
        minLines: 1,
        maxLines: 4,
        maxLength: 5000,
        style: const TextStyle(fontSize: 12),
        decoration: InputDecoration(hintText: t('private note…'), counterText: ''),
        onChanged: (_) {
          _dirty = true;
          _debounce?.cancel();
          _debounce = Timer(const Duration(milliseconds: 600), _flush);
        },
      );
}
