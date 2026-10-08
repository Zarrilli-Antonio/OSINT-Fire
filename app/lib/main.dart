import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'ai_dialog.dart';
import 'api.dart';
import 'backend.dart';
import 'l10n.dart';
import 'graph_view.dart';
import 'manual_dialogs.dart';
import 'note_editor.dart';
import 'pivot_links.dart';
import 'platform.dart';
import 'settings_dialog.dart';
import 'theme.dart';

final homeKey = GlobalKey<State<Home>>();

void main() => runApp(const App());

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<String>(
        valueListenable: appLang,
        builder: (context, lang, _) => MaterialApp(
          title: 'OSINT-Fire',
          debugShowCheckedModeBanner: false,
          theme: buildTheme(),
          builder: (context, child) => LangScope(notifier: appLang, child: Backdrop(child: child!)),
          home: Home(key: homeKey), // not const: a new instance makes the whole screen rebuild in the new language
        ),
      );
}

class Home extends StatefulWidget {
  const Home({super.key, this.autostart = true, this.initialGraph, this.initialInv, this.initialName, this.initialSeeds, this.backendReadyForTests = false});
  final bool autostart; // false in tests: do not spawn the backend
  final Graph? initialGraph; // tests only: start with a loaded graph
  final int? initialInv;
  final String? initialName; // tests and README screenshots only: a search already filled in
  final List<(String, String)>? initialSeeds;
  final bool backendReadyForTests;

  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  final backend = Backend();
  late final AppLifecycleListener _life;
  String? backendError;
  bool backendReady = false;

  @override
  void initState() {
    super.initState();
    _life = AppLifecycleListener(onExitRequested: () async {
      backend.stop();
      return ui.AppExitResponse.exit;
    });
    if (widget.initialGraph != null) {
      _raw = widget.initialGraph!;
      inv = widget.initialInv;
    }
    name.text = widget.initialName ?? '';
    seeds.addAll(widget.initialSeeds ?? const []);
    if (widget.backendReadyForTests) backendReady = true;
    if (widget.autostart) _startBackend();
  }

  Future<void> _startBackend() async {
    setState(() {
      backendError = null;
      backendReady = false;
    });
    final err = await backend.ensure();
    if (mounted) setState(() => (backendError = err, backendReady = err == null));
    if (err == null) await _loadSettings();
  }

  /// Pull the user's settings and apply the ones the UI uses (default depth, grouping threshold).
  Future<void> _loadSettings() async {
    try {
      var st = await fetchSettings();
      if (!mounted) return;
      if (st.strOf('language').isEmpty) st = await saveSettings({'language': appLang.value}); // first run: keep the system language
      appLang.value = st.strOf('language');
      setState(() {
        settings = st;
        groupMin = st.intOf('group_min');
        if (!running) depth = st.intOf('default_depth');
      });
    } catch (_) {}
  }

  int get _maxEntities => settings?.intOf('default_max_entities') ?? 300;

  Future<void> _openSettings({int tab = 0}) async {
    final saved = await showDialog<bool>(context: context, builder: (_) => SettingsDialog(backend: backend, initialTab: tab));
    if (saved == true) {
      await _loadSettings();
      // a wipe may have removed the open investigation
      if (inv != null && !(await listInvestigations()).any((i) => i['id'] == inv) && mounted) {
        setState(() {
          inv = null;
          graph = Graph([], []);
          selected = null;
        });
      } else if (inv != null && mounted) {
        await _reloadGraph(); // labels come from the server in the chosen language
      }
    }
  }

  Future<void> _openAi() async {
    if (inv == null) return;
    final r = await showDialog<Object>(context: context, builder: (_) => AiDialog(inv: inv!));
    if (r == 'settings') {
      await _openSettings(tab: 3);
    } else if (r is AiPivot) {
      await _expand((r.type, r.value), 1);
    }
  }

  @override
  void dispose() {
    searchCtl.dispose();
    searchFocus.dispose();
    _life.dispose();
    backend.stop();
    super.dispose();
  }

  final value = TextEditingController();
  final name = TextEditingController();
  final purpose = TextEditingController();
  String type = 'Dominio';
  final seeds = <(String, String)>[];
  int depth = 2;
  bool running = false;
  bool stopping = false;
  Graph _raw = Graph([], []);
  final graphKey = GlobalKey<GraphViewState>();
  final searchCtl = TextEditingController();
  final searchFocus = FocusNode();
  String query = '';
  int _matchIdx = -1;
  bool groupNodes = true;
  Settings? settings;
  SavedLayout? layout; // positions/camera saved for the open investigation
  Set<int>? newIds; // entities added by the latest update
  double? sinceTs;
  double? updatedAt;
  int? runCount;
  int groupMin = 6;
  bool sidebarOpen = true;
  String viewMode = 'clean'; // clean = hidden nodes omitted, full = hidden nodes shown faded, split = both side by side
  final graphKey2 = GlobalKey<GraphViewState>();
  bool linkMode = false; // choosing the two ends of a bridge
  GNode? linkFrom;
  int _hiddenVer = 0;
  final _memo = <bool, (String, Graph)>{};

  /// The graph as displayed: raw data, with or without the hidden nodes, optionally with leaf groups collapsed. Memoised so
  /// GraphView sees a stable object between rebuilds.
  Graph _view(bool withHidden) {
    final key = '${identityHashCode(_raw)}|$groupNodes|$groupMin|$_hiddenVer';
    final m = _memo[withHidden];
    if (m != null && m.$1 == key) return m.$2;
    final g = withHidden ? _raw : withoutHidden(_raw);
    final out = groupNodes ? collapseGroups(g, min: groupMin, keep: {for (final n in g.nodes) if (n.manual) n.id}) : g;
    _memo[withHidden] = (key, out);
    return out;
  }

  /// What the selection, search, stats and detail panel work on: the primary view.
  Graph get graph => _view(viewMode != 'clean');

  set graph(Graph g) => _raw = g;
  final log = <String>[];
  GNode? selected;
  Timer? refresh;
  int? inv;

  Future<void> start() async {
    _addSeed();
    if (seeds.isEmpty || name.text.trim().isEmpty) {
      setState(() => log.insert(0, t('A name and at least one seed are required')));
      return;
    }
    setState(() {
      running = true;
      graph = Graph([], []);
      selected = null;
      layout = null;
      newIds = null;
      sinceTs = null;
      updatedAt = null;
      log.clear();
    });
    try {
      inv = await createInvestigation(name: name.text.trim(), purpose: purpose.text.trim(), seeds: seeds, maxDepth: depth, maxEntities: _maxEntities);
    } catch (e) {
      if (mounted) {
        setState(() {
          log.insert(0, t('Error: {0} (is the backend running on {1}?)', [e, baseUrl]));
          running = false;
        });
      }
      return;
    }
    await _follow(inv!);
  }

  Future<void> _stop() async {
    if (inv == null || !running || stopping) return;
    setState(() {
      stopping = true;
      log.insert(0, t('Stop requested…'));
    });
    try {
      await stopInvestigation(inv!);
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error: {0}', [e])));
    } finally {
      if (mounted) setState(() => stopping = false);
    }
  }

  /// Extend the current investigation from one entity already in the graph.
  Future<void> _expand((String, String) target, int d) async {
    if (inv == null || running) return;
    sinceTs = DateTime.now().millisecondsSinceEpoch / 1000 - 1;
    setState(() {
      running = true;
      log.insert(0, t('↳ expanding from {0} · {1} (depth {2})', [graph.typeName(target.$1), target.$2, d]));
    });
    try {
      await expandInvestigation(inv!, [target], d, maxEntities: _maxEntities);
    } catch (e) {
      if (mounted) {
        setState(() {
          log.insert(0, t('Error: {0}', [e]));
          running = false;
        });
      }
      return;
    }
    await _follow(inv!);
  }

  /// Stream the events of a running investigation and keep the graph refreshed.
  Future<void> _follow(int id) async {
    try {
      await for (final ev in events(id)) {
        setState(() => log.insert(0, _fmt(ev)));
        // throttle graph refetch while events stream in
        refresh ??= Timer(const Duration(milliseconds: 500), () async {
          refresh = null;
          final g = await fetchGraph(id);
          if (mounted) setState(() => graph = g);
        });
      }
      refresh?.cancel();
      refresh = null;
      final g = await fetchGraph(id);
      final d = await fetchInvestigation(id);
      if (mounted) {
        setState(() {
          graph = g;
          updatedAt = d.updated;
          runCount = d.runs;
          final since = sinceTs;
          // only an update of an already populated graph has "new" data worth flagging
          newIds = since == null ? null : {for (final n in g.nodes) if (n.added >= since) n.id};
          if (newIds != null && newIds!.isEmpty) newIds = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error: {0} (is the backend running on {1}?)', [e, baseUrl])));
    } finally {
      if (mounted) setState(() => running = false);
    }
  }

  /// Reset everything for a fresh investigation (the previous one stays saved in the history).
  void _newSearch() {
    if (running) return;
    refresh?.cancel();
    refresh = null;
    setState(() {
      inv = null;
      graph = Graph([], []);
      selected = null;
      seeds.clear();
      name.clear();
      purpose.clear();
      value.clear();
      log.clear();
      query = '';
      searchCtl.clear();
      _matchIdx = -1;
      viewMode = 'clean';
      linkMode = false;
      linkFrom = null;
      layout = null;
      newIds = null;
      sinceTs = null;
      updatedAt = null;
      runCount = null;
    });
  }

  Set<int>? _highlight() {
    final q = query.trim().toLowerCase();
    if (q.isEmpty) return null;
    bool has(String? s) => s != null && s.toLowerCase().contains(q);
    return {
      for (final n in graph.nodes)
        if (has(n.value) || has(n.label) || has(n.type) || has(graph.typeName(n.type)) || n.members.any(has) || has(graph.notes[n.id]?.text)) n.id
    };
  }

  void _clearSearch() {
    if (linkMode) _cancelLink(); // Esc also leaves bridge mode, whichever widget has the focus
    searchCtl.clear();
    setState(() {
      query = '';
      _matchIdx = -1;
    });
    searchFocus.unfocus();
  }

  void _select(GNode n) {
    setState(() => selected = n);
    graphKey.currentState?.focusOn(n.id);
  }

  void _nextMatch(Set<int> hl) {
    if (hl.isEmpty) return;
    final ids = hl.toList()..sort();
    _matchIdx = (_matchIdx + 1) % ids.length;
    _select(graph.nodes.firstWhere((n) => n.id == ids[_matchIdx]));
  }

  /// Update the user's note/star on a node: optimistic local change (map shared with the raw graph), then persist.
  Future<void> _saveNote(GNode n, {String? text, bool? starred}) async {
    if (inv == null) return;
    final cur = graph.notes[n.id];
    final next = GNote((text ?? cur?.text ?? '').trim(), starred ?? cur?.starred ?? false);
    if (next.text.isEmpty && !next.starred) {
      graph.notes.remove(n.id);
    } else {
      graph.notes[n.id] = next;
    }
    if (mounted) setState(() {});
    graphKey.currentState?.repaintNow();
    try {
      await saveNote(inv!, n.id, next.text, next.starred);
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error, note: {0}', [e])));
    }
  }

  // ---------- hiding ----------

  List<int> _idsOf(GNode n) => n.memberIds.isNotEmpty ? n.memberIds : [n.id];

  Future<void> _setHidden(Iterable<int> ids, bool hide) async {
    final list = ids.where((i) => i > 0).toList();
    if (inv == null || list.isEmpty) return;
    void apply(Iterable<int> changed) {
      setState(() {
        hide ? _raw.hidden.addAll(changed) : _raw.hidden.removeAll(changed);
        _hiddenVer++;
        if (hide && viewMode == 'clean') selected = null;
      });
      graphKey.currentState?.repaintNow();
      graphKey2.currentState?.repaintNow();
    }

    apply(list); // immediately, then add what the server hid/showed along with them (nodes that hung only from these)
    try {
      final changed = await setHidden(inv!, list, hide);
      if (mounted) apply(changed);
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error: {0}', [e])));
    }
  }

  Future<void> _unhideAll() => _setHidden(_raw.hidden.toList(), false);

  // ---------- nodes and bridges made by hand ----------

  Future<void> _reloadGraph() async {
    if (inv == null) return;
    final g = await fetchGraph(inv!);
    if (mounted) setState(() => graph = g);
  }

  Future<void> _addNode() async {
    if (inv == null) return;
    final r = await showDialog<(String, String)>(context: context, builder: (_) => const NodeDialog());
    if (r == null) return;
    try {
      final (id, created) = await createEntity(inv!, r.$1, r.$2);
      await _reloadGraph();
      if (mounted) setState(() => log.insert(0, created ? t('+ node created: {0} · {1}', [typeLabel(r.$1), r.$2]) : t('Already existed: {0} · {1}', [typeLabel(r.$1), r.$2])));
      final n = graph.nodes.where((x) => x.id == id).firstOrNull;
      if (n != null) _select(n);
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error: {0}', [e.toString().replaceFirst('Exception: ', '')])));
    }
  }

  Future<void> _editNode(GNode n) async {
    final r = await showDialog<(String, String)>(context: context, builder: (_) => NodeDialog(type: n.type, value: n.value));
    if (r == null || inv == null) return;
    try {
      await updateEntity(inv!, n.id, type: r.$1, value: r.$2);
      await _reloadGraph();
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error: {0}', [e.toString().replaceFirst('Exception: ', '')])));
    }
  }

  Future<void> _deleteNode(GNode n) async {
    if (inv == null) return;
    final ids = _idsOf(n);
    final detail = n.members.isNotEmpty
        ? t('The {0} nodes of the group are deleted along with their links. Data that came only from them is hidden (you can show it again). An update will not recreate them.', [ids.length])
        : n.manual
            ? t('The bridges that connect it and its notes are deleted too. Data that came only from it is hidden (you can show it again).')
            : t('The node and its links are deleted and an update will not recreate it. Data that came only from it is hidden (you can show it again).');
    if (!await _confirmDelete(context, n.label, title: n.members.isNotEmpty ? t('Delete group «{0}»?', [n.label]) : t('Delete node «{0}»?', [n.label]), detail: detail)) return;
    try {
      final (deleted, hidden) = await deleteEntities(inv!, ids);
      setState(() {
        selected = null;
        log.insert(0, hidden.isEmpty ? t('✕ deleted {0} nodes', [deleted]) : t('✕ deleted {0} nodes, hid {1} that depended on them', [deleted, hidden.length]));
      });
      await _reloadGraph();
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error: {0}', [e.toString().replaceFirst('Exception: ', '')])));
    }
  }

  Future<void> _deleteBridge(GEdge e) async {
    if (inv == null) return;
    try {
      await deleteRelation(inv!, e.id);
      await _reloadGraph();
    } catch (err) {
      if (mounted) setState(() => log.insert(0, t('Error: {0}', [err.toString().replaceFirst('Exception: ', '')])));
    }
  }

  void _startLink([GNode? from]) {
    if (inv == null) return;
    setState(() {
      linkMode = true;
      linkFrom = from; // the description panel stays closed while choosing: it would only be in the way
    });
  }

  void _cancelLink() => setState(() {
        linkMode = false;
        linkFrom = null;
        selected = null; // leaving bridge mode must not pop a description open
      });

  void _onSelect(GNode? n) {
    if (linkMode && n != null) {
      _pickLinkEnd(n);
      return;
    }
    setState(() => selected = n);
  }

  Future<void> _pickLinkEnd(GNode n) async {
    if (n.id <= 0) {
      setState(() => log.insert(0, t('A group cannot be linked: turn off «group» to pick a single node')));
      return;
    }
    final from = linkFrom;
    if (from == null) {
      setState(() => linkFrom = n);
      return;
    }
    if (from.id == n.id) return;
    final r = await showDialog<(String, String)>(context: context, builder: (_) => BridgeDialog(from: from.value, to: n.value));
    if (r == null) {
      _cancelLink();
      return;
    }
    try {
      await createRelation(inv!, from.id, n.id, r.$1, reason: r.$2);
      await _reloadGraph();
      if (mounted) setState(() => log.insert(0, t('+ bridge: {0} —{1}→ {2}', [from.label, r.$1, n.label])));
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error: {0}', [e.toString().replaceFirst('Exception: ', '')])));
    }
    if (mounted) {
      setState(() {
        linkMode = false;
        linkFrom = null;
        selected = null;
      });
    }
  }

  /// A map with no search behind it: nodes and bridges are all made by hand.
  Future<void> _createBlank() async {
    if (name.text.trim().isEmpty) {
      setState(() => log.insert(0, t('Give the map a name')));
      return;
    }
    try {
      final id = await createInvestigation(name: name.text.trim(), purpose: purpose.text.trim(), seeds: const [], maxDepth: depth);
      await _open(id);
    } catch (e) {
      if (mounted) setState(() => log.insert(0, t('Error: {0}', [e.toString().replaceFirst('Exception: ', '')])));
    }
  }

  void _addSeed() {
    final v = value.text.trim();
    if (v.isEmpty) return;
    setState(() {
      seeds.add((type, v));
      value.clear();
    });
  }

  Future<bool> _confirmDelete(BuildContext c, String name, {String? title, String? detail}) async =>
      await showDialog<bool>(
        context: c,
        builder: (d) => AlertDialog(
          title: Text(title ?? t('Delete search «{0}»?', [name])),
          content: Text(detail ?? t('Graph, evidence, images and cached results of this search are deleted. This cannot be undone.')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(d, false), child: Text(t('Cancel'))),
            FilledButton(onPressed: () => Navigator.pop(d, true), child: Text(t('Delete'))),
          ],
        ),
      ) ??
      false;

  /// Open a saved investigation exactly as it was left: search definition in the form, nodes where they were, same camera.
  Future<void> _open(int id) async {
    final r = await Future.wait([fetchGraph(id), fetchInvestigation(id), fetchLayout(id)]);
    final g = r[0] as Graph, d = r[1] as InvestigationDetail, l = r[2] as SavedLayout;
    if (!mounted) return;
    setState(() {
      inv = id;
      graph = g;
      layout = l;
      viewMode = const {'clean', 'full', 'split'}.contains(l.view['mode']) ? l.view['mode'] as String : 'clean';
      linkMode = false;
      linkFrom = null;
      selected = null;
      newIds = null;
      sinceTs = null;
      name.text = d.name;
      purpose.text = d.purpose;
      seeds
        ..clear()
        ..addAll(d.seeds);
      depth = d.maxDepth;
      updatedAt = d.updated;
      runCount = d.runs;
      log.insert(0, t('Loaded «{0}» (#{1})', [d.name, id]));
    });
  }

  /// Re-run the open investigation as it is defined in the form (seeds, depth), ignoring cached results.
  Future<void> _refresh() async {
    if (inv == null || running) return;
    _addSeed();
    if (seeds.isEmpty || name.text.trim().isEmpty) {
      setState(() => log.insert(0, t('A name and at least one seed are required')));
      return;
    }
    setState(() {
      running = true;
      log.insert(0, t('↻ updating «{0}»', [name.text.trim()]));
    });
    try {
      sinceTs = await refreshInvestigation(inv!, name: name.text.trim(), purpose: purpose.text.trim(), seeds: seeds, maxDepth: depth);
    } catch (e) {
      if (mounted) {
        setState(() {
          log.insert(0, t('Error: {0}', [e]));
          running = false;
        });
      }
      return;
    }
    await _follow(inv!);
  }

  String _when(double ts) {
    return fmtDateTime(DateTime.fromMillisecondsSinceEpoch((ts * 1000).round()));
  }

  Future<void> _export(String fmt) async {
    if (inv == null) return;
    final dl = downloadsDir();
    try {
      String done;
      if (fmt == 'obsidian') {
        final dir = '$dl${Platform.pathSeparator}osint-$inv-vault';
        for (final e in (await exportVault(inv!, includeHidden: viewMode != 'clean')).entries) {
          final f = File('$dir/${e.key}');
          await f.parent.create(recursive: true);
          await f.writeAsString(e.value);
        }
        done = dir;
      } else {
        done = '$dl${Platform.pathSeparator}osint-$inv.$fmt';
        await File(done).writeAsBytes(await exportBytes(inv!, fmt, includeHidden: viewMode != 'clean'));
      }
      setState(() => log.insert(0, t('Exported: {0}', [done])));
    } catch (e) {
      setState(() => log.insert(0, t('Error, export: {0}', [e])));
    }
  }

  String _fmt(Map<String, dynamic> e) => switch (e['type']) {
        'run' => t('{0} · {1} · {2} results', [e['collector'], e['target'], e['found']]),
        'entity' => '+ ${e['entity']['type_label'] ?? e['entity']['type']} ${e['entity']['label'] ?? e['entity']['value']}',
        'error' => '✗ ${e['collector']} · ${e['target']}',
        'done' => e['stopped'] == true
            ? t('Stopped · partial results saved')
            : (e['new'] is int && (e['new'] as int) > 0 ? t('Completed · +{0} new items', [e['new']]) : t('Completed')),
        _ => e.toString(),
      };

  @override
  Widget build(BuildContext context) {
    final sel = selected == null || linkMode ? null : graph.nodes.where((n) => n.id == selected!.id).firstOrNull;
    final hl = _highlight();
    return CallbackShortcuts(
      bindings: {
        // ⌘ on macOS, Ctrl on Windows and Linux
        for (final meta in [true, false]) ...{
          SingleActivator(LogicalKeyboardKey.keyB, meta: meta, control: !meta): () => setState(() => sidebarOpen = !sidebarOpen),
          SingleActivator(LogicalKeyboardKey.keyF, meta: meta, control: !meta): () => searchFocus.requestFocus(),
          SingleActivator(LogicalKeyboardKey.keyN, meta: meta, control: !meta): _newSearch,
        },
        const SingleActivator(LogicalKeyboardKey.escape): () => linkMode ? _cancelLink() : null,
      },
      child: Focus(
        autofocus: true,
        child: Scaffold(
          body: Row(children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 220),
              curve: Curves.easeOutCubic,
              width: sidebarOpen ? 330 : 48,
              decoration: const BoxDecoration(color: Color(0x99080809), border: Border(right: BorderSide(color: line))),
              child: ClipRect(
                child: sidebarOpen
                    ? OverflowBox(alignment: Alignment.topLeft, minWidth: 330, maxWidth: 330, child: _sidebar())
                    : _rail(),
              ),
            ),
            Expanded(
              child: Stack(children: [
                Row(children: [
                  Expanded(child: _pane(graphKey, graph, sel, hl, ghosts: viewMode == 'clean' ? null : _raw.hidden, title: viewMode == 'split' ? t('WITH HIDDEN') : null)),
                  if (viewMode == 'split') ...[
                    const VerticalDivider(width: 1),
                    Expanded(child: _pane(graphKey2, _view(false), sel, hl, saves: false, title: t('WITHOUT HIDDEN'))),
                  ],
                ]),
                if (graph.nodes.isNotEmpty) Positioned(left: 16, top: 16, width: 280, child: _searchBox(hl)),
                if (graph.nodes.isEmpty)
                  Center(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      Opacity(opacity: 0.85, child: Image.asset('assets/icon.png', width: 110, height: 110)),
                      const SizedBox(height: 18),
                      Text(t('// no graph\n// start a search'), textAlign: TextAlign.center, style: TextStyle(color: dim, height: 1.8)),
                    ]),
                  ),
                if (_raw.hidden.isNotEmpty && graph.nodes.isNotEmpty) Positioned(bottom: 14, left: 0, right: 0, child: Center(child: _viewBar())),
                if (linkMode) Positioned(top: 16, left: 0, right: 0, child: Center(child: _linkBanner())),
                if (sel != null) Positioned(right: 16, top: 16, width: 360, child: _detail(sel)),
              ]),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _pane(GlobalKey<GraphViewState> key, Graph g, GNode? sel, Set<int>? hl, {Set<int>? ghosts, bool saves = true, String? title}) => ClipRect(
          child: Stack(children: [
        GraphView(
          key: key,
          graph: g,
          selected: (linkMode ? linkFrom : sel)?.id, // while drawing a bridge, only the chosen start node is marked
          highlight: hl,
          layout: layout,
          layoutId: inv,
          newIds: newIds,
          ghostIds: ghosts,
          saveLayoutEnabled: saves,
          linkMode: linkMode,
          onAddNode: inv == null ? null : _addNode,
          onToggleLink: inv == null ? null : (linkMode ? _cancelLink : _startLink),
          onSelect: _onSelect,
          onLayoutChanged: (id, nodes, view) => saveLayout(id, nodes, {...view, 'mode': viewMode}).catchError((Object _) {}),
        ),
        if (title != null)
          Positioned(
            top: 12,
            right: 16,
            child: IgnorePointer(child: Text(title, style: const TextStyle(fontSize: 10, letterSpacing: 2, color: dim))),
          ),
      ]));

  /// Switch between the three ways to look at hidden nodes.
  Widget _viewBar() => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
        decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(6), border: Border.all(color: line)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          for (final (m, label, tip) in [
            ('clean', t('CLEAN'), t('Without the hidden nodes')),
            ('full', t('FULL'), t('With the hidden nodes, faded')),
            ('split', t('SIDE BY SIDE'), t('The two views next to each other')),
          ])
            Tooltip(
              message: tip,
              child: InkWell(
                borderRadius: BorderRadius.circular(4),
                onTap: () {
                  setState(() {
                    viewMode = m;
                    if (m == 'clean' && selected != null && _raw.hidden.contains(selected!.id)) selected = null;
                  });
                  // the panes change width when the split opens or closes: frame the graph again once they have their new size
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    graphKey.currentState?.fit();
                    graphKey2.currentState?.fit();
                  });
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(color: viewMode == m ? accent.withValues(alpha: 0.2) : null, borderRadius: BorderRadius.circular(4)),
                  child: Text(label, style: TextStyle(fontSize: 10.5, letterSpacing: 1.2, color: viewMode == m ? fg : dim)),
                ),
              ),
            ),
          const SizedBox(width: 8),
          Text(t('{0} hidden', [_raw.hidden.length]), style: const TextStyle(fontSize: 10.5, color: dim)),
          TextButton(onPressed: _unhideAll, child: Text(t('SHOW ALL'), style: TextStyle(fontSize: 10.5, letterSpacing: 1))),
        ]),
      );

  Widget _linkBanner() => Container(
        padding: const EdgeInsets.fromLTRB(14, 6, 6, 6),
        decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(6), border: Border.all(color: accent)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.share_outlined, size: 14, color: accent),
          const SizedBox(width: 10),
          Text(linkFrom == null ? t('BRIDGE · click the start node') : t('BRIDGE · from «{0}» click the destination', [linkFrom!.label.length > 28 ? '${linkFrom!.label.substring(0, 28)}…' : linkFrom!.label]),
              style: const TextStyle(fontSize: 11.5)),
          TextButton(onPressed: _cancelLink, child: Text(t('CANCEL (Esc)'), style: TextStyle(fontSize: 10.5))),
        ]),
      );

  Widget _searchBox(Set<int>? hl) => CallbackShortcuts(
        bindings: {const SingleActivator(LogicalKeyboardKey.escape): _clearSearch},
        child: Container(
          decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(6), border: Border.all(color: line)),
          child: TextField(
            controller: searchCtl,
            focusNode: searchFocus,
            style: const TextStyle(fontSize: 12),
            decoration: InputDecoration(
              hintText: t('search the graph (⌘/Ctrl+F)'),
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              prefixIcon: const Icon(Icons.search, size: 16),
              suffixIcon: hl == null
                  ? null
                  : Row(mainAxisSize: MainAxisSize.min, children: [
                      Text(t('{0} found', [hl.length]), style: TextStyle(fontSize: 11, color: hl.isEmpty ? accent : dim)),
                      IconButton(
                        tooltip: t('Hide the nodes found'),
                        icon: const Icon(Icons.visibility_off_outlined, size: 16),
                        onPressed: hl.isEmpty ? null : () => _setHidden([for (final n in graph.nodes) if (hl.contains(n.id)) ..._idsOf(n)], true),
                      ),
                      IconButton(
                        tooltip: t('Hide all the others (only what you found stays)'),
                        icon: const Icon(Icons.filter_alt_outlined, size: 16),
                        onPressed: hl.isEmpty ? null : () => _setHidden([for (final n in graph.nodes) if (!hl.contains(n.id)) ..._idsOf(n)], true),
                      ),
                    ]),
              contentPadding: const EdgeInsets.symmetric(vertical: 10),
            ),
            onChanged: (v) => setState(() {
              query = v;
              _matchIdx = -1;
            }),
            onSubmitted: (_) {
              if (hl != null) _nextMatch(hl);
              searchFocus.requestFocus();
            },
          ),
        ),
      );

  Widget _rail() => Column(children: [
        const SizedBox(height: 12),
        Image.asset('assets/icon.png', width: 28, height: 28),
        const SizedBox(height: 4),
        IconButton(tooltip: t('Open panel (⌘/Ctrl+B)'), icon: const Icon(Icons.chevron_right), onPressed: () => setState(() => sidebarOpen = true)),
        IconButton(tooltip: t('New search (⌘/Ctrl+N)'), icon: const Icon(Icons.add_circle_outline), onPressed: running ? null : _newSearch),
        const SizedBox(height: 6),
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
              color: backendReady ? accent : dim, shape: BoxShape.circle, boxShadow: backendReady ? const [BoxShadow(color: accent, blurRadius: 8)] : null),
        ),
        const SizedBox(height: 10),
        _history(),
        _exportMenu(),
        IconButton(tooltip: t('AI analysis'), icon: const Icon(Icons.auto_awesome, size: 18), onPressed: inv == null ? null : _openAi),
        IconButton(tooltip: t('Settings'), icon: const Icon(Icons.tune, size: 18), onPressed: _openSettings),
      ]);

  Widget _exportMenu() => PopupMenuButton<String>(
        tooltip: t('Export'),
        enabled: inv != null,
        icon: const Icon(Icons.file_download_outlined, size: 18),
        onSelected: _export,
        itemBuilder: (_) => [
          const PopupMenuItem(value: 'pdf', child: Text('PDF')),
          const PopupMenuItem(value: 'md', child: Text('Markdown')),
          PopupMenuItem(value: 'obsidian', child: Text(t('Obsidian folder'))),
          const PopupMenuItem(value: 'graphml', child: Text('GraphML')),
        ],
      );

  Widget _label(String s) => Padding(
        padding: const EdgeInsets.only(top: 18, bottom: 2),
        child: Text(s.toUpperCase(), style: const TextStyle(fontSize: 10, letterSpacing: 1.6, color: dim)),
      );

  Widget _history() => IconButton(
        tooltip: t('Previous searches'),
        icon: const Icon(Icons.history),
        onPressed: () async {
          final all = [...await listInvestigations()];
          if (!mounted) return;
          final id = await showDialog<int>(
            context: context,
            builder: (c) {
              var q = '';
              return StatefulBuilder(builder: (c, setD) {
                final shown = all.where((i) => '${i['name']} ${i['purpose']}'.toLowerCase().contains(q.toLowerCase()));
                return SimpleDialog(
                  title: Text(t('Previous searches'), style: TextStyle(fontSize: 14)),
                  children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 24),
                      child: TextField(
                          autofocus: true,
                          decoration: InputDecoration(hintText: t('search by name'), prefixIcon: Icon(Icons.search, size: 16)),
                          onChanged: (v) => setD(() => q = v)),
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: 420,
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                        for (final i in shown)
                          ListTile(
                            dense: true,
                            title: Text('${i['name']}'),
                            subtitle: Text(t('#{0} · {1} entities · upd. {2}', [i['id'], i['entities'], _when((i['updated'] as num) > 0 ? (i['updated'] as num).toDouble() : (i['created'] as num).toDouble())]), style: const TextStyle(color: dim, fontSize: 11)),
                            onTap: () => Navigator.pop(c, i['id'] as int),
                            trailing: IconButton(
                              tooltip: t('Delete'),
                              icon: const Icon(Icons.delete_outline),
                              onPressed: () async {
                                if (await _confirmDelete(c, '${i['name']}')) {
                                  await deleteInvestigation(i['id'] as int);
                                  all.remove(i);
                                  setD(() {});
                                  if (inv == i['id'] && mounted) {
                                    setState(() {
                                      inv = null;
                                      graph = Graph([], []);
                                      selected = null;
                                    });
                                  }
                                }
                              },
                            ),
                          ),
                        if (shown.isEmpty) Padding(padding: const EdgeInsets.all(16), child: Text(t('no results'), style: const TextStyle(color: dim))),
                      ]),
                    ),
                  ],
                );
              });
            },
          );
          if (id != null) _open(id);
        },
      );

  Widget _sidebar() => Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Image.asset('assets/icon.png', width: 30, height: 30),
            const SizedBox(width: 10),
            const Expanded(child: Text('OSINT/FIRE', style: TextStyle(fontSize: 14, letterSpacing: 3, fontWeight: FontWeight.w700))),
            IconButton(tooltip: t('Collapse panel (⌘/Ctrl+B)'), icon: const Icon(Icons.chevron_left), onPressed: () => setState(() => sidebarOpen = false)),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            IconButton(tooltip: t('New search (⌘/Ctrl+N)'), icon: const Icon(Icons.add_circle_outline), onPressed: running ? null : _newSearch),
            _history(),
            _exportMenu(),
            IconButton(tooltip: t('AI analysis'), icon: const Icon(Icons.auto_awesome, size: 18), onPressed: inv == null ? null : _openAi),
            IconButton(tooltip: t('Settings'), icon: const Icon(Icons.tune, size: 18), onPressed: _openSettings),
          ]),
          _label(t('Search')),
          TextField(controller: name, decoration: InputDecoration(hintText: t('name'))),
          TextField(controller: purpose, decoration: InputDecoration(hintText: t('purpose (optional)'))),
          _label(t('Seed')),
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            SizedBox(
              width: 112,
              child: DropdownButtonFormField<String>(
                initialValue: type,
                isExpanded: true,
                dropdownColor: const Color(0xFF131316),
                items: [for (final ty in ['Dominio', 'Email', 'Username', 'IP', 'Telefono', 'Persona', 'Azienda']) DropdownMenuItem(value: ty, child: Text(typeLabel(ty), style: const TextStyle(fontSize: 12)))],
                onChanged: (v) => setState(() => type = v!),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: value,
                decoration: InputDecoration(
                    hintText: t('value'),
                    suffixIcon: IconButton(tooltip: t('Add seed'), icon: const Icon(Icons.add, size: 16), onPressed: _addSeed)),
                onSubmitted: (_) => _addSeed(),
              ),
            ),
          ]),
          if (seeds.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Wrap(spacing: 6, runSpacing: 6, children: [
                for (final s in seeds)
                  InputChip(
                    label: Text('${typeLabel(s.$1)} · ${s.$2}'),
                    visualDensity: VisualDensity.compact,
                    avatar: Container(width: 7, height: 7, decoration: BoxDecoration(color: typeColor(s.$1), shape: BoxShape.circle)),
                    onDeleted: () => setState(() => seeds.remove(s)),
                  ),
              ]),
            ),
          _label(t('Depth · {0}', [depth])),
          Slider(value: depth.toDouble(), min: 0, max: 4, divisions: 4, onChanged: (v) => setState(() => depth = v.round())),
          const SizedBox(height: 6),
          if (running)
            OutlinedButton(
              style: OutlinedButton.styleFrom(
                foregroundColor: accent,
                side: const BorderSide(color: accent),
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
              ),
              onPressed: stopping ? null : _stop,
              child: Text(stopping ? t('STOPPING…') : t('STOP'), style: const TextStyle(fontSize: 12, letterSpacing: 1.2, fontWeight: FontWeight.w600)),
            )
          else if (inv == null) ...[
            FilledButton(onPressed: !backendReady ? null : start, child: Text(t('START'))),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(onPressed: backendReady ? _createBlank : null, child: Text(t('or create an empty map to build by hand'), style: TextStyle(fontSize: 10.5))),
            ),
          ] else ...[
            FilledButton(onPressed: !backendReady || seeds.isEmpty ? null : _refresh, child: Text(t('UPDATE'))),
            if (seeds.isEmpty)
              Padding(padding: const EdgeInsets.only(top: 6), child: Text(t('map without seeds: add one to be able to update it'), style: const TextStyle(fontSize: 10.5, color: dim))),
            if (updatedAt != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(runCount == null ? t('last update {0}', [_when(updatedAt!)]) : t('last update {0} · {1} runs', [_when(updatedAt!), runCount]), style: const TextStyle(fontSize: 10.5, color: dim)),
              ),
          ],
          if (!backendReady)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Row(children: [
                Expanded(child: Text(backendError ?? t('starting backend…'), style: TextStyle(fontSize: 11, color: backendError == null ? dim : accent))),
                if (backendError != null) TextButton(onPressed: _startBackend, child: Text(t('retry'))),
              ]),
            ),
          const SizedBox(height: 16),
          const Divider(),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              Expanded(child: Text(t('{0} nodes · {1} edges', [graph.nodes.length, graph.edges.length]), style: const TextStyle(fontSize: 11, color: dim))),
              if (newIds != null)
                InkWell(
                  onTap: () => setState(() => newIds = null),
                  child: Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Text(t('● {0} new ✕', [newIds!.length]), style: const TextStyle(fontSize: 11, color: Color(0xFF7EE787))),
                  ),
                ),
              Text(t('group'), style: const TextStyle(fontSize: 11, color: dim)),
              Transform.scale(
                scale: 0.7,
                child: Switch(value: groupNodes, onChanged: (v) => setState(() => groupNodes = v)),
              ),
            ]),
          ),
          if (graph.links.any((l) => l.status == 'review')) ...[
            const Divider(),
            _label(t('To review')),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 220),
              child: ListView(shrinkWrap: true, children: [
                for (final l in graph.links.where((l) => l.status == 'review')) _review(l),
              ]),
            ),
            const SizedBox(height: 8),
          ],
          if (graph.nodes.any((n) => graph.notes[n.id]?.starred ?? false)) ...[
            const Divider(),
            _label(t('Favorites')),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 150),
              child: ListView(shrinkWrap: true, children: [
                for (final n in graph.nodes.where((n) => graph.notes[n.id]?.starred ?? false))
                  InkWell(
                    onTap: () => _select(n),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(children: [
                        const Icon(Icons.star, size: 12, color: gold),
                        const SizedBox(width: 8),
                        Expanded(child: Text(n.label.replaceFirst(RegExp(r'^https?://(www\.)?'), ''), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11.5))),
                        Text(graph.typeName(n.type), style: const TextStyle(fontSize: 10, color: dim)),
                      ]),
                    ),
                  ),
              ]),
            ),
            const SizedBox(height: 8),
          ],
          const Divider(),
          Expanded(
            child: ListView(padding: const EdgeInsets.only(top: 10), children: [
              for (final l in log)
                Padding(
                  padding: const EdgeInsets.only(bottom: 3),
                  child: Text(l,
                      style: TextStyle(
                          fontSize: 10.5,
                          height: 1.3,
                          color: l.startsWith('✗') || l.startsWith(t('Error')) ? accent : (l.startsWith(t('Completed')) || l.startsWith(t('Stopped')) ? fg : dim))),
                ),
            ]),
          ),
        ]),
      );

  Widget _expandButton((String, String) tg) {
    final enabled = !running && backendReady;
    return PopupMenuButton<int>(
      enabled: enabled,
      tooltip: t('Look for more data starting from this one'),
      onSelected: (d) => _expand(tg, d),
      itemBuilder: (_) => [
        PopupMenuItem(value: 0, child: Text(t('Only this item'))),
        PopupMenuItem(value: 1, child: Text(t('Up to depth 1'))),
        PopupMenuItem(value: 2, child: Text(t('Up to depth 2'))),
      ],
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          border: Border.all(color: enabled ? accent : line),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.travel_explore, size: 14, color: enabled ? accent : dim),
          const SizedBox(width: 8),
          Flexible(
            child: Text(t('EXPAND · {0} «{1}»', [graph.typeName(tg.$1), tg.$2]),
                maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 11, letterSpacing: 0.8, color: enabled ? accent : dim)),
          ),
          Icon(Icons.arrow_drop_down, size: 16, color: enabled ? accent : dim),
        ]),
      ),
    );
  }

  /// Manual lookups on external sites (need a browser/login, so the app opens them instead of scraping).
  Widget _pivotLinks(GNode n, List<GEdge> edges) {
    final original = n.type == 'Immagine' ? edges.map((e) => e.url).firstWhere((u) => u.startsWith('http'), orElse: () => '') : null;
    final links = n.members.isNotEmpty ? const <PivotLink>[] : pivotLinks(n.type, n.value, imageUrl: original);
    if (links.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(t('SEARCH ON'), style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim)),
        const SizedBox(height: 6),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final l in links)
            InkWell(
              onTap: () => openUrl(l.url),
              borderRadius: BorderRadius.circular(4),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(border: Border.all(color: line), borderRadius: BorderRadius.circular(4)),
                child: Text('${l.label} ↗', style: const TextStyle(fontSize: 10.5)),
              ),
            ),
        ]),
      ]),
    );
  }

  Widget _img(String hash, double size) => ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Image.network(imageUrl(hash), width: size, height: size, fit: BoxFit.cover,
            errorBuilder: (_, _, _) => SizedBox(width: size, height: size, child: const Icon(Icons.broken_image_outlined, color: dim, size: 20))),
      );

  Widget _linkedImages(GNode n) {
    final byId = {for (final x in graph.nodes) x.id: x};
    final hashes = {
      for (final e in graph.edges)
        if (e.src == n.id || e.dst == n.id) ...[
          if (byId[e.src]?.type == 'Immagine') byId[e.src]!.value,
          if (byId[e.dst]?.type == 'Immagine') byId[e.dst]!.value,
        ]
    };
    if (hashes.isEmpty) return const SizedBox.shrink();
    return Padding(padding: const EdgeInsets.only(bottom: 10), child: Wrap(spacing: 6, children: [for (final h in hashes) _img(h, 72)]));
  }

  Widget _review(GLink l) {
    final byId = {for (final x in graph.nodes) x.id: x.label};
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text('${byId[l.a]} ↔ ${byId[l.b]}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11.5)),
      subtitle: Text('${(l.score * 100).round()}% · ${l.signalLabels.join(', ')}', style: const TextStyle(fontSize: 10.5, color: dim)),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton(tooltip: t('Confirm'), icon: const Icon(Icons.check), onPressed: () => _decide(l, 'confirmed')),
        IconButton(tooltip: t('Discard'), icon: const Icon(Icons.close), onPressed: () => _decide(l, 'rejected')),
      ]),
    );
  }

  Future<void> _decide(GLink l, String decision) async {
    await decideLink(inv!, l.id, decision);
    final g = await fetchGraph(inv!);
    if (mounted) setState(() => graph = g);
  }

  Widget _nodeActions(GNode n) {
    final ids = _idsOf(n);
    final isHidden = ids.every(_raw.hidden.contains);
    Widget chip(IconData icon, String label, VoidCallback onTap, {Color color = dim}) => InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(border: Border.all(color: color == dim ? line : color.withValues(alpha: 0.6)), borderRadius: BorderRadius.circular(4)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(icon, size: 13, color: color),
              const SizedBox(width: 6),
              Text(label, style: TextStyle(fontSize: 10.5, letterSpacing: 0.8, color: color == dim ? fg : color)),
            ]),
          ),
        );
    return Wrap(spacing: 6, runSpacing: 6, children: [
      chip(isHidden ? Icons.visibility_outlined : Icons.visibility_off_outlined, isHidden ? t('SHOW') : t('HIDE'), () => _setHidden(ids, !isHidden)),
      if (n.id > 0 && n.members.isEmpty) chip(Icons.share_outlined, t('LINK TO…'), () => _startLink(n)),
      if (n.manual) chip(Icons.edit_outlined, t('EDIT'), () => _editNode(n)),
      chip(Icons.delete_outline, t('DELETE'), () => _deleteNode(n), color: accent),
    ]);
  }

  Widget _detail(GNode n) {
    final byId = {for (final x in graph.nodes) x.id: x};
    final edges = graph.edges.where((e) => e.src == n.id || e.dst == n.id).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Row(children: [
            Container(width: 8, height: 8, decoration: BoxDecoration(color: typeColor(n.type), shape: BoxShape.circle)),
            const SizedBox(width: 8),
            Expanded(child: Text(graph.typeName(n.type).toUpperCase(), style: const TextStyle(fontSize: 10, letterSpacing: 1.5, color: dim))),
            InkWell(onTap: () => setState(() => selected = null), child: const Icon(Icons.close, size: 14, color: dim)),
          ]),
          const SizedBox(height: 10),
          if (n.type == 'Immagine' && n.members.isEmpty) Padding(padding: const EdgeInsets.only(bottom: 10), child: _img(n.value, 128)),
          if (n.type != 'Immagine' && n.members.isEmpty) _linkedImages(n),
          SelectableText(n.label, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          _nodeActions(n),
          if (n.id > 0 && n.members.isEmpty) ...[
            const SizedBox(height: 8),
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              IconButton(
                tooltip: (graph.notes[n.id]?.starred ?? false) ? t('Remove from favorites') : t('Add to favorites'),
                icon: Icon((graph.notes[n.id]?.starred ?? false) ? Icons.star : Icons.star_border,
                    color: (graph.notes[n.id]?.starred ?? false) ? gold : dim, size: 18),
                onPressed: () => _saveNote(n, starred: !(graph.notes[n.id]?.starred ?? false)),
              ),
              Expanded(
                child: NoteEditor(
                  key: ValueKey('$inv-${n.id}'),
                  initial: graph.notes[n.id]?.text ?? '',
                  onChanged: (v) => _saveNote(n, text: v),
                ),
              ),
            ]),
          ],
          if (expandTarget(n) case final tg?) ...[
            const SizedBox(height: 12),
            _expandButton(tg),
          ],
          _pivotLinks(n, edges),
          const SizedBox(height: 10),
          const Divider(),
          const SizedBox(height: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 380),
            child: n.members.isNotEmpty && n.type == 'Immagine'
                ? SingleChildScrollView(child: Wrap(spacing: 6, runSpacing: 6, children: [for (final h in n.members.take(120)) _img(h, 72)]))
                : n.members.isNotEmpty
                ? SingleChildScrollView(child: SelectableText(n.members.join(', '), style: const TextStyle(fontSize: 11.5, height: 1.5)))
                : ListView(shrinkWrap: true, children: [
                    for (final e in edges)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 5),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Expanded(
                              child: Text(
                                e.src == n.id ? '${e.relLabel} → ${byId[e.dst]?.label}' : '${byId[e.src]?.label} → ${e.relLabel}',
                                style: TextStyle(fontSize: 11.5, color: e.manual ? gold : fg),
                              ),
                            ),
                            if (e.manual) InkWell(onTap: () => _deleteBridge(e), child: Tooltip(message: t('Delete this bridge'), child: const Icon(Icons.close, size: 13, color: dim))),
                          ]),
                          Text(
                            '${e.reasonLabel} · ${e.collector} · ${(e.conf * 100).round()}%${e.url.isEmpty ? '' : '\n${e.url}'}',
                            style: const TextStyle(fontSize: 10, color: dim, height: 1.4),
                          ),
                        ]),
                      ),
                  ]),
          ),
        ]),
      ),
    );
  }
}
