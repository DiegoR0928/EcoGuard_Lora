#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <RadioLib.h>
#include <U8g2lib.h>
#include <Wire.h>

// --- PIN BOTÓN (Para encender/apagar y despertar pantalla) ---
#define BOTON_PRG 0

// --- PINES DE ENERGÍA Y BATERÍA (Heltec V3/V4) ---
#define VEXT 36
#define BATTERY_PIN 1
#define ADC_CTRL 37

// --- PINES LORA ---
#define RADIO_NSS    8
#define RADIO_DIO1   14
#define RADIO_NRST   12
#define RADIO_BUSY   13
SX1262 radio = new Module(RADIO_NSS, RADIO_DIO1, RADIO_NRST, RADIO_BUSY);

// --- PINES PANTALLA OLED ---
#define OLED_SDA 17
#define OLED_SCL 18
#define OLED_RST 21
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, OLED_RST, OLED_SCL, OLED_SDA);

// --- UUIDs BLUETOOTH ---
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

bool flagTransmitirSOS = false;
uint8_t payloadSOS[10];

// --- VARIABLES DE AHORRO DE ENERGÍA ---
unsigned long tiempoUltimaAccion = 0;
const unsigned long TIEMPO_PANTALLA_ACTIVA = 10000; // 10 segundos
bool pantallaEncendida = true;

// Función para leer la batería
int obtenerPorcentajeBateria() {
    // Encender el medidor de batería
    pinMode(ADC_CTRL, OUTPUT);
    digitalWrite(ADC_CTRL, LOW); 
    delay(10); // Estabilizar voltaje
    
    // Leer voltaje
    int adcValue = analogRead(BATTERY_PIN);
    
    // Apagar el medidor
    digitalWrite(ADC_CTRL, HIGH); 

    // Mapeo a porcentaje
    int porcentaje = map(adcValue, 700, 1050, 0, 100);
    if (porcentaje > 100) porcentaje = 100;
    if (porcentaje < 0) porcentaje = 0;
    
    return porcentaje;
}

// Función para actualizar y despertar la pantalla con barra de estado
void mostrarEnPantalla(const char* linea1, const char* linea2, const char* linea3 = "") {
    if (!pantallaEncendida) {
        u8g2.setPowerSave(0); 
        pantallaEncendida = true;
    }
    
    int bateria = obtenerPorcentajeBateria();
    char txtBateria[10];
    sprintf(txtBateria, "%d%%", bateria);

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

// Callback BLE de Recepción de Datos
class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
        std::string rxValue = pCharacteristic->getValue();
        if (rxValue.length() == 10) {
            for(int i = 0; i < 10; i++) payloadSOS[i] = rxValue[i];
            
            mostrarEnPantalla("Alerta recibida", "Preparando LoRa...", "");
            flagTransmitirSOS = true; 
        }
    }
};

// Callback BLE de Conexión/Desconexión
class ServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
        mostrarEnPantalla("Celular Conectado", "Listo para SOS", "");
    }
    void onDisconnect(BLEServer* pServer) {
        mostrarEnPantalla("Celular Desconectado", "Esperando reconexion...", "");
        pServer->startAdvertising(); 
    }
};

void setup() {
    // 0. CONFIGURACIÓN DEL BOTÓN DE ENCENDIDO/APAGADO
    pinMode(BOTON_PRG, INPUT_PULLUP);
    esp_sleep_enable_ext0_wakeup(GPIO_NUM_0, 0); 

    // 1. BAJAR VELOCIDAD DEL PROCESADOR (Ahorro de batería)
    setCpuFrequencyMhz(80);

    // 2. ENCENDER EL PIN DE ENERGÍA
    pinMode(VEXT, OUTPUT);
    digitalWrite(VEXT, LOW); 
    delay(50);

    // 3. INICIALIZAR PANTALLA OLED
    pinMode(OLED_RST, OUTPUT);
    digitalWrite(OLED_RST, HIGH);
    u8g2.begin();
    u8g2.setContrast(255); 
    u8g2.setFont(u8g2_font_6x10_tf); 
    
    mostrarEnPantalla("Iniciando sistema...", "CPU a 80MHz", "");
    delay(1000);

    // 4. INICIALIZAR RADIO LORA
    int estado = radio.begin(915.0, 125.0, 9, 7, 0x12, 22);
    if (estado == RADIOLIB_ERR_NONE) {
        mostrarEnPantalla("LoRa: 915MHz OK", "Durmiendo radio...", "");
        radio.sleep(); // Dormir radio por defecto
    } else {
        mostrarEnPantalla("ERROR DE RADIO", "Revisar antena", "");
        while (true); 
    }
    delay(1000);

    // 5. INICIALIZAR BLUETOOTH
    BLEDevice::init("Heltec_EcoGuard");
    BLEServer *pServer = BLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks()); 
    BLEService *pService = pServer->createService(SERVICE_UUID);
    BLECharacteristic *pCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID, BLECharacteristic::PROPERTY_WRITE
    );
    pCharacteristic->setCallbacks(new MyCallbacks());
    pService->start();
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    BLEDevice::startAdvertising();
    
    mostrarEnPantalla("Sistema Ahorro Activo", "Esperando conexion...", "");
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
            if (!pantallaEncendida) u8g2.setPowerSave(0);
            mostrarEnPantalla("Apagando sistema...", "Hasta pronto", "");
            delay(2000);
            
            u8g2.setPowerSave(1);         
            digitalWrite(VEXT, HIGH);     
            radio.sleep();                
            esp_deep_sleep_start();       
        } else {
            // --- ACCIÓN: CLIC CORTO (DESPERTAR PANTALLA) ---
            if (!pantallaEncendida) {
                mostrarEnPantalla("Heltec Activo", "Buscando app...", "");
            } else {
                tiempoUltimaAccion = millis(); // Reiniciar contador de pantalla
            }
        }
    }

    // --- GESTIÓN DE APAGADO DE PANTALLA (Inactividad) ---
    if (pantallaEncendida && (millis() - tiempoUltimaAccion > TIEMPO_PANTALLA_ACTIVA)) {
        u8g2.setPowerSave(1); 
        pantallaEncendida = false;
    }

    // --- GESTIÓN DE ENVÍO LORA ---
    if (flagTransmitirSOS) {
        delay(500);
        mostrarEnPantalla("Transmitiendo SOS...", "Por favor espere", "");
        
        radio.standby(); 
        int estado_envio = radio.transmit(payloadSOS, 10); 
        radio.sleep(); 
        
        if (estado_envio == RADIOLIB_ERR_NONE) {
            mostrarEnPantalla("SOS ENVIADO OK", "Mensaje en el aire", "Esperando confirmacion");
        } else {
            mostrarEnPantalla("ERROR AL ENVIAR", "Intente de nuevo", "");
        }
        
        flagTransmitirSOS = false;
    }
    
    delay(100);
}