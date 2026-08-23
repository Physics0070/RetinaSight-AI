/// Build-time configuration.
///
/// Every environment-specific value arrives via `--dart-define`, so no API
/// host, credential or clinical threshold is compiled into the binary.
/// Clinical rules themselves live server-side and are fetched, never hardcoded.
library;

class AppConfig {
  const AppConfig._();

  /// Raw compile-time value. Empty when `--dart-define` was not supplied.
  ///
  /// There is deliberately no `defaultValue`. `String.fromEnvironment` is
  /// resolved at compile time, so a default here is baked into the shipped
  /// binary — an APK built without the define would point at the developer's
  /// machine, and there is no way to notice that short of running it.
  static const String _apiBaseUrl = String.fromEnvironment('RS_API_BASE_URL');

  /// Backend API root.
  ///
  /// Build with, for example:
  ///   flutter run --dart-define=RS_API_BASE_URL=http://10.0.2.2:8000/api/v1
  /// (the Android emulator reaches the host machine on 10.0.2.2).
  static String get apiBaseUrl {
    if (_apiBaseUrl.trim().isEmpty) {
      throw StateError(
        'RS_API_BASE_URL was not set at build time. Pass it with '
        '--dart-define=RS_API_BASE_URL=<api root>; see .env.example.',
      );
    }
    return _apiBaseUrl.trim();
  }

  /// Whether an API root was supplied, without throwing. Lets startup show a
  /// configuration screen rather than crashing on first request.
  static bool get hasApiBaseUrl => _apiBaseUrl.trim().isNotEmpty;

  /// Stable identifier for this device, used to scope the sync queue.
  /// Generated and persisted on first run when not supplied.
  static const String configuredDeviceId =
      String.fromEnvironment('RS_DEVICE_ID', defaultValue: '');

  /// How often the background sync worker retries while online.
  static const Duration syncInterval = Duration(seconds: 30);

  /// Maximum attempts before an item is parked as failed for manual review.
  static const int maxSyncAttempts = 5;

  /// Standing disclaimer shown wherever AI output is presented.
  static const String aiDisclaimer =
      'AI-assisted screening support. This is not a diagnosis. '
      'Clinical review by a qualified clinician is required.';
}
