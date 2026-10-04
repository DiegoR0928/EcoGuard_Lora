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

// Llaves de ChirpStack. Si falta, copia include/lorawan_config.example.h como lorawan_config.h
#include "lorawan_config.h"

// Protocolo BLE, formato de la trama LoRaWAN y puesta en marcha: ver README.md

// --- PIN BOTÓN (Para encender/apagar y despertar pantalla) ---
#define BOTON_PRG 0

// --- PINES DE ENERGÍA Y BATERÍA (Heltec V4) ---
#define VEXT 36
#define BATTERY_PIN 1
#define ADC_CTRL 37                        // En la V4 el medidor se activa en HIGH (en la V3 era LOW)
#define ADC_MULTIPLICADOR (4.9f * 1.045f)  // Divisor 390k/100k, con la corrección que usa Meshtastic

// --- PINES LORA ---
#define RADIO_NSS    8
#define RADIO_DIO1   14
#define RADIO_NRST   12
#define RADIO_BUSY   13
#define RADIO_TCXO_V 1.8
SX1262 radio = new Module(RADIO_NSS, RADIO_DIO1, RADIO_NRST, RADIO_BUSY);

// --- AMPLIFICADOR DE RADIO (FEM) DE LA V4 ---
// La V4 amplifica la salida del SX1262 hasta ~28 dBm. Si el FEM no se enciende,
// la radio reporta envíos exitosos pero la señal casi no sale de la antena.
#define FEM_POWER    7   // LDO que alimenta el FEM
#define FEM_CSD      2   // Habilita el chip (HIGH) en ambas revisiones
#define FEM_CPS_V4_2 46  // V4.2 (GC1109): HIGH = amplificador completo al transmitir
#define FEM_CTX_V4_3 5   // V4.3 (KCT8103L): HIGH al transmitir, LOW al recibir (LNA)

enum TipoFEM { FEM_GC1109, FEM_KCT8103L };
TipoFEM tipoFEM;

// El pin de cada revisión se conmuta igual: HIGH al transmitir y LOW el resto del tiempo.
// La selección de camino TX/RX la hace DIO2 del SX1262 automáticamente.
uint32_t pinesFEM[Module::RFSWITCH_MAX_PINS];
static const Module::RfSwitchMode_t tablaFEM[] = {
    { Module::MODE_IDLE, { LOW } },
    { Module::MODE_RX,   { LOW } },
    { Module::MODE_TX,   { HIGH } },
    END_OF_MODE_TABLE,
};

// --- PINES PANTALLA OLED ---
#define OLED_SDA 17
#define OLED_SCL 18
#define OLED_RST 21
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, OLED_RST, OLED_SCL, OLED_SDA);

// --- UUIDs BLUETOOTH ---
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"  // Celular → nodo (comandos)
#define ESTADO_UUID         "d2b0f5a1-7c3e-4b8a-9f61-3a5e8c1d4e72"  // Nodo → celular (notificaciones)

#define CMD_SOS      0x01
#define CMD_POSICION 0x02
#define CMD_CANCELAR 0x03

// --- LORAWAN ---
const LoRaWANBand_t REGION = US915;
const uint8_t PUERTO_LORAWAN = 1;
// DR1 = SF9. El nodo se mueve con el visitante, así que se fija el datarate en lugar de usar ADR
const uint8_t DATARATE = 1;

const unsigned long INTERVALO_SOS = 30UL * 1000;             // Reenvío mientras la alerta está activa
const unsigned long INTERVALO_REPORTE = 10UL * 60 * 1000;    // Reporte periódico para el monitoreo de salud (CU-5)
const unsigned long REINTENTO_JOIN = 60UL * 1000;
const unsigned long VIGENCIA_POSICION = 5UL * 60 * 1000;     // Una posición más vieja ya no se envía
const uint8_t MAX_INTENTOS_CANCELACION = 3;

uint64_t joinEUI = LORAWAN_JOIN_EUI;
uint64_t devEUI = 0;
uint8_t appKey[] = { LORAWAN_APP_KEY };
uint8_t nwkKey[] = { LORAWAN_NWK_KEY };
LoRaWANNode node(&radio, &REGION, LORAWAN_SUB_BANDA);
Preferences almacen;
char textoDevEUI[17];

#ifdef SIMULAR_LORAWAN
// Entorno "sin_gateway" de platformio.ini: no hay join, cada trama se imprime por serial
// y se simula el ACK de la central. Solo para probar la pantalla y el Bluetooth sin gateway
const char *TEXTO_EN_RED = "Red SIMULADA";
bool enRed() { return true; }
#else
const char *TEXTO_EN_RED = "Red LoRaWAN OK";
bool enRed() { return node.isActivated(); }
#endif

// La sesión sobrevive al deep sleep en memoria RTC: al volver a encender no hace falta otro join
RTC_DATA_ATTR uint8_t sesionGuardada[RADIOLIB_LORAWAN_SESSION_BUF_SIZE];
RTC_DATA_ATTR bool haySesionGuardada = false;

// --- ESTADO COMPARTIDO CON LOS CALLBACKS BLE (corren en otra tarea) ---
portMUX_TYPE candado = portMUX_INITIALIZER_UNLOCKED;
volatile bool pedidoSOS = false;
volatile bool pedidoCancelar = false;
volatile bool celularConectado = false;
volatile bool cambioConexion = false;
int32_t latE6 = 0;   // Grados × 1 000 000
int32_t lonE6 = 0;
unsigned long posicionRecibidaEn = 0;
bool hayPosicion = false;

// --- ESTADO DEL NODO ---
bool modoSOS = false;
bool cancelacionPendiente = false;
uint8_t intentosCancelacion = 0;
bool alertaConfirmada = false;  // La central respondió con ACK a alguna trama de esta alerta
uint16_t ultimaBateriaMv = 0;
unsigned long proximoEnvio = 0;
unsigned long proximoIntentoJoin = 0;
BLECharacteristic *caracteristicaEstado = nullptr;

// --- VARIABLES DE AHORRO DE ENERGÍA ---
unsigned long tiempoUltimaAccion = 0;
const unsigned long TIEMPO_PANTALLA_ACTIVA = 10000; // 10 segundos
bool pantallaEncendida = true;

void escribirInt32LE(uint8_t *destino, int32_t valor) {
    for (int i = 0; i < 4; i++) destino[i] = (uint32_t)valor >> (8 * i);
}

int32_t leerInt32LE(const uint8_t *origen) {
    return (int32_t)((uint32_t)origen[0] | ((uint32_t)origen[1] << 8) | ((uint32_t)origen[2] << 16) | ((uint32_t)origen[3] << 24));
}

// Voltaje de la celda en milivoltios (el SDD pide mV: la curva de descarga de una LiPo no es lineal)
uint16_t leerBateriaMv() {
    digitalWrite(ADC_CTRL, HIGH);
    delay(10); // Estabilizar voltaje

    uint32_t suma = 0;
    for (int i = 0; i < 8; i++) suma += analogReadMilliVolts(BATTERY_PIN);

    digitalWrite(ADC_CTRL, LOW);
    return (suma / 8) * ADC_MULTIPLICADOR;
}

// Solo para la pantalla: aproximación lineal entre 3.3 V (vacía) y 4.2 V (llena)
int porcentajeBateria(uint16_t mv) {
    return constrain(map(mv, 3300, 4200, 0, 100), 0, 100);
}

// Función para actualizar y despertar la pantalla con barra de estado
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

// Enciende el FEM de la V4 y detecta la revisión: el pin CSD tiene pull-down interno
// en el GC1109 (V4.2) y pull-up en el KCT8103L (V4.3). Debe llamarse antes de radio.begin()
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

// EUI-64 derivado de la MAC del ESP32 (se inserta FFFE a la mitad): único y fijo para cada placa
uint64_t devEuiDesdeMac() {
    uint64_t mac = ESP.getEfuseMac();  // El primer byte de la MAC queda en el byte menos significativo
    uint8_t m[6];
    for (int i = 0; i < 6; i++) m[i] = mac >> (8 * i);
    return ((uint64_t)m[0] << 56) | ((uint64_t)m[1] << 48) | ((uint64_t)m[2] << 40) | (0xFFULL << 32) |
           (0xFEULL << 24) | ((uint64_t)m[3] << 16) | ((uint64_t)m[4] << 8) | m[5];
}

// Notifica a la app: batería en mV y banderas de estado (ver README.md)
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

bool intentarUnirse() {
    mostrarEnPantalla("Conectando a la red", "LoRaWAN...", textoDevEUI);
    int16_t estado = node.activateOTAA();

    // Los nonces avanzan en cada intento; si no se guardan, ChirpStack rechaza el join tras reiniciar
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

// Arma y envía una trama. Devuelve true si la central la confirmó con ACK
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

// Callback BLE de Recepción de Datos
class MyCallbacks: public BLECharacteristicCallbacks {
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

// Callback BLE de Conexión/Desconexión
class ServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
        celularConectado = true;
        cambioConexion = true;
    }
    void onDisconnect(BLEServer* pServer) {
        celularConectado = false;
        cambioConexion = true;
        pServer->startAdvertising();
    }
};

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

void loop() {
    // --- LÓGICA DEL BOTÓN MULTIFUNCIÓN ---
    if (digitalRead(BOTON_PRG) == LOW) {
        unsigned long tiempoInicioPresion = millis();
        bool esApagado = false;

        // Revisar cuánto tiempo se mantiene presionado
        while (digitalRead(BOTON_PRG) == LOW) {
            if (millis() - tiempoInicioPresion >= 3000) { // 3 segundos para apagar
                esApagado = true;
                break;
            }
            delay(10);
        }

        if (esApagado) {
            // --- ACCIÓN: APAGADO (DEEP SLEEP) ---
            apagarNodo();
        } else {
            // --- ACCIÓN: CLIC CORTO (DESPERTAR PANTALLA CON EL ESTADO) ---
            mostrarEnPantalla(modoSOS ? "SOS ACTIVO" : "Heltec Activo",
                              enRed() ? TEXTO_EN_RED : "Sin red LoRaWAN",
                              textoDevEUI);
        }
    }

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
