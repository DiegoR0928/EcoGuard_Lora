import 'package:flutter/material.dart';
import 'dart:ui';

void main() {
  runApp(const EcoGuardApp());
}

class EcoGuardApp extends StatelessWidget {
  const EcoGuardApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EcoGuard Visitante',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0F172A), // Slate 900
        fontFamily: 'Segoe UI',
      ),
      home: const PantallaVisitante(),
    );
  }
}

class PantallaVisitante extends StatefulWidget {
  const PantallaVisitante({super.key});

  @override
  State<PantallaVisitante> createState() => _PantallaVisitanteState();
}

class _PantallaVisitanteState extends State<PantallaVisitante> with SingleTickerProviderStateMixin {
  bool nodoConectado = false;
  bool isSosActive = false;
  int bateriaNodo = 85; // Cambia este valor a 15 para probar la alerta de batería baja

  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    // Animación continua para el botón SOS
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    
    _pulseAnimation = Tween<double>(begin: 1.0, end: 1.15).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  // CU-09: Emparejar nodo
  void _buscarNodos() {
    setState(() {
      nodoConectado = true;
    });
  }

  // CU-11: Emitir alerta crítica
  void _emitirAlerta() {
    setState(() { 
      isSosActive = true; 
    });
    
    // Mensaje exacto según SRS (CU-11)
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Row(
          children: [
            Icon(Icons.check_circle, color: Colors.white),
            SizedBox(width: 10),
            Text("¡Alerta enviada exitosamente!", style: TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
        backgroundColor: Colors.green[700],
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  // CU-12: Cancelar falsa alarma
  void _cancelarAlerta() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1E293B),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text("¿Desea cancelar el rescate?", style: TextStyle(color: Colors.white)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context), // FA1 de CU-12: "Regresar" sin confirmar
            child: const Text("Regresar", style: TextStyle(color: Colors.grey)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.orange[700],
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
            onPressed: () {
              setState(() { isSosActive = false; });
              Navigator.pop(context); // Confirma y regresa
            },
            child: const Text("Confirmar", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: isSosActive 
                ? [const Color(0xFF450A0A), const Color(0xFF0F172A)] // Rojo de emergencia
                : [const Color(0xFF064E3B), const Color(0xFF0F172A)], // Verde seguro
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              _buildHeader(), // CU-10: Verificar estado de hardware
              
              // FA1 de CU-10: Alerta de batería baja local
              if (nodoConectado && bateriaNodo < 20)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.red[900]?.withOpacity(0.8),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: Colors.redAccent),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.warning_amber_rounded, color: Colors.white),
                      SizedBox(width: 10),
                      Text("Batería del nodo baja", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                    ],
                  ),
                ),

              const Spacer(),

              // Vistas dinámicas según el estado
              if (!nodoConectado)
                _buildDesconectado() // CU-09
              else if (isSosActive)
                _buildAlertaActiva() // CU-12
              else
                _buildBotonSOS(),    // CU-11

              const Spacer(),
              
              // Etiqueta decorativa de modo offline
              const Padding(
                padding: EdgeInsets.only(bottom: 20),
                child: Text("SISTEMA OFFLINE ACTIVO", style: TextStyle(color: Colors.white38, letterSpacing: 2, fontSize: 12, fontWeight: FontWeight.bold)),
              )
            ],
          ),
        ),
      ),
    );
  }

  // Tarjeta superior (Estado y Batería)
  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.all(20.0),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.05),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: Colors.white.withOpacity(0.1)),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        nodoConectado ? "Estado: Conectado" : "Nodo desconectado. Acérquese al dispositivo",
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: nodoConectado ? 16 : 13,
                          color: nodoConectado ? Colors.tealAccent : Colors.redAccent,
                        ),
                      ),
                    ],
                  ),
                ),
                if (nodoConectado)
                  Row(
                    children: [
                      Text(
                        "Batería: $bateriaNodo%",
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          color: bateriaNodo < 20 ? Colors.redAccent : Colors.greenAccent,
                        ),
                      ),
                    ],
                  )
              ],
            ),
          ),
        ),
      ),
    );
  }

  // Vista cuando el nodo no está emparejado
  Widget _buildDesconectado() {
    return Column(
      children: [
        Icon(Icons.bluetooth_disabled_rounded, size: 80, color: Colors.white.withOpacity(0.2)),
        const SizedBox(height: 30),
        ElevatedButton.icon(
          icon: const Icon(Icons.bluetooth_searching, color: Colors.white),
          label: const Text("Buscar nodos", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.teal[600],
            padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 15),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
          ),
          onPressed: _buscarNodos,
        ),
        const SizedBox(height: 15),
        TextButton(
          onPressed: _buscarNodos,
          child: const Text("Escanear de nuevo", style: TextStyle(color: Colors.tealAccent, fontSize: 16)),
        )
      ],
    );
  }

  // Vista principal del botón SOS
  Widget _buildBotonSOS() {
    return GestureDetector(
      onLongPress: _emitirAlerta,
      child: ScaleTransition(
        scale: _pulseAnimation,
        child: Container(
          width: 260,
          height: 260,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: const RadialGradient(
              colors: [Color(0xFFEF4444), Color(0xFF991B1B)], 
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.red.withOpacity(0.4),
                blurRadius: 30,
                spreadRadius: 10,
              ),
            ],
            border: Border.all(color: Colors.red[300]!.withOpacity(0.5), width: 4),
          ),
          child: const Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.power_settings_new_rounded, size: 60, color: Colors.white),
              SizedBox(height: 10),
              Text(
                "SOS",
                style: TextStyle(color: Colors.white, fontSize: 48, fontWeight: FontWeight.w900, letterSpacing: 4),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // Vista de cancelación
  Widget _buildAlertaActiva() {
    return Column(
      children: [
        ScaleTransition(
          scale: _pulseAnimation,
          child: const Icon(Icons.emergency_share_rounded, color: Colors.redAccent, size: 100),
        ),
        const SizedBox(height: 30),
        const Text("SOS Activo", style: TextStyle(fontSize: 36, color: Colors.redAccent, fontWeight: FontWeight.bold, letterSpacing: 2)),
        const SizedBox(height: 50),
        ElevatedButton.icon(
          icon: const Icon(Icons.cancel_outlined, color: Colors.white),
          label: const Text("Cancelar Alerta", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.orange[800],
            padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 15),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
            elevation: 10,
          ),
          onPressed: _cancelarAlerta,
        ),
      ],
    );
  }
}