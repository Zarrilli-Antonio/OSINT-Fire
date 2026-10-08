import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/flags.dart';
import 'package:osint_fire/l10n.dart';
import 'package:osint_fire/translations.dart';

void main() {
  tearDown(() => appLang.value = 'en');

  test('every t() string in lib/ has it, es and de, with the same placeholders', () {
    final re = RegExp(r"\bt\(\s*((?:'(?:[^'\\]|\\.)*'\s*|" r'"(?:[^"\\]|\\.)*"\s*)+)');
    final lit = RegExp(r"'((?:[^'\\]|\\.)*)'|" r'"((?:[^"\\]|\\.)*)"');
    final used = <String>{};
    for (final f in Directory('lib').listSync().whereType<File>()) {
      if (f.path.contains('tr_') || f.path.endsWith('translations.dart')) continue;
      for (final m in re.allMatches(f.readAsStringSync())) {
        // adjacent literals are one string
        final joined = lit.allMatches(m.group(1)!).map((x) => x.group(1) ?? x.group(2)!).join();
        used.add(joined.replaceAll(r"\'", "'").replaceAll(r'\"', '"').replaceAll(r'\n', '\n').replaceAll(r'\$', r'$'));
      }
    }
    expect(used, isNotEmpty);
    final holes = <String>[];
    for (final k in used) {
      final tr = kTranslations[k];
      final ph = RegExp(r'\{\d\}').allMatches(k).map((m) => m.group(0)).toSet();
      if (tr == null || tr.length != 3 || tr.any((s) => s.trim().isEmpty) || tr.any((s) => RegExp(r'\{\d\}').allMatches(s).map((m) => m.group(0)).toSet().difference(ph).isNotEmpty || ph.difference(RegExp(r'\{\d\}').allMatches(s).map((m) => m.group(0)).toSet()).isNotEmpty)) holes.add(k);
    }
    expect(holes, isEmpty);
  });

  test('no key is defined in two translation tables', () {
    final seen = <String, String>{};
    final dup = <String>[];
    for (final f in Directory('lib').listSync().whereType<File>().where((f) => RegExp(r'tr_\w+\.dart$').hasMatch(f.path))) {
      for (final m in RegExp(r"^  '((?:[^'\\]|\\.)*)':", multiLine: true).allMatches(f.readAsStringSync())) {
        final k = m.group(1)!;
        if (seen.containsKey(k)) dup.add('$k (${seen[k]} / ${f.path})');
        seen[k] = f.path;
      }
    }
    expect(dup, isEmpty);
  });

  test('t() switches language and fills placeholders', () {
    appLang.value = 'en';
    expect(t('Domain'), 'Domain');
    appLang.value = 'it';
    expect(t('Domain'), 'Dominio');
    appLang.value = 'de';
    expect(t('note not saved ({0})', [500]), 'Notiz nicht gespeichert (500)');
    appLang.value = 'es';
    expect(t('Person'), 'Persona');
    expect(t('never translated'), 'never translated');
  });

  test('type labels map both ways', () {
    appLang.value = 'de';
    expect(typeLabel('Azienda'), 'Unternehmen');
    expect(typeKey('Unternehmen'), 'Azienda');
    expect(typeKey('Company'), 'Azienda');
    expect(typeKey('Custom thing'), 'Custom thing');
    expect(typeLabel('Dominio', {'Dominio': 'Domain name'}), 'Domain name');
  });

  test('systemLang falls back to English', () {
    expect(systemLang('fr'), 'en');
    expect(systemLang('es'), 'es');
  });

  testWidgets('every flag paints', (tester) async {
    await tester.pumpWidget(Directionality(textDirection: TextDirection.ltr, child: Row(children: [for (final l in supportedLangs) FlagIcon(l)])));
    expect(find.byType(FlagIcon), findsNWidgets(4));
  });
}
