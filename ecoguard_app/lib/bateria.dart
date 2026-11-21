/// @brief Porcentaje de carga de la batería del nodo a partir de su voltaje.
library;

/// Carga restante de una celda LiPo 1S según su voltaje en reposo, en pares [mV, %]. Es la misma
/// curva del panel web (frontend/src/lib/formato.ts) y de la pantalla del nodo, para que los tres
/// muestren el mismo porcentaje. El 0 % está en 3.3 V, donde RNF-05 da la celda por agotada.
const _curvaLipo = [
  [3300, 0], [3610, 5], [3690, 10], [3710, 15], [3730, 20], [3750, 25], [3770, 30],
  [3790, 35], [3800, 40], [3820, 45], [3840, 50], [3850, 55], [3870, 60], [3910, 65],
  [3950, 70], [3980, 75], [4020, 80], [4080, 85], [4110, 90], [4150, 95], [4200, 100],
];

/// Porcentaje por debajo del cual se avisa «Batería del nodo baja» (CU-10, FA1).
const umbralBateriaBaja = 20;

/// @brief Convierte el voltaje de la batería en porcentaje de carga.
///
/// Se interpola linealmente entre los dos puntos de la curva que rodean al voltaje.
/// @param mv Voltaje de la celda en mV.
/// @return Carga restante de 0 a 100 %.
int porcentajeBateria(int mv) {
  if (mv <= _curvaLipo.first[0]) return 0;
  for (var i = 1; i < _curvaLipo.length; i++) {
    final [mvAlto, pctAlto] = _curvaLipo[i];
    if (mv <= mvAlto) {
      final [mvBajo, pctBajo] = _curvaLipo[i - 1];
      return (pctBajo + (mv - mvBajo) / (mvAlto - mvBajo) * (pctAlto - pctBajo)).round();
    }
  }
  return 100;
}
