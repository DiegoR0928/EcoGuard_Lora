# EcoGuard: documentación del código {#mainpage}

EcoGuard es un sistema de rescate para parques ecoturísticos. El visitante lleva un nodo LoRa
prestado en la entrada. Si tiene una emergencia, la alerta sale del teléfono o del botón del nodo y
llega por LoRaWAN al panel de los vigilantes, con su posición, aun donde no hay cobertura celular.

Esta documentación se genera con Doxygen a partir de los comentarios del código de los cuatro
componentes del sistema: el firmware del nodo (C++), el backend (Python/Django), la app del visitante
(Flutter/Dart) y el panel del vigilante (SvelteKit/TypeScript).

## Arquitectura

Recorrido de una alerta:

1. **App del visitante** (Flutter, `ecoguard_app/`): el visitante mantiene presionado el botón SOS;
   la app toma la posición GPS y la manda al nodo por Bluetooth Low Energy (BLE). El visitante
   también puede activar la alerta manteniendo el botón PRG del nodo.
2. **Nodo** (Heltec WiFi LoRa 32 V4, `EcoGuard-Node/src/main.cpp`): arma una trama de 3 u 11 bytes
   y la transmite por LoRaWAN 1.1 (US915, sub-banda 2, SF9). Mientras la alerta sigue activa la
   reenvía cada 30 s, confirmada.
3. **Gateway y servidor de red** (Raspberry Pi con HAT Dragino): recibe la trama por radio y la
   entrega a ChirpStack, instalado en la misma Raspberry. ChirpStack la autentica, la descifra y la
   reenvía al backend con su integración HTTP.
4. **Backend** (Django, `backend/`): el webhook (views.chirpstack_webhook()) decodifica la trama
   (tramas.py), abre o actualiza el incidente en PostgreSQL/PostGIS y avisa por WebSocket (Django
   Channels con Redis).
5. **Panel del vigilante** (SvelteKit, `frontend/`): muestra la alerta en el mapa con los datos del
   visitante, y el vigilante la atiende y la cierra. También administra los nodos y los préstamos.

Como alternativa a ChirpStack, `backend/geolocalizacion/management/commands/escuchar_ttn.py` recibe
las tramas de The Things Network por MQTT.

## Cómo está organizada

Cada archivo de Python, Dart, TypeScript y Svelte aparece como un paquete (espacio de nombres) con
el nombre de su ruta:

| Paquete                       | Contenido                                                                 |
|-------------------------------|---------------------------------------------------------------------------|
| `geolocalizacion.*`, `ecoguard.*` | Backend: modelos, vistas, serializadores, tramas, comandos y ajustes.    |
| `ecoguard_app::*`             | App del visitante: protocolo BLE, estado (visitante), servicios y pantallas. |
| `frontend::lib::*`            | Panel: tipos, comunicación con la API, estado compartido y formato.        |
| `frontend::lib::componentes::*` | Panel: componentes reutilizables (mapa, ficha del visitante, menú).        |
| `frontend::routes::*`         | Panel: una sección por ruta (`page` es la página `+page.svelte`).          |

El firmware está en la lista de archivos: `main.cpp` (variables, constantes y funciones) y la
plantilla de llaves.

Puntos de partida recomendados:

- Firmware: setup() y loop() en `main.cpp`.
- Backend: `tramas.py` (formato de la trama y reglas del incidente) y `models.py` (tablas).
- App: la clase Visitante de `ecoguard_app::visitante` (casos de uso CU-09 a CU-12).
- Panel: `frontend::lib::estado` (estado compartido y acciones) y `frontend::lib::api`.

## Dart, TypeScript y Svelte en Doxygen

Doxygen no tiene analizadores para estos lenguajes. Los archivos pasan por dos filtros de
`docs/filtros/` que los traducen a declaraciones equivalentes de C++ con los mismos comentarios:
`dart_a_doxygen.py` y `ts_a_doxygen.mjs`, que usa el compilador de TypeScript del panel. Por eso:

- Las firmas se muestran al estilo C++: `Tipo nombre(Tipo parametro)`. Cuando el tipo de retorno es
  anulable o una unión (`int?`, `number | null`), se escribe al final: `auto nombre() -> Tipo`.
- Los getters de Dart aparecen como atributos; los constructores con nombre (`EstadoNodo.desdeBytes`),
  como métodos estáticos.
- En un componente Svelte, sus props forman la estructura `Props`; su descripción es el comentario
  `<!-- @component -->` del archivo.
- Las implementaciones de una interfaz de Dart (p. ej. UbicacionGps) heredan la documentación de los
  métodos abstractos que implementan.

## Generar la documentación

Requisitos: Doxygen 1.11 o posterior, MiKTeX o TeX Live (pdflatex), Python, Node.js y las
dependencias del panel instaladas (`pnpm install` en `frontend/`).

En Windows basta con ejecutar `docs/generar_documentacion.bat`. A mano, desde la carpeta `docs/`:

```
doxygen Doxyfile
doxygen\latex\make.bat
```

El primer comando genera el HTML (`docs/doxygen/html/index.html`) y las fuentes LaTeX
(`docs/doxygen/latex/`); `make.bat` (o `make` en Linux) las compila con pdflatex y deja el PDF en
`docs/doxygen/latex/refman.pdf`. Las advertencias de Doxygen quedan en `docs/doxygen/advertencias.txt`.

## Fuera de esta documentación

- `EcoGuard-Node/include/lorawan_config.h` contiene las llaves LoRaWAN del nodo y se excluye a
  propósito; se documenta su plantilla, `lorawan_config.example.h`.
- Las pruebas automáticas (`tests.py`, `ecoguard_app/test/`), las migraciones de la base de datos,
  el marcado HTML de los componentes Svelte y los estilos.
