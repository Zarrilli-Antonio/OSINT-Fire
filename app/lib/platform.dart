import 'dart:io';

/// Everything that differs between macOS, Windows and Linux lives here, as pure functions so it can be tested on any machine.

String downloadsDirFor(Map<String, String> env, {required bool windows}) {
  if (windows) return '${env['USERPROFILE'] ?? env['HOMEDRIVE'] ?? ''}\\Downloads';
  // a sandboxed macOS app reports a HOME inside its container; the real folder is above it
  return '${(env['HOME'] ?? '').split('/Library/Containers').first}/Downloads';
}

String downloadsDir() => downloadsDirFor(Platform.environment, windows: Platform.isWindows);

String homeDir() => (Platform.isWindows ? Platform.environment['USERPROFILE'] : Platform.environment['HOME']) ?? '.';

/// Where the packaged app keeps its Python backend, relative to the running executable.
/// macOS: OSINT-Fire.app/Contents/MacOS/OSINT-Fire -> ../Resources/backend/osint-backend
/// Windows: OSINT-Fire\OSINT-Fire.exe -> backend\osint-backend.exe
String bundledBackendPathFor(String resolvedExecutable, {required bool windows}) {
  final sep = windows ? '\\' : '/';
  final parts = resolvedExecutable.split(sep);
  parts.removeLast(); // the executable itself
  if (windows) return '${parts.join(sep)}\\backend\\osint-backend.exe';
  parts.removeLast(); // MacOS -> Contents
  return '${parts.join(sep)}/Resources/backend/osint-backend';
}

/// The command that opens a URL in the default browser. Only http(s) is ever opened.
List<String>? openUrlCommand(String url, {required bool windows, required bool macos}) {
  final u = Uri.tryParse(url);
  if (u == null || !(u.scheme == 'http' || u.scheme == 'https')) return null;
  if (macos) return ['open', url];
  // rundll32 hands the URL over untouched: `cmd /c start` would treat '&' in a query string as a second command
  if (windows) return ['rundll32', 'url.dll,FileProtocolHandler', url];
  return ['xdg-open', url];
}
