import 'package:flutter/material.dart';

/// Small flags drawn as vectors, so they look the same everywhere (Windows has no flag emoji).
class FlagIcon extends StatelessWidget {
  const FlagIcon(this.lang, {super.key, this.width = 24});
  final String lang;
  final double width;

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(2.5),
        child: CustomPaint(size: Size(width, width * 2 / 3), painter: _FlagPainter(lang)),
      );
}

class _FlagPainter extends CustomPainter {
  _FlagPainter(this.lang);
  final String lang;

  @override
  void paint(Canvas canvas, Size s) {
    Paint p(int c) => Paint()..color = Color(c);
    void bands(List<int> colors, {required bool vertical, List<double>? weights}) {
      final w = weights ?? List.filled(colors.length, 1.0);
      final total = w.fold<double>(0, (a, b) => a + b);
      var at = 0.0;
      for (var i = 0; i < colors.length; i++) {
        final len = w[i] / total * (vertical ? s.width : s.height);
        canvas.drawRect(vertical ? Rect.fromLTWH(at, 0, len + 0.5, s.height) : Rect.fromLTWH(0, at, s.width, len + 0.5), p(colors[i]));
        at += len;
      }
    }

    switch (lang) {
      case 'it':
        bands([0xFF009246, 0xFFFFFFFF, 0xFFCE2B37], vertical: true);
      case 'es':
        bands([0xFFAA151B, 0xFFF1BF00, 0xFFAA151B], vertical: false, weights: [1, 2, 1]);
      case 'de':
        bands([0xFF000000, 0xFFDD0000, 0xFFFFCE00], vertical: false);
      default: // United Kingdom, simplified Union Jack
        canvas.save();
        canvas.scale(s.width / 60, s.height / 30);
        canvas.drawRect(const Rect.fromLTWH(0, 0, 60, 30), p(0xFF012169));
        final diag = Paint()..style = PaintingStyle.stroke;
        canvas.drawLine(Offset.zero, const Offset(60, 30), diag..color = Colors.white..strokeWidth = 6);
        canvas.drawLine(const Offset(60, 0), const Offset(0, 30), diag);
        canvas.drawLine(Offset.zero, const Offset(60, 30), diag..color = const Color(0xFFC8102E)..strokeWidth = 2);
        canvas.drawLine(const Offset(60, 0), const Offset(0, 30), diag);
        canvas.drawRect(const Rect.fromLTWH(0, 10, 60, 10), p(0xFFFFFFFF));
        canvas.drawRect(const Rect.fromLTWH(25, 0, 10, 30), p(0xFFFFFFFF));
        canvas.drawRect(const Rect.fromLTWH(0, 12, 60, 6), p(0xFFC8102E));
        canvas.drawRect(const Rect.fromLTWH(27, 0, 6, 30), p(0xFFC8102E));
        canvas.restore();
    }
    canvas.drawRect(Offset.zero & s, Paint()..color = const Color(0x33000000)..style = PaintingStyle.stroke..strokeWidth = 0.6); // hairline so white bands show on light themes too
  }

  @override
  bool shouldRepaint(_FlagPainter old) => old.lang != lang;
}
