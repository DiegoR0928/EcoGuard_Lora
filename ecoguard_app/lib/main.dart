import 'package:flutter/material.dart';

// Importamos las pantallas
import 'pantallas/dashboard_sos.dart';
import 'pantallas/setup_BLE.dart';
import 'pantallas/mapa_offline.dart';
import 'pantallas/perfil_medico.dart';

void main() {
  runApp(const EcoGuardApp());
}

class EcoGuardApp extends StatelessWidget {
  const EcoGuardApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EcoGuard SOS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF0F172A),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF1E293B),
          elevation: 0,
        ),
        bottomNavigationBarTheme: const BottomNavigationBarThemeData(
          backgroundColor: Color(0xFF1E293B),
          selectedItemColor: Colors.blueAccent,
          unselectedItemColor: Colors.grey,
        ),
      ),
      home: const MainNavigationScreen(),
    );
  }
}

class MainNavigationScreen extends StatefulWidget {
  const MainNavigationScreen({super.key});

  @override
  State<MainNavigationScreen> createState() => _MainNavigationScreenState();
}

class _MainNavigationScreenState extends State<MainNavigationScreen> {
  int _currentIndex = 0;

  final List<Widget> _screens = [
    const DashboardSOSScreen(),
    const DeviceSetupScreen(),
    const OfflineMapsScreen(),
    const MedicalProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        type: BottomNavigationBarType.fixed,
        onTap: (index) => setState(() => _currentIndex = index),
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.emergency), label: 'S O S'),
          BottomNavigationBarItem(icon: Icon(Icons.bluetooth), label: 'Heltec'),
          BottomNavigationBarItem(icon: Icon(Icons.map), label: 'Mapas'),
          BottomNavigationBarItem(icon: Icon(Icons.medical_information), label: 'Perfil'),
        ],
      ),
    );
  }
}