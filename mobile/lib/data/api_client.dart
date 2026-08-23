/// Backend API client.
///
/// Distinguishes "no connection" from "server rejected this" — the offline-first
/// UX depends on that difference being explicit rather than a generic failure.
library;

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import '../core/config.dart';

/// A failure the user can be shown. Never carries a stack trace or status code
/// into the UI.
class ApiException implements Exception {
  const ApiException(this.message, {this.code = 'error', this.statusCode = 0});

  final String message;
  final String code;
  final int statusCode;

  /// True when the request never reached the server.
  bool get isOffline => code == 'network_unavailable';

  bool get isAuthFailure => statusCode == 401;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  static const _accessKey = 'rs.access_token';
  static const _refreshKey = 'rs.refresh_token';
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  Future<String?> get accessToken => _storage.read(key: _accessKey);

  Future<void> _storeTokens(Map<String, dynamic> tokens) async {
    await _storage.write(key: _accessKey, value: tokens['access_token'] as String);
    await _storage.write(key: _refreshKey, value: tokens['refresh_token'] as String);
  }

  Future<void> clearTokens() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }

  Uri _uri(String path, [Map<String, dynamic>? query]) => Uri.parse(
        '${AppConfig.apiBaseUrl}$path',
      ).replace(
        queryParameters: query?.map((k, v) => MapEntry(k, '$v')),
      );

  // ------------------------------------------------------------------ //
  // Auth
  // ------------------------------------------------------------------ //
  Future<Map<String, dynamic>> login(String email, String password) async {
    final response = await _send(
      () => _client.post(
        _uri('/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}),
      ),
    );
    final body = _decode(response);
    await _storeTokens(body['tokens'] as Map<String, dynamic>);
    return body['user'] as Map<String, dynamic>;
  }

  Future<void> logout() async {
    final refresh = await _storage.read(key: _refreshKey);
    try {
      await _authorized(
        (headers) => _client.post(
          _uri('/auth/logout'),
          headers: headers,
          body: jsonEncode({'refresh_token': refresh}),
        ),
      );
    } on ApiException {
      // Signing out must always succeed locally, even with no connectivity.
    } finally {
      await clearTokens();
    }
  }

  /// Rotate the refresh token. Returns false when the session cannot be saved.
  Future<bool> _refreshSession() async {
    final refresh = await _storage.read(key: _refreshKey);
    if (refresh == null || refresh.isEmpty) return false;
    try {
      final response = await _client.post(
        _uri('/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': refresh}),
      );
      if (response.statusCode != 200) return false;
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      await _storeTokens(body['tokens'] as Map<String, dynamic>);
      return true;
    } catch (_) {
      return false;
    }
  }

  // ------------------------------------------------------------------ //
  // Configuration (clinical thresholds are fetched, never compiled in)
  // ------------------------------------------------------------------ //
  Future<Map<String, dynamic>> fetchConfig(String key) async {
    final response = await _authorized(
      (headers) => _client.get(_uri('/config/$key'), headers: headers),
    );
    return _decode(response)['value'] as Map<String, dynamic>;
  }

  // ------------------------------------------------------------------ //
  // Sync
  // ------------------------------------------------------------------ //
  /// Push a batch of queued changes. Idempotent server-side: replaying an
  /// already-applied item is acknowledged as a duplicate.
  Future<Map<String, dynamic>> pushSyncBatch({
    required String deviceId,
    required List<Map<String, dynamic>> items,
  }) async {
    final response = await _authorized(
      (headers) => _client.post(
        _uri('/sync/push'),
        headers: headers,
        body: jsonEncode({'device_id': deviceId, 'items': items}),
      ),
    );
    return _decode(response);
  }

  Future<Map<String, dynamic>> syncStatus(String deviceId) async {
    final response = await _authorized(
      (headers) => _client.get(_uri('/sync/status', {'device_id': deviceId}), headers: headers),
    );
    return _decode(response);
  }

  // ------------------------------------------------------------------ //
  // Internals
  // ------------------------------------------------------------------ //
  Future<http.Response> _authorized(
    Future<http.Response> Function(Map<String, String> headers) request,
  ) async {
    Future<Map<String, String>> buildHeaders() async => {
          'Content-Type': 'application/json',
          if (await accessToken case final token? when token.isNotEmpty)
            'Authorization': 'Bearer $token',
        };

    var response = await _send(() async => request(await buildHeaders()));

    if (response.statusCode == 401 && await _refreshSession()) {
      response = await _send(() async => request(await buildHeaders()));
    }
    return response;
  }

  Future<http.Response> _send(Future<http.Response> Function() request) async {
    try {
      return await request().timeout(const Duration(seconds: 30));
    } catch (_) {
      throw const ApiException(
        'You appear to be offline. Your work is saved on this device and will '
        'sync when connectivity returns.',
        code: 'network_unavailable',
      );
    }
  }

  Map<String, dynamic> _decode(http.Response response) {
    if (response.statusCode >= 400) {
      throw _errorFrom(response);
    }
    if (response.body.isEmpty) return <String, dynamic>{};
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  ApiException _errorFrom(http.Response response) {
    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final error = body['error'] as Map<String, dynamic>?;
      if (error != null) {
        return ApiException(
          error['message'] as String? ?? 'Something went wrong.',
          code: error['code'] as String? ?? 'error',
          statusCode: response.statusCode,
        );
      }
    } catch (_) {
      // Fall through to a generic, user-safe message.
    }
    return ApiException(
      'Something went wrong. Please try again.',
      statusCode: response.statusCode,
    );
  }

  void dispose() => _client.close();
}
