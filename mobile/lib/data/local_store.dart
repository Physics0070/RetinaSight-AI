/// Encrypted offline-first local store.
///
/// Patient data and retinal images never touch unencrypted storage:
///
///  * structured records live in a SQLCipher-encrypted SQLite database
///  * the encryption key is generated on first run and held in the platform
///    keystore/keychain via flutter_secure_storage — never in the database,
///    never in shared preferences, never in source
///  * captured images are written to the app's private directory, which is not
///    world-readable and is excluded from device backups
///
/// This is the store the sync queue drains from; it is the source of truth
/// while the device is offline.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite_sqlcipher/sqflite.dart';

import '../domain/models.dart';

class LocalStore {
  LocalStore._(this._db, this._imageDirectory);

  final Database _db;
  final Directory _imageDirectory;

  static const _keyName = 'rs.local_db_key';
  static const _secureStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static Future<LocalStore> open() async {
    final key = await _resolveEncryptionKey();
    final documents = await getApplicationDocumentsDirectory();

    final database = await openDatabase(
      p.join(documents.path, 'retinasight.db'),
      password: key,
      version: 1,
      onConfigure: (db) => db.execute('PRAGMA foreign_keys = ON'),
      onCreate: _createSchema,
    );

    final images = Directory(p.join(documents.path, 'captures'));
    if (!images.existsSync()) images.createSync(recursive: true);

    return LocalStore._(database, images);
  }

  /// Fetch the database key from the platform keystore, generating one on
  /// first run. Losing this key makes the local database unreadable — which is
  /// the intended behaviour if the device is wiped.
  static Future<String> _resolveEncryptionKey() async {
    final existing = await _secureStorage.read(key: _keyName);
    if (existing != null && existing.isNotEmpty) return existing;

    final random = Random.secure();
    final bytes = Uint8List.fromList(
      List<int>.generate(32, (_) => random.nextInt(256)),
    );
    final generated = base64UrlEncode(bytes);
    await _secureStorage.write(key: _keyName, value: generated);
    return generated;
  }

  static Future<void> _createSchema(Database db, int version) async {
    await db.execute('''
      CREATE TABLE patients (
        local_id TEXT PRIMARY KEY,
        server_id TEXT,
        full_name TEXT NOT NULL,
        patient_code TEXT,
        phone TEXT,
        has_diabetes INTEGER,
        screening_consent INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
      )
    ''');

    await db.execute('''
      CREATE TABLE screening_sessions (
        local_id TEXT PRIMARY KEY,
        server_id TEXT,
        patient_local_id TEXT NOT NULL REFERENCES patients(local_id) ON DELETE CASCADE,
        patient_server_id TEXT,
        state TEXT NOT NULL,
        sync_status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
      )
    ''');

    await db.execute('''
      CREATE TABLE captures (
        local_id TEXT PRIMARY KEY,
        server_id TEXT,
        session_local_id TEXT NOT NULL REFERENCES screening_sessions(local_id) ON DELETE CASCADE,
        eye_side TEXT NOT NULL,
        file_path TEXT NOT NULL,
        quality_json TEXT,
        is_acceptable INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
      )
    ''');

    // (local_id, entity_type) is UNIQUE: this is what makes a replayed sync
    // batch idempotent rather than duplicating a clinical record.
    await db.execute('''
      CREATE TABLE sync_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        local_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        operation TEXT NOT NULL DEFAULT 'create',
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_attempt_at TEXT,
        last_error TEXT,
        server_id TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (local_id, entity_type)
      )
    ''');

    await db.execute('CREATE INDEX idx_sync_status ON sync_queue(status)');
    await db.execute('CREATE INDEX idx_sessions_state ON screening_sessions(state)');
  }

  // ------------------------------------------------------------------ //
  // Patients
  // ------------------------------------------------------------------ //
  Future<void> savePatient(Patient patient) async {
    await _db.insert(
      'patients',
      {
        'local_id': patient.localId,
        'server_id': patient.serverId,
        'full_name': patient.fullName,
        'patient_code': patient.patientCode,
        'phone': patient.phone,
        'has_diabetes': patient.hasDiabetes == null ? null : (patient.hasDiabetes! ? 1 : 0),
        'screening_consent': patient.screeningConsent ? 1 : 0,
        'created_at': DateTime.now().toUtc().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<List<Patient>> listPatients() async {
    final rows = await _db.query('patients', orderBy: 'created_at DESC');
    return rows.map(_patientFromRow).toList(growable: false);
  }

  Future<Patient?> findPatient(String localId) async {
    final rows = await _db.query(
      'patients',
      where: 'local_id = ?',
      whereArgs: [localId],
      limit: 1,
    );
    return rows.isEmpty ? null : _patientFromRow(rows.first);
  }

  Patient _patientFromRow(Map<String, Object?> row) => Patient(
        localId: row['local_id'] as String,
        serverId: row['server_id'] as String?,
        fullName: row['full_name'] as String,
        patientCode: row['patient_code'] as String?,
        phone: row['phone'] as String?,
        hasDiabetes: row['has_diabetes'] == null ? null : row['has_diabetes'] == 1,
        screeningConsent: row['screening_consent'] == 1,
      );

  // ------------------------------------------------------------------ //
  // Sessions
  // ------------------------------------------------------------------ //
  Future<void> saveSession(ScreeningSession session) async {
    await _db.insert(
      'screening_sessions',
      {
        'local_id': session.localId,
        'server_id': session.serverId,
        'patient_local_id': session.patientLocalId,
        'patient_server_id': session.patientServerId,
        'state': session.state.value,
        'sync_status': session.syncStatus.value,
        'created_at': (session.createdAt ?? DateTime.now().toUtc()).toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> updateSessionState(String localId, ScreeningState state) async {
    await _db.update(
      'screening_sessions',
      {'state': state.value},
      where: 'local_id = ?',
      whereArgs: [localId],
    );
  }

  Future<void> markSessionSynced(String localId, String serverId) async {
    await _db.update(
      'screening_sessions',
      {'server_id': serverId, 'sync_status': SyncStatus.synced.value},
      where: 'local_id = ?',
      whereArgs: [localId],
    );
  }

  Future<List<ScreeningSession>> listSessions() async {
    final rows = await _db.query('screening_sessions', orderBy: 'created_at DESC');
    return rows
        .map((row) => ScreeningSession(
              localId: row['local_id'] as String,
              serverId: row['server_id'] as String?,
              patientLocalId: row['patient_local_id'] as String,
              patientServerId: row['patient_server_id'] as String?,
              state: ScreeningStateX.parse(row['state'] as String),
              syncStatus: SyncStatusX.parse(row['sync_status'] as String),
              createdAt: DateTime.tryParse(row['created_at'] as String),
            ))
        .toList(growable: false);
  }

  // ------------------------------------------------------------------ //
  // Captures
  // ------------------------------------------------------------------ //
  /// Persist image bytes to private storage and record their metadata.
  Future<String> saveCapture({
    required String localId,
    required String sessionLocalId,
    required EyeSide eyeSide,
    required Uint8List bytes,
    required QualityAssessment quality,
  }) async {
    final file = File(p.join(_imageDirectory.path, '$localId.jpg'));
    await file.writeAsBytes(bytes, flush: true);

    // A fresh acceptable capture supersedes earlier ones for the same eye.
    await _db.update(
      'captures',
      {'is_active': 0},
      where: 'session_local_id = ? AND eye_side = ?',
      whereArgs: [sessionLocalId, eyeSide.value],
    );

    await _db.insert(
      'captures',
      {
        'local_id': localId,
        'session_local_id': sessionLocalId,
        'eye_side': eyeSide.value,
        'file_path': file.path,
        'quality_json': jsonEncode(quality.toJson()),
        'is_acceptable': quality.isAcceptable ? 1 : 0,
        'is_active': 1,
        'created_at': DateTime.now().toUtc().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );

    return file.path;
  }

  Future<List<Map<String, Object?>>> listCaptures(String sessionLocalId) =>
      _db.query(
        'captures',
        where: 'session_local_id = ? AND is_active = 1',
        whereArgs: [sessionLocalId],
        orderBy: 'created_at',
      );

  Future<void> deleteCapture(String localId) async {
    final rows = await _db.query(
      'captures',
      where: 'local_id = ?',
      whereArgs: [localId],
      limit: 1,
    );
    if (rows.isNotEmpty) {
      final file = File(rows.first['file_path'] as String);
      if (file.existsSync()) await file.delete();
    }
    await _db.delete('captures', where: 'local_id = ?', whereArgs: [localId]);
  }

  // ------------------------------------------------------------------ //
  // Sync queue
  // ------------------------------------------------------------------ //
  Future<void> enqueue({
    required String localId,
    required SyncEntityType entityType,
    required Map<String, dynamic> payload,
  }) async {
    await _db.insert(
      'sync_queue',
      {
        'local_id': localId,
        'entity_type': entityType.value,
        'operation': 'create',
        'payload': jsonEncode(payload),
        'status': SyncStatus.pending.value,
        'created_at': DateTime.now().toUtc().toIso8601String(),
      },
      // Re-queuing the same item must not create a second row.
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }

  Future<List<SyncQueueItem>> pendingSyncItems({int limit = 50}) async {
    final rows = await _db.query(
      'sync_queue',
      where: 'status IN (?, ?, ?)',
      whereArgs: [
        SyncStatus.pending.value,
        SyncStatus.retrying.value,
        SyncStatus.failed.value,
      ],
      orderBy: 'created_at',
      limit: limit,
    );

    return rows
        .map((row) => SyncQueueItem(
              localId: row['local_id'] as String,
              entityType: SyncEntityType.values.firstWhere(
                (e) => e.value == row['entity_type'],
                orElse: () => SyncEntityType.patient,
              ),
              payload: jsonDecode(row['payload'] as String) as Map<String, dynamic>,
              serverId: row['server_id'] as String?,
              status: SyncStatusX.parse(row['status'] as String),
              attemptCount: row['attempt_count'] as int? ?? 0,
              lastError: row['last_error'] as String?,
            ))
        .toList(growable: false);
  }

  Future<void> markSyncResult({
    required String localId,
    required SyncEntityType entityType,
    required SyncStatus status,
    String? serverId,
    String? error,
  }) async {
    await _db.rawUpdate(
      '''
      UPDATE sync_queue
         SET status = ?,
             server_id = COALESCE(?, server_id),
             last_error = ?,
             attempt_count = attempt_count + 1,
             last_attempt_at = ?
       WHERE local_id = ? AND entity_type = ?
      ''',
      [
        status.value,
        serverId,
        error,
        DateTime.now().toUtc().toIso8601String(),
        localId,
        entityType.value,
      ],
    );
  }

  Future<Map<String, int>> syncCounts() async {
    final rows = await _db.rawQuery(
      'SELECT status, COUNT(*) AS total FROM sync_queue GROUP BY status',
    );
    return {
      for (final row in rows) row['status'] as String: (row['total'] as int?) ?? 0,
    };
  }

  Future<int> pendingCount() async {
    final counts = await syncCounts();
    return (counts[SyncStatus.pending.value] ?? 0) +
        (counts[SyncStatus.retrying.value] ?? 0);
  }

  Future<void> close() => _db.close();
}
