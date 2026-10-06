import 'dart:io';

import 'package:http/http.dart' as http;

import 'api.dart';
import 'platform.dart';

/// Starts the Python backend as a child process if nothing answers on [baseUrl].
// ponytail: dev-layout only (finds ../backend next to the app, runs `uv run`). Bundle the backend (PyInstaller) for distribution.
class Backend {
  Process? _p;

  Future<bool> _up() async {
    try {
      final r = await http.get(Uri.parse('$baseUrl/collectors')).timeout(const Duration(seconds: 2));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// The backend executable inside a packaged app, or null when running from source.
  static File? bundled() {
    final f = File(bundledBackendPathFor(Platform.resolvedExecutable, windows: Platform.isWindows));
    return f.existsSync() ? f : null;
  }

  Directory? dir() {
    final env = Platform.environment['OSINT_BACKEND_DIR'];
    if (env != null) return Directory(env);
    var d = File(Platform.resolvedExecutable).parent;
    for (var i = 0; i < 12; i++, d = d.parent) {
      if (File('${d.path}/backend/pyproject.toml').existsSync()) return Directory('${d.path}/backend');
    }
    return null;
  }

  /// Returns null when the backend is reachable, else an error message.
  Future<String?> ensure() async {
    if (await _up()) return null;
    try {
      final exe = bundled();
      if (exe != null) {
        _p = await Process.start(exe.path, [], workingDirectory: homeDir());
      } else {
        final dir = this.dir();
        if (dir == null) return 'backend non trovato (imposta OSINT_BACKEND_DIR)';
        _p = Platform.isWindows
            ? await Process.start('uv', ['run', 'python', 'run_backend.py'], workingDirectory: dir.path, runInShell: true)
            // login shell so PATH includes uv
            : await Process.start('/bin/zsh', ['-lc', 'exec uv run python run_backend.py'], workingDirectory: dir.path);
      }
      // nobody reads the child's output: drain it, or a full pipe would eventually block the backend
      _p!.stdout.drain<void>();
      _p!.stderr.drain<void>();
    } catch (e) {
      return 'avvio backend fallito: $e';
    }
    for (var i = 0; i < 60; i++) {
      if (await _up()) return null;
      await Future.delayed(const Duration(milliseconds: 500));
    }
    return 'backend avviato ma non risponde su $baseUrl';
  }

  void stop() {
    final p = _p;
    if (p == null) return;
    // on Windows kill() only ends the shell that was started, not uv and the Python it spawned: end the whole tree
    if (Platform.isWindows) {
      Process.runSync('taskkill', ['/PID', '${p.pid}', '/T', '/F']);
    } else {
      p.kill();
    }
  }
}
