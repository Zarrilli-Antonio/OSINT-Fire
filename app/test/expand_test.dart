import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/api.dart';

void main() {
  (String, String)? t(String type, String value, {List<String> members = const []}) => expandTarget(GNode(1, type, value, members));

  test('searchable types expand as themselves', () {
    expect(t('Email', 'a@b.com'), ('Email', 'a@b.com'));
    expect(t('Dominio', 'x.com'), ('Dominio', 'x.com'));
    expect(t('Persona', 'Ann Lee'), ('Persona', 'Ann Lee'));
  });

  test('account urls expand from their handle', () {
    expect(t('Account', 'https://github.com/torvalds'), ('Username', 'torvalds'));
    expect(t('Account', 'https://www.linkedin.com/in/foo-bar'), ('Username', 'foo-bar'));
    expect(t('Account', 'https://mastodon.social/@gargron'), ('Username', 'gargron'));
    expect(t('Account', 'https://torvalds.wordpress.com/'), ('Username', 'torvalds'));
    expect(t('Account', 'https://www.example.com/'), isNull);
  });

  test('other types and groups are not expandable', () {
    expect(t('Luogo', 'Roma'), isNull);
    expect(t('Breach', '12 breach', members: ['a']), isNull);
  });
}
