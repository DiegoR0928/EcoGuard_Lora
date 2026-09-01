import 'package:flutter/material.dart';

class DeviceSetupScreen extends StatelessWidget {
  const DeviceSetupScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Tu Dispositivo Heltec")),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.developer_board, size: 100, color: Colors.blueAccent),
            const SizedBox(height: 20),
            const Text("Heltec V4 - EcoGuard", style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            const Text("Estado: Conectado", style: TextStyle(color: Colors.greenAccent)),
            const SizedBox(height: 40),
            
            _buildDeviceStatRow(Icons.battery_charging_full, "Batería del Nodo", "92%"),
            _buildDeviceStatRow(Icons.cell_tower, "Potencia Transmisión", "22 dBm"),
            
            const SizedBox(height: 50),
            ElevatedButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.volume_up),
              label: const Text("Hacer sonar dispositivo"),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF334155), 
                padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 15)
              ),
            )
          ],
        ),
      ),
    );
  }

  Widget _buildDeviceStatRow(IconData icon, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Icon(icon, color: Colors.grey), 
              const SizedBox(width: 10), 
              Text(label, style: const TextStyle(color: Colors.white70))
            ]
          ),
          Text(value, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
        ],
      ),
    );
  }
}