/// RetinaSight AI — health-worker mobile app.
///
/// Offline-first by design: the local encrypted store is the source of truth
/// during a screening, and the sync service drains it when connectivity allows.
library;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/config.dart';
import 'data/api_client.dart';
import 'data/local_store.dart';
import 'services/screening_controller.dart';
import 'services/sync_service.dart';
import 'ui/screens/home_screen.dart';
import 'ui/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  List<CameraDescription> cameras = const [];
  try {
    cameras = await availableCameras();
  } on CameraException {
    // The app remains usable for review and sync without a camera.
    cameras = const [];
  }

  final store = await LocalStore.open();
  final api = ApiClient();
  final deviceId = AppConfig.configuredDeviceId.isNotEmpty
      ? AppConfig.configuredDeviceId
      : 'device-${DateTime.now().millisecondsSinceEpoch}';

  final sync = SyncService(store: store, api: api, deviceId: deviceId);
  await sync.start();

  runApp(
    RetinaSightApp(store: store, api: api, sync: sync, cameras: cameras),
  );
}

class RetinaSightApp extends StatelessWidget {
  const RetinaSightApp({
    super.key,
    required this.store,
    required this.api,
    required this.sync,
    required this.cameras,
  });

  final LocalStore store;
  final ApiClient api;
  final SyncService sync;
  final List<CameraDescription> cameras;

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<LocalStore>.value(value: store),
        Provider<ApiClient>.value(value: api),
        Provider<List<CameraDescription>>.value(value: cameras),
        ChangeNotifierProvider<SyncService>.value(value: sync),
        ChangeNotifierProvider<ScreeningController>(
          create: (_) => ScreeningController(store: store),
        ),
      ],
      child: MaterialApp(
        title: 'RetinaSight AI',
        theme: buildRetinaSightTheme(),
        debugShowCheckedModeBanner: false,
        home: const HomeScreen(),
      ),
    );
  }
}
