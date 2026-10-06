import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/pivot_links.dart';

void main() {
  test('every searchable type has links, all http(s), values are encoded', () {
    for (final t in ['Dominio', 'IP', 'Email', 'Username', 'Persona', 'Azienda', 'Telefono', 'Account']) {
      final l = pivotLinks(t, t == 'Account' ? 'https://github.com/x' : 'a b&c@d.com');
      expect(l, isNotEmpty, reason: t);
      for (final x in l) {
        expect(x.url, startsWith('http'), reason: '$t ${x.label}');
        expect(Uri.tryParse(x.url), isNotNull, reason: x.url);
      }
    }
    final email = pivotLinks('Email', 'a b&c@d.com').first.url;
    expect(email, contains('%22a+b%26c%40d.com%22')); // quoted + query-encoded, no raw & or space
    expect(pivotLinks('Telefono', '+39 02-123').map((l) => l.url), contains('https://wa.me/3902123'));
  });

  test('image search needs the original url; groups/unknown types give nothing', () {
    expect(pivotLinks('Immagine', 'hash'), isEmpty);
    final l = pivotLinks('Immagine', 'hash', imageUrl: 'https://x.com/a.jpg?s=1&t=2');
    expect(l.first.url, contains('url=https%3A%2F%2Fx.com%2Fa.jpg%3Fs%3D1%26t%3D2'));
    expect(pivotLinks('Luogo', 'Roma'), isEmpty);
  });
}
