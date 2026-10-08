import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api_ops.dart';
import 'l10n.dart';
import 'pivot_links.dart';
import 'theme.dart';

/// Asks what to do before saving a proof of [url]. Pops `true` (also archive at archive.org), `false` (local copy only) or null (cancel).
/// When [save] is given the dialog runs it itself, shows progress and errors, and pops the choice only on success.
class SaveProofDialog extends StatefulWidget {
  const SaveProofDialog({super.key, required this.url, this.entity, this.save});
  final String url;
  final int? entity;
  final Future<void> Function(bool archive)? save;

  @override
  State<SaveProofDialog> createState() => _SaveProofDialogState();
}

class _SaveProofDialogState extends State<SaveProofDialog> {
  bool archive = false, busy = false;
  String? error;

  Future<void> _go() async {
    if (widget.save == null) return Navigator.pop(context, archive);
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.save!(archive);
      if (mounted) Navigator.pop(context, archive);
    } catch (e) {
      if (mounted) {
        setState(() {
          busy = false;
          error = e.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    return AlertDialog(
      title: Text(t('Save proof'), style: const TextStyle(fontSize: 14)),
      content: SizedBox(
        width: 460,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          SelectableText(widget.url, style: const TextStyle(fontSize: 11.5, fontFamily: mono, fontFamilyFallback: monoFallback)),
          const SizedBox(height: 10),
          Text(t('The page is downloaded now and stored in this investigation: a copy of the page, its SHA-256 fingerprint and the time.'),
              style: const TextStyle(fontSize: 11.5, color: dim, height: 1.4)),
          const SizedBox(height: 8),
          CheckboxListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            value: archive,
            onChanged: busy ? null : (x) => setState(() => archive = x ?? false),
            title: Text(t('Also ask the Internet Archive to keep a copy'), style: const TextStyle(fontSize: 12.5)),
          ),
          Text(t('Warning: this sends the address to archive.org, and the archived copy becomes public.'), style: const TextStyle(fontSize: 11, color: gold, height: 1.4)),
          if (error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(error!, style: const TextStyle(fontSize: 11.5, color: accent))),
        ]),
      ),
      actions: [
        TextButton(onPressed: busy ? null : () => Navigator.pop(context), child: Text(t('Cancel'))),
        FilledButton(
          onPressed: busy ? null : _go,
          child: busy ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)) : Text(t('SAVE PROOF')),
        ),
      ],
    );
  }
}

/// Proofs saved for an investigation (or for one entity).
class ProofsDialog extends StatefulWidget {
  const ProofsDialog({super.key, required this.inv, this.entity, this.fetch, this.delete, this.open, this.copy});
  final int inv;
  final int? entity;
  // tests: replace the backend, browser and clipboard
  final Future<List<Proof>> Function(int inv, {int? entity})? fetch;
  final Future<void> Function(int inv, int id)? delete;
  final Future<void> Function(String url)? open;
  final Future<void> Function(String text)? copy;

  @override
  State<ProofsDialog> createState() => _ProofsDialogState();
}

class _ProofsDialogState extends State<ProofsDialog> {
  List<Proof>? proofs;
  String? error, notice;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final p = await (widget.fetch ?? fetchProofs)(widget.inv, entity: widget.entity);
      if (mounted) setState(() => proofs = p);
    } catch (e) {
      if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    }
  }

  Future<void> _delete(Proof p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        content: Text(t('Delete this proof? The stored copy cannot be recovered.'), style: const TextStyle(fontSize: 12.5)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(t('Cancel'))),
          FilledButton(style: FilledButton.styleFrom(backgroundColor: accent), onPressed: () => Navigator.pop(c, true), child: Text(t('DELETE'))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await (widget.delete ?? deleteProof)(widget.inv, p.id);
      if (mounted) setState(() => proofs = proofs!.where((x) => x.id != p.id).toList());
    } catch (e) {
      if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    }
  }

  Future<void> _copy(String hash) async {
    await (widget.copy ?? (s) => Clipboard.setData(ClipboardData(text: s)))(hash);
    if (mounted) setState(() => notice = t('Hash copied'));
  }

  String _size(int b) => b > 1e6 ? '${(b / 1e6).toStringAsFixed(1)} MB' : '${(b / 1e3).toStringAsFixed(0)} kB';

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    final list = proofs;
    final open = widget.open ?? openUrl;
    return Dialog(
      insetPadding: const EdgeInsets.all(24),
      child: SizedBox(
        width: 700,
        height: 560,
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 12, 0),
            child: Row(children: [
              Expanded(child: Text(t('PROOFS'), style: const TextStyle(fontSize: 12, letterSpacing: 2, fontWeight: FontWeight.w700))),
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
                        ? Center(child: Text(t('No proofs saved yet.'), style: const TextStyle(color: dim)))
                        : ListView(padding: const EdgeInsets.symmetric(horizontal: 20), children: [
                            for (final p in list)
                              Container(
                                margin: const EdgeInsets.only(bottom: 10),
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(border: Border.all(color: line), borderRadius: BorderRadius.circular(6)),
                                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                  Text(p.url, style: const TextStyle(fontSize: 12, fontFamily: mono, fontFamilyFallback: monoFallback), overflow: TextOverflow.ellipsis),
                                  const SizedBox(height: 4),
                                  Text(
                                      '${fmtDateTime(DateTime.fromMillisecondsSinceEpoch((p.ts * 1000).round()))} · HTTP ${p.status} · ${_size(p.size)}'
                                      '${p.truncated ? ' · ${t('truncated')}' : ''}',
                                      style: const TextStyle(fontSize: 11, color: dim)),
                                  Row(children: [
                                    Text('SHA-256 ${p.sha256.length > 12 ? p.sha256.substring(0, 12) : p.sha256}…',
                                        style: const TextStyle(fontSize: 11, fontFamily: mono, fontFamilyFallback: monoFallback, color: dim)),
                                    IconButton(
                                        tooltip: t('Copy full hash'), iconSize: 14, visualDensity: VisualDensity.compact, icon: const Icon(Icons.copy), onPressed: () => _copy(p.sha256)),
                                  ]),
                                  Wrap(spacing: 4, children: [
                                    TextButton(onPressed: () => open(proofSnapshotUrl(widget.inv, p.id)), child: Text(t('OPEN SNAPSHOT'), style: const TextStyle(fontSize: 11))),
                                    if (p.wayback.isNotEmpty) TextButton(onPressed: () => open(p.wayback), child: Text(t('WAYBACK COPY'), style: const TextStyle(fontSize: 11))),
                                    TextButton(onPressed: () => _delete(p), child: Text(t('DELETE'), style: const TextStyle(fontSize: 11, color: accent))),
                                  ]),
                                ]),
                              ),
                          ]),
          ),
          if (notice != null) Padding(padding: const EdgeInsets.only(bottom: 8), child: Text(notice!, style: const TextStyle(fontSize: 11, color: dim))),
        ]),
      ),
    );
  }
}
