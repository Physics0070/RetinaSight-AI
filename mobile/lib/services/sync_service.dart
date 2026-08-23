/// Background synchronisation.
///
/// Watches connectivity and drains the local queue whenever the device is
/// online. Design rules:
///
///  * Every item carries a client-generated `local_id`; the server treats
///    (local_id, entity_type) as unique, so a retried batch updates rather than
///    duplicating a clinical record.
///  * Items are ordered patient → session → image, because each depends on the
///    server id of the one before it.
///  * A single bad item never blocks the queue; it is parked with its reason
///    after a bounded number of attempts.
///  * Nothing is deleted locally on success — the device keeps its copy until
///    the record is confirmed stored.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import '../core/config.dart';
import '../data/api_client.dart';
import '../data/local_store.dart';
import '../domain/models.dart';

class SyncOutcome {
  const SyncOutcome({
    this.accepted = 0,
    this.duplicates = 0,
    this.failed = 0,
    this.skippedOffline = false,
    this.message,
  });

  final int accepted;
  final int duplicates;
  final int failed;
  final bool skippedOffline;
  final String? message;

  bool get didWork => accepted > 0 || duplicates > 0 || failed > 0;
}

class SyncService extends ChangeNotifier {
  SyncService({
    required LocalStore store,
    required ApiClient api,
    required this.deviceId,
    Connectivity? connectivity,
  })  : _store = store,
        _api = api,
        _connectivity = connectivity ?? Connectivity();

  final LocalStore _store;
  final ApiClient _api;
  final Connectivity _connectivity;
  final String deviceId;

  StreamSubscription<List<ConnectivityResult>>? _subscription;
  Timer? _timer;

  bool _online = true;
  bool _syncing = false;
  int _pending = 0;
  String? _lastError;

  bool get isOnline => _online;
  bool get isSyncing => _syncing;
  int get pendingCount => _pending;
  String? get lastError => _lastError;

  /// Begin watching connectivity and start the periodic drain.
  Future<void> start() async {
    _online = _isOnline(await _connectivity.checkConnectivity());
    await refreshPendingCount();

    _subscription = _connectivity.onConnectivityChanged.listen((results) {
      final wasOffline = !_online;
      _online = _isOnline(results);
      notifyListeners();
      // Reconnecting is the moment that matters — drain immediately.
      if (wasOffline && _online) unawaited(syncNow());
    });

    _timer = Timer.periodic(AppConfig.syncInterval, (_) {
      if (_online && !_syncing) unawaited(syncNow());
    });

    if (_online) unawaited(syncNow());
  }

  bool _isOnline(List<ConnectivityResult> results) =>
      results.any((r) => r != ConnectivityResult.none);

  Future<void> refreshPendingCount() async {
    _pending = await _store.pendingCount();
    notifyListeners();
  }

  /// Drain the queue once. Safe to call concurrently — overlapping calls
  /// return immediately rather than double-sending.
  Future<SyncOutcome> syncNow() async {
    if (_syncing) return const SyncOutcome();
    if (!_online) {
      return const SyncOutcome(
        skippedOffline: true,
        message: 'Offline — items stay queued on this device.',
      );
    }

    _syncing = true;
    _lastError = null;
    notifyListeners();

    var accepted = 0;
    var duplicates = 0;
    var failed = 0;

    try {
      final queued = await _store.pendingSyncItems();
      if (queued.isEmpty) {
        return const SyncOutcome();
      }

      for (final item in _ordered(queued)) {
        if (item.attemptCount >= AppConfig.maxSyncAttempts &&
            item.status == SyncStatus.failed) {
          // Parked for manual attention; do not spin on it forever.
          continue;
        }

        try {
          final payload = await _preparePayload(item);
          final result = await _api.pushSyncBatch(
            deviceId: deviceId,
            items: [
              {
                'local_id': item.localId,
                'entity_type': item.entityType.value,
                'operation': 'create',
                'payload': payload,
              }
            ],
          );

          final results = (result['items'] as List?) ?? const [];
          final first = results.isEmpty ? null : results.first as Map<String, dynamic>;
          final status = first?['status'] as String?;
          final serverId = first?['server_id'] as String?;

          if (status == 'synced' || status == 'duplicate') {
            if (status == 'synced') {
              accepted++;
            } else {
              duplicates++;
            }
            await _store.markSyncResult(
              localId: item.localId,
              entityType: item.entityType,
              status: SyncStatus.synced,
              serverId: serverId,
            );
            if (item.entityType == SyncEntityType.screeningSession &&
                serverId != null) {
              await _store.markSessionSynced(item.localId, serverId);
            }
          } else {
            failed++;
            await _store.markSyncResult(
              localId: item.localId,
              entityType: item.entityType,
              status: SyncStatus.failed,
              error: first?['error'] as String? ?? 'This item could not be synchronised.',
            );
          }
        } on ApiException catch (error) {
          if (error.isOffline) {
            _online = false;
            await _store.markSyncResult(
              localId: item.localId,
              entityType: item.entityType,
              status: SyncStatus.retrying,
              error: null,
            );
            break; // Connection lost mid-drain; resume on reconnect.
          }
          failed++;
          await _store.markSyncResult(
            localId: item.localId,
            entityType: item.entityType,
            status: SyncStatus.failed,
            error: error.message,
          );
        }
      }
    } finally {
      _syncing = false;
      await refreshPendingCount();
      notifyListeners();
    }

    if (failed > 0) {
      _lastError = '$failed item${failed == 1 ? '' : 's'} could not be synchronised.';
    }

    return SyncOutcome(accepted: accepted, duplicates: duplicates, failed: failed);
  }

  /// Patients before sessions before images: each needs the previous one's
  /// server id to exist.
  List<SyncQueueItem> _ordered(List<SyncQueueItem> items) {
    int rank(SyncEntityType type) => switch (type) {
          SyncEntityType.patient => 0,
          SyncEntityType.screeningSession => 1,
          SyncEntityType.retinalImage => 2,
        };
    final sorted = [...items]..sort((a, b) => rank(a.entityType).compareTo(rank(b.entityType)));
    return sorted;
  }

  /// Image bytes are read at send time rather than held in the queue row, so
  /// the database stays small and the file remains the single copy.
  Future<Map<String, dynamic>> _preparePayload(SyncQueueItem item) async {
    if (item.entityType != SyncEntityType.retinalImage) return item.payload;

    final path = item.payload['file_path'] as String?;
    if (path == null) return item.payload;

    final file = File(path);
    if (!file.existsSync()) {
      throw const ApiException('The captured image is no longer on this device.');
    }

    final bytes = await file.readAsBytes();
    return {
      ...item.payload,
      'content_base64': base64Encode(bytes),
    }..remove('file_path');
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _timer?.cancel();
    super.dispose();
  }
}
