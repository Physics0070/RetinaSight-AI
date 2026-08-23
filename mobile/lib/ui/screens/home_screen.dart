/// Health-worker home: today's work, connectivity state and the sync queue.
///
/// The primary action dominates; everything else answers "what still needs
/// doing?".
library;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/local_store.dart';
import '../../domain/models.dart';
import '../../services/screening_controller.dart';
import '../../services/sync_service.dart';
import '../theme.dart';
import '../widgets/capture_reticle.dart';
import 'capture_screen.dart';
import 'register_patient_screen.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final sync = context.watch<SyncService>();
    final store = context.read<LocalStore>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('RetinaSight AI'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: RsSpacing.md),
            child: Center(child: _ConnectivityPill(online: sync.isOnline)),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (!sync.isOnline) OfflineBanner(pending: sync.pendingCount),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(RsSpacing.md),
                children: [
                  NeumorphicPanel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Start a new screening',
                          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: RsSpacing.xs),
                        const Text(
                          'Register the patient, record consent, then capture both eyes.',
                          style: TextStyle(color: RsColors.inkMuted),
                        ),
                        const SizedBox(height: RsSpacing.md),
                        ElevatedButton(
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => const RegisterPatientScreen(),
                            ),
                          ),
                          child: const Text('New screening'),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: RsSpacing.md),
                  _SyncSummary(sync: sync),
                  const SizedBox(height: RsSpacing.md),
                  _PatientList(store: store),
                  const SizedBox(height: RsSpacing.md),
                  const AiAssistanceNotice(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Offline is a normal operating mode — say what happens next, never just
/// "Network Error".
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key, required this.pending});

  final int pending;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(RsSpacing.md),
      color: RsColors.warn.withValues(alpha: 0.12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'OFFLINE MODE',
            style: TextStyle(
              color: RsColors.warn,
              fontWeight: FontWeight.w800,
              fontSize: 12,
              letterSpacing: 1.1,
            ),
          ),
          const SizedBox(height: RsSpacing.xs),
          const Text(
            'RetinaSight AI is continuing offline. Your screening data is stored '
            'securely on this device and will synchronise when connectivity returns.',
            style: TextStyle(color: RsColors.inkMuted, height: 1.35),
          ),
          if (pending > 0) ...[
            const SizedBox(height: RsSpacing.xs),
            Text(
              '$pending item${pending == 1 ? '' : 's'} waiting to sync.',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ],
        ],
      ),
    );
  }
}

class _ConnectivityPill extends StatelessWidget {
  const _ConnectivityPill({required this.online});

  final bool online;

  @override
  Widget build(BuildContext context) {
    final color = online ? RsColors.ok : RsColors.warn;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(online ? Icons.circle : Icons.circle_outlined, size: 10, color: color),
        const SizedBox(width: 6),
        Text(
          online ? 'ONLINE' : 'OFFLINE',
          style: TextStyle(
            color: color,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.9,
          ),
        ),
      ],
    );
  }
}

class _SyncSummary extends StatelessWidget {
  const _SyncSummary({required this.sync});

  final SyncService sync;

  @override
  Widget build(BuildContext context) {
    return NeumorphicPanel(
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'SYNC QUEUE',
                  style: TextStyle(
                    fontSize: 10,
                    letterSpacing: 1.2,
                    fontWeight: FontWeight.w700,
                    color: RsColors.inkSubtle,
                  ),
                ),
                const SizedBox(height: RsSpacing.xs),
                Text(
                  sync.pendingCount == 0
                      ? 'Everything is synchronised'
                      : '${sync.pendingCount} waiting to sync',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                ),
                if (sync.lastError != null) ...[
                  const SizedBox(height: RsSpacing.xs),
                  Text(
                    sync.lastError!,
                    style: const TextStyle(color: RsColors.danger, fontSize: 13),
                  ),
                ],
              ],
            ),
          ),
          OutlinedButton(
            onPressed: sync.isSyncing ? null : () => sync.syncNow(),
            child: Text(sync.isSyncing ? 'Syncing…' : 'Sync now'),
          ),
        ],
      ),
    );
  }
}

class _PatientList extends StatelessWidget {
  const _PatientList({required this.store});

  final LocalStore store;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Patient>>(
      future: store.listPatients(),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: Padding(
            padding: EdgeInsets.all(RsSpacing.lg),
            child: CircularProgressIndicator(),
          ));
        }

        final patients = snapshot.data ?? const <Patient>[];
        if (patients.isEmpty) {
          return const NeumorphicPanel(
            child: Text(
              'No patients registered on this device yet.',
              style: TextStyle(color: RsColors.inkMuted),
            ),
          );
        }

        return NeumorphicPanel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'PATIENTS ON THIS DEVICE',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.2,
                  fontWeight: FontWeight.w700,
                  color: RsColors.inkSubtle,
                ),
              ),
              const SizedBox(height: RsSpacing.sm),
              for (final patient in patients.take(10))
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(patient.fullName),
                  subtitle: Text(patient.patientCode ?? 'Not yet synced'),
                  trailing: TextButton(
                    onPressed: () => _startScreening(context, patient),
                    child: const Text('Screen'),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _startScreening(BuildContext context, Patient patient) async {
    final controller = context.read<ScreeningController>();
    final cameras = context.read<List<CameraDescription>>();

    try {
      await controller.startScreening(patient);
      if (!context.mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => CaptureScreen(
            controller: controller,
            patientName: patient.fullName,
            cameras: cameras,
          ),
        ),
      );
    } on WorkflowException catch (error) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.message)));
    }
  }
}
