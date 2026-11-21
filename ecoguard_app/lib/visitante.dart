/// @brief Lógica de la app del visitante: CU-09 a CU-12 del SRS.
///
/// Las pantallas solo leen este estado y llaman a sus métodos; el Bluetooth y el GPS llegan como
/// interfaces (EnlaceNodo, Ubicacion) para poder probarlo sin hardware.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'bateria.dart';
import 'protocolo.dart';
import 'servicios/enlace_nodo.dart';
import 'servicios/ubicacion.dart';

/// @brief Etapa en la que está la app. Decide qué pantalla se muestra.
enum Fase {
  /// Sin nodo emparejado: pantalla de emparejamiento.
  sinNodo,
  /// Escaneando nodos cercanos (CU-09).
  buscando,
  /// Conectando con el nodo elegido (CU-09).
  conectando,
  /// Emparejado y sin alerta: pantalla de monitoreo con el botón SOS (CU-10).
  conectado,
  /// Obteniendo la ubicación y enviando el SOS al nodo (CU-11).
  enviandoSos,
  /// Alerta en curso (CU-11).
  sosActivo,
  /// Enviando la cancelación al nodo (CU-12).
  cancelando,
}

/// @brief Tipo de un aviso en pantalla; define su color e ícono.
enum TipoAviso {
  /// Operación exitosa.
  exito,
  /// Algo falló y el visitante debe actuar.
  error,
  /// Información sin urgencia.
  informacion,
}

/// @brief Mensaje breve de un caso de uso, que la app muestra como SnackBar.
class Aviso {
  /// Texto del mensaje.
  final String texto;
  /// Tipo del mensaje.
  final TipoAviso tipo;
  /// @brief Crea un aviso.
  /// @param texto Texto del mensaje.
  /// @param tipo Tipo del mensaje.
  const Aviso(this.texto, this.tipo);
}

/// @brief Estado y acciones de la app del visitante.
///
/// Es un ChangeNotifier: cada cambio de fase, de nodo o de estado del nodo avisa a las pantallas para
/// que se redibujen. Los mensajes de los casos de uso salen por avisos.
class Visitante extends ChangeNotifier {
  /// @brief Crea el estado y se suscribe a las notificaciones y pérdidas del enlace.
  /// @param _enlace Enlace con el nodo (real o simulado).
  /// @param _ubicacion GPS del teléfono (real o simulado).
  /// @param limiteGps Espera máxima por un fix GPS al emitir el SOS.
  /// @param esperaReconexion Pausa entre intentos de reconexión cuando se pierde el enlace.
  /// @param refrescoPosicion Cada cuánto se reenvía la posición durante la alerta.
  Visitante(
    this._enlace,
    this._ubicacion, {
    this.limiteGps = const Duration(seconds: 8),
    this.esperaReconexion = const Duration(seconds: 5),
    this.refrescoPosicion = const Duration(seconds: 60),
  }) {
    _suscripciones
      ..add(_enlace.estados.listen(_alRecibirEstado))
      ..add(_enlace.perdidas.listen((_) => _alPerderEnlace()));
  }

  /// Enlace con el nodo.
  final EnlaceNodo _enlace;
  /// GPS del teléfono.
  final Ubicacion _ubicacion;

  /// Espera máxima por un fix GPS al emitir el SOS. RNF-01 da 15 s entre la pulsación y la
  /// confirmación en pantalla: 3 s de pulsación, hasta 8 s de GPS (que empieza a buscar al tocar el
  /// botón) y el envío al nodo.
  final Duration limiteGps;
  /// Pausa entre intentos de reconexión cuando se pierde el enlace.
  final Duration esperaReconexion;
  /// Cada cuánto se reenvía la última posición durante la alerta. El nodo deja de enviar una posición
  /// con más de 5 min: se reenvía aunque el visitante no se mueva.
  final Duration refrescoPosicion;

  /// Fuente de los avisos.
  final _avisos = StreamController<Aviso>.broadcast();
  /// Suscripciones a los flujos del enlace; se cancelan en dispose().
  final List<StreamSubscription> _suscripciones = [];
  /// Suscripción a las posiciones del GPS durante la alerta.
  StreamSubscription<Coordenadas>? _posiciones;
  /// Temporizador que reenvía la posición cada refrescoPosicion.
  Timer? _refresco;
  /// Búsqueda de posición iniciada por prepararUbicacion(), que emitirSos() aprovecha.
  Future<Coordenadas?>? _ubicacionEnCurso;
  /// Momento en que se inició _ubicacionEnCurso.
  DateTime? _ubicacionPedidaEn;
  /// Última posición enviada o recibida del GPS.
  Coordenadas? _ultimaPosicion;
  /// Verdadero tras dispose(): detiene los reintentos de conexión.
  bool _cerrado = false;

  /// Etapa actual de la app.
  Fase fase = Fase.sinNodo;
  /// Nodos encontrados en el último escaneo.
  List<NodoEncontrado> encontrados = [];
  /// Nodo emparejado; null si no hay.
  NodoEncontrado? nodo; // Nodo emparejado
  /// Último estado notificado por el nodo.
  EstadoNodo? estadoNodo;
  /// El visitante se alejó del nodo y se perdió el enlace (CU-10, FE1).
  bool enlacePerdido = false; // CU-10, FE1: el visitante se alejó del nodo
  /// La alerta ya lleva coordenadas.
  bool ubicacionEnviada = false; // La alerta ya lleva coordenadas

  /// Mensajes de los casos de uso, para mostrarlos en pantalla.
  Stream<Aviso> get avisos => _avisos.stream;

  /// Verdadero mientras se envía, está activa o se cancela una alerta. Bloquea desvincular el nodo.
  bool get enEmergencia => fase == Fase.enviandoSos || fase == Fase.sosActivo || fase == Fase.cancelando;

  /// Batería del nodo en porcentaje; null si todavía no se conoce.
  int? get bateria => estadoNodo == null ? null : porcentajeBateria(estadoNodo!.bateriaMv);

  /// Verdadero si la batería está por debajo de umbralBateriaBaja (CU-10, FA1).
  bool get bateriaBaja => bateria != null && bateria! < umbralBateriaBaja;

  /// @brief Busca nodos cercanos (CU-09, pasos 2 y 3, y FA1 «Escanear de nuevo»).
  ///
  /// Si el Bluetooth no está disponible avisa al visitante. La lista encontrados se actualiza
  /// mientras dura el escaneo.
  /// @return Se completa al terminar el escaneo.
  Future<void> buscarNodos() async {
    if (fase == Fase.buscando || fase == Fase.conectando) return;
    bool disponible;
    try {
      disponible = await _enlace.bluetoothDisponible();
    } catch (_) {
      disponible = false; // Plataforma sin Bluetooth LE o sin permisos
    }
    if (!disponible) {
      _avisar('Active el Bluetooth para buscar su nodo', TipoAviso.error);
      return;
    }
    fase = Fase.buscando;
    encontrados = [];
    notifyListeners();
    try {
      await _enlace.buscar((lista) {
        encontrados = lista;
        notifyListeners();
      });
    } catch (_) {
      _avisar('No se pudieron buscar nodos. Revise los permisos de Bluetooth', TipoAviso.error);
    }
    if (fase == Fase.buscando) fase = Fase.sinNodo;
    notifyListeners();
  }

  /// @brief Empareja el nodo elegido (CU-09, pasos 4 y 5, y FE1).
  ///
  /// Al conectar se concilia con el estado del nodo y se pide el permiso de ubicación, para no
  /// interrumpir una emergencia con ese diálogo.
  /// @param elegido Nodo que el visitante eligió de la lista.
  /// @return Se completa al conectar o al fallar la conexión.
  Future<void> conectar(NodoEncontrado elegido) async {
    fase = Fase.conectando;
    notifyListeners();
    final EstadoNodo inicial;
    try {
      inicial = await _enlace.conectar(elegido.id);
    } catch (_) {
      fase = Fase.sinNodo;
      notifyListeners();
      _avisar('Error al conectar, intente nuevamente', TipoAviso.error);
      return;
    }
    nodo = elegido;
    enlacePerdido = false;
    fase = Fase.conectado;
    await _sincronizar(inicial);
    notifyListeners();
    // El permiso de ubicación se pide ahora y no al emitir el SOS, para no interrumpir una emergencia
    unawaited(_ubicacion.solicitarPermiso());
  }

  /// @brief Desvincula el nodo para emparejar otro. No se permite durante una emergencia.
  /// @return Se completa al cerrarse la conexión con el nodo.
  Future<void> desvincular() async {
    if (enEmergencia) return;
    nodo = null;
    estadoNodo = null;
    enlacePerdido = false;
    fase = Fase.sinNodo;
    notifyListeners();
    await _enlace.desconectar();
  }

  /// @brief Empieza a buscar la posición al presionar el botón SOS (CU-11, paso 1).
  ///
  /// El GPS busca mientras corren los 3 s de pulsación, así la posición suele estar lista cuando se
  /// suelta. Una búsqueda de hace menos de 30 s se reutiliza.
  void prepararUbicacion() {
    final pedida = _ubicacionPedidaEn;
    if (_ubicacionEnCurso != null && pedida != null && DateTime.now().difference(pedida) < const Duration(seconds: 30)) {
      return;
    }
    _ubicacionPedidaEn = DateTime.now();
    _ubicacionEnCurso = _ubicacion.obtener(limiteGps);
  }

  /// @brief Emite el SOS con la posición del teléfono (CU-11, pasos 2 a 4, FA1 y FE1).
  ///
  /// Sin fix GPS la alerta sale igual, sin posición (FA1); si el nodo no responde se avisa al
  /// visitante que use el botón físico (FE1). Al enviarse, la posición se sigue enviando al nodo
  /// mientras dura la alerta.
  /// @return Se completa cuando el nodo recibió la alerta o falló el envío.
  Future<void> emitirSos() async {
    if (fase != Fase.conectado) return;
    fase = Fase.enviandoSos;
    notifyListeners();

    final coordenadas = await (_ubicacionEnCurso ?? _ubicacion.obtener(limiteGps));
    _ubicacionEnCurso = null;
    try {
      // Sin fix GPS la alerta sale igual, marcada sin posición (FA1); el nodo nunca inventa coordenadas
      await _enlace.enviar(codificarComando(Comando.sos, coordenadas));
    } catch (_) {
      fase = Fase.conectado;
      notifyListeners();
      _avisar('Falla al comunicar con el nodo, intente presionar el botón físico en el dispositivo', TipoAviso.error);
      return;
    }
    _ultimaPosicion = coordenadas;
    ubicacionEnviada = coordenadas != null;
    fase = Fase.sosActivo;
    notifyListeners();
    _avisar('¡Alerta enviada exitosamente!', TipoAviso.exito);
    _seguirPosicion();
  }

  /// @brief Cancela la alerta activa (CU-12, pasos 4 a 6, y FE1).
  ///
  /// La confirmación («¿Desea cancelar el rescate?») la pide la pantalla antes de llamar aquí.
  /// @return Se completa cuando el nodo recibió la cancelación o falló el envío.
  Future<void> cancelarSos() async {
    if (fase != Fase.sosActivo) return;
    fase = Fase.cancelando;
    notifyListeners();
    try {
      await _enlace.enviar(codificarComando(Comando.cancelar));
    } catch (_) {
      fase = Fase.sosActivo;
      notifyListeners();
      _avisar('No se pudo cancelar. Contacte a los vigilantes si se los encuentra', TipoAviso.error);
      return;
    }
    _dejarDeSeguir();
    ubicacionEnviada = false;
    fase = Fase.conectado;
    notifyListeners();
    _avisar('Alerta cancelada', TipoAviso.informacion);
  }

  /// @brief Durante la alerta, envía al nodo cada posición nueva y reenvía la última cada refrescoPosicion.
  void _seguirPosicion() {
    _dejarDeSeguir();
    _posiciones = _ubicacion.seguir().listen((coordenadas) {
      _ultimaPosicion = coordenadas;
      _enviarPosicion(coordenadas);
    });
    _refresco = Timer.periodic(refrescoPosicion, (_) {
      final ultima = _ultimaPosicion;
      if (ultima != null) _enviarPosicion(ultima);
    });
  }

  /// @brief Detiene el seguimiento de la posición.
  void _dejarDeSeguir() {
    _posiciones?.cancel();
    _posiciones = null;
    _refresco?.cancel();
    _refresco = null;
  }

  /// @brief Envía una posición al nodo durante la alerta. Si falla, se reintenta con la siguiente.
  /// @param coordenadas Posición a enviar.
  /// @return Se completa al terminar el intento de envío.
  Future<void> _enviarPosicion(Coordenadas coordenadas) async {
    if (enlacePerdido || fase != Fase.sosActivo) return;
    try {
      await _enlace.enviar(codificarComando(Comando.posicion, coordenadas));
      if (!ubicacionEnviada) {
        ubicacionEnviada = true;
        notifyListeners();
      }
    } catch (_) {
      // Se reintenta con la siguiente posición o el siguiente refresco
    }
  }

  /// @brief Guarda cada estado que notifica el nodo.
  /// @param estado Estado notificado.
  void _alRecibirEstado(EstadoNodo estado) {
    estadoNodo = estado;
    notifyListeners();
  }

  /// @brief Concilia la app con el nodo al conectar o reconectar.
  ///
  /// Si el nodo se reinició durante la emergencia y perdió el SOS, se le vuelve a ordenar. Si la app
  /// se reabrió con una alerta en curso en el nodo, se muestra para poder seguirla o cancelarla.
  /// @param estado Estado del nodo al conectar.
  /// @return Se completa al terminar la conciliación.
  Future<void> _sincronizar(EstadoNodo estado) async {
    estadoNodo = estado;
    if (fase == Fase.sosActivo && !estado.sosActivo) {
      // El nodo se reinició durante la emergencia y perdió el SOS: se le vuelve a ordenar
      try {
        await _enlace.enviar(codificarComando(Comando.sos, _ultimaPosicion));
      } catch (_) {}
    } else if (!enEmergencia && estado.sosActivo) {
      // La app se reabrió con una alerta en curso: se muestra para poder seguirla o cancelarla
      fase = Fase.sosActivo;
      _seguirPosicion();
    }
  }

  /// @brief Reacciona a la pérdida del enlace (CU-10, FE1).
  ///
  /// El nodo sigue con su SOS aunque se pierda el enlace; la app marca enlacePerdido y reintenta conectar.
  void _alPerderEnlace() {
    if (nodo == null || enlacePerdido) return;
    enlacePerdido = true;
    notifyListeners();
    _reconectar();
  }

  /// @brief Reintenta conectar con el nodo cada esperaReconexion hasta lograrlo, desvincularlo o cerrar la app.
  /// @return Se completa al reconectar o al dejar de intentarlo.
  Future<void> _reconectar() async {
    while (enlacePerdido && nodo != null && !_cerrado) {
      await Future.delayed(esperaReconexion);
      final actual = nodo;
      if (!enlacePerdido || actual == null || _cerrado) return;
      try {
        final estado = await _enlace.conectar(actual.id);
        enlacePerdido = false;
        await _sincronizar(estado);
        notifyListeners();
      } catch (_) {
        // Sigue fuera de alcance: se reintenta
      }
    }
  }

  /// @brief Publica un aviso para la pantalla.
  /// @param texto Texto del mensaje.
  /// @param tipo Tipo del mensaje.
  void _avisar(String texto, TipoAviso tipo) {
    if (!_avisos.isClosed) _avisos.add(Aviso(texto, tipo));
  }

  /// @brief Libera las suscripciones y detiene los reintentos al cerrar la app.
  @override
  void dispose() {
    _cerrado = true;
    _dejarDeSeguir();
    for (final s in _suscripciones) {
      s.cancel();
    }
    _avisos.close();
    super.dispose();
  }
}
