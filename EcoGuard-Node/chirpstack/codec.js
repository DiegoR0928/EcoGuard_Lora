// Decodificador de ChirpStack v4 para los nodos EcoGuard.
// Se pega en: Device profile → Codec → "JavaScript functions".
// Formato de la trama: ver EcoGuard-Node/README.md
//
// Devuelve los campos que lee el webhook del backend: sos, latitude, longitude, battery_mv.

function decodeUplink(input) {
  var b = input.bytes;
  if (input.fPort !== 1 || b.length < 3) {
    return { errors: ["Trama EcoGuard invalida (puerto " + input.fPort + ", " + b.length + " bytes)"] };
  }

  var banderas = b[0];
  var data = {
    sos: (banderas & 0x01) !== 0,
    cancelado: (banderas & 0x04) !== 0,
    battery_mv: b[1] | (b[2] << 8)
  };

  // Sin fix GPS la trama no trae coordenadas: el backend guarda el punto como nulo
  if ((banderas & 0x02) !== 0 && b.length >= 11) {
    data.latitude = int32LE(b, 3) / 1e6;
    data.longitude = int32LE(b, 7) / 1e6;
  }

  return { data: data };
}

// En JavaScript, << trabaja con enteros de 32 bits con signo: las coordenadas negativas salen bien
function int32LE(b, i) {
  return b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24);
}
