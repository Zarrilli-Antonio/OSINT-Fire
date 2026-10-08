import 'dart:async';
import 'dart:math';
import 'dart:ui' as ui;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:http/http.dart' as http;

import 'api.dart';
import 'l10n.dart';
import 'theme.dart';

/// Interactive force-directed graph: drag nodes (they stay pinned), drag background to pan, scroll/pinch to zoom,
/// double-click a node to release it. Positions persist across graph updates.
// ponytail: O(n^2) repulsion, fine up to ~500 nodes. Switch to Barnes-Hut or a grid if larger.
class GraphView extends StatefulWidget {
  const GraphView({super.key, required this.graph, required this.onSelect, this.selected, this.highlight, this.layout, this.layoutId, this.newIds, this.onLayoutChanged, this.ghostIds, this.onAddNode, this.onToggleLink, this.linkMode = false, this.saveLayoutEnabled = true});
  final Graph graph;
  final Set<int>? highlight; // search matches: everything else is dimmed
  final int? selected;
  final void Function(GNode?) onSelect;
  final SavedLayout? layout; // positions/pins/camera saved the last time: applied when it changes
  final int? layoutId; // investigation the layout belongs to
  final Set<int>? newIds; // entities that appeared in the latest update
  final Set<int>? ghostIds; // hidden nodes shown faded (the "with hidden" view)
  final VoidCallback? onAddNode, onToggleLink; // toolbar: create a node / start drawing a bridge
  final bool linkMode; // choosing the two ends of a bridge
  final bool saveLayoutEnabled; // false for the secondary pane of the split view
  final void Function(int id, List<Map<String, dynamic>> nodes, Map<String, dynamic> view)? onLayoutChanged;

  @override
  State<GraphView> createState() => GraphViewState();
}

class GraphViewState extends State<GraphView> with SingleTickerProviderStateMixin {
  final pos = <int, Offset>{}, vel = <int, Offset>{};
  final deg = <int, int>{};
  final stash = <int, (Offset, bool)>{}; // positions of nodes that left the graph (hidden): they come back where they were
  final pinned = <int>{};
  final hidden = <String>{}; // node types switched off from the legend
  final imgs = <String, ui.Image?>{}; // hash -> decoded thumbnail (null while loading)
  final imgErr = <String, String>{}; // hash -> last error after retries
  final repaint = ValueNotifier<int>(0);
  final rnd = Random(1);
  late final Ticker ticker;
  var byId = <int, GNode>{};
  var nbr = <int, Set<int>>{};
  Size size = Size.zero;
  double scale = 1;
  Offset pan = Offset.zero;
  int steps = 0;
  bool autoFit = false;
  int? hovered, dragId, _downHit;
  Offset _grab = Offset.zero;
  Offset _lastPan = Offset.zero;
  double _lastScale = 1;
  int _tapT = 0;
  Timer? _holdTimer; // fires when the pointer has been down for a while: a hold is not a click
  bool _held = false;
  int? _tapId;
  Timer? _saveTimer;

  @override
  void initState() {
    super.initState();
    ticker = createTicker((_) {
      final energy = _step();
      steps--;
      if (energy < 0.02 && dragId == null) steps = 0; // settled
      if (steps <= 0) {
        steps = 0;
        ticker.stop(); // no frames while idle
        _scheduleSave();
        if (autoFit) {
          autoFit = false;
          fit();
        }
      }
      repaint.value++;
    });
    _sync();
  }

  @override
  void didUpdateWidget(GraphView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.layoutId != widget.layoutId && (_saveTimer?.isActive ?? false)) _emitLayout(oldWidget.layoutId); // do not lose the old picture
    if (oldWidget.layout != widget.layout) {
      stash.clear();
      pos.clear();
      vel.clear();
      pinned.clear();
      hidden.clear();
    }
    if (oldWidget.graph != widget.graph || oldWidget.layout != widget.layout) _sync();
    repaint.value++;
  }

  @override
  void dispose() {
    if (_saveTimer?.isActive ?? false) _emitLayout(widget.layoutId);
    _saveTimer?.cancel();
    _holdTimer?.cancel();
    ticker.dispose();
    repaint.dispose();
    super.dispose();
  }

  void _scheduleSave() {
    if (widget.onLayoutChanged == null || widget.layoutId == null || !widget.saveLayoutEnabled) return;
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(milliseconds: 1500), () => _emitLayout(widget.layoutId));
  }

  void _emitLayout(int? id) {
    if (id == null || pos.isEmpty || widget.onLayoutChanged == null) return;
    widget.onLayoutChanged!(id, [
      for (final e in pos.entries)
        if (e.key > 0 && byId.containsKey(e.key)) {'id': e.key, 'x': e.value.dx, 'y': e.value.dy, 'pinned': pinned.contains(e.key)}
    ], {
      'scale': scale,
      'pan': [pan.dx, pan.dy],
      'hidden': hidden.toList(),
    });
  }

  void _heat(int n) {
    steps = max(steps, n);
    if (!ticker.isActive) ticker.start();
  }

  Offset toScreen(Offset w) => size.center(Offset.zero) + pan + w * scale;
  Offset toWorld(Offset s) => (s - size.center(Offset.zero) - pan) / scale;
  bool _imageGroup(GNode n) => n.type == 'Immagine' && n.members.isNotEmpty;
  double _r(GNode n) => _imageGroup(n) ? 22 : n.type == 'Immagine' ? 16 : n.members.isNotEmpty ? 10 : 5 + min(deg[n.id] ?? 0, 14) * 0.6;

  int? hit(Offset s) => _hit(s);

  int? _hit(Offset s) {
    int? best;
    var bd = double.infinity;
    for (final n in widget.graph.nodes) {
      if (hidden.contains(n.type)) continue;
      final d = (toScreen(pos[n.id]!) - s).distance;
      if (d < _r(n) + 5 && d < bd) {
        best = n.id;
        bd = d;
      }
    }
    return best;
  }

  void _zoomAt(Offset p, double f) {
    final ns = (scale * f).clamp(0.1, 4.0);
    f = ns / scale;
    final c = size.center(Offset.zero);
    pan = (p - c) - ((p - c) - pan) * f; // keeps the world point under the cursor fixed
    scale = ns;
  }

  void repaintNow() => repaint.value++;

  /// Centre the camera on a node (keeps the current zoom).
  void focusOn(int id) {
    final p = pos[id];
    if (p == null) return;
    pan = -p * scale;
    repaint.value++;
  }

  void fit() {
    if (pos.isEmpty || size.isEmpty) return;
    var r = Rect.fromPoints(pos.values.first, pos.values.first);
    for (final p in pos.values) {
      r = r.expandToInclude(Rect.fromPoints(p, p));
    }
    scale = min((size.width - 140) / max(r.width, 1), (size.height - 140) / max(r.height, 1)).clamp(0.15, 1.5);
    pan = -r.center * scale;
    repaint.value++;
  }

  /// Fetch + decode a thumbnail. Retries with backoff (the backend can be busy while collectors run); after the last
  /// failure the key is dropped so the next graph update tries again, and the node shows a "broken" placeholder.
  Future<void> _loadImage(String hash, [int attempt = 0]) async {
    imgs[hash] = null;
    try {
      final r = await http.get(Uri.parse(imageUrl(hash))).timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) throw 'HTTP ${r.statusCode}';
      final codec = await ui.instantiateImageCodec(r.bodyBytes, targetWidth: 64);
      final img = (await codec.getNextFrame()).image;
      if (!mounted) return;
      imgs[hash] = img;
      imgErr.remove(hash);
      repaint.value++;
    } catch (e) {
      if (!mounted) return;
      if (attempt < 3) {
        await Future.delayed(Duration(seconds: 1 << attempt));
        if (mounted) _loadImage(hash, attempt + 1);
      } else {
        imgErr[hash] = '$e';
        imgs.remove(hash);
        repaint.value++;
      }
    }
  }

  void _sync() {
    final g = widget.graph;
    byId = {for (final n in g.nodes) n.id: n};
    for (final k in pos.keys.where((k) => !byId.containsKey(k) && k > 0)) {
      stash[k] = (pos[k]!, pinned.contains(k));
    }
    pos.removeWhere((k, _) => !byId.containsKey(k));
    vel.removeWhere((k, _) => !byId.containsKey(k));
    pinned.removeWhere((k) => !byId.containsKey(k));
    var restored = false;
    final lay = widget.layout;
    if (pos.isEmpty && lay != null && !lay.isEmpty) {
      for (final n in g.nodes) {
        final p = lay.pos[n.id];
        if (p == null) continue;
        pos[n.id] = p;
        vel[n.id] = Offset.zero;
        if (lay.pinned.contains(n.id)) pinned.add(n.id);
        restored = true;
      }
      final v = lay.view;
      if (restored && v['scale'] is num && v['pan'] is List && (v['pan'] as List).length == 2) {
        scale = (v['scale'] as num).toDouble().clamp(0.1, 4.0);
        pan = Offset(((v['pan'] as List)[0] as num).toDouble(), ((v['pan'] as List)[1] as num).toDouble());
        hidden.addAll((v['hidden'] as List? ?? const []).cast<String>());
      }
    }
    if (pos.isEmpty && g.nodes.isNotEmpty) autoFit = true; // first picture of a new search: frame everything
    deg.clear();
    nbr = {};
    void link(int a, int b, {bool count = true}) {
      if (count) {
        deg[a] = (deg[a] ?? 0) + 1;
        deg[b] = (deg[b] ?? 0) + 1;
      }
      nbr.putIfAbsent(a, () => {}).add(b);
      nbr.putIfAbsent(b, () => {}).add(a);
    }

    for (final e in g.edges) {
      link(e.src, e.dst);
    }
    for (final l in g.links) {
      link(l.a, l.b, count: false);
    }
    final first = pos.isEmpty;
    var added = 0;
    var i = 0;
    for (final n in g.nodes) {
      for (final h in n.type != 'Immagine' ? const <String>[] : n.members.isNotEmpty ? n.members.take(4) : [n.value]) {
        if (!imgs.containsKey(h)) _loadImage(h);
      }
      if (pos.containsKey(n.id)) continue;
      if (stash.remove(n.id) case (final at, final wasPinned)) {
        pos[n.id] = at;
        vel[n.id] = Offset.zero;
        if (wasPinned) pinned.add(n.id);
        continue;
      }
      final nb = g.edges
          .where((e) => (e.src == n.id && pos.containsKey(e.dst)) || (e.dst == n.id && pos.containsKey(e.src)))
          .map((e) => pos[e.src == n.id ? e.dst : e.src]!)
          .firstOrNull;
      pos[n.id] = nb != null
          ? nb + Offset(rnd.nextDouble() * 60 - 30, rnd.nextDouble() * 60 - 30)
          : Offset.fromDirection(i * 2.399, 30.0 * sqrt(++i)); // phyllotaxis spiral: decent starting layout
      vel[n.id] = Offset.zero;
      added++;
    }
    if (restored && added == 0) return; // same picture as last time: nothing to settle
    _heat(first ? 400 : (restored ? 120 : 300));
  }

  /// One simulation step, returns average kinetic energy.
  double _step() {
    final ids = byId.keys.toList();
    final n = ids.length;
    if (n == 0) return 0;
    final idx = {for (var i = 0; i < n; i++) ids[i]: i};
    final f = List<Offset>.filled(n, Offset.zero);
    for (var a = 0; a < n; a++) {
      for (var b = a + 1; b < n; b++) {
        final d = pos[ids[a]]! - pos[ids[b]]!;
        final dist = max(d.distance, 1.0);
        final push = d / dist * min(6000 / (dist * dist), 20);
        f[a] += push;
        f[b] -= push;
      }
    }
    void spring(int a, int b, double rest, double k) {
      final ia = idx[a], ib = idx[b];
      if (ia == null || ib == null) return;
      final d = pos[b]! - pos[a]!;
      final pull = d / max(d.distance, 1.0) * ((d.distance - rest) * k);
      f[ia] += pull;
      f[ib] -= pull;
    }

    for (final e in widget.graph.edges) {
      spring(e.src, e.dst, 90, 0.02);
    }
    for (final l in widget.graph.links) {
      spring(l.a, l.b, 140, 0.008);
    }
    var energy = 0.0;
    for (var i = 0; i < n; i++) {
      final id = ids[i];
      if (pinned.contains(id) || dragId == id) {
        vel[id] = Offset.zero;
        continue;
      }
      vel[id] = (vel[id]! + f[i] - pos[id]! * 0.002) * 0.85;
      pos[id] = pos[id]! + vel[id]!;
      energy += vel[id]!.distanceSquared;
    }
    return energy / n;
  }

  void _tap(TapUpDetails d) {
    _holdTimer?.cancel();
    if (_held) {
      _held = false; // pressed and held: the user was grabbing the node, not clicking it
      return;
    }
    final now = DateTime.now().millisecondsSinceEpoch;
    final id = _hit(d.localPosition);
    if (id != null && id == _tapId && now - _tapT < 350) {
      pinned.contains(id) ? pinned.remove(id) : pinned.add(id); // double click toggles the pin
      _heat(120);
      _scheduleSave();
    }
    _tapId = id;
    _tapT = now;
    widget.onSelect(id == null ? null : byId[id]);
  }

  @override
  Widget build(BuildContext context) {
    LangScope.watch(context);
    final counts = <String, int>{};
    for (final n in widget.graph.nodes) {
      counts[n.type] = (counts[n.type] ?? 0) + 1;
    }
    return LayoutBuilder(builder: (context, box) {
      size = box.biggest;
      return Stack(children: [
        Positioned.fill(
          child: MouseRegion(
            cursor: widget.linkMode
                ? SystemMouseCursors.precise
                : dragId != null
                    ? SystemMouseCursors.grabbing
                : hovered != null
                    ? SystemMouseCursors.click
                    : SystemMouseCursors.basic,
            onHover: (e) {
              final h = _hit(e.localPosition);
              if (h != hovered) {
                setState(() => hovered = h);
                repaint.value++;
              }
            },
            child: Listener(
              onPointerSignal: (e) {
                if (e is PointerScrollEvent) {
                  _zoomAt(e.localPosition, exp(-e.scrollDelta.dy / 300));
                  repaint.value++;
                  _scheduleSave();
                }
              },
              onPointerPanZoomStart: (_) {
                _lastPan = Offset.zero;
                _lastScale = 1;
              },
              onPointerPanZoomEnd: (_) => _scheduleSave(),
              onPointerPanZoomUpdate: (e) {
                pan += e.pan - _lastPan;
                _lastPan = e.pan;
                _zoomAt(e.localPosition, e.scale / _lastScale);
                _lastScale = e.scale;
                repaint.value++;
              },
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTapDown: (_) {
                  _held = false;
                  _holdTimer?.cancel();
                  _holdTimer = Timer(const Duration(milliseconds: 400), () => _held = true);
                },
                onTapCancel: () => _holdTimer?.cancel(),
                onTapUp: _tap,
                // hit-test at pointer-down: the pan only starts after a touch slop, by which time the cursor may have left the node
                onPanDown: (d) {
                  _downHit = widget.linkMode ? null : _hit(d.localPosition); // while choosing bridge ends, a drag only pans
                  if (_downHit != null) _grab = pos[_downHit!]! - toWorld(d.localPosition);
                },
                onPanStart: (d) {
                  final id = _downHit;
                  if (id == null) return;
                  setState(() => dragId = id);
                  pinned.add(id); // moving a node pins it; it does not open its description

                },
                onPanUpdate: (d) {
                  if (dragId != null) {
                    pos[dragId!] = toWorld(d.localPosition) + _grab;
                    _heat(90); // neighbours follow the dragged node
                  } else {
                    pan += d.delta;
                  }
                  repaint.value++;
                },
                onPanEnd: (_) {
                  setState(() => dragId = null);
                  _scheduleSave();
                },
                child: CustomPaint(size: size, painter: _Painter(this)),
              ),
            ),
          ),
        ),
        Positioned(
          left: 16,
          bottom: 14,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            for (final e in counts.entries)
              InkWell(
                onTap: () {
                  setState(() => hidden.contains(e.key) ? hidden.remove(e.key) : hidden.add(e.key));
                  repaint.value++;
                  _scheduleSave();
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: hidden.contains(e.key) ? Colors.transparent : typeColor(e.key),
                        shape: BoxShape.circle,
                        border: Border.all(color: typeColor(e.key)),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text('${widget.graph.typeName(e.key)}  ${e.value}',
                        style: TextStyle(
                            fontSize: 10,
                            color: hidden.contains(e.key) ? const Color(0x558A8A92) : dim,
                            decoration: hidden.contains(e.key) ? TextDecoration.lineThrough : null)),
                  ]),
                ),
              ),
            if (counts.isNotEmpty) ...[
              const SizedBox(height: 6),
              IgnorePointer(
                child: Text(t('click the legend = show/hide · drag nodes · double click = unpin'),
                    style: const TextStyle(fontSize: 10, color: Color(0x668A8A92))),
              ),
            ],
          ]),
        ),
        Positioned(
          right: 16,
          bottom: 14,
          child: Column(children: [
            if (widget.onAddNode != null) _Btn(Icons.add_circle_outline, t('Add a node'), widget.onAddNode!),
            if (widget.onToggleLink != null) _Btn(Icons.share_outlined, widget.linkMode ? t('Cancel the link') : t('Create a bridge between two nodes'), widget.onToggleLink!, active: widget.linkMode),
            if (widget.onAddNode != null || widget.onToggleLink != null) const SizedBox(height: 10),
            _Btn(Icons.add, t('Zoom +'), () {
              _zoomAt(size.center(Offset.zero), 1.25);
              repaint.value++;
            }),
            _Btn(Icons.remove, t('Zoom −'), () {
              _zoomAt(size.center(Offset.zero), 0.8);
              repaint.value++;
            }),
            _Btn(Icons.center_focus_strong_outlined, t('Fit all'), () {
              fit();
              _scheduleSave();
            }),
            _Btn(Icons.lock_open, t('Unpin all nodes'), () {
              pinned.clear();
              _heat(300);
              _scheduleSave();
            }),
          ]),
        ),
      ]);
    });
  }
}

class _Btn extends StatelessWidget {
  const _Btn(this.icon, this.tip, this.onTap, {this.active = false});
  final bool active;
  final IconData icon;
  final String tip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Tooltip(
          message: tip,
          child: Material(
            color: active ? accent.withValues(alpha: 0.25) : panel,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6), side: BorderSide(color: active ? accent : line)),
            child: InkWell(
              borderRadius: BorderRadius.circular(6),
              onTap: onTap,
              child: SizedBox(width: 32, height: 32, child: Icon(icon, size: 16, color: active ? accent : dim)),
            ),
          ),
        ),
      );
}

class _Painter extends CustomPainter {
  _Painter(this.s) : super(repaint: s.repaint);
  final GraphViewState s;

  @override
  void paint(Canvas canvas, Size size) {
    final g = s.widget.graph;
    final focus = s.dragId ?? s.widget.selected ?? s.hovered;
    final Set<int>? near = focus == null ? s.widget.highlight : {focus, ...?s.nbr[focus]};
    Offset? at(int id) => s.pos[id] == null ? null : s.toScreen(s.pos[id]!);

    bool shown(int id) => s.byId[id] != null && !s.hidden.contains(s.byId[id]!.type);
    final ghost = s.widget.ghostIds ?? const <int>{};
    for (final e in g.edges) {
      final a = at(e.src), b = at(e.dst);
      if (a == null || b == null || !shown(e.src) || !shown(e.dst)) continue;
      final hot = focus != null && (e.src == focus || e.dst == focus);
      final faded = ghost.contains(e.src) || ghost.contains(e.dst);
      canvas.drawLine(
        a,
        b,
        Paint()
          ..color = hot
              ? accent.withValues(alpha: 0.9)
              : e.manual
                  ? gold.withValues(alpha: faded ? 0.25 : (focus == null ? 0.85 : 0.2))
                  : fg.withValues(alpha: faded ? 0.03 : (focus == null ? 0.08 + 0.28 * e.conf : 0.04))
          ..strokeWidth = hot ? 1.4 : (e.manual ? 1.8 : 0.6 + e.conf),
      );
      if (e.manual && !faded && s.scale >= 0.6 && (focus == null || hot)) _edgeLabel(canvas, a, b, e.relLabel);
    }
    for (final l in g.links) {
      final a = at(l.a), b = at(l.b);
      if (a == null || b == null || !shown(l.a) || !shown(l.b)) continue;
      final dim = focus != null && l.a != focus && l.b != focus;
      _dashed(canvas, a, b,
          Paint()
            ..color = const Color(0xFFFFB454).withValues(alpha: dim ? 0.1 : (l.status == 'review' ? 0.55 : 0.95))
            ..strokeWidth = l.status == 'review' ? 1.2 : 1.8);
    }

    final labels = <(Offset, GNode, double)>[];
    for (final n in g.nodes) {
      final p = at(n.id);
      if (p == null || s.hidden.contains(n.type)) continue;
      final lit = near == null || near.contains(n.id);
      final isGhost = ghost.contains(n.id);
      final a = isGhost ? 0.28 : (lit ? 1.0 : 0.22);
      final r = s._r(n);
      final color = typeColor(n.type);
      if (n.id == s.widget.selected) {
        canvas.drawCircle(p, r + 10, Paint()..color = accent.withValues(alpha: 0.5)..maskFilter = const MaskFilter.blur(BlurStyle.normal, 9));
      }
      final img = n.type == 'Immagine' && n.members.isEmpty ? s.imgs[n.value] : null;
      if (s._imageGroup(n)) {
        _mosaic(canvas, p, r, n, color, a);
      } else if (img != null) {
        final rect = Rect.fromCenter(center: p, width: r * 2, height: r * 2);
        final rr = RRect.fromRectAndRadius(rect, const Radius.circular(6));
        canvas.save();
        canvas.clipRRect(rr);
        canvas.drawImageRect(img, Rect.fromLTWH(0, 0, img.width.toDouble(), img.height.toDouble()), rect, Paint()..color = Colors.white.withValues(alpha: a));
        canvas.restore();
        canvas.drawRRect(rr, Paint()..color = color.withValues(alpha: a)..style = PaintingStyle.stroke..strokeWidth = 1.5);
      } else if (n.type == 'Immagine' && n.members.isEmpty) {
        // thumbnail still loading (dashed-looking dim box) or failed (crossed box)
        final rect = Rect.fromCenter(center: p, width: r * 2, height: r * 2);
        final rr = RRect.fromRectAndRadius(rect, const Radius.circular(6));
        canvas.drawRRect(rr, Paint()..color = color.withValues(alpha: 0.12 * a));
        canvas.drawRRect(rr, Paint()..color = color.withValues(alpha: 0.7 * a)..style = PaintingStyle.stroke..strokeWidth = 1.2);
        if (s.imgErr.containsKey(n.value)) {
          final q = Paint()..color = accent.withValues(alpha: a)..strokeWidth = 1.5;
          canvas.drawLine(rect.topLeft + const Offset(5, 5), rect.bottomRight - const Offset(5, 5), q);
          canvas.drawLine(rect.topRight + const Offset(-5, 5), rect.bottomLeft + const Offset(5, -5), q);
        }
      } else {
        canvas.drawCircle(p, r, Paint()..color = color.withValues(alpha: a));
        canvas.drawCircle(p, r, Paint()..color = bg.withValues(alpha: 0.7 * a)..style = PaintingStyle.stroke..strokeWidth = 1.2);
        if (n.members.isNotEmpty) _count(canvas, p, n.members.length, bg.withValues(alpha: a), null);
      }
      if (n.id == s.widget.selected) {
        canvas.drawCircle(p, r + 3, Paint()..color = accent..style = PaintingStyle.stroke..strokeWidth = 1.5);
      } else if (s.pinned.contains(n.id)) {
        canvas.drawCircle(p, r + 3, Paint()..color = fg.withValues(alpha: 0.35 * a)..style = PaintingStyle.stroke..strokeWidth = 1);
      }
      if (isGhost) _dashedRing(canvas, p, r + 4, fg.withValues(alpha: 0.35));
      if (n.manual && !isGhost) _diamond(canvas, p + Offset(r + 3, -r - 3), 4.5, gold.withValues(alpha: a));
      if (s.widget.newIds?.contains(n.id) ?? false) canvas.drawCircle(p + Offset(-r - 3, -r - 3), 3.5, Paint()..color = const Color(0xFF7EE787).withValues(alpha: a));
      final note = g.notes[n.id];
      if (note != null) {
        if (note.starred) canvas.drawCircle(p, r + 6, Paint()..color = gold.withValues(alpha: a)..style = PaintingStyle.stroke..strokeWidth = 1.8);
        if (note.text.isNotEmpty) canvas.drawRect(Rect.fromCenter(center: p + Offset(r + 2, -r - 2), width: 5, height: 5), Paint()..color = gold.withValues(alpha: a));
      }
      if ((n.type != 'Immagine' || n.members.isNotEmpty) && (n.id == focus || (!isGhost && (near?.contains(n.id) ?? s.scale >= 0.75)))) labels.add((p, n, r));
    }
    for (final (p, n, r) in labels) {
      final tp = TextPainter(
        text: TextSpan(
          text: n.label.replaceFirst(RegExp(r'^https?://(www\.)?'), ''),
          style: TextStyle(
            color: fg.withValues(alpha: n.id == focus ? 1 : 0.8),
            fontSize: 10,
            fontFamily: mono,
            fontFamilyFallback: monoFallback,
            fontWeight: n.id == focus ? FontWeight.w600 : FontWeight.normal,
            shadows: const [Shadow(color: bg, blurRadius: 4), Shadow(color: bg, blurRadius: 2)],
          ),
        ),
        textDirection: TextDirection.ltr,
        maxLines: 1,
        ellipsis: '…',
      )..layout(maxWidth: 170);
      tp.paint(canvas, p + Offset(r + 6, -tp.height / 2));
    }
  }

  /// 2x2 thumbnails of the first four group members plus a count badge.
  void _mosaic(Canvas canvas, Offset p, double r, GNode n, Color color, double a) {
    final rect = Rect.fromCenter(center: p, width: r * 2, height: r * 2);
    final rr = RRect.fromRectAndRadius(rect, const Radius.circular(7));
    canvas.drawRRect(rr, Paint()..color = bg.withValues(alpha: 0.9 * a));
    canvas.save();
    canvas.clipRRect(rr);
    final cell = r; // each of the 4 cells is r x r
    for (var i = 0; i < min(4, n.members.length); i++) {
      final img = s.imgs[n.members[i]];
      final dst = Rect.fromLTWH(rect.left + (i % 2) * cell, rect.top + (i ~/ 2) * cell, cell, cell).deflate(0.5);
      if (img != null) {
        canvas.drawImageRect(img, Rect.fromLTWH(0, 0, img.width.toDouble(), img.height.toDouble()), dst, Paint()..color = Colors.white.withValues(alpha: a));
      } else {
        canvas.drawRect(dst, Paint()..color = color.withValues(alpha: 0.25 * a));
      }
    }
    canvas.restore();
    canvas.drawRRect(rr, Paint()..color = color.withValues(alpha: a)..style = PaintingStyle.stroke..strokeWidth = 1.5);
    final badge = p + Offset(r - 2, r - 2);
    canvas.drawCircle(badge, 8, Paint()..color = accent.withValues(alpha: a));
    _count(canvas, badge, n.members.length, Colors.white.withValues(alpha: a), null);
  }

  void _count(Canvas canvas, Offset c, int count, Color color, Color? shadow) {
    final tp = TextPainter(
      text: TextSpan(text: count > 999 ? '999+' : '$count', style: TextStyle(color: color, fontSize: 8, fontWeight: FontWeight.w700, fontFamily: mono)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, c - Offset(tp.width / 2, tp.height / 2));
  }

  void _diamond(Canvas canvas, Offset c, double r, Color color) {
    canvas.drawPath(Path()..moveTo(c.dx, c.dy - r)..lineTo(c.dx + r, c.dy)..lineTo(c.dx, c.dy + r)..lineTo(c.dx - r, c.dy)..close(), Paint()..color = color);
  }

  void _dashedRing(Canvas canvas, Offset c, double r, Color color) {
    final paint = Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 1.2;
    for (var i = 0; i < 16; i += 2) {
      canvas.drawArc(Rect.fromCircle(center: c, radius: r), i * pi / 8, pi / 8, false, paint);
    }
  }

  /// The label the user gave to a bridge, at its midpoint.
  void _edgeLabel(Canvas canvas, Offset a, Offset b, String text) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: TextStyle(color: gold, fontSize: 9.5, fontFamily: mono, fontFamilyFallback: monoFallback, shadows: const [Shadow(color: bg, blurRadius: 4), Shadow(color: bg, blurRadius: 2)])),
      textDirection: TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    )..layout(maxWidth: 150);
    tp.paint(canvas, (a + b) / 2 - Offset(tp.width / 2, tp.height / 2));
  }

  void _dashed(Canvas canvas, Offset a, Offset b, Paint paint) {
    final d = b - a;
    final n = (d.distance / 8).floor();
    for (var i = 0; i < n; i += 2) {
      canvas.drawLine(a + d * (i / n), a + d * ((i + 1) / n), paint);
    }
  }

  @override
  bool shouldRepaint(_Painter old) => true;
}
