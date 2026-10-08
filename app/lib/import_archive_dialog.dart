import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api_archive.dart';
import 'l10n.dart';
import 'platform.dart';
import 'theme.dart';

final _candidate = RegExp(r'^(osint-.*\.(json|graphml)|.*\.osint\.json)$', caseSensitive: false);

/// Export files in [dir], newest first.
List<File> findArchives(Directory dir) {
  try {
    final files = dir.listSync().whereType<File>().where((f) => _candidate.hasMatch(f.uri.pathSegments.last)).toList();
    files.sort((a, b) => b.statSync().modified.compareTo(a.statSync().modified));
    return files;
  } catch (_) {
    return [];
  }
}

String _size(int n) => n < 1024 ? '$n B' : n < 1 << 20 ? '${(n / 1024).toStringAsFixed(0)} KB' : '${(n / (1 << 20)).toStringAsFixed(1)} MB';
String _when(DateTime d) => d.toString().substring(0, 16);

/// Pick an exported file (Downloads list, typed path or pasted text), import it as a new investigation, pop its id.
class ImportArchiveDialog extends StatefulWidget {
  const ImportArchiveDialog({super.key, this.import = importArchive, this.downloads});
  final Future<ImportResult> Function(String content) import;
  final Directory? downloads;

  @override
  State<ImportArchiveDialog> createState() => _ImportArchiveDialogState();
}

class _ImportArchiveDialogState extends State<ImportArchiveDialog> {
  final path = TextEditingController();
  late final List<File> files = findArchives(widget.downloads ?? Directory(downloadsDir()));
  String? pasted;
  bool busy = false;
  String? error;
  ImportResult? result;

  @override
  void dispose() {
    path.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final d = await Clipboard.getData(Clipboard.kTextPlain);
    if (d?.text != null) {
      setState(() {
        pasted = d!.text!;
        path.clear();
      });
    }
  }

  Future<void> _run() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      String content;
      try {
        content = pasted ?? File(path.text.trim()).readAsStringSync();
      } catch (e) {
        throw Exception(t('Could not read the file: {0}', ['$e'.replaceFirst('Exception: ', '')]));
      }
      final r = await widget.import(content);
      if (mounted) setState(() => result = r);
    } catch (e) {
      if (mounted) setState(() => error = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = result;
    final small = TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim);
    return AlertDialog(
      title: Text(t('Import an investigation'), style: const TextStyle(fontSize: 14)),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (r == null) ...[
              Text(t('Files found in Downloads'), style: small),
              if (files.isEmpty) Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Text(t('No export files found in Downloads'), style: TextStyle(fontSize: 11, color: dim))),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 160),
                child: ListView(shrinkWrap: true, children: [
                  for (final f in files)
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      selected: path.text == f.path,
                      title: Text(f.uri.pathSegments.last, style: const TextStyle(fontSize: 12)),
                      trailing: Text('${_size(f.lengthSync())} · ${_when(f.lastModifiedSync())}', style: TextStyle(fontSize: 11, color: dim)),
                      onTap: () => setState(() {
                        pasted = null;
                        path.text = f.path;
                      }),
                    ),
                ]),
              ),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: Text(t('or type the path of the file'), style: small)),
                TextButton(onPressed: _paste, child: Text(t('PASTE'))),
              ]),
              TextField(
                controller: path,
                onChanged: (_) => setState(() => pasted = null),
                style: const TextStyle(fontSize: 12),
                decoration: InputDecoration(hintText: t('File path'), border: const OutlineInputBorder(borderSide: BorderSide(color: line))),
              ),
              if (pasted != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text(t('Pasted content: {0} characters', [pasted!.length]), style: TextStyle(fontSize: 11, color: dim))),
              if (busy) const Padding(padding: EdgeInsets.only(top: 10), child: LinearProgressIndicator()),
              if (error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(error!, style: const TextStyle(fontSize: 11, color: accent))),
            ] else ...[
              Text(r.name.isEmpty ? t('Imported: {0} entities, {1} relations', [r.entities, r.relations]) : t('Imported «{0}»: {1} entities, {2} relations', [r.name, r.entities, r.relations]),
                  style: const TextStyle(fontSize: 12)),
              if (r.warnings.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(t('{0} warnings', [r.warnings.length]), style: small),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 160),
                  child: ListView(shrinkWrap: true, children: [for (final w in r.warnings) Text(w, style: TextStyle(fontSize: 11, color: dim))]),
                ),
              ],
            ],
          ]),
        ),
      ),
      actions: [
        if (r == null) ...[
          TextButton(onPressed: busy ? null : () => Navigator.pop(context), child: Text(t('Cancel'))),
          FilledButton(onPressed: busy || (pasted == null && path.text.trim().isEmpty) ? null : _run, child: Text(t('IMPORT'))),
        ] else
          FilledButton(onPressed: () => Navigator.pop(context, r.id), child: Text(t('OPEN'))),
      ],
    );
  }
}
