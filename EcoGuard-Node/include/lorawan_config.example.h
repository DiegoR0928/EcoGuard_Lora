// Copia este archivo como lorawan_config.h (misma carpeta) y pon las llaves del dispositivo
// que registraste en ChirpStack. lorawan_config.h está en .gitignore: las llaves no se suben al repo.
#pragma once

// JoinEUI (antes AppEUI). Para dispositivos propios se recomienda dejarlo en ceros (LoRa Alliance TR007).
#define LORAWAN_JOIN_EUI 0x0000000000000000

// DevEUI: si no lo defines, se deriva de la MAC del ESP32 (único por placa) y se muestra
// en la pantalla al encender. Ese es el valor que registras en ChirpStack y en el admin de EcoGuard.
// #define LORAWAN_DEV_EUI 0x0000000000000000

// Llaves OTAA de un perfil LoRaWAN 1.1.0 (ChirpStack: dispositivo → pestaña "OTAA keys").
#define LORAWAN_APP_KEY 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
#define LORAWAN_NWK_KEY 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00

// Sub-banda US915: debe coincidir con la configuración del gateway y de ChirpStack.
// ChirpStack region_us915_0 (canales 0–7) → 1, region_us915_1 (canales 8–15) → 2, etc.
#define LORAWAN_SUB_BANDA 2
