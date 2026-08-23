/// Build-time configuration.
///
/// Every environment-specific value arrives via `--dart-define`, so no API
/// host, credential or clinical threshold is compiled into the binary.
/// Clinical rules themselves live server-side and are fetched, never hardcoded.
library;

class AppConfig {
  const AppConfig._();

  /// Backend API root. The Android emulator reaches the host machine on
  /// 10.0.2.2, which is why that is the development default.
  static const String apiBaseUrl = String.fromEnvironment(
    'RS_API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );

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
