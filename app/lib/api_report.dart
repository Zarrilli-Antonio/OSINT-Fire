import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'api.dart' show baseUrl;

const reportSections = ['summary', 'entities', 'relations', 'links', 'notes', 'tags', 'proofs', 'timeline'];

class ReportOptions {
  ReportOptions({
    this.format = 'html',
    List<String>? sections,
    this.title = '',
    this.header = '',
    this.footer = '',
    this.logoBase64,
    this.includeHidden = false,
    this.lang,
  }) : sections = sections ?? List.of(reportSections);

  final String format; // html | pdf | md
  final List<String> sections;
  final String title, header, footer;
  final String? logoBase64;
  final bool includeHidden;
  final String? lang; // it | en | es | de; null lets the server pick

  Map<String, dynamic> toJson() => {
        'format': format,
        'sections': sections,
        'title': title,
        'header': header,
        'footer': footer,
        if (logoBase64 != null) 'logo': logoBase64,
        'include_hidden': includeHidden,
        'lang': lang,
      };
}

/// Build a custom report on the backend; returns the file bytes.
Future<Uint8List> buildReport(int inv, ReportOptions o) async {
  final r = await http.post(Uri.parse('$baseUrl/investigations/$inv/report'),
      headers: {'Content-Type': 'application/json'}, body: jsonEncode(o.toJson()));
  if (r.statusCode != 200) {
    String d;
    try {
      final x = jsonDecode(utf8.decode(r.bodyBytes))['detail'];
      d = x is String ? x : jsonEncode(x);
    } catch (_) {
      d = r.body;
    }
    throw Exception(d);
  }
  return r.bodyBytes;
}
