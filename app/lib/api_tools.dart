import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api.dart';

class ParsedSeeds {
  ParsedSeeds(this.seeds, this.skipped);
  final List<(String, String)> seeds; // (canonical type, value)
  final List<String> skipped; // lines that were not understood
}

/// Detect seeds in pasted text or CSV.
Future<ParsedSeeds> parseSeeds(String text) async {
  final r = await http.post(Uri.parse('$baseUrl/seeds/parse'), headers: {'content-type': 'application/json'}, body: jsonEncode({'text': text}));
  final j = jsonDecode(utf8.decode(r.bodyBytes));
  if (r.statusCode != 200) throw Exception(j is Map && j['detail'] is String ? j['detail'] : '${r.statusCode}');
  return ParsedSeeds([for (final s in j['seeds']) (s['type'] as String, s['value'] as String)], [for (final s in j['skipped']) s as String]);
}
