/// Patient registration with consent.
///
/// Consent comes first and gates everything after it — the same rule the
/// backend enforces, so the UI cannot lead a worker into a dead end.
library;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/local_store.dart';
import '../../domain/models.dart';
import '../../services/screening_controller.dart';
import '../../services/sync_service.dart';
import '../theme.dart';
import 'capture_screen.dart';

class RegisterPatientScreen extends StatefulWidget {
  const RegisterPatientScreen({super.key});

  @override
  State<RegisterPatientScreen> createState() => _RegisterPatientScreenState();
}

class _RegisterPatientScreenState extends State<RegisterPatientScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();

  bool _screeningConsent = false;
  bool _storageConsent = false;
  bool? _hasDiabetes;
  bool _saving = false;

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _saveAndStart() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (!_screeningConsent) return;

    setState(() => _saving = true);
    final store = context.read<LocalStore>();
    final controller = context.read<ScreeningController>();
    final sync = context.read<SyncService>();
    final cameras = context.read<List<CameraDescription>>();

    try {
      final localId = 'patient-${DateTime.now().microsecondsSinceEpoch}';
      final patient = Patient(
        localId: localId,
        fullName: _nameController.text.trim(),
        phone: _phoneController.text.trim().isEmpty
            ? null
            : _phoneController.text.trim(),
        hasDiabetes: _hasDiabetes,
        screeningConsent: _screeningConsent,
      );

      // Local first, queue second: the workflow continues with no connectivity.
      await store.savePatient(patient);
      await store.enqueue(
        localId: localId,
        entityType: SyncEntityType.patient,
        payload: patient.toSyncPayload(),
      );
      await sync.refreshPendingCount();

      await controller.startScreening(patient);

      if (!mounted) return;
      await Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(
          builder: (_) => CaptureScreen(
            controller: controller,
            patientName: patient.fullName,
            cameras: cameras,
          ),
        ),
      );
    } on WorkflowException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Register patient')),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(RsSpacing.md),
            children: [
              NeumorphicPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'STEP 1 · CONSENT',
                      style: TextStyle(
                        fontSize: 10,
                        letterSpacing: 1.2,
                        fontWeight: FontWeight.w700,
                        color: RsColors.inkSubtle,
                      ),
                    ),
                    const SizedBox(height: RsSpacing.sm),
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _screeningConsent,
                      onChanged: (value) =>
                          setState(() => _screeningConsent = value ?? false),
                      title: const Text('Consent to retinal screening'),
                      subtitle: const Text(
                        'The patient agrees to photographs of the back of their '
                        'eyes being taken for diabetic retinopathy screening.',
                      ),
                    ),
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _storageConsent,
                      onChanged: (value) =>
                          setState(() => _storageConsent = value ?? false),
                      title: const Text('Consent to secure data storage'),
                      subtitle: const Text(
                        'Images and results are stored securely and shared with '
                        'the reviewing clinician.',
                      ),
                    ),
                    if (!_screeningConsent)
                      const Padding(
                        padding: EdgeInsets.only(top: RsSpacing.sm),
                        child: Text(
                          'Screening consent is required before any image can be captured.',
                          style: TextStyle(color: RsColors.inkSubtle, fontSize: 13),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: RsSpacing.md),
              NeumorphicPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'STEP 2 · PATIENT DETAILS',
                      style: TextStyle(
                        fontSize: 10,
                        letterSpacing: 1.2,
                        fontWeight: FontWeight.w700,
                        color: RsColors.inkSubtle,
                      ),
                    ),
                    const SizedBox(height: RsSpacing.md),
                    TextFormField(
                      controller: _nameController,
                      decoration: const InputDecoration(labelText: 'Full name *'),
                      textCapitalization: TextCapitalization.words,
                      validator: (value) => (value == null || value.trim().isEmpty)
                          ? 'Please enter the patient name.'
                          : null,
                    ),
                    const SizedBox(height: RsSpacing.md),
                    TextFormField(
                      controller: _phoneController,
                      decoration: const InputDecoration(
                        labelText: 'Phone',
                        helperText: 'Used for follow-up reminders.',
                      ),
                      keyboardType: TextInputType.phone,
                    ),
                    const SizedBox(height: RsSpacing.md),
                    DropdownButtonFormField<bool?>(
                      initialValue: _hasDiabetes,
                      decoration:
                          const InputDecoration(labelText: 'Diagnosed with diabetes'),
                      items: const [
                        DropdownMenuItem(value: null, child: Text('Unknown')),
                        DropdownMenuItem(value: true, child: Text('Yes')),
                        DropdownMenuItem(value: false, child: Text('No')),
                      ],
                      onChanged: (value) => setState(() => _hasDiabetes = value),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: RsSpacing.lg),
              ElevatedButton(
                onPressed: _screeningConsent && !_saving ? _saveAndStart : null,
                child: Text(_saving ? 'Saving…' : 'Save and start screening'),
              ),
              const SizedBox(height: RsSpacing.sm),
              OutlinedButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cancel'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
