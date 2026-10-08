import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/widgets.dart';

import 'translations.dart';

/// Interface languages. English is the language of the source strings; the others come from [kTranslations].
const supportedLangs = ['it', 'en', 'es', 'de'];
const langNames = {'it': 'Italiano', 'en': 'English', 'es': 'Español', 'de': 'Deutsch'};

/// The language of the interface right now. Changing it rebuilds every screen that called [LangScope.watch].
final ValueNotifier<String> appLang = ValueNotifier(systemLang());

String systemLang([String? code]) {
  final c = code ?? PlatformDispatcher.instance.locale.languageCode;
  return supportedLangs.contains(c) ? c : 'en';
}

/// Translate a source string (English). `{0}`, `{1}`… are replaced by [args]. Unknown strings and English return as written.
String t(String en, [List<Object?> args = const []]) {
  final i = const {'it': 0, 'es': 1, 'de': 2}[appLang.value];
  var s = i == null ? en : (kTranslations[en]?[i] ?? en);
  for (var k = 0; k < args.length; k++) {
    s = s.replaceAll('{$k}', '${args[k]}');
  }
  return s;
}

/// Put once above the app: any widget that calls [watch] in `build` is rebuilt when the language changes.
class LangScope extends InheritedNotifier<ValueNotifier<String>> {
  const LangScope({super.key, required ValueNotifier<String> notifier, required super.child}) : super(notifier: notifier);

  static String watch(BuildContext context) {
    context.dependOnInheritedWidgetOfExactType<LangScope>();
    return appLang.value;
  }
}

/// Entity types the user can pick by name (seed types and the types offered for hand-made nodes), as [English source, canonical type].
const _pickableTypes = <String, String>{
  'Dominio': 'Domain', 'Email': 'Email', 'Username': 'Username', 'IP': 'IP', 'Telefono': 'Phone', 'Portafoglio': 'Wallet', 'Persona': 'Person', 'Azienda': 'Company',
  'Account': 'Account', 'Luogo': 'Place', 'Evento': 'Event', 'Oggetto': 'Object', 'Documento': 'Document', 'Nota': 'Note',
};

/// Name of an entity type in the interface language. [fromServer] are the labels the backend sent with the graph.
String typeLabel(String canonical, [Map<String, String>? fromServer]) {
  final s = fromServer?[canonical];
  if (s != null) return s;
  final en = _pickableTypes[canonical];
  return en == null ? canonical : t(en);
}

/// Back from what the user typed or picked to the canonical (stored) type name; anything else is a custom type, kept as typed.
String typeKey(String label) {
  final l = label.trim().toLowerCase();
  for (final e in _pickableTypes.entries) {
    if (l == t(e.value).toLowerCase() || l == e.key.toLowerCase() || l == e.value.toLowerCase()) return e.key;
  }
  return label.trim();
}

/// Date and time in the order people expect in the current language.
String fmtDateTime(DateTime d) {
  String two(int x) => x.toString().padLeft(2, '0');
  final time = '${two(d.hour)}:${two(d.minute)}';
  return switch (appLang.value) {
    'en' => '${d.year}-${two(d.month)}-${two(d.day)} $time',
    'de' => '${two(d.day)}.${two(d.month)}.${d.year} $time',
    _ => '${two(d.day)}/${two(d.month)}/${d.year} $time',
  };
}
