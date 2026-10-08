import 'dart:io';

import 'l10n.dart';
import 'platform.dart';

class PivotLink {
  const PivotLink(this.label, this.url);
  final String label, url;
}

String _q(String s) => Uri.encodeQueryComponent(s);
String _p(String s) => Uri.encodeComponent(s);

/// External lookups worth doing by hand for an entity: sites that need a browser, a login or a captcha, so the app
/// opens them instead of scraping. [imageUrl] is the original avatar URL for reverse image search.
List<PivotLink> pivotLinks(String type, String value, {String? imageUrl}) {
  switch (type) {
    case 'Dominio':
      return [
        PivotLink('Google site:', 'https://www.google.com/search?q=${_q('site:$value')}'),
        PivotLink('VirusTotal', 'https://www.virustotal.com/gui/domain/${_p(value)}'),
        PivotLink('urlscan', 'https://urlscan.io/search/#${_p('domain:$value')}'),
        PivotLink('Shodan', 'https://www.shodan.io/search?query=${_q('hostname:$value')}'),
        PivotLink('Censys', 'https://search.censys.io/search?q=${_q(value)}'),
        PivotLink('SecurityTrails', 'https://securitytrails.com/domain/${_p(value)}/dns'),
        PivotLink('Wayback', 'https://web.archive.org/web/*/${_p(value)}'),
        PivotLink('BuiltWith', 'https://builtwith.com/${_p(value)}'),
        PivotLink('Robtex', 'https://www.robtex.com/dns-lookup/${_p(value)}'),
        PivotLink('Whois', 'https://who.is/whois/${_p(value)}'),
      ];
    case 'IP':
      return [
        PivotLink('Shodan', 'https://www.shodan.io/host/${_p(value)}'),
        PivotLink('Censys', 'https://search.censys.io/hosts/${_p(value)}'),
        PivotLink('VirusTotal', 'https://www.virustotal.com/gui/ip-address/${_p(value)}'),
        PivotLink('AbuseIPDB', 'https://www.abuseipdb.com/check/${_p(value)}'),
        PivotLink('GreyNoise', 'https://viz.greynoise.io/ip/${_p(value)}'),
        PivotLink('BGP Toolkit', 'https://bgp.he.net/ip/${_p(value)}'),
        PivotLink('Robtex', 'https://www.robtex.com/ip-lookup/${_p(value)}'),
      ];
    case 'Email':
      return [
        PivotLink('Google', 'https://www.google.com/search?q=${_q('"$value"')}'),
        PivotLink('Have I Been Pwned', 'https://haveibeenpwned.com/account/${_p(value)}'),
        PivotLink('IntelX', 'https://intelx.io/?s=${_q(value)}'),
        PivotLink('Epieos', 'https://epieos.com/?q=${_q(value)}&t=email'),
        PivotLink('Bing', 'https://www.bing.com/search?q=${_q('"$value"')}'),
        PivotLink('GitHub', 'https://github.com/search?q=${_q(value)}&type=users'),
        PivotLink(t('Facebook (your login)'), 'https://www.facebook.com/search/top?q=${_q(value)}'),
        PivotLink(t('LinkedIn (your login)'), 'https://www.linkedin.com/search/results/all/?keywords=${_q(value)}'),
        PivotLink(t('X (your login)'), 'https://x.com/search?q=${_q(value)}'),
      ];
    case 'Username':
      return [
        PivotLink('Google', 'https://www.google.com/search?q=${_q('"$value"')}'),
        PivotLink('Instagram', 'https://www.instagram.com/${_p(value)}/'),
        PivotLink('X', 'https://x.com/${_p(value)}'),
        PivotLink('Facebook', 'https://www.facebook.com/${_p(value)}'),
        PivotLink('LinkedIn', 'https://www.linkedin.com/in/${_p(value)}'),
        PivotLink('TikTok', 'https://www.tiktok.com/@${_p(value)}'),
        PivotLink('Reddit', 'https://www.reddit.com/user/${_p(value)}'),
        PivotLink('Telegram', 'https://t.me/${_p(value)}'),
        PivotLink('GitHub', 'https://github.com/${_p(value)}'),
        PivotLink('Threads', 'https://www.threads.net/@${_p(value)}'),
        PivotLink('YouTube', 'https://www.youtube.com/@${_p(value)}'),
        PivotLink('Twitch', 'https://www.twitch.tv/${_p(value)}'),
        PivotLink('Pinterest', 'https://www.pinterest.com/${_p(value)}/'),
        PivotLink('Snapchat', 'https://www.snapchat.com/add/${_p(value)}'),
        PivotLink('Spotify', 'https://open.spotify.com/user/${_p(value)}'),
        PivotLink('WhatsMyName', 'https://whatsmyname.app/?q=${_q(value)}'),
        PivotLink('Namechk', 'https://namechk.com/?q=${_q(value)}'),
      ];
    case 'Persona':
      return [
        PivotLink('Google', 'https://www.google.com/search?q=${_q('"$value"')}'),
        PivotLink('LinkedIn', 'https://www.linkedin.com/search/results/people/?keywords=${_q(value)}'),
        PivotLink('Facebook', 'https://www.facebook.com/search/people/?q=${_q(value)}'),
        PivotLink('Instagram', 'https://www.google.com/search?q=${_q('site:instagram.com "$value"')}'),
        PivotLink('X', 'https://x.com/search?q=${_q('"$value"')}&f=user'),
        PivotLink('TikTok', 'https://www.tiktok.com/search/user?q=${_q(value)}'),
        PivotLink('YouTube', 'https://www.youtube.com/results?search_query=${_q(value)}&sp=EgIQAg%253D%253D'),
        PivotLink('Google Scholar', 'https://scholar.google.com/scholar?q=${_q('author:"$value"')}'),
        PivotLink('Google News', 'https://news.google.com/search?q=${_q('"$value"')}'),
        PivotLink('OpenCorporates', 'https://opencorporates.com/officers?q=${_q(value)}'),
      ];
    case 'Azienda':
      return [
        PivotLink('Google', 'https://www.google.com/search?q=${_q('"$value"')}'),
        PivotLink('OpenCorporates', 'https://opencorporates.com/companies?q=${_q(value)}'),
        PivotLink('LinkedIn', 'https://www.linkedin.com/search/results/companies/?keywords=${_q(value)}'),
        PivotLink('Registro Imprese', 'https://www.registroimprese.it/'),
        PivotLink('Crunchbase', 'https://www.crunchbase.com/textsearch?q=${_q(value)}'),
        PivotLink('Google News', 'https://news.google.com/search?q=${_q('"$value"')}'),
      ];
    case 'Telefono':
      final digits = value.replaceAll(RegExp(r'[^\d]'), '');
      return [
        PivotLink('Google', 'https://www.google.com/search?q=${_q('"$value"')}'),
        PivotLink('WhatsApp', 'https://wa.me/$digits'),
        PivotLink('Telegram', 'https://t.me/+$digits'),
        PivotLink('Truecaller', 'https://www.truecaller.com/search/it/$digits'),
        PivotLink('Tellows', 'https://www.tellows.it/num/$digits'),
        PivotLink(t('Facebook (your login)'), 'https://www.facebook.com/search/top?q=${_q(value)}'),
      ];
    case 'Account':
      return [
        PivotLink(t('Open profile'), value),
        PivotLink('Wayback', 'https://web.archive.org/web/*/$value'),
      ];
    case 'Immagine':
      final u = imageUrl;
      if (u == null || u.isEmpty) return const [];
      return [
        PivotLink('Google Lens', 'https://lens.google.com/uploadbyurl?url=${_q(u)}'),
        PivotLink('TinEye', 'https://tineye.com/search?url=${_q(u)}'),
        PivotLink('Yandex', 'https://yandex.com/images/search?rpt=imageview&url=${_q(u)}'),
        PivotLink('Bing', 'https://www.bing.com/images/search?view=detailv2&iss=sbi&q=imgurl:${_q(u)}'),
        PivotLink(t('Open original'), u),
      ];
  }
  return const [];
}

/// Open a URL in the default browser. Only http(s) is ever opened.
Future<void> openUrl(String url) async {
  final cmd = openUrlCommand(url, windows: Platform.isWindows, macos: Platform.isMacOS);
  if (cmd != null) await Process.run(cmd.first, cmd.skip(1).toList());
}
