/**
 * @file lorawan_config.example.h
 * @brief Plantilla de las credenciales LoRaWAN del nodo.
 *
 * Copia este archivo como lorawan_config.h (misma carpeta) y pon las llaves del dispositivo
 * que registraste en ChirpStack. lorawan_config.h está en .gitignore: las llaves no se suben al repo
 * (y tampoco se incluyen en esta documentación).
 */
#pragma once

/// JoinEUI (antes AppEUI). Para dispositivos propios se recomienda dejarlo en ceros (LoRa Alliance TR007).
#define LORAWAN_JOIN_EUI 0x0000000000000000

// DevEUI: si no lo defines, se deriva de la MAC del ESP32 (único por placa) y se muestra
// en la pantalla al encender. Ese es el valor que registras en ChirpStack y en el admin de EcoGuard.
// #define LORAWAN_DEV_EUI 0x0000000000000000

/**
 * @brief AppKey: llave raíz de aplicación (16 bytes separados por comas), de un perfil LoRaWAN 1.1.0.
 *
 * De ella y de los nonces del join se deriva la AppSKey, que cifra la carga útil de punta a punta
 * (del nodo a la aplicación). En ChirpStack: dispositivo, pestaña "OTAA keys".
 */
#define LORAWAN_APP_KEY 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
/**
 * @brief NwkKey: llave raíz de red (16 bytes separados por comas), de un perfil LoRaWAN 1.1.0.
 *
 * De ella se derivan las llaves de sesión de red, que firman las tramas (MIC) y cifran los comandos
 * MAC. En ChirpStack: dispositivo, pestaña "OTAA keys".
 */
#define LORAWAN_NWK_KEY 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00

/**
 * @brief Sub-banda US915 (grupo de 8 canales): debe coincidir con el gateway y con ChirpStack.
 *
 * ChirpStack region_us915_0 (canales 0–7) → 1, region_us915_1 (canales 8–15) → 2, etc.
 */
#define LORAWAN_SUB_BANDA 2
