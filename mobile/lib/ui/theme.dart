/// Health-worker visual identity.
///
/// Medical-device neumorphism: soft tactile surfaces, large controls, physical
/// depth. Built for one-handed use in the field, often outdoors, sometimes with
/// gloves — so touch targets are generous and contrast stays high in daylight.
library;

import 'package:flutter/material.dart';

class RsColors {
  const RsColors._();

  static const surface = Color(0xFFE8ECF1);
  static const surfaceRaised = Color(0xFFEEF2F6);
  static const surfaceSunken = Color(0xFFDDE3EA);
  static const ink = Color(0xFF16202B);
  static const inkMuted = Color(0xFF46566A);
  static const inkSubtle = Color(0xFF6A7A8C);
  static const line = Color(0xFFC9D3DE);
  static const accent = Color(0xFF0F766E);

  // Retinal imaging palette.
  static const retina = Color(0xFFC2410C);
  static const retinaDeep = Color(0xFF7C2D12);
  static const vitreous = Color(0xFF0A0F16);

  // Clinical risk — always paired with a glyph and label, never colour alone.
  static const riskLow = Color(0xFF0F766E);
  static const riskModerate = Color(0xFFA16207);
  static const riskHigh = Color(0xFFC2410C);
  static const riskUrgent = Color(0xFFB91C1C);

  static const ok = Color(0xFF0F766E);
  static const warn = Color(0xFFA16207);
  static const danger = Color(0xFFB91C1C);
}

class RsSpacing {
  const RsSpacing._();
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
}

ThemeData buildRetinaSightTheme() {
  final base = ThemeData.light(useMaterial3: true);

  return base.copyWith(
    scaffoldBackgroundColor: RsColors.surface,
    colorScheme: base.colorScheme.copyWith(
      primary: RsColors.accent,
      surface: RsColors.surfaceRaised,
      error: RsColors.danger,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: RsColors.surfaceRaised,
      foregroundColor: RsColors.ink,
      elevation: 0,
      centerTitle: false,
    ),
    textTheme: base.textTheme.apply(
      bodyColor: RsColors.ink,
      displayColor: RsColors.ink,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: RsColors.accent,
        foregroundColor: Colors.white,
        // Large target for gloved, one-handed use.
        minimumSize: const Size.fromHeight(56),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: RsColors.ink,
        minimumSize: const Size.fromHeight(52),
        side: const BorderSide(color: RsColors.line),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: RsColors.surfaceSunken,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: RsColors.line),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
    ),
  );
}

/// Raised neumorphic surface: light from the top-left, shadow bottom-right.
class NeumorphicPanel extends StatelessWidget {
  const NeumorphicPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(RsSpacing.md),
    this.sunken = false,
  });

  final Widget child;
  final EdgeInsets padding;
  final bool sunken;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: sunken ? RsColors.surfaceSunken : RsColors.surfaceRaised,
        borderRadius: BorderRadius.circular(18),
        boxShadow: sunken
            ? null
            : const [
                BoxShadow(
                  color: Color(0x6B8B9BAC),
                  offset: Offset(6, 6),
                  blurRadius: 14,
                ),
                BoxShadow(
                  color: Color(0xEBFFFFFF),
                  offset: Offset(-6, -6),
                  blurRadius: 14,
                ),
              ],
      ),
      child: child,
    );
  }
}
