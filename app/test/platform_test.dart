import 'package:flutter_test/flutter_test.dart';
import 'package:osint_fire/platform.dart';

void main() {
  test('downloads folder per platform', () {
    expect(downloadsDirFor({'HOME': '/Users/a/Library/Containers/it.osintfire.osintFire/Data'}, windows: false), '/Users/a/Downloads');
    expect(downloadsDirFor({'HOME': '/home/b'}, windows: false), '/home/b/Downloads');
    expect(downloadsDirFor({'USERPROFILE': r'C:\Users\Anna'}, windows: true), r'C:\Users\Anna\Downloads');
  });

  test('packaged backend is found next to the executable on Windows and in Resources on macOS', () {
    expect(bundledBackendPathFor('/Applications/OSINT-Fire.app/Contents/MacOS/OSINT-Fire', windows: false),
        '/Applications/OSINT-Fire.app/Contents/Resources/backend/osint-backend');
    expect(bundledBackendPathFor(r'C:\Apps\OSINT-Fire\OSINT-Fire.exe', windows: true), r'C:\Apps\OSINT-Fire\backend\osint-backend.exe');
  });

  test('urls open with the right command and only http(s)', () {
    const url = 'https://www.google.com/search?q=a&b=c';
    expect(openUrlCommand(url, windows: false, macos: true), ['open', url]);
    expect(openUrlCommand(url, windows: true, macos: false), ['rundll32', 'url.dll,FileProtocolHandler', url]); // '&' must reach the browser intact
    expect(openUrlCommand(url, windows: false, macos: false), ['xdg-open', url]);
    expect(openUrlCommand('file:///etc/passwd', windows: false, macos: true), isNull);
    expect(openUrlCommand('javascript:alert(1)', windows: true, macos: false), isNull);
    expect(openUrlCommand('not a url', windows: false, macos: true), isNull);
  });
}
