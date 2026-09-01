import 'package:flutter/material.dart';

class MedicalProfileScreen extends StatelessWidget {
  const MedicalProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Ficha Médica de Rescate")),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              "Esta información será transmitida automáticamente a los rescatistas al presionar SOS.", 
              style: TextStyle(color: Colors.grey)
            ),
            const SizedBox(height: 30),
            
            _buildTextField("Nombre Completo", "Ej. Diego Ricardo Gómez"),
            const SizedBox(height: 20),
            _buildTextField("Tipo de Sangre", "Ej. O+"),
            const SizedBox(height: 20),
            _buildTextField("Alergias Médicas", "Ej. Penicilina, Abejas"),
            const SizedBox(height: 20),
            _buildTextField("Contacto de Emergencia", "Teléfono de un familiar"),
            
            const SizedBox(height: 40),
            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton(
                onPressed: () {},
                style: ElevatedButton.styleFrom(backgroundColor: Colors.blueAccent),
                child: const Text("Guardar Perfil", style: TextStyle(fontSize: 18, color: Colors.white, fontWeight: FontWeight.bold)),
              ),
            )
          ],
        ),
      ),
    );
  }

  Widget _buildTextField(String label, String hint) {
    return TextField(
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        filled: true,
        fillColor: const Color(0xFF1E293B),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10), 
          borderSide: BorderSide.none
        ),
      ),
    );
  }
}