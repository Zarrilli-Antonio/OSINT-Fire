import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api.dart';
import 'diff.dart';
import 'timeline_view.dart';

/// Dated facts of an investigation plus how many facts had no usable date.
Future<(List<TimelineEvent>, int)> fetchTimeline(int inv) async {
  final r = await http.get(Uri.parse('$baseUrl/investigations/$inv/timeline'));
  if (r.statusCode != 200) throw Exception('timeline ${r.statusCode}');
  final j = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
  return ([for (final e in j['events'] as List) TimelineEvent.fromJson(e as Map<String, dynamic>)], (j['undated'] ?? 0) as int);
}

/// What is new since [since] (epoch seconds); default on the server: the last run.
Future<GraphDiff> fetchDiff(int inv, {double? since}) async {
  final q = since == null ? '' : '?since=$since';
  final r = await http.get(Uri.parse('$baseUrl/investigations/$inv/diff$q'));
  if (r.statusCode != 200) throw Exception('diff ${r.statusCode}');
  return GraphDiff.fromJson(jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>);
}
