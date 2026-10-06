import 'package:flutter/material.dart';

const bg = Color(0xFF0A0A0C);
const accent = Color(0xFFE5484D);
const fg = Color(0xFFE6E6E8);
const dim = Color(0xFF8A8A92);
const panel = Color(0xE6111114);
const line = Color(0x1FFFFFFF);
const gold = Color(0xFFFFD166);

const mono = 'Menlo';
const monoFallback = ['SF Mono', 'Monaco', 'Cascadia Mono', 'Consolas', 'Courier New', 'monospace']; // Menlo exists only on macOS

const _typeColors = {
  'Dominio': Color(0xFF6EA8FE),
  'IP': Color(0xFFFFB454),
  'Email': Color(0xFF7EE787),
  'Username': Color(0xFFD2A8FF),
  'Persona': Color(0xFFFF7B72),
  'Account': Color(0xFF56D4DD),
  'Azienda': Color(0xFF8B9CF7),
  'Immagine': Color(0xFF39C5CF),
  'Wikidata': Color(0xFFC49A6C),
  'Breach': Color(0xFFFF7EB6),
  'Servizio': Color(0xFFE3B341),
  'Vulnerabilità': Color(0xFFFF5252),
  'Luogo': Color(0xFFA3D977),
  'Rete': Color(0xFF8B949E),
  'Tecnologia': Color(0xFFB794F6),
  'Registrazione': Color(0xFFE5C07B),
  'Telefono': Color(0xFFFFA657),
  'Chiave SSH': Color(0xFFC9D1D9),
  'Chiave PGP': Color(0xFFB1BAC4),
  'Data': Color(0xFF79C0FF),
  'ID tracciamento': Color(0xFFFF9E64),
  'App': Color(0xFF9ECE6A),
  'Interesse': Color(0xFFBB9AF7),
};

Color typeColor(String type) => _typeColors[type] ?? dim;

TextTheme _text(TextTheme base) {
  final t = base.apply(bodyColor: fg, displayColor: fg);
  TextStyle? sz(TextStyle? s, double size) => s?.copyWith(fontSize: size);
  return t.copyWith(
    bodyLarge: sz(t.bodyLarge, 13),
    bodyMedium: sz(t.bodyMedium, 12),
    bodySmall: sz(t.bodySmall, 11),
    titleLarge: sz(t.titleLarge, 16),
    titleMedium: sz(t.titleMedium, 13),
    titleSmall: sz(t.titleSmall, 12),
    labelLarge: sz(t.labelLarge, 12),
    labelMedium: sz(t.labelMedium, 11),
    labelSmall: sz(t.labelSmall, 10),
  );
}

ThemeData buildTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    fontFamily: mono,
    fontFamilyFallback: monoFallback,
    scaffoldBackgroundColor: Colors.transparent,
    colorScheme: const ColorScheme.dark(
      primary: accent,
      onPrimary: Colors.white,
      secondary: accent,
      surface: Color(0xFF111114),
      onSurface: fg,
      outline: line,
    ),
  );
  final side = const BorderSide(color: line);
  return base.copyWith(
    textTheme: _text(base.textTheme),
    dividerTheme: const DividerThemeData(color: line, space: 1, thickness: 1),
    inputDecorationTheme: const InputDecorationTheme(
      isDense: true,
      labelStyle: TextStyle(color: dim, fontSize: 12),
      enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: line)),
      focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: accent)),
      contentPadding: EdgeInsets.symmetric(vertical: 8),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: accent,
        disabledBackgroundColor: const Color(0x33E5484D),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
        padding: const EdgeInsets.symmetric(vertical: 14),
        // a button style replaces the theme's text style instead of merging with it: name the font explicitly
        textStyle: const TextStyle(letterSpacing: 1.2, fontWeight: FontWeight.w600, fontSize: 12, fontFamily: mono, fontFamilyFallback: monoFallback),
      ),
    ),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(foregroundColor: accent)),
    iconButtonTheme: IconButtonThemeData(style: IconButton.styleFrom(foregroundColor: dim, iconSize: 18)),
    sliderTheme: const SliderThemeData(
      activeTrackColor: accent,
      thumbColor: accent,
      inactiveTrackColor: line,
      trackHeight: 2,
      overlayShape: RoundSliderOverlayShape(overlayRadius: 12),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: Colors.transparent,
      side: side,
      labelStyle: const TextStyle(fontSize: 11, color: fg, fontFamily: mono, fontFamilyFallback: monoFallback), // chips do not inherit the theme font
      deleteIconColor: dim,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
    ),
    cardTheme: CardThemeData(
      color: panel,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: side),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: const Color(0xFF131316),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: side),
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: const Color(0xFF131316),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6), side: side),
      textStyle: const TextStyle(fontSize: 12, color: fg, fontFamily: mono),
    ),
    dropdownMenuTheme: const DropdownMenuThemeData(textStyle: TextStyle(fontSize: 12)),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: const Color(0xFF1A1A1E), borderRadius: BorderRadius.circular(4), border: Border.all(color: line)),
      textStyle: const TextStyle(fontSize: 11, color: fg, fontFamily: mono),
    ),
  );
}

/// Near-black base with two soft red glows.
class Backdrop extends StatelessWidget {
  const Backdrop({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Stack(fit: StackFit.expand, children: [
        const ColoredBox(color: bg),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: RadialGradient(center: Alignment(-1.0, -1.1), radius: 1.3, colors: [Color(0x40E5484D), Color(0x00E5484D)]),
          ),
        ),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: RadialGradient(center: Alignment(1.1, 1.2), radius: 1.1, colors: [Color(0x26E5484D), Color(0x00E5484D)]),
          ),
        ),
        child,
      ]);
}
