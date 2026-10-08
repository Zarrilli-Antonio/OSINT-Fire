import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api.dart' show baseUrl;

class ImportResult {
  ImportResult(this.id, this.name, this.entities, this.relations, this.warnings);
  final int id;
  final String name;
  final int entities;
  final int relations;
  final List<String> warnings;
}

/// Bring an investigation back from an archive (or a json / GraphML export). Creates a NEW investigation.
Future<ImportResult> importArchive(String content) async {
  final r = await http.post(Uri.parse('$baseUrl/investigations/import'), headers: {'Content-Type': 'application/octet-stream'}, body: utf8.encode(content));
  final j = jsonDecode(utf8.decode(r.bodyBytes));
  if (r.statusCode != 200) throw Exception(j is Map && j['detail'] is String ? j['detail'] : 'HTTP ${r.statusCode}');
  return ImportResult(j['id'] as int, '${j['name'] ?? ''}', j['entities'] as int, j['relations'] as int, [for (final w in j['warnings'] as List) '$w']);
}
