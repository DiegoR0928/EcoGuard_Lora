/**
 * @file main.cpp
 * @brief Firmware del nodo EcoGuard: Heltec WiFi LoRa 32 V4 (ESP32-S3 + SX1262).
 *
 * El nodo lo lleva el visitante durante su recorrido. Recibe la alerta del teléfono por Bluetooth
 * Low Energy (BLE) o del botón PRG y la transmite por LoRaWAN al gateway del parque, que la entrega
 * al backend a través de ChirpStack.
 *
 * @par Flujo general
 * -# setup() configura energía, pantalla, radio, credenciales LoRaWAN y el servidor BLE.
 * -# loop() se une a la red con OTAA (reintenta cada 60 s), atiende el botón y los comandos del
 *    teléfono, y envía tramas: cada 30 s mientras hay una alerta activa o una cancelación pendiente,
 *    y cada 10 min como reporte de estado.
 * -# Tres clics sin alerta activa apagan el nodo (deep sleep); la sesión LoRaWAN se conserva en la
 *    memoria RTC y el botón lo vuelve a encender.
 *
 * @par Protocolo BLE (servicio SERVICE_UUID)
 * - CHARACTERISTIC_UUID (escritura, teléfono a nodo): comandos.
 *   - CMD_SOS y CMD_POSICION: 10 bytes, [comando][banderas][lat int32][lon int32], little-endian,
 *     coordenadas en grados × 1 000 000. Bit 0 de banderas: el teléfono tiene posición GPS.
 *   - CMD_CANCELAR: 1 byte.
 * - ESTADO_UUID (lectura y notificación, nodo a teléfono): 3 bytes, [batería mV uint16][estado].
 *   Bits de estado: 0x01 unido a la red, 0x02 alerta activa, 0x04 la central confirmó la alerta.
 *
 * @par Trama LoRaWAN (puerto PUERTO_LORAWAN)
 * [banderas][batería mV uint16][lat int32][lon int32], little-endian. Banderas: 0x01 SOS,
 * 0x02 trae posición, 0x04 cancelación. Sin posición vigente mide 3 bytes; con posición, 11.
 * El backend la decodifica en geolocalizacion/tramas.py.
 *
 * @par Botón PRG
 * - Mantenerlo PULSACION_SOS ms: emite el SOS (el mismo gesto del botón de la app, CU-11).
 * - Tres clics: cancelan la alerta o, si no hay ninguna, apagan el nodo.
 * - Un clic: enciende la pantalla y muestra el estado.
 *
 * @par Configuración
 * Las llaves LoRaWAN van en include/lorawan_config.h (copia de lorawan_config.example.h, fuera de
 * git). El entorno "sin_gateway" de platformio.ini define SIMULAR_LORAWAN para probar la pantalla y
 * el Bluetooth sin red. Más detalles en EcoGuard-Node/README.md.
 */
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Preferences.h>
#include <RadioLib.h>
#include <U8g2lib.h>
#include <Wire.h>
#include <driver/gpio.h>

// Llaves LoRaWAN. Si falta, copia include/lorawan_config.example.h como lorawan_config.h
#include "lorawan_config.h"

// Protocolo BLE, formato de la trama LoRaWAN y puesta en marcha: ver README.md

/**
 * @name Botón PRG
 * Mantenerlo 3 s emite el SOS, el mismo gesto del botón de la app (CU-11). Tres clics cancelan la
 * alerta o, si no hay ninguna, apagan el nodo: repetir el gesto del SOS por nervios nunca la cancela.
 */
///@{
#define BOTON_PRG 0  ///< GPIO del botón PRG (activo en LOW, con pull-up). También despierta al nodo del deep sleep.
const unsigned long PULSACION_SOS = 3000;      ///< Tiempo presionado, en ms, que emite el SOS.
const unsigned long AVISO_PULSACION = 500;     ///< A partir de aquí (ms) la pantalla pide seguir presionando.
const unsigned long PAUSA_ENTRE_CLICS = 600;   ///< Una pausa mayor (ms) termina la serie de clics.
const unsigned long REBOTE_BOTON = 30;         ///< Espera antirrebote tras cada cambio del botón, en ms.

/// Gesto reconocido por leerGestoBoton().
enum GestoBoton {
    GESTO_CLIC,         ///< Uno o dos clics: muestra el estado.
    GESTO_TRIPLE_CLIC,  ///< Tres o más clics: cancela la alerta o apaga el nodo.
    GESTO_MANTENIDO     ///< Presionado PULSACION_SOS ms: emite el SOS.
};
/// Verdadero tras un GESTO_MANTENIDO hasta que se suelta el botón, para no contarlo como otro gesto.
bool esperarSoltarBoton = false;
///@}

/** @name Pines de energía y batería (Heltec V4) */
///@{
#define VEXT 36                            ///< Controla la alimentación de la pantalla y periféricos (LOW = encendido).
#define BATTERY_PIN 1                      ///< Entrada analógica del divisor de voltaje de la batería.
#define ADC_CTRL 37                        ///< Activa el divisor de la batería. En la V4 se activa en HIGH (en la V3 era LOW).
#define ADC_MULTIPLICADOR (4.9f * 1.045f)  ///< Divisor 390k/100k, con la corrección que usa Meshtastic.
///@}

/** @name Radio LoRa SX1262 */
///@{
#define RADIO_NSS    8    ///< Selección de chip SPI del SX1262.
#define RADIO_DIO1   14   ///< Interrupción DIO1 del SX1262 (fin de transmisión o recepción).
#define RADIO_NRST   12   ///< Reset del SX1262.
#define RADIO_BUSY   13   ///< Señal BUSY del SX1262.
#define RADIO_TCXO_V 1.8  ///< Voltaje del oscilador TCXO del SX1262, en V.
/// Radio LoRa (RadioLib).
SX1262 radio = new Module(RADIO_NSS, RADIO_DIO1, RADIO_NRST, RADIO_BUSY);
///@}

/**
 * @name Amplificador de radio (FEM) de la V4
 * La V4 amplifica la salida del SX1262 hasta ~28 dBm. Si el FEM no se enciende, la radio reporta
 * envíos exitosos pero la señal casi no sale de la antena. Hay dos revisiones de placa con chips
 * distintos; encenderFEM() detecta cuál es.
 */
///@{
#define FEM_POWER    7   ///< LDO que alimenta el FEM.
#define FEM_CSD      2   ///< Habilita el chip (HIGH) en ambas revisiones.
#define FEM_CPS_V4_2 46  ///< V4.2 (GC1109): HIGH = amplificador completo al transmitir.
#define FEM_CTX_V4_3 5   ///< V4.3 (KCT8103L): HIGH al transmitir, LOW al recibir (LNA).

/// Chip FEM de la placa.
enum TipoFEM {
    FEM_GC1109,    ///< Heltec V4.2.
    FEM_KCT8103L   ///< Heltec V4.3.
};
/// Revisión detectada por encenderFEM().
TipoFEM tipoFEM;

/// Pines que RadioLib conmuta según el modo de la radio; solo se usa el primero (el del FEM).
/// El pin de cada revisión se conmuta igual: HIGH al transmitir y LOW el resto del tiempo.
/// La selección de camino TX/RX la hace DIO2 del SX1262 automáticamente.
uint32_t pinesFEM[Module::RFSWITCH_MAX_PINS];
/// Nivel del pin del FEM en cada modo de la radio: HIGH solo al transmitir.
static const Module::RfSwitchMode_t tablaFEM[] = {
    { Module::MODE_IDLE, { LOW } },
    { Module::MODE_RX,   { LOW } },
    { Module::MODE_TX,   { HIGH } },
    END_OF_MODE_TABLE,
};
///@}

/** @name Pantalla OLED SSD1306 (128 × 64, I2C) */
///@{
#define OLED_SDA 17  ///< Datos I2C de la pantalla.
#define OLED_SCL 18  ///< Reloj I2C de la pantalla.
#define OLED_RST 21  ///< Reset de la pantalla.
/// Controlador de la pantalla (U8g2, búfer completo). Se inicializa con llaves para que Doxygen no
/// confunda la definición con la declaración de una función.
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2{U8G2_R0, OLED_RST, OLED_SCL, OLED_SDA};
///@}

/** @name Bluetooth Low Energy */
///@{
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"  ///< Servicio BLE de EcoGuard; la app filtra el escaneo por él.
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"  ///< Celular → nodo (comandos).
#define ESTADO_UUID         "d2b0f5a1-7c3e-4b8a-9f61-3a5e8c1d4e72"  ///< Nodo → celular (notificaciones).

#define CMD_SOS      0x01  ///< Comando BLE: alerta con la posición del teléfono (10 bytes).
#define CMD_POSICION 0x02  ///< Comando BLE: solo actualiza la posición (10 bytes).
#define CMD_CANCELAR 0x03  ///< Comando BLE: cancela la alerta activa (1 byte).
///@}

/** @name LoRaWAN */
///@{
const LoRaWANBand_t REGION = US915;  ///< Plan de frecuencias (Norteamérica, 902-928 MHz).
const uint8_t PUERTO_LORAWAN = 1;    ///< Puerto (FPort) de las tramas de EcoGuard; el backend ignora los demás.
/// Datarate fijo: DR1 = SF9 a 125 kHz. El nodo se mueve con el visitante, así que se fija el
/// datarate en lugar de usar ADR, que lo ajustaría según condiciones de radio que cambian a cada paso.
const uint8_t DATARATE = 1;

const unsigned long INTERVALO_SOS = 30UL * 1000;             ///< Reenvío mientras la alerta está activa, en ms.
const unsigned long INTERVALO_REPORTE = 10UL * 60 * 1000;    ///< Reporte periódico para el monitoreo de salud (CU-5), en ms.
const unsigned long REINTENTO_JOIN = 60UL * 1000;            ///< Espera entre intentos de unirse a la red, en ms.
const unsigned long VIGENCIA_POSICION = 5UL * 60 * 1000;     ///< Una posición más vieja (ms) ya no se envía.
const uint8_t MAX_INTENTOS_CANCELACION = 3;                  ///< Envíos de la cancelación sin ACK antes de darla por terminada.

uint64_t joinEUI = LORAWAN_JOIN_EUI;    ///< JoinEUI (antes AppEUI), de lorawan_config.h.
uint64_t devEUI = 0;                    ///< DevEUI: el de lorawan_config.h o, si no está definido, devEuiDesdeMac().
uint8_t appKey[] = { LORAWAN_APP_KEY }; ///< AppKey (raíz de la AppSKey, que cifra la carga útil), de lorawan_config.h.
uint8_t nwkKey[] = { LORAWAN_NWK_KEY }; ///< NwkKey (raíz de las llaves de red de LoRaWAN 1.1), de lorawan_config.h.
/// Nodo LoRaWAN de RadioLib, en la sub-banda LORAWAN_SUB_BANDA. Se inicializa con llaves por la
/// misma razón que #u8g2.
LoRaWANNode node{&radio, &REGION, LORAWAN_SUB_BANDA};
/// Memoria flash no volátil (espacio "lorawan"). Guarda los nonces del join para no repetir el DevNonce.
Preferences almacen;
char textoDevEUI[17];  ///< DevEUI en hexadecimal (16 dígitos y terminador) para la pantalla y el nombre BLE.
///@}

#ifdef SIMULAR_LORAWAN
// Entorno "sin_gateway" de platformio.ini: no hay join, cada trama se imprime por serial
// y se simula el ACK de la central. Solo para probar la pantalla y el Bluetooth sin gateway
const char *TEXTO_EN_RED = "Red SIMULADA";
bool enRed() { return true; }
#else
/// Texto de la pantalla cuando el nodo está en la red. Con SIMULAR_LORAWAN es "Red SIMULADA".
const char *TEXTO_EN_RED = "Red LoRaWAN OK";
/**
 * @brief Indica si el nodo puede transmitir.
 *
 * Con SIMULAR_LORAWAN (entorno "sin_gateway") siempre devuelve true: no hay join, cada trama se
 * imprime por serial y se simula el ACK de la central.
 * @return true si el nodo tiene una sesión LoRaWAN activa.
 */
bool enRed() { return node.isActivated(); }
#endif

/** @name Sesión LoRaWAN en memoria RTC
 * La sesión sobrevive al deep sleep en memoria RTC: al volver a encender no hace falta otro join.
 */
///@{
RTC_DATA_ATTR uint8_t sesionGuardada[RADIOLIB_LORAWAN_SESSION_BUF_SIZE];  ///< Copia de la sesión que guarda apagarNodo().
RTC_DATA_ATTR bool haySesionGuardada = false;                              ///< Verdadero si sesionGuardada es válida.
///@}

/**
 * @name Estado compartido con los callbacks BLE
 * Los callbacks BLE corren en otra tarea de FreeRTOS: las banderas son volatile y la posición se
 * lee y escribe dentro de una sección crítica con #candado.
 */
///@{
portMUX_TYPE candado = portMUX_INITIALIZER_UNLOCKED;  ///< Protege latE6, lonE6, posicionRecibidaEn y hayPosicion.
volatile bool pedidoSOS = false;          ///< El teléfono o el botón pidieron un SOS; lo atiende loop().
volatile bool pedidoCancelar = false;     ///< El teléfono o el botón pidieron cancelar; lo atiende loop().
volatile bool celularConectado = false;   ///< Hay un teléfono conectado por BLE.
volatile bool cambioConexion = false;     ///< Cambió la conexión BLE; loop() lo muestra en pantalla.
int32_t latE6 = 0;   ///< Última latitud recibida del teléfono, en grados × 1 000 000.
int32_t lonE6 = 0;   ///< Última longitud recibida del teléfono, en grados × 1 000 000.
unsigned long posicionRecibidaEn = 0;  ///< millis() de la última posición recibida.
bool hayPosicion = false;              ///< Verdadero si alguna vez llegó una posición.
///@}

/** @name Estado del nodo */
///@{
bool modoSOS = false;               ///< Hay una alerta activa: se reenvía cada INTERVALO_SOS.
bool cancelacionPendiente = false;  ///< Falta transmitir la cancelación de la alerta.
uint8_t intentosCancelacion = 0;    ///< Envíos de la cancelación sin ACK.
bool alertaConfirmada = false;      ///< La central respondió con ACK a alguna trama de esta alerta.
uint16_t ultimaBateriaMv = 0;       ///< Última lectura de la batería, en mV.
unsigned long proximoEnvio = 0;          ///< millis() del próximo envío de trama.
unsigned long proximoIntentoJoin = 0;    ///< millis() del próximo intento de unirse a la red.
BLECharacteristic *caracteristicaEstado = nullptr;  ///< Característica de estado (ESTADO_UUID) para notificar a la app.
///@}

/** @name Ahorro de energía */
///@{
unsigned long tiempoUltimaAccion = 0;                ///< millis() de la última actualización de la pantalla.
const unsigned long TIEMPO_PANTALLA_ACTIVA = 10000;  ///< La pantalla se apaga tras 10 s sin cambios.
bool pantallaEncendida = true;                       ///< Estado actual de la pantalla.
///@}

/**
 * @brief Escribe un entero de 32 bits con signo en little-endian.
 * @param destino Búfer de al menos 4 bytes.
 * @param valor Entero a escribir.
 */
void escribirInt32LE(uint8_t *destino, int32_t valor) {
    for (int i = 0; i < 4; i++) destino[i] = (uint32_t)valor >> (8 * i);
}

/**
 * @brief Lee un entero de 32 bits con signo en little-endian.
 * @param origen Búfer de al menos 4 bytes.
 * @return El entero leído.
 */
int32_t leerInt32LE(const uint8_t *origen) {
    return (int32_t)((uint32_t)origen[0] | ((uint32_t)origen[1] << 8) | ((uint32_t)origen[2] << 16) | ((uint32_t)origen[3] << 24));
}

/**
 * @brief Mide el voltaje de la celda de la batería.
 *
 * Activa el divisor con ADC_CTRL, promedia 8 lecturas calibradas y lo vuelve a desactivar para no
 * gastar batería. Se reporta en mV porque el SDD lo pide así: la curva de descarga de una LiPo no
 * es lineal.
 * @return Voltaje de la celda en mV.
 */
uint16_t leerBateriaMv() {
    digitalWrite(ADC_CTRL, HIGH);
    delay(10); // Estabilizar voltaje

    uint32_t suma = 0;
    for (int i = 0; i < 8; i++) suma += analogReadMilliVolts(BATTERY_PIN);

    digitalWrite(ADC_CTRL, LOW);
    return (suma / 8) * ADC_MULTIPLICADOR;
}

/**
 * @brief Carga restante de una celda LiPo 1S, en pares {mV, %}.
 *
 * Es la misma curva del panel web (frontend/src/lib/formato.ts) y de la app
 * (ecoguard_app/lib/bateria.dart), para que los tres muestren el mismo porcentaje. El 0 % está en
 * 3.3 V, donde RNF-05 da la celda por agotada.
 */
const uint16_t CURVA_LIPO[][2] = {
    {3300, 0},  {3610, 5},  {3690, 10}, {3710, 15}, {3730, 20}, {3750, 25}, {3770, 30},
    {3790, 35}, {3800, 40}, {3820, 45}, {3840, 50}, {3850, 55}, {3870, 60}, {3910, 65},
    {3950, 70}, {3980, 75}, {4020, 80}, {4080, 85}, {4110, 90}, {4150, 95}, {4200, 100},
};

/**
 * @brief Convierte el voltaje de la batería en porcentaje con la curva CURVA_LIPO.
 *
 * Solo se usa en la pantalla: a la red viajan los mV. Interpola linealmente entre los dos puntos de
 * la curva que rodean al voltaje.
 * @param mv Voltaje de la celda en mV.
 * @return Carga restante de 0 a 100 %.
 */
int porcentajeBateria(uint16_t mv) {
    const size_t puntos = sizeof(CURVA_LIPO) / sizeof(CURVA_LIPO[0]);
    if (mv <= CURVA_LIPO[0][0]) return 0;
    for (size_t i = 1; i < puntos; i++) {
        if (mv <= CURVA_LIPO[i][0]) {
            const uint16_t* bajo = CURVA_LIPO[i - 1];
            const uint16_t* alto = CURVA_LIPO[i];
            const float fraccion = float(mv - bajo[0]) / (alto[0] - bajo[0]);
            return lroundf(bajo[1] + fraccion * (alto[1] - bajo[1]));
        }
    }
    return 100;
}

/**
 * @brief Muestra tres líneas de texto en la pantalla, con una barra de estado arriba.
 *
 * Enciende la pantalla si estaba apagada, actualiza ultimaBateriaMv y reinicia el temporizador de
 * apagado (TIEMPO_PANTALLA_ACTIVA). La barra de estado muestra "EcoGuard" y el porcentaje de batería.
 * @param linea1 Primera línea (hasta 21 caracteres con la fuente de 6 × 10).
 * @param linea2 Segunda línea.
 * @param linea3 Tercera línea; vacía por defecto.
 */
void mostrarEnPantalla(const char* linea1, const char* linea2, const char* linea3 = "") {
    if (!pantallaEncendida) {
        u8g2.setPowerSave(0);
        pantallaEncendida = true;
    }

    ultimaBateriaMv = leerBateriaMv();
    char txtBateria[10];
    sprintf(txtBateria, "%d%%", porcentajeBateria(ultimaBateriaMv));

    u8g2.clearBuffer();

    // --- BARRA DE ESTADO FIJA (Arriba) ---
    u8g2.drawStr(0, 10, "EcoGuard");
    u8g2.drawStr(100, 10, txtBateria);
    u8g2.drawLine(0, 13, 128, 13);

    // --- TEXTOS DINÁMICOS (Movidos hacia abajo) ---
    u8g2.drawStr(0, 28, linea1);
    u8g2.drawStr(0, 46, linea2);
    u8g2.drawStr(0, 64, linea3);

    u8g2.sendBuffer();

    tiempoUltimaAccion = millis();
}

/**
 * @brief Enciende el amplificador (FEM) de la V4 y detecta la revisión de la placa.
 *
 * El pin CSD tiene pull-down interno en el GC1109 (V4.2) y pull-up en el KCT8103L (V4.3): leyéndolo
 * como entrada antes de manejarlo se sabe qué chip hay. Luego registra en RadioLib el pin que debe
 * subir al transmitir (tablaFEM). Libera los pines que apagarNodo() dejó fijados.
 * @pre Debe llamarse antes de radio.begin().
 */
void encenderFEM() {
    pinMode(FEM_POWER, OUTPUT);
    digitalWrite(FEM_POWER, HIGH);
    gpio_hold_dis((gpio_num_t)FEM_POWER);
    delay(1);

    gpio_hold_dis((gpio_num_t)FEM_CSD);
    pinMode(FEM_CSD, INPUT);
    delay(1);
    tipoFEM = digitalRead(FEM_CSD) == HIGH ? FEM_KCT8103L : FEM_GC1109;

    pinMode(FEM_CSD, OUTPUT);
    digitalWrite(FEM_CSD, HIGH);

    for (auto &pin : pinesFEM) pin = RADIOLIB_NC;
    pinesFEM[0] = tipoFEM == FEM_KCT8103L ? FEM_CTX_V4_3 : FEM_CPS_V4_2;
    radio.setRfSwitchTable(pinesFEM, tablaFEM);
}

/**
 * @brief Deriva un EUI-64 de la MAC del ESP32, insertando FFFE a la mitad.
 *
 * Es único y fijo para cada placa, así que sirve como DevEUI sin configurar nada.
 * @return DevEUI de 64 bits, p. ej. la MAC AA:BB:CC:DD:EE:FF da AABBCCFFFEDDEEFF.
 */
uint64_t devEuiDesdeMac() {
    uint64_t mac = ESP.getEfuseMac();  // El primer byte de la MAC queda en el byte menos significativo
    uint8_t m[6];
    for (int i = 0; i < 6; i++) m[i] = mac >> (8 * i);
    return ((uint64_t)m[0] << 56) | ((uint64_t)m[1] << 48) | ((uint64_t)m[2] << 40) | (0xFFULL << 32) |
           (0xFEULL << 24) | ((uint64_t)m[3] << 16) | ((uint64_t)m[4] << 8) | m[5];
}

/**
 * @brief Actualiza la característica de estado y notifica a la app si está conectada.
 *
 * Valor de 3 bytes: batería en mV (uint16 little-endian) y banderas: 0x01 unido a la red, 0x02
 * alerta activa, 0x04 la central confirmó la alerta.
 */
void publicarEstado() {
    if (!caracteristicaEstado) return;

    uint8_t datos[3] = {
        (uint8_t)(ultimaBateriaMv & 0xFF),
        (uint8_t)(ultimaBateriaMv >> 8),
        (uint8_t)((enRed() ? 0x01 : 0) | (modoSOS ? 0x02 : 0) | (alertaConfirmada ? 0x04 : 0))
    };
    caracteristicaEstado->setValue(datos, sizeof(datos));
    if (celularConectado) caracteristicaEstado->notify();
}

/**
 * @brief Intenta unirse a la red LoRaWAN por OTAA, o restaurar la sesión guardada.
 *
 * Guarda los nonces en flash después de cada intento: avanzan en cada Join Request y, si no se
 * guardan, la red rechaza el join tras reiniciar (DevNonce repetido). Al unirse desactiva ADR y fija
 * DATARATE. Muestra el resultado en la pantalla.
 * @note Bloquea unos segundos: espera las ventanas de recepción del Join Accept.
 * @return true si hay sesión (nueva o restaurada); false si falló, y loop() reintenta en REINTENTO_JOIN.
 */
bool intentarUnirse() {
    mostrarEnPantalla("Conectando a la red", "LoRaWAN...", textoDevEUI);
    int16_t estado = node.activateOTAA();

    // Los nonces avanzan en cada intento; si no se guardan, la red rechaza el join tras reiniciar
    almacen.putBytes("nonces", node.getBufferNonces(), RADIOLIB_LORAWAN_NONCES_BUF_SIZE);
    Serial.printf("[LoRaWAN] join: %d\n", estado);

    if (estado != RADIOLIB_LORAWAN_NEW_SESSION && estado != RADIOLIB_LORAWAN_SESSION_RESTORED) {
        char linea[22];
        snprintf(linea, sizeof(linea), "Sin red (join %d)", estado);
        mostrarEnPantalla(linea, "Reintento en 60 s", (modoSOS || cancelacionPendiente) ? "Alerta en espera" : textoDevEUI);
        return false;
    }

    node.setADR(false);
    node.setDatarate(DATARATE);
    mostrarEnPantalla("Red LoRaWAN OK", modoSOS ? "SOS en cola" : "Listo", textoDevEUI);
    return true;
}

/**
 * @brief Arma y envía una trama de EcoGuard, y espera el ACK si es una alerta.
 *
 * Incluye la posición solo si se recibió hace menos de VIGENCIA_POSICION. Las alertas y las
 * cancelaciones van confirmadas: el ACK de la central es la confirmación que ve el visitante. Imprime
 * la trama en hexadecimal por el puerto serial y actualiza la pantalla y el estado BLE.
 * @param cancelacion true para enviar la cancelación (bandera 0x04) en lugar de la alerta o el reporte.
 * @return true si la central confirmó la trama con ACK.
 */
bool enviarTrama(bool cancelacion) {
    int32_t lat, lon;
    bool conGPS;
    portENTER_CRITICAL(&candado);
    conGPS = hayPosicion && (millis() - posicionRecibidaEn < VIGENCIA_POSICION);
    lat = latE6;
    lon = lonE6;
    portEXIT_CRITICAL(&candado);

    // 11 bytes como máximo: cabe en cualquier datarate de US915 (DR0 admite 11)
    uint8_t trama[11];
    size_t largo = 3;
    ultimaBateriaMv = leerBateriaMv();
    trama[0] = (modoSOS ? 0x01 : 0) | (conGPS ? 0x02 : 0) | (cancelacion ? 0x04 : 0);
    trama[1] = ultimaBateriaMv & 0xFF;
    trama[2] = ultimaBateriaMv >> 8;
    if (conGPS) {
        escribirInt32LE(&trama[3], lat);
        escribirInt32LE(&trama[7], lon);
        largo = 11;
    }

    bool esAlerta = modoSOS || cancelacion;
    if (esAlerta) mostrarEnPantalla(modoSOS ? "Transmitiendo SOS..." : "Enviando cancelacion", "Por favor espere", "");

    // Las alertas van confirmadas: el ACK de la central es la confirmación que ve el visitante
    LoRaWANEvent_t eventoBajada;
#ifdef SIMULAR_LORAWAN
    static uint32_t fCntSimulado = 0;
    delay(1500);  // Aproxima el tiempo en el aire más la espera de la ventana RX1
    int16_t estado = esAlerta ? 1 : RADIOLIB_ERR_NONE;  // Las alertas reciben ACK en RX1
    eventoBajada.confirming = esAlerta;
    uint32_t fCnt = fCntSimulado++;
#else
    int16_t estado = node.sendReceive(trama, largo, PUERTO_LORAWAN, esAlerta, nullptr, &eventoBajada);
    uint32_t fCnt = node.getFCntUp();
#endif
    bool ack = estado > 0 && eventoBajada.confirming;

    // La trama en hexadecimal sirve para probarla contra chirpstack/codec.js
    char hex[2 * sizeof(trama) + 1] = "";
    for (size_t i = 0; i < largo; i++) sprintf(&hex[2 * i], "%02X", trama[i]);
    Serial.printf("[LoRaWAN] uplink fCnt=%lu sos=%d gps=%d cancel=%d trama=%s: %d ack=%d\n",
                  (unsigned long)fCnt, modoSOS, conGPS, cancelacion, hex, estado, ack);

    if (modoSOS) {
        if (ack) alertaConfirmada = true;
        if (estado < RADIOLIB_ERR_NONE) mostrarEnPantalla("ERROR AL ENVIAR", "Reintento en 30 s", "");
        else if (alertaConfirmada) mostrarEnPantalla("SOS RECIBIDO", "La central tiene", "tu alerta");
        else mostrarEnPantalla("SOS ENVIADO", "Sin confirmacion aun", "Reintento en 30 s");
    } else if (cancelacion) {
        mostrarEnPantalla(ack ? "Alerta cancelada" : "Cancelacion enviada", ack ? "Confirmado" : "Sin confirmacion aun", "");
    }

    publicarEstado();
    return ack;
}

/**
 * @brief Apaga el nodo: guarda la sesión LoRaWAN y entra en deep sleep.
 *
 * Copia la sesión en la memoria RTC (sesionGuardada) para no repetir el join al encender, apaga la
 * pantalla y la radio, y fija los pines del FEM y de VEXT durante el sueño: flotando, podrían seguir
 * consumiendo. El botón PRG despierta al nodo, que arranca de nuevo desde setup().
 * @note No regresa.
 */
void apagarNodo() {
    mostrarEnPantalla("Apagando sistema...", "Hasta pronto", "");
    delay(2000);

    if (node.isActivated()) {
        memcpy(sesionGuardada, node.getBufferSession(), RADIOLIB_LORAWAN_SESSION_BUF_SIZE);
        haySesionGuardada = true;
    }

    u8g2.setPowerSave(1);
    radio.sleep();

    // Se fijan los pines durante el deep sleep: flotando, el FEM y Vext podrían seguir consumiendo
    digitalWrite(FEM_CSD, LOW);
    digitalWrite(FEM_POWER, LOW);
    digitalWrite(VEXT, HIGH);
    gpio_hold_en((gpio_num_t)FEM_CSD);
    gpio_hold_en((gpio_num_t)FEM_POWER);
    gpio_hold_en((gpio_num_t)VEXT);
    gpio_deep_sleep_hold_en();

    esp_deep_sleep_start();
}

/**
 * @brief Sigue el botón desde que se presiona hasta reconocer el gesto.
 *
 * Bloquea solo mientras dura el gesto. Si el botón se mantiene, a los AVISO_PULSACION ms la
 * pantalla pide seguir presionando (salvo con una alerta activa). Una serie de clics termina cuando
 * pasa PAUSA_ENTRE_CLICS sin volver a presionar.
 * @pre El botón está presionado (LOW) al llamarla.
 * @return GESTO_MANTENIDO, GESTO_TRIPLE_CLIC (3 o más clics) o GESTO_CLIC.
 */
GestoBoton leerGestoBoton() {
    uint8_t clics = 0;
    while (true) {
        unsigned long inicio = millis();
        bool avisado = false;
        while (digitalRead(BOTON_PRG) == LOW) {
            unsigned long presionado = millis() - inicio;
            if (presionado >= PULSACION_SOS) return GESTO_MANTENIDO;
            if (!avisado && !modoSOS && clics == 0 && presionado >= AVISO_PULSACION) {
                mostrarEnPantalla("Manten presionado", "para enviar SOS", "");
                avisado = true;
            }
            delay(10);
        }
        clics++;
        delay(REBOTE_BOTON);

        unsigned long soltado = millis();
        while (digitalRead(BOTON_PRG) == HIGH) {
            if (millis() - soltado >= PAUSA_ENTRE_CLICS) return clics >= 3 ? GESTO_TRIPLE_CLIC : GESTO_CLIC;
            delay(10);
        }
        delay(REBOTE_BOTON);
    }
}

/**
 * @brief Ejecuta la acción del gesto del botón.
 *
 * - Mantenido: pide el SOS (o, si ya hay uno, recuerda cómo cancelarlo).
 * - Tres clics: pide la cancelación o, sin alerta activa, apaga el nodo.
 * - Clic: muestra el estado de la alerta, de la red y el DevEUI.
 */
void atenderBoton() {
    switch (leerGestoBoton()) {
        case GESTO_MANTENIDO:
            esperarSoltarBoton = true;  // Si sigue presionado no debe contar como otro gesto
            if (modoSOS) mostrarEnPantalla("SOS ACTIVO", "3 clics: cancelar", "");
            else pedidoSOS = true;
            break;
        case GESTO_TRIPLE_CLIC:
            if (modoSOS) pedidoCancelar = true;
            else apagarNodo();
            break;
        case GESTO_CLIC:
            mostrarEnPantalla(modoSOS ? "SOS ACTIVO" : "Heltec Activo",
                              enRed() ? TEXTO_EN_RED : "Sin red LoRaWAN",
                              textoDevEUI);
            break;
    }
}

/**
 * @brief Recibe los comandos que el teléfono escribe en la característica CHARACTERISTIC_UUID.
 *
 * Corre en la tarea de BLE, no en loop(): solo guarda la posición y levanta banderas (pedidoSOS,
 * pedidoCancelar), y loop() hace el resto.
 */
class MyCallbacks: public BLECharacteristicCallbacks {
    /**
     * @brief Procesa un comando del teléfono.
     *
     * CMD_SOS y CMD_POSICION traen [comando][banderas][lat int32][lon int32]; la posición solo se
     * guarda si el bit 0 de banderas indica que el teléfono tiene posición GPS. CMD_CANCELAR no trae
     * datos. Los comandos incompletos o desconocidos se ignoran.
     * @param pCharacteristic Característica escrita por el teléfono.
     */
    void onWrite(BLECharacteristic *pCharacteristic) {
        uint8_t *datos = pCharacteristic->getData();
        size_t largo = pCharacteristic->getLength();
        if (largo == 0) return;

        uint8_t comando = datos[0];
        Serial.printf("[BLE] comando 0x%02X (%u bytes)\n", comando, (unsigned)largo);
        if ((comando == CMD_SOS || comando == CMD_POSICION) && largo >= 10) {
            if (datos[1] & 0x01) {  // El celular tiene fix GPS
                portENTER_CRITICAL(&candado);
                latE6 = leerInt32LE(&datos[2]);
                lonE6 = leerInt32LE(&datos[6]);
                posicionRecibidaEn = millis();
                hayPosicion = true;
                portEXIT_CRITICAL(&candado);
            }
            if (comando == CMD_SOS) pedidoSOS = true;
        } else if (comando == CMD_CANCELAR) {
            pedidoCancelar = true;
        }
    }
};

/**
 * @brief Sigue la conexión y desconexión del teléfono por BLE.
 */
class ServerCallbacks: public BLEServerCallbacks {
    /**
     * @brief Un teléfono se conectó: lo anota para que loop() lo muestre y le publique el estado.
     * @param pServer Servidor BLE.
     */
    void onConnect(BLEServer* pServer) {
        celularConectado = true;
        cambioConexion = true;
    }
    /**
     * @brief El teléfono se desconectó: lo anota y vuelve a anunciarse para que pueda reconectarse.
     *
     * Una alerta activa sigue transmitiéndose aunque el teléfono se desconecte.
     * @param pServer Servidor BLE.
     */
    void onDisconnect(BLEServer* pServer) {
        celularConectado = false;
        cambioConexion = true;
        pServer->startAdvertising();
    }
};

/**
 * @brief Arranque del nodo (también al despertar del deep sleep).
 *
 * -# Configura el botón PRG como fuente para despertar.
 * -# Baja la CPU a 80 MHz para ahorrar batería.
 * -# Enciende VEXT y prepara la lectura de la batería.
 * -# Inicia la pantalla.
 * -# Enciende el FEM e inicia la radio; si falla, se detiene con "ERROR DE RADIO".
 * -# Carga las credenciales LoRaWAN y los nonces guardados; si hay una sesión en memoria RTC, la
 *    restaura sin salir al aire. El join en sí se hace en loop() para no bloquear el arranque.
 * -# Inicia el servidor BLE con el nombre "EcoGuard-" y los últimos 4 dígitos del DevEUI.
 */
void setup() {
    Serial.begin(115200);

    // 0. CONFIGURACIÓN DEL BOTÓN DE ENCENDIDO/APAGADO
    pinMode(BOTON_PRG, INPUT_PULLUP);
    esp_sleep_enable_ext0_wakeup(GPIO_NUM_0, 0);

    // 1. BAJAR VELOCIDAD DEL PROCESADOR (Ahorro de batería)
    setCpuFrequencyMhz(80);

    // 2. ENCENDER EL PIN DE ENERGÍA (se liberan los pines fijados antes del deep sleep)
    pinMode(VEXT, OUTPUT);
    digitalWrite(VEXT, LOW);
    gpio_hold_dis((gpio_num_t)VEXT);
    gpio_deep_sleep_hold_dis();
    pinMode(ADC_CTRL, OUTPUT);
    digitalWrite(ADC_CTRL, LOW);
    analogSetPinAttenuation(BATTERY_PIN, ADC_2_5db);
    delay(50);

    // 3. INICIALIZAR PANTALLA OLED
    pinMode(OLED_RST, OUTPUT);
    digitalWrite(OLED_RST, HIGH);
    u8g2.begin();
    u8g2.setContrast(255);
    u8g2.setFont(u8g2_font_6x10_tf);

    mostrarEnPantalla("Iniciando sistema...", "CPU a 80MHz", "");
    delay(1000);

    // 4. INICIALIZAR RADIO LORA (primero el amplificador de la V4)
    encenderFEM();
    int estado = radio.begin(915.0, 125.0, 9, 7, RADIOLIB_SX126X_SYNC_WORD_PRIVATE, 10, 8, RADIO_TCXO_V);
    if (estado != RADIOLIB_ERR_NONE) {
        mostrarEnPantalla("ERROR DE RADIO", "Revisar antena", "");
        while (true);
    }
    mostrarEnPantalla("Radio OK", tipoFEM == FEM_KCT8103L ? "Placa V4.3 (KCT8103L)" : "Placa V4.2 (GC1109)", "");
    delay(1000);
#ifdef SIMULAR_LORAWAN
    mostrarEnPantalla("MODO SIMULACION", "Sin gateway: ACK", "simulado");
    delay(1500);
#endif

    // 5. CREDENCIALES LORAWAN (el join se hace en loop() para no bloquear el arranque)
#ifdef LORAWAN_DEV_EUI
    devEUI = LORAWAN_DEV_EUI;
#else
    devEUI = devEuiDesdeMac();
#endif
    snprintf(textoDevEUI, sizeof(textoDevEUI), "%08lX%08lX", (unsigned long)(devEUI >> 32), (unsigned long)(devEUI & 0xFFFFFFFF));
    Serial.printf("[LoRaWAN] DevEUI: %s\n", textoDevEUI);

    node.beginOTAA(joinEUI, devEUI, nwkKey, appKey);
    almacen.begin("lorawan", false);
    if (almacen.isKey("nonces")) {
        uint8_t nonces[RADIOLIB_LORAWAN_NONCES_BUF_SIZE];
        almacen.getBytes("nonces", nonces, sizeof(nonces));
        node.setBufferNonces(nonces);

        // Tras apagar con el botón se recupera la sesión sin volver a salir al aire
        if (haySesionGuardada && node.setBufferSession(sesionGuardada) == RADIOLIB_ERR_NONE) {
            intentarUnirse();
        }
    }

    // 6. INICIALIZAR BLUETOOTH (el nombre lleva los últimos 4 dígitos del DevEUI para distinguir nodos)
    char nombreBLE[20];
    snprintf(nombreBLE, sizeof(nombreBLE), "EcoGuard-%s", &textoDevEUI[12]);
    BLEDevice::init(nombreBLE);
    BLEServer *pServer = BLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks());
    BLEService *pService = pServer->createService(SERVICE_UUID);
    BLECharacteristic *pCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID, BLECharacteristic::PROPERTY_WRITE
    );
    pCharacteristic->setCallbacks(new MyCallbacks());
    caracteristicaEstado = pService->createCharacteristic(
        ESTADO_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
    );
    caracteristicaEstado->addDescriptor(new BLE2902());
    publicarEstado();
    pService->start();
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    BLEDevice::startAdvertising();

    mostrarEnPantalla(nombreBLE, "DevEUI:", textoDevEUI);
}

/**
 * @brief Ciclo principal, cada ~100 ms.
 *
 * -# Atiende el botón PRG.
 * -# Apaga la pantalla tras TIEMPO_PANTALLA_ACTIVA sin cambios.
 * -# Muestra los cambios de conexión del teléfono.
 * -# Atiende los pedidos de SOS y de cancelación (del teléfono o del botón). Un SOS hace que la
 *    primera trama salga de inmediato.
 * -# Sin red, intenta unirse cada REINTENTO_JOIN. Con red, envía la siguiente trama cuando toca:
 *    cada INTERVALO_SOS con alerta o cancelación pendiente, y cada INTERVALO_REPORTE si no. La
 *    cancelación se da por terminada con el ACK o tras MAX_INTENTOS_CANCELACION envíos.
 */
void loop() {
    // --- BOTÓN FÍSICO ---
    if (digitalRead(BOTON_PRG) == HIGH) esperarSoltarBoton = false;
    else if (!esperarSoltarBoton) atenderBoton();

    // --- GESTIÓN DE APAGADO DE PANTALLA (Inactividad) ---
    if (pantallaEncendida && (millis() - tiempoUltimaAccion > TIEMPO_PANTALLA_ACTIVA)) {
        u8g2.setPowerSave(1);
        pantallaEncendida = false;
    }

    // --- EVENTOS DEL CELULAR ---
    if (cambioConexion) {
        cambioConexion = false;
        if (celularConectado) {
            mostrarEnPantalla("Celular Conectado", modoSOS ? "SOS ACTIVO" : "Listo para SOS", "");
            publicarEstado();
        } else {
            mostrarEnPantalla("Celular Desconectado", modoSOS ? "El SOS sigue activo" : "Esperando reconexion...", "");
        }
    }

    if (pedidoSOS) {
        pedidoSOS = false;
        if (!modoSOS) {
            modoSOS = true;
            alertaConfirmada = false;
            cancelacionPendiente = false;
            proximoEnvio = millis(); // La primera trama sale de inmediato
            mostrarEnPantalla("Alerta recibida", enRed() ? "Preparando LoRa..." : "Sin red: en espera", "");
            publicarEstado();
        }
    }

    if (pedidoCancelar) {
        pedidoCancelar = false;
        if (modoSOS) {
            modoSOS = false;
            cancelacionPendiente = true;
            intentosCancelacion = 0;
            proximoEnvio = millis();
            mostrarEnPantalla("Cancelacion recibida", enRed() ? "Preparando LoRa..." : "Sin red: en espera", "");
            publicarEstado();
        } else {
            mostrarEnPantalla("Sin alerta activa", "Nada que cancelar", "");
        }
    }

    // --- GESTIÓN DE LA RED Y ENVÍOS LORAWAN ---
    if (!enRed()) {
        if ((long)(millis() - proximoIntentoJoin) >= 0) {
            if (intentarUnirse()) proximoEnvio = millis(); // El primer reporte registra el contacto
            else proximoIntentoJoin = millis() + REINTENTO_JOIN;
            publicarEstado();
        }
    } else if ((long)(millis() - proximoEnvio) >= 0) {
        bool cancelacion = cancelacionPendiente;
        bool ack = enviarTrama(cancelacion);
        if (cancelacion && (ack || ++intentosCancelacion >= MAX_INTENTOS_CANCELACION)) {
            cancelacionPendiente = false;
        }
        proximoEnvio = millis() + ((modoSOS || cancelacionPendiente) ? INTERVALO_SOS : INTERVALO_REPORTE);
    }

    delay(100);
}
