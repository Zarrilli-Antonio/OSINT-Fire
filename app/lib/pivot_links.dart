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
List<PivotLink> pivotLinks(String type, String value, {String? imageUrl}) => [..._core(type, value, imageUrl: imageUrl), ..._more(type, value)];

List<PivotLink> _core(String type, String value, {String? imageUrl}) {
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

/// More public search engines, registries and lookup sites per type (links only: nothing is fetched by the app).
List<PivotLink> _more(String type, String value) {
  final quoted = _q('"$value"');
  switch (type) {
    case 'Dominio':
      return [
        PivotLink('crt.sh', 'https://crt.sh/?q=${_q(value)}'),
        PivotLink('DNSDumpster', 'https://dnsdumpster.com/'),
        PivotLink('ViewDNS', 'https://viewdns.info/reverseip/?host=${_q(value)}&t=1'),
        PivotLink('SecurityHeaders', 'https://securityheaders.com/?q=${_q(value)}&followRedirects=on'),
        PivotLink('SSL Labs', 'https://www.ssllabs.com/ssltest/analyze.html?d=${_q(value)}'),
        PivotLink('Netcraft', 'https://sitereport.netcraft.com/?url=${_q(value)}'),
        PivotLink('AlienVault OTX', 'https://otx.alienvault.com/indicator/domain/${_p(value)}'),
        PivotLink('Pulsedive', 'https://pulsedive.com/indicator/?ioc=${_q(value)}'),
        PivotLink('URLhaus', 'https://urlhaus.abuse.ch/browse.php?search=${_q(value)}'),
        PivotLink('Hunter', 'https://hunter.io/search/${_p(value)}'),
        PivotLink('Similarweb', 'https://www.similarweb.com/website/${_p(value)}/'),
        PivotLink('Archive.today', 'https://archive.ph/${_p(value)}'),
        PivotLink('Google docs', 'https://www.google.com/search?q=${_q('site:$value (filetype:pdf OR filetype:docx OR filetype:xlsx)')}'),
        PivotLink('Google login pages', 'https://www.google.com/search?q=${_q('site:$value (inurl:login OR inurl:admin)')}'),
        PivotLink('Bing', 'https://www.bing.com/search?q=${_q('domain:$value')}'),
        PivotLink('DuckDuckGo', 'https://duckduckgo.com/?q=${_q('site:$value')}'),
        PivotLink('Yandex', 'https://yandex.com/search/?text=${_q('host:$value')}'),
      ];
    case 'IP':
      return [
        PivotLink('IPinfo', 'https://ipinfo.io/${_p(value)}'),
        PivotLink('Netlas', 'https://app.netlas.io/host/${_p(value)}/'),
        PivotLink('Criminal IP', 'https://www.criminalip.io/asset/report/${_p(value)}'),
        PivotLink('Cisco Talos', 'https://talosintelligence.com/reputation_center/lookup?search=${_q(value)}'),
        PivotLink('AlienVault OTX', 'https://otx.alienvault.com/indicator/ip/${_p(value)}'),
        PivotLink('Pulsedive', 'https://pulsedive.com/indicator/?ioc=${_q(value)}'),
        PivotLink('IPVoid', 'https://www.ipvoid.com/ip-blacklist-check/?ip=${_q(value)}'),
        PivotLink('Spamhaus', 'https://check.spamhaus.org/results/?query=${_q(value)}'),
        PivotLink('DNSlytics', 'https://dnslytics.com/ip/${_p(value)}'),
        PivotLink('Google', 'https://www.google.com/search?q=$quoted'),
      ];
    case 'Email':
      return [
        PivotLink('DuckDuckGo', 'https://duckduckgo.com/?q=$quoted'),
        PivotLink('Yandex', 'https://yandex.com/search/?text=$quoted'),
        PivotLink('EmailRep', 'https://emailrep.io/${_p(value)}'),
        PivotLink('Hunter verify', 'https://hunter.io/email-verifier/${_p(value)}'),
        PivotLink('LeakCheck', 'https://leakcheck.io/'),
        PivotLink('Pastes (Google)', 'https://www.google.com/search?q=${_q('"$value" (site:pastebin.com OR site:ghostbin.com OR site:paste.ee)')}'),
        PivotLink('Documents (Google)', 'https://www.google.com/search?q=${_q('"$value" (filetype:pdf OR filetype:xlsx OR filetype:docx)')}'),
        PivotLink('GitLab', 'https://gitlab.com/search?search=${_q(value)}'),
        PivotLink('Skype/Teams', 'https://www.google.com/search?q=${_q('"$value" site:linkedin.com')}'),
      ];
    case 'Username':
      return [
        PivotLink('DuckDuckGo', 'https://duckduckgo.com/?q=$quoted'),
        PivotLink('Yandex', 'https://yandex.com/search/?text=$quoted'),
        PivotLink('Bluesky', 'https://bsky.app/profile/${_p(value)}.bsky.social'),
        PivotLink('Mastodon', 'https://mastodon.social/@${_p(value)}'),
        PivotLink('GitLab', 'https://gitlab.com/${_p(value)}'),
        PivotLink('Codeberg', 'https://codeberg.org/${_p(value)}'),
        PivotLink('Medium', 'https://medium.com/@${_p(value)}'),
        PivotLink('Tumblr', 'https://${_p(value)}.tumblr.com'),
        PivotLink('Flickr', 'https://www.flickr.com/people/${_p(value)}/'),
        PivotLink('Vimeo', 'https://vimeo.com/${_p(value)}'),
        PivotLink('SoundCloud', 'https://soundcloud.com/${_p(value)}'),
        PivotLink('Steam', 'https://steamcommunity.com/id/${_p(value)}'),
        PivotLink('Behance', 'https://www.behance.net/${_p(value)}'),
        PivotLink('Dribbble', 'https://dribbble.com/${_p(value)}'),
        PivotLink('Patreon', 'https://www.patreon.com/${_p(value)}'),
        PivotLink('Linktree', 'https://linktr.ee/${_p(value)}'),
        PivotLink('Keybase', 'https://keybase.io/${_p(value)}'),
        PivotLink('Docker Hub', 'https://hub.docker.com/u/${_p(value)}'),
        PivotLink('VK', 'https://vk.com/${_p(value)}'),
        PivotLink('Wayback', 'https://web.archive.org/web/*/${_p(value)}'),
      ];
    case 'Persona':
      return [
        PivotLink('DuckDuckGo', 'https://duckduckgo.com/?q=$quoted'),
        PivotLink('Bing', 'https://www.bing.com/search?q=$quoted'),
        PivotLink('Yandex', 'https://yandex.com/search/?text=$quoted'),
        PivotLink('Wikipedia', 'https://www.wikipedia.org/w/index.php?search=${_q(value)}'),
        PivotLink('Wikidata', 'https://www.wikidata.org/w/index.php?search=${_q(value)}'),
        PivotLink('ORCID', 'https://orcid.org/orcid-search/search?searchQuery=${_q(value)}'),
        PivotLink('ResearchGate', 'https://www.researchgate.net/search/researcher?q=${_q(value)}'),
        PivotLink('Archive.org', 'https://archive.org/search?query=${_q(value)}'),
        PivotLink('OpenSanctions', 'https://www.opensanctions.org/search/?q=${_q(value)}'),
        PivotLink('ICIJ Offshore Leaks', 'https://offshoreleaks.icij.org/search?q=${_q(value)}'),
        PivotLink('OFAC sanctions', 'https://sanctionssearch.ofac.treas.gov/'),
        PivotLink('Documents (Google)', 'https://www.google.com/search?q=${_q('"$value" (filetype:pdf OR filetype:docx)')}'),
        PivotLink('Patents (Google)', 'https://patents.google.com/?inventor=${_q(value)}'),
      ];
    case 'Azienda':
      return [
        PivotLink('DuckDuckGo', 'https://duckduckgo.com/?q=$quoted'),
        PivotLink('Bing', 'https://www.bing.com/search?q=$quoted'),
        PivotLink('Wikipedia', 'https://www.wikipedia.org/w/index.php?search=${_q(value)}'),
        PivotLink('Wikidata', 'https://www.wikidata.org/w/index.php?search=${_q(value)}'),
        PivotLink('GLEIF (LEI)', 'https://search.gleif.org/#/search/simpleSearch=${_p(value)}'),
        PivotLink('SEC EDGAR', 'https://www.sec.gov/cgi-bin/browse-edgar?company=${_q(value)}&action=getcompany'),
        PivotLink('OpenSanctions', 'https://www.opensanctions.org/search/?q=${_q(value)}'),
        PivotLink('ICIJ Offshore Leaks', 'https://offshoreleaks.icij.org/search?q=${_q(value)}'),
        PivotLink('Companies House (UK)', 'https://find-and-update.company-information.service.gov.uk/search?q=${_q(value)}'),
        PivotLink('Patents (Google)', 'https://patents.google.com/?assignee=${_q(value)}'),
        PivotLink('EUIPO trademarks', 'https://euipo.europa.eu/eSearch/#basic/1+1+1+1/100+100+100+100/${_p(value)}'),
        PivotLink('Archive.org', 'https://archive.org/search?query=${_q(value)}'),
      ];
    case 'Telefono':
      return [
        PivotLink('DuckDuckGo', 'https://duckduckgo.com/?q=$quoted'),
        PivotLink('Bing', 'https://www.bing.com/search?q=$quoted'),
        PivotLink('Signal', 'https://signal.me/#p/${_p(value)}'),
        PivotLink('Pastes (Google)', 'https://www.google.com/search?q=${_q('"$value" (site:pastebin.com OR site:ghostbin.com)')}'),
      ];
  }
  return const [];
}

/// Open a URL in the default browser. Only http(s) is ever opened.
Future<void> openUrl(String url) async {
  final cmd = openUrlCommand(url, windows: Platform.isWindows, macos: Platform.isMacOS);
  if (cmd != null) await Process.run(cmd.first, cmd.skip(1).toList());
}
