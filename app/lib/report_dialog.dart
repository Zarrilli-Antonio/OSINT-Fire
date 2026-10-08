import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'api_report.dart';
import 'flags.dart';
import 'l10n.dart';
import 'platform.dart';
import 'theme.dart';

typedef ReportBuild = Future<Uint8List> Function(int inv, ReportOptions o);
typedef ReportSave = Future<String> Function(String fileName, Uint8List bytes);

/// Same place the export menu writes to: the Downloads folder.
Future<String> saveToDownloads(String fileName, Uint8List bytes) async {
  final path = '${downloadsDir()}${Platform.pathSeparator}$fileName';
  await File(path).writeAsBytes(bytes);
  return path;
}

const maxLogoBytes = 1024 * 1024;

/// Null when [b] is a PNG or JPEG, otherwise the reason it is not accepted.
String? logoProblem(Uint8List b) {
  if (b.length > maxLogoBytes) return t('The logo is larger than 1 MB');
  final png = b.length > 4 && b[0] == 0x89 && b[1] == 0x50 && b[2] == 0x4E && b[3] == 0x47;
  final jpg = b.length > 3 && b[0] == 0xFF && b[1] == 0xD8 && b[2] == 0xFF;
  return png || jpg ? null : t('The logo must be a PNG or JPEG image');
}

/// Options remembered for the rest of the session.
class _Last {
  static String format = 'html', header = '', footer = '', lang = 'app';
  static List<String> sections = List.of(reportSections);
  static bool hidden = false;
}

/// Forget the options remembered from earlier dialogs (tests).
void resetReportMemory() {
  _Last.format = 'html';
  _Last.header = _Last.footer = '';
  _Last.lang = 'app';
  _Last.sections = List.of(reportSections);
  _Last.hidden = false;
}

/// Pops the path of the saved report, or null.
class ReportDialog extends StatefulWidget {
  const ReportDialog({super.key, required this.inv, required this.defaultTitle, this.hasHidden = false, this.build = buildReport, this.save = saveToDownloads});
  final int inv;
  final String defaultTitle;
  final bool hasHidden;
  final ReportBuild build;
  final ReportSave save;

  @override
  State<ReportDialog> createState() => _ReportDialogState();
}

class _ReportDialogState extends State<ReportDialog> {
  late String format = _Last.format, lang = _Last.lang;
  late final Set<String> sections = {..._Last.sections};
  late bool hidden = widget.hasHidden && _Last.hidden;
  late final title = TextEditingController(text: widget.defaultTitle);
  late final header = TextEditingController(text: _Last.header);
  late final footer = TextEditingController(text: _Last.footer);
  final logoPath = TextEditingController();
  Uint8List? logo;
  String? logoError, error;
  bool busy = false;

  static List<(String, String)> get _sectionNames => [
        ('summary', t('Summary')),
        ('entities', t('Entities')),
        ('relations', t('Relations')),
        ('links', t('Suspected links')),
        ('notes', t('Notes')),
        ('tags', t('Tags')),
        ('proofs', t('Proofs')),
        ('timeline', t('Timeline')),
      ];

  void _readLogo(String p) {
    p = p.trim();
    Uint8List? b;
    String? err;
    if (p.isNotEmpty) {
      try {
        final f = File(p);
        err = f.lengthSync() > maxLogoBytes ? t('The logo is larger than 1 MB') : null;
        if (err == null) {
          b = f.readAsBytesSync();
          err = logoProblem(b);
        }
      } catch (_) {
        err = t('Cannot read the file');
      }
      if (err != null) b = null;
    }
    setState(() {
      logo = b;
      logoError = err;
    });
  }

  String get _fileName {
    final base = title.text.trim().replaceAll(RegExp(r'[^\w\- ]+', unicode: true), '_');
    return '${base.isEmpty ? 'report' : base}.$format';
  }

  Future<void> _create() async {
    final o = ReportOptions(
      format: format,
      sections: [for (final s in reportSections) if (sections.contains(s)) s],
      title: title.text.trim(),
      header: header.text.trim(),
      footer: footer.text.trim(),
      logoBase64: logo == null ? null : base64Encode(logo!),
      includeHidden: hidden,
      lang: lang == 'app' ? appLang.value : lang,
    );
    _Last.format = format;
    _Last.sections = o.sections;
    _Last.header = o.header;
    _Last.footer = o.footer;
    _Last.lang = lang;
    _Last.hidden = hidden;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final path = await widget.save(_fileName, await widget.build(widget.inv, o));
      if (mounted) Navigator.pop(context, path);
    } catch (e) {
      if (mounted) {
        setState(() {
          busy = false;
          error = t('Error: {0}', [e]);
        });
      }
    }
  }

  Widget _label(String s) => Padding(
        padding: const EdgeInsets.only(top: 16, bottom: 6),
        child: Text(s.toUpperCase(), style: const TextStyle(fontSize: 10, letterSpacing: 1.6, color: dim)),
      );

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    return AlertDialog(
      title: Text(t('Custom report')),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _label(t('Format')),
            Wrap(spacing: 8, children: [
              for (final (v, n) in [('html', t('HTML (standalone)')), ('pdf', 'PDF'), ('md', 'Markdown')])
                ChoiceChip(label: Text(n), selected: format == v, onSelected: busy ? null : (_) => setState(() => format = v)),
            ]),
            _label(t('Sections')),
            Wrap(spacing: 8, runSpacing: 4, children: [
              for (final (v, n) in _sectionNames)
                FilterChip(
                  label: Text(n),
                  selected: sections.contains(v),
                  onSelected: busy ? null : (on) => setState(() => on ? sections.add(v) : sections.remove(v)),
                ),
            ]),
            _label(t('Text')),
            TextField(controller: title, decoration: InputDecoration(labelText: t('Title'), isDense: true)),
            const SizedBox(height: 8),
            TextField(controller: header, decoration: InputDecoration(labelText: t('Header'), isDense: true)),
            const SizedBox(height: 8),
            TextField(controller: footer, decoration: InputDecoration(labelText: t('Footer'), isDense: true)),
            _label(t('Logo')),
            Row(children: [
              Expanded(
                child: TextField(
                  controller: logoPath,
                  onChanged: _readLogo,
                  decoration: InputDecoration(labelText: t('Path of a PNG or JPEG file (max 1 MB)'), isDense: true, errorText: logoError),
                ),
              ),
              TextButton(
                onPressed: logoPath.text.isEmpty ? null : () {
                  logoPath.clear();
                  _readLogo('');
                },
                child: Text(t('Clear')),
              ),
              if (logo != null) Padding(padding: const EdgeInsets.only(left: 8), child: Image.memory(logo!, height: 32, errorBuilder: (_, _, _) => const SizedBox())),
            ]),
            if (widget.hasHidden)
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(t('Include hidden items')),
                value: hidden,
                onChanged: busy ? null : (v) => setState(() => hidden = v),
              ),
            _label(t('Report language')),
            DropdownButton<String>(
              value: lang,
              isDense: true,
              onChanged: busy ? null : (v) => setState(() => lang = v ?? 'app'),
              items: [
                DropdownMenuItem(value: 'app', child: Text(t('App language'))),
                for (final c in supportedLangs)
                  DropdownMenuItem(value: c, child: Row(children: [FlagIcon(c, width: 20), const SizedBox(width: 8), Text(langNames[c]!)])),
              ],
            ),
            if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: accent))),
          ]),
        ),
      ),
      actions: [
        TextButton(onPressed: busy ? null : () => Navigator.pop(context), child: Text(t('Cancel'))),
        FilledButton(
          onPressed: busy || sections.isEmpty || logoError != null ? null : _create,
          child: busy ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : Text(t('Create')),
        ),
      ],
    );
  }

  @override
  void dispose() {
    title.dispose();
    header.dispose();
    footer.dispose();
    logoPath.dispose();
    super.dispose();
  }
}
