import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

class DashboardSOSScreen extends StatefulWidget {
  const DashboardSOSScreen({super.key});

  @override
  State<DashboardSOSScreen> createState() => _DashboardSOSScreenState();
}

class _DashboardSOSScreenState extends State<DashboardSOSScreen> {
  bool isConnected = true; 
  String sosState = "IDLE"; 
  final LatLng myLocation = const LatLng(22.7709, -102.5832); 

  void triggerSOS() {
    setState(() => sosState = "SENDING");
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted) setState(() => sosState = "CONFIRMED");
    });
  }

  void cancelSOS() {
    setState(() => sosState = "IDLE");
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("EcoGuard SOS", style: TextStyle(fontWeight: FontWeight.bold)),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16.0),
            child: Icon(
              isConnected ? Icons.bluetooth_connected : Icons.bluetooth_disabled,
              color: isConnected ? Colors.blueAccent : Colors.grey,
            ),
          )
        ],
      ),
      body: Column(
        children: [
          Expanded(
            flex: 4,
            child: Container(
              margin: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF334155), width: 2),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(14),
                child: FlutterMap(
                  options: MapOptions(initialCenter: myLocation, initialZoom: 14.0),
                  children: [
                    TileLayer(urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'),
                    MarkerLayer(
                      markers: [
                        Marker(
                          point: myLocation,
                          width: 60, height: 60,
                          child: const Icon(Icons.my_location, color: Colors.blueAccent, size: 40),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
          Expanded(
            flex: 3,
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: const BoxDecoration(
                color: Color(0xFF1E293B),
                borderRadius: BorderRadius.only(topLeft: Radius.circular(30), topRight: Radius.circular(30)),
              ),
              child: sosState == "IDLE" 
                  ? _buildSOSButton() 
                  : _buildRescueStatus(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSOSButton() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        GestureDetector(
          onTap: triggerSOS,
          child: Container(
            width: 150, height: 150,
            decoration: BoxDecoration(
              color: Colors.red[700],
              shape: BoxShape.circle,
              boxShadow: [BoxShadow(color: Colors.red.withValues(alpha: 0.5), blurRadius: 30, spreadRadius: 10)],
            ),
            child: const Center(
              child: Text("S O S", style: TextStyle(fontSize: 36, fontWeight: FontWeight.bold, color: Colors.white, letterSpacing: 4)),
            ),
          ),
        ),
        const SizedBox(height: 20),
        const Text("Presiona para alertar a los guardabosques", style: TextStyle(color: Colors.grey)),
      ],
    );
  }

  Widget _buildRescueStatus() {
    bool isConfirmed = sosState == "CONFIRMED";
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          isConfirmed ? Icons.check_circle_outline : Icons.sensors,
          color: isConfirmed ? Colors.greenAccent : Colors.orangeAccent,
          size: 60,
        ),
        const SizedBox(height: 16),
        Text(
          isConfirmed ? "RESCATE EN CAMINO" : "ENVIANDO POR LORA...",
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: isConfirmed ? Colors.greenAccent : Colors.orangeAccent),
        ),
        const SizedBox(height: 10),
        Text(
          isConfirmed 
            ? "El Gateway ha confirmado tu señal. No te muevas de tu posición actual. ETA: 45 min." 
            : "Transmitiendo alerta por radiofrecuencia a 915 MHz...",
          textAlign: TextAlign.center,
          style: const TextStyle(color: Colors.white70),
        ),
        const Spacer(),
        TextButton(
          onPressed: cancelSOS,
          child: const Text("Cancelar Alerta", style: TextStyle(color: Colors.redAccent)),
        )
      ],
    );
  }
}