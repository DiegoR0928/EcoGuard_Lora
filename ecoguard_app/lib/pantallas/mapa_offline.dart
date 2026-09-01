import 'package:flutter/material.dart';

class OfflineMapsScreen extends StatelessWidget {
  const OfflineMapsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Mapas Offline")),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text("Descargados", style: TextStyle(color: Colors.grey, fontWeight: FontWeight.bold)),
          _buildMapCard("Cerro de la Bufa", "Zacatecas, Zac.", "12.4 MB", true),
          const SizedBox(height: 20),
          const Text("Disponibles para descargar", style: TextStyle(color: Colors.grey, fontWeight: FontWeight.bold)),
          _buildMapCard("Sierra de Órganos", "Sombrerete, Zac.", "45.1 MB", false),
          _buildMapCard("Parque Nacional Los Dinamos", "CDMX", "89.2 MB", false),
        ],
      ),
    );
  }

  Widget _buildMapCard(String title, String subtitle, String size, bool isDownloaded) {
    return Card(
      color: const Color(0xFF1E293B),
      margin: const EdgeInsets.symmetric(vertical: 8),
      child: ListTile(
        leading: Icon(
          isDownloaded ? Icons.map : Icons.cloud_download, 
          color: isDownloaded ? Colors.greenAccent : Colors.grey
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text("$subtitle • $size"),
        trailing: isDownloaded 
          ? IconButton(icon: const Icon(Icons.delete, color: Colors.redAccent), onPressed: (){})
          : IconButton(icon: const Icon(Icons.download), onPressed: (){}),
      ),
    );
  }
}