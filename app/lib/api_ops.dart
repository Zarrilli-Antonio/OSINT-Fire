import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api.dart';

// ---------------- monitoring and alerts ----------------

class Alert {
  Alert(this.id, this.inv, this.name, this.ts, this.entities, this.relations, this.summary, this.seen);
  final int id, inv, entities, relations;
  final String name;
  final double ts; // epoch seconds
  final List<({String type, String label})> summary; // type is already localized by the backend (type_label)
  final bool seen;

  static Alert fromJson(Map<String, dynamic> j) => Alert(
        j['id'] as int,
        j['inv'] as int,
        (j['name'] ?? '') as String,
        (j['ts'] as num).toDouble(),
        (j['entities'] ?? 0) as int,
        (j['relations'] ?? 0) as int,
        [
          for (final s in (j['summary'] as List? ?? []))
            (type: (s['type_label'] ?? s['type'] ?? '') as String, label: (s['label'] ?? s['value'] ?? '') as String)
        ],
        j['seen'] == true,
      );
}

String _err(http.Response r) {
  try {
    final d = jsonDecode(utf8.decode(r.bodyBytes))['detail'];
    return d is String ? d : jsonEncode(d);
  } catch (_) {
    return r.body;
  }
}

Future<List<Alert>> fetchAlerts({bool unseenOnly = false}) async {
  final r = await http.get(Uri.parse('$baseUrl/alerts?unseen=$unseenOnly'));
  if (r.statusCode != 200) throw Exception(_err(r));
  return [for (final j in jsonDecode(utf8.decode(r.bodyBytes))) Alert.fromJson(j)];
}

Future<void> markAlertSeen(int id) async {
  final r = await http.post(Uri.parse('$baseUrl/alerts/$id/seen'));
  if (r.statusCode != 200) throw Exception(_err(r));
}

Future<void> markAllAlertsSeen() async {
  final r = await http.post(Uri.parse('$baseUrl/alerts/seen-all'));
  if (r.statusCode != 200) throw Exception(_err(r));
}

Future<void> setMonitor(int inv, int days) async {
  final r = await http.put(Uri.parse('$baseUrl/investigations/$inv/monitor'),
      headers: {'Content-Type': 'application/json'}, body: jsonEncode({'days': days}));
  if (r.statusCode != 200) throw Exception(_err(r));
}

/// Current monitoring interval in days (0 = off) and when it last ran (epoch seconds, 0 = never).
Future<({int days, double checked})> fetchMonitorDays(int inv) async {
  final r = await http.get(Uri.parse('$baseUrl/investigations/$inv'));
  if (r.statusCode != 200) throw Exception(_err(r));
  final j = jsonDecode(utf8.decode(r.bodyBytes));
  return (days: (j['monitor_days'] ?? 0) as int, checked: ((j['monitor_checked'] ?? 0) as num).toDouble());
}

// ---------------- proofs ----------------

class Proof {
  Proof(this.id, this.url, this.ts, this.sha256, this.size, this.status, this.contentType, this.wayback, this.truncated, this.archiveError, this.entity);
  final int id, size, status;
  final int? entity;
  final String url, sha256, contentType, wayback, archiveError;
  final double ts;
  final bool truncated;

  static Proof fromJson(Map<String, dynamic> j) => Proof(
        j['id'] as int,
        (j['url'] ?? '') as String,
        (j['ts'] as num).toDouble(),
        (j['sha256'] ?? '') as String,
        (j['size'] ?? 0) as int,
        (j['status'] ?? 0) as int,
        (j['content_type'] ?? '') as String,
        (j['wayback'] ?? '') as String,
        j['truncated'] == true || j['truncated'] == 1,
        (j['archive_error'] ?? '') as String,
        j['entity'] as int?,
      );
}

Future<Proof> saveProof(int inv, String url, {int? entity, bool archive = false}) async {
  final r = await http.post(Uri.parse('$baseUrl/investigations/$inv/proofs'),
      headers: {'Content-Type': 'application/json'}, body: jsonEncode({'url': url, 'entity': entity, 'archive': archive}));
  if (r.statusCode != 200) throw Exception(_err(r));
  return Proof.fromJson(jsonDecode(utf8.decode(r.bodyBytes)));
}

Future<List<Proof>> fetchProofs(int inv, {int? entity}) async {
  final r = await http.get(Uri.parse('$baseUrl/investigations/$inv/proofs${entity == null ? '' : '?entity=$entity'}'));
  if (r.statusCode != 200) throw Exception(_err(r));
  return [for (final j in jsonDecode(utf8.decode(r.bodyBytes))) Proof.fromJson(j)];
}

Future<void> deleteProof(int inv, int id) async {
  final r = await http.delete(Uri.parse('$baseUrl/investigations/$inv/proofs/$id'));
  if (r.statusCode != 200) throw Exception(_err(r));
}

String proofSnapshotUrl(int inv, int id) => '$baseUrl/investigations/$inv/proofs/$id/snapshot';
