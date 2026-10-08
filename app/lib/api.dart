import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' show Offset;

import 'package:http/http.dart' as http;

import 'l10n.dart';

const baseUrl = 'http://127.0.0.1:8765';

class GNode {
  GNode(this.id, this.type, this.value, [this.members = const [], this.added = 0, this.manual = false, this.memberIds = const [], String? label]) : label = label ?? value;
  final String label; // value as shown in the interface language (the value itself is the identity)
  final bool manual; // created by the user
  final List<int> memberIds; // entity ids behind a collapsed group
  final double added; // when the entity first appeared (epoch seconds)
  final int id;
  final String type, value;
  final List<String> members; // set on collapsed groups
}

class GEdge {
  GEdge(this.src, this.dst, this.rel, this.conf, this.reason, this.collector, this.url, [this.id = 0, this.manual = false, String? relLabel, String? reasonLabel])
      : relLabel = relLabel ?? rel,
        reasonLabel = reasonLabel ?? reason;
  final String relLabel, reasonLabel; // as shown in the interface language
  final int id; // relation id (0 for the synthetic edge of a group)
  final bool manual; // a bridge drawn by the user
  final int src, dst;
  final String rel, reason, collector, url;
  final double conf;
}

class GLink {
  GLink(this.id, this.a, this.b, this.score, this.signals, this.status, [List<String>? signalLabels]) : signalLabels = signalLabels ?? signals;
  final List<String> signalLabels; // signals in the interface language
  final int id, a, b;
  final double score;
  final List<String> signals;
  final String status; // auto | review | confirmed
}

class GNote {
  GNote(this.text, this.starred);
  final String text;
  final bool starred;
}

class Graph {
  Graph(this.nodes, this.edges, [this.links = const [], Map<int, GNote>? notes, Set<int>? hidden, this.typeLabels = const {}, Map<int, List<String>>? tags]) : notes = notes ?? {}, hidden = hidden ?? {}, tags = tags ?? {};
  final Map<int, List<String>> tags; // entity id -> tags (only tagged entities)
  final Map<String, String> typeLabels; // canonical type -> name in the interface language
  String typeName(String type) => typeLabel(type, typeLabels);
  final List<GNode> nodes;
  final List<GEdge> edges;
  final List<GLink> links;
  final Map<int, GNote> notes; // entity id -> user note; mutated in place when the user edits
  final Set<int> hidden; // entities the user hid; mutated in place
}

Future<void> saveNote(int inv, int entity, String text, bool starred) async {
  final r = await http.put(
    Uri.parse('$baseUrl/investigations/$inv/entities/$entity/note'),
    headers: {'content-type': 'application/json'},
    body: jsonEncode({'text': text, 'starred': starred}),
  );
  if (r.statusCode != 200) throw Exception(t('note not saved ({0})', [r.statusCode]));
}

Future<void> decideLink(int inv, int linkId, String decision) async {
  await http.post(
    Uri.parse('$baseUrl/investigations/$inv/links/$linkId'),
    headers: {'content-type': 'application/json'},
    body: jsonEncode({'decision': decision}),
  );
}

Future<int> createInvestigation({
  required String name,
  String purpose = '',
  required List<(String, String)> seeds,
  required int maxDepth,
  int maxEntities = 300,
}) async {
  final r = await http.post(
    Uri.parse('$baseUrl/investigations'),
    headers: {'content-type': 'application/json'},
    body: jsonEncode({
      'name': name,
      'purpose': purpose,
      'seeds': [
        for (final (t, v) in seeds) {'type': t, 'value': v}
      ],
      'max_depth': maxDepth,
      'max_entities': maxEntities,
    }),
  );
  if (r.statusCode != 200) throw Exception('${r.statusCode} ${r.body}');
  return jsonDecode(r.body)['id'] as int;
}

/// Collapse >= [min] leaf nodes of the same type that hang off the same source with the same relation
/// (e.g. 214 breaches, 58 accounts, 12 avatars) into one group node. Members keep their values, so image
/// groups can still show every picture. Nodes involved in links stay visible.
/// [keep]: node ids that are never folded into a group (user-made or hidden nodes shown as ghosts).
Graph collapseGroups(Graph g, {int min = 6, Set<int> keep = const {}}) {
  final byId = {for (final n in g.nodes) n.id: n};
  final deg = <int, int>{};
  for (final e in g.edges) {
    deg[e.src] = (deg[e.src] ?? 0) + 1;
    deg[e.dst] = (deg[e.dst] ?? 0) + 1;
  }
  final linked = {for (final l in g.links) ...[l.a, l.b], ...g.notes.keys, ...keep, ...g.hidden, for (final n in g.nodes) if (n.manual) n.id}; // linked, annotated, user-made or hidden nodes stay visible
  final groups = <(int, String, String), List<GEdge>>{};
  for (final e in g.edges) {
    final d = byId[e.dst];
    if (d != null && deg[e.dst] == 1 && e.src != e.dst && !linked.contains(e.dst)) {
      groups.putIfAbsent((e.src, d.type, e.rel), () => []).add(e);
    }
  }
  final nodes = [...g.nodes], edges = [...g.edges];
  for (final MapEntry(key: (src, type, rel), value: es) in groups.entries) {
    if (es.length < min) continue;
    final gone = {for (final e in es) e.dst};
    nodes.removeWhere((n) => gone.contains(n.id));
    edges.removeWhere((e) => gone.contains(e.dst));
    final id = -(src * 100000 + (type.hashCode ^ rel.hashCode).abs() % 99999 + 1); // stable across refetches
    final sorted = [...es]..sort((a, b) => byId[a.dst]!.value.compareTo(byId[b.dst]!.value));
    nodes.add(GNode(id, type, '${es.length} ${type.toLowerCase()}', [for (final e in sorted) byId[e.dst]!.value], 0, false, [for (final e in sorted) e.dst],
        '${es.length} ${g.typeName(type).toLowerCase()}'));
    edges.add(GEdge(src, id, rel, es.first.conf, es.first.reason, es.first.collector, es.first.url, 0, false, es.first.relLabel, es.first.reasonLabel));
  }
  return Graph(nodes, edges, g.links, g.notes, g.hidden, g.typeLabels, g.tags);
}

Future<Graph> fetchGraph(int inv) async {
  final r = await http.get(Uri.parse('$baseUrl/investigations/$inv/graph'));
  return graphFromJson(jsonDecode(r.body));
}

/// The graph payload of GET /investigations/{inv}/graph.
Graph graphFromJson(Map<String, dynamic> j) {
  return (Graph(
    [for (final n in j['nodes']) GNode(n['id'], n['type'], n['value'], const [], (n['added'] as num).toDouble(), (n['manual'] ?? 0) == 1, const [], n['label'] as String?)],
    [
      for (final e in j['edges'])
        GEdge(e['src'], e['dst'], e['rel'], (e['conf'] as num).toDouble(), e['reason'], e['collector'], e['url'], e['id'], (e['manual'] ?? 0) == 1, e['rel_label'] as String?, e['reason_label'] as String?)
    ],
    [
      for (final l in j['links'])
        GLink(l['id'], l['a'], l['b'], (l['score'] as num).toDouble(), [for (final s in l['signals']) s[0] as String],
            l['status'], [for (final s in l['signal_labels'] ?? l['signals'].map((s) => s[0])) s as String])
    ],
    {for (final n in j['notes'] ?? []) n['entity'] as int: GNote(n['text'] as String, n['starred'] as bool)},
    {for (final i in j['hidden'] ?? []) i as int},
    Map<String, String>.from(j['type_labels'] ?? {}),
    {for (final x in j['tags'] ?? []) x['entity'] as int: [for (final s in x['tags']) s as String]},
  ));
}

/// Server-sent events, one decoded JSON map per event. Ends after "done".
Stream<Map<String, dynamic>> events(int inv) async* {
  final client = http.Client();
  try {
    final res = await client.send(http.Request('GET', Uri.parse('$baseUrl/investigations/$inv/events')));
    await for (final line in res.stream.transform(utf8.decoder).transform(const LineSplitter())) {
      if (line.startsWith('data: ')) yield jsonDecode(line.substring(6)) as Map<String, dynamic>;
    }
  } finally {
    client.close();
  }
}

Future<List<Map<String, dynamic>>> listInvestigations() async {
  final r = await http.get(Uri.parse('$baseUrl/investigations'));
  return (jsonDecode(r.body) as List).cast<Map<String, dynamic>>();
}

Future<Uint8List> exportBytes(int inv, String format, {bool includeHidden = false}) async {
  final r = await http.get(Uri.parse('$baseUrl/investigations/$inv/export?format=$format&include_hidden=$includeHidden'));
  if (r.statusCode != 200) throw Exception('export ${r.statusCode}');
  return r.bodyBytes;
}

/// Obsidian vault as {relative path: content}.
Future<Map<String, String>> exportVault(int inv, {bool includeHidden = false}) async =>
    (jsonDecode(utf8.decode(await exportBytes(inv, 'obsidian', includeHidden: includeHidden)))['files'] as Map).cast<String, String>();

String imageUrl(String hash) => '$baseUrl/images/$hash';

Future<void> deleteInvestigation(int inv) async {
  final r = await http.delete(Uri.parse('$baseUrl/investigations/$inv'));
  if (r.statusCode != 200) throw Exception('${r.statusCode} ${r.body}');
}

/// Run collectors on entities already in investigation [inv] (or new ones), results are added to the same graph.
Future<void> expandInvestigation(int inv, List<(String, String)> seeds, int maxDepth, {int maxEntities = 300}) async {
  final r = await http.post(
    Uri.parse('$baseUrl/investigations/$inv/expand'),
    headers: {'content-type': 'application/json'},
    body: jsonEncode({
      'seeds': [
        for (final (t, v) in seeds) {'type': t, 'value': v}
      ],
      'max_depth': maxDepth,
      'max_entities': maxEntities,
    }),
  );
  if (r.statusCode != 200) throw Exception('${r.statusCode} ${jsonDecode(r.body)['detail'] ?? r.body}');
}

/// What a node can be expanded from: its own type for searchable entities, the handle for an account URL.
(String, String)? expandTarget(GNode n) {
  if (n.members.isNotEmpty) return null;
  switch (n.type) {
    case 'Dominio' || 'Email' || 'Username' || 'IP' || 'Persona' || 'Azienda':
      return (n.type, n.value);
    case 'Account':
      final u = Uri.tryParse(n.value);
      if (u == null || u.host.isEmpty) return null;
      final seg = u.pathSegments.where((s) => s.isNotEmpty).toList();
      final labels = u.host.split('.');
      final handle = seg.isNotEmpty ? seg.last : (labels.length >= 3 && labels.first != 'www' ? labels.first : '');
      final h = handle.replaceFirst('@', '');
      return h.isEmpty ? null : ('Username', h);
  }
  return null;
}


// ---------------- settings, maintenance, AI ----------------

String _detail(http.Response r) {
  try {
    final d = jsonDecode(utf8.decode(r.bodyBytes))['detail'];
    return d is String ? d : jsonEncode(d);
  } catch (_) {
    return r.body;
  }
}

class Settings {
  Settings(this.values, this.secrets);
  final Map<String, dynamic> values;
  final Map<String, String> secrets; // key -> masked hint, empty when unset

  static Settings fromJson(Map<String, dynamic> j) =>
      Settings(Map<String, dynamic>.from(j['values']), Map<String, String>.from(j['secrets']));
  int intOf(String k) => values[k] as int;
  bool boolOf(String k) => values[k] as bool;
  String strOf(String k) => values[k] as String;
}

Future<Settings> fetchSettings() async {
  final r = await http.get(Uri.parse('$baseUrl/settings'));
  return Settings.fromJson(jsonDecode(utf8.decode(r.bodyBytes)));
}

/// Send only the changed keys; the backend validates all-or-nothing and returns the effective settings.
Future<Settings> saveSettings(Map<String, dynamic> patch) async {
  final r = await http.put(Uri.parse('$baseUrl/settings'), headers: {'content-type': 'application/json'}, body: jsonEncode({'values': patch}));
  if (r.statusCode != 200) throw Exception(_detail(r));
  return Settings.fromJson(jsonDecode(utf8.decode(r.bodyBytes)));
}

class CollectorInfo {
  CollectorInfo(this.name, this.accepts, this.active, this.key, this.status);
  final String name;
  final List<String> accepts;
  final bool active; // contacts the target's own servers
  final String? key; // setting that holds the API key it needs
  final String status; // ok | disabled | passive | nokey

  static CollectorInfo fromJson(Map<String, dynamic> j) =>
      CollectorInfo(j['name'], List<String>.from(j['accepts']), j['active'], j['key'], j['status']);
}

Future<List<CollectorInfo>> fetchCollectors() async {
  final r = await http.get(Uri.parse('$baseUrl/collectors'));
  return [for (final j in jsonDecode(utf8.decode(r.bodyBytes))) CollectorInfo.fromJson(j)];
}

Future<Map<String, dynamic>> maintenanceStats() async =>
    Map<String, dynamic>.from(jsonDecode(utf8.decode((await http.get(Uri.parse('$baseUrl/maintenance/stats'))).bodyBytes)));

Future<int> clearCache() async => jsonDecode((await http.post(Uri.parse('$baseUrl/maintenance/clear-cache'))).body)['cleared'] as int;

Future<void> vacuumDb() async {
  await http.post(Uri.parse('$baseUrl/maintenance/vacuum'));
}

Future<Uint8List> backupBytes() async => (await http.get(Uri.parse('$baseUrl/maintenance/backup'))).bodyBytes;

Future<int> wipeAll(String confirm) async {
  final r = await http.post(Uri.parse('$baseUrl/maintenance/wipe'), headers: {'content-type': 'application/json'}, body: jsonEncode({'confirm': confirm}));
  if (r.statusCode != 200) throw Exception(_detail(r));
  return jsonDecode(r.body)['deleted'] as int;
}

class AiStatus {
  AiStatus(this.configured, this.reason, this.provider, this.model);
  final bool configured;
  final String reason, provider, model;
}

Future<AiStatus> fetchAiStatus() async {
  final j = jsonDecode(utf8.decode((await http.get(Uri.parse('$baseUrl/ai/status'))).bodyBytes));
  return AiStatus(j['configured'], j['reason'], j['provider'], j['model']);
}

class AiPivot {
  AiPivot(this.type, this.value, this.reason);
  final String type, value, reason;
}

class AiResult {
  AiResult(this.text, this.pivots);
  final String text;
  final List<AiPivot> pivots;
}

Future<AiResult> runAi(int inv, String task, {String question = ''}) async {
  final r = await http
      .post(Uri.parse('$baseUrl/investigations/$inv/ai'), headers: {'content-type': 'application/json'}, body: jsonEncode({'task': task, 'question': question}))
      .timeout(const Duration(seconds: 150));
  if (r.statusCode != 200) throw Exception(_detail(r));
  final j = jsonDecode(utf8.decode(r.bodyBytes));
  return AiResult(j['text'], [for (final p in j['pivots']) AiPivot(p['type'], p['value'], p['reason'])]);
}

/// Stop a running search; results found so far are kept. False when nothing was running.
Future<bool> stopInvestigation(int inv) async {
  final r = await http.post(Uri.parse('$baseUrl/investigations/$inv/stop'));
  if (r.statusCode != 200) throw Exception(_detail(r));
  return jsonDecode(r.body)['stopped'] as bool;
}


// ---------------- saved search definition and layout ----------------

class InvestigationDetail {
  InvestigationDetail(this.id, this.name, this.purpose, this.updated, this.seeds, this.maxDepth, this.runs);
  final int id, maxDepth, runs;
  final String name, purpose;
  final double updated; // epoch seconds of the last run
  final List<(String, String)> seeds;
}

Future<InvestigationDetail> fetchInvestigation(int id) async {
  final r = await http.get(Uri.parse('$baseUrl/investigations/$id'));
  if (r.statusCode != 200) throw Exception(_detail(r));
  final j = jsonDecode(utf8.decode(r.bodyBytes));
  return InvestigationDetail(j['id'], j['name'], j['purpose'], (j['updated'] as num).toDouble(),
      [for (final s in j['seeds']) (s['type'] as String, s['value'] as String)], j['max_depth'], (j['runs'] as List).length);
}

/// Re-run the search as last defined, optionally with edits; returns the server time at which it started.
Future<double> refreshInvestigation(int id, {String? name, String? purpose, List<(String, String)>? seeds, int? maxDepth}) async {
  final r = await http.post(
    Uri.parse('$baseUrl/investigations/$id/refresh'),
    headers: {'content-type': 'application/json'},
    body: jsonEncode({
      'name': ?name,
      'purpose': ?purpose,
      if (seeds != null) 'seeds': [for (final (t, v) in seeds) {'type': t, 'value': v}],
      'max_depth': ?maxDepth,
    }),
  );
  if (r.statusCode != 200) throw Exception(_detail(r));
  return (jsonDecode(r.body)['started'] as num).toDouble();
}

class SavedLayout {
  SavedLayout(this.pos, this.pinned, this.view);
  final Map<int, Offset> pos;
  final Set<int> pinned;
  final Map<String, dynamic> view; // scale, pan [dx, dy], hidden types
  bool get isEmpty => pos.isEmpty;
}

Future<SavedLayout> fetchLayout(int id) async {
  final r = await http.get(Uri.parse('$baseUrl/investigations/$id/layout'));
  if (r.statusCode != 200) return SavedLayout({}, {}, {});
  final j = jsonDecode(utf8.decode(r.bodyBytes));
  return SavedLayout({for (final n in j['nodes']) n['id'] as int: Offset((n['x'] as num).toDouble(), (n['y'] as num).toDouble())},
      {for (final n in j['nodes']) if (n['pinned'] == true) n['id'] as int}, Map<String, dynamic>.from(j['view'] ?? {}));
}

Future<void> saveLayout(int id, List<Map<String, dynamic>> nodes, Map<String, dynamic> view) async {
  await http.put(Uri.parse('$baseUrl/investigations/$id/layout'), headers: {'content-type': 'application/json'}, body: jsonEncode({'nodes': nodes, 'view': view}));
}

/// One cheap authenticated call with the saved credentials of [provider]; (ok, message).
Future<(bool, String)> testConnection(String provider) async {
  final r = await http.post(Uri.parse('$baseUrl/connections/$provider/test')).timeout(const Duration(seconds: 90));
  if (r.statusCode != 200) return (false, _detail(r));
  final j = jsonDecode(utf8.decode(r.bodyBytes));
  return (j['ok'] as bool, j['message'] as String);
}


/// The graph without the nodes the user hid (and their edges/links). Shares the notes map with [g].
Graph withoutHidden(Graph g) {
  if (g.hidden.isEmpty) return g;
  final h = g.hidden;
  return Graph([for (final n in g.nodes) if (!h.contains(n.id)) n], [for (final e in g.edges) if (!h.contains(e.src) && !h.contains(e.dst)) e],
      [for (final l in g.links) if (!h.contains(l.a) && !h.contains(l.b)) l], g.notes, <int>{}, g.typeLabels, g.tags);
}

// ---------------- nodes and bridges made by the user, hiding ----------------

Future<(int id, bool created)> createEntity(int inv, String type, String value) async {
  final r = await http.post(Uri.parse('$baseUrl/investigations/$inv/entities'), headers: {'content-type': 'application/json'}, body: jsonEncode({'type': type, 'value': value}));
  if (r.statusCode != 200) throw Exception(_detail(r));
  final j = jsonDecode(r.body);
  return (j['id'] as int, j['created'] as bool);
}

Future<void> updateEntity(int inv, int id, {String? type, String? value}) async {
  final r = await http.patch(Uri.parse('$baseUrl/investigations/$inv/entities/$id'),
      headers: {'content-type': 'application/json'}, body: jsonEncode({'type': ?type, 'value': ?value}));
  if (r.statusCode != 200) throw Exception(_detail(r));
}

Future<void> deleteEntity(int inv, int id) async {
  final r = await http.delete(Uri.parse('$baseUrl/investigations/$inv/entities/$id'));
  if (r.statusCode != 200) throw Exception(_detail(r));
}

Future<int> createRelation(int inv, int src, int dst, String rel, {String reason = ''}) async {
  final r = await http.post(Uri.parse('$baseUrl/investigations/$inv/relations'),
      headers: {'content-type': 'application/json'}, body: jsonEncode({'src': src, 'dst': dst, 'rel': rel, 'reason': reason}));
  if (r.statusCode != 200) throw Exception(_detail(r));
  return jsonDecode(r.body)['id'] as int;
}

Future<void> deleteRelation(int inv, int id) async {
  final r = await http.delete(Uri.parse('$baseUrl/investigations/$inv/relations/$id'));
  if (r.statusCode != 200) throw Exception(_detail(r));
}

/// Hide or show nodes. The server also hides what hung only from them (and shows it back with them); returns every id that changed.
Future<List<int>> setHidden(int inv, Iterable<int> ids, bool hide, {bool cascade = true}) async {
  final r = await http.put(Uri.parse('$baseUrl/investigations/$inv/hidden'),
      headers: {'content-type': 'application/json'}, body: jsonEncode({'ids': ids.toList(), 'hidden': hide, 'cascade': cascade}));
  if (r.statusCode != 200) throw Exception(_detail(r));
  return [for (final i in jsonDecode(r.body)['ids']) i as int];
}

/// Delete nodes, collected or user-made. With cascade, data that started only from them is hidden (not deleted).
Future<(int deleted, List<int> hidden)> deleteEntities(int inv, Iterable<int> ids, {bool cascade = true}) async {
  final r = await http.post(Uri.parse('$baseUrl/investigations/$inv/entities/delete'),
      headers: {'content-type': 'application/json'}, body: jsonEncode({'ids': ids.toList(), 'cascade': cascade}));
  if (r.statusCode != 200) throw Exception(_detail(r));
  final j = jsonDecode(r.body);
  return (j['deleted'] as int, [for (final i in j['hidden']) i as int]);
}

/// Replace the tags of an entity; returns the tags as stored by the server.
Future<List<String>> setTags(int inv, int entity, List<String> tags) async {
  final r = await http.put(Uri.parse('$baseUrl/investigations/$inv/entities/$entity/tags'),
      headers: {'content-type': 'application/json'}, body: jsonEncode({'tags': tags}));
  if (r.statusCode != 200) throw Exception(_detail(r));
  return [for (final s in jsonDecode(utf8.decode(r.bodyBytes))['tags']) s as String];
}
