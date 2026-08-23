/// Screening state machine and workflow guards on the device.
///
/// The transition table here must stay in step with the server's
/// (backend/app/services/screening_state_machine.py) — these tests pin the
/// invariants that matter clinically.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:retinasight/domain/models.dart';
import 'package:retinasight/services/screening_controller.dart';

void main() {
  group('state machine', () {
    test('the happy path is legal end to end', () {
      const path = [
        ScreeningState.idle,
        ScreeningState.patientSelected,
        ScreeningState.captureLeftEye,
        ScreeningState.qualityCheck,
        ScreeningState.readyForInference,
        ScreeningState.inferenceRunning,
        ScreeningState.resultAvailable,
        ScreeningState.referralPending,
        ScreeningState.referralCreated,
        ScreeningState.doctorReview,
        ScreeningState.followUp,
        ScreeningState.completed,
      ];

      for (var i = 0; i < path.length - 1; i++) {
        expect(
          canTransition(path[i], path[i + 1]),
          isTrue,
          reason: '${path[i].value} -> ${path[i + 1].value} should be legal',
        );
      }
    });

    test('screening cannot start before an image exists', () {
      expect(canTransition(ScreeningState.idle, ScreeningState.inferenceRunning), isFalse);
      expect(
        canTransition(ScreeningState.patientSelected, ScreeningState.resultAvailable),
        isFalse,
      );
    });

    test('a failed quality check routes to retake', () {
      expect(
        canTransition(ScreeningState.qualityCheck, ScreeningState.retakeRequired),
        isTrue,
      );
      expect(
        canTransition(ScreeningState.retakeRequired, ScreeningState.captureLeftEye),
        isTrue,
      );
    });

    test('single-eye screening is permitted', () {
      expect(
        canTransition(ScreeningState.captureLeftEye, ScreeningState.readyForInference),
        isTrue,
      );
    });

    test('terminal states are truly terminal', () {
      expect(kTransitions[ScreeningState.completed], isEmpty);
      expect(kTransitions[ScreeningState.cancelled], isEmpty);
      expect(ScreeningState.completed.isTerminal, isTrue);
      expect(ScreeningState.cancelled.isTerminal, isTrue);
    });

    test('no open state traps the user', () {
      for (final entry in kTransitions.entries) {
        if (entry.key.isTerminal) continue;
        final hasExit = entry.value.contains(ScreeningState.cancelled) ||
            entry.value.contains(ScreeningState.completed);
        expect(hasExit, isTrue, reason: '${entry.key.value} offers no way out');
      }
    });

    test('an error state is recoverable', () {
      expect(canTransition(ScreeningState.error, ScreeningState.captureLeftEye), isTrue);
      expect(canTransition(ScreeningState.error, ScreeningState.cancelled), isTrue);
    });
  });

  group('domain vocabulary', () {
    test('screening states round-trip through their wire values', () {
      for (final state in ScreeningState.values) {
        expect(ScreeningStateX.parse(state.value), state);
      }
    });

    test('an unknown state degrades to idle rather than crashing', () {
      expect(ScreeningStateX.parse('not_a_real_state'), ScreeningState.idle);
    });

    test('the grading scale has exactly five classes', () {
      expect(ScreeningCategory.values.length, 5);
      expect(
        ScreeningCategory.values.map((c) => c.value).toList(),
        ['no_dr', 'mild', 'moderate', 'severe', 'proliferative'],
      );
    });

    test('every risk level has a distinct glyph so colour is never alone', () {
      final glyphs = RiskLevel.values.map((r) => r.glyph).toSet();
      expect(glyphs.length, RiskLevel.values.length);
      for (final level in RiskLevel.values) {
        expect(level.label, isNotEmpty);
      }
    });

    test('eye sides carry clinical laterality labels', () {
      expect(EyeSide.left.label, contains('OS'));
      expect(EyeSide.right.label, contains('OD'));
    });
  });

  group('sync payloads', () {
    test('a patient payload carries consent', () {
      const patient = Patient(
        localId: 'p1',
        fullName: 'Test Patient',
        screeningConsent: true,
      );

      final payload = patient.toSyncPayload();

      expect(payload['full_name'], 'Test Patient');
      expect((payload['consents'] as Map)['screening'], isTrue);
    });

    test('sync entity types use the server wire format', () {
      expect(SyncEntityType.screeningSession.value, 'screening_session');
      expect(SyncEntityType.retinalImage.value, 'retinal_image');
      expect(SyncEntityType.patient.value, 'patient');
    });
  });
}
