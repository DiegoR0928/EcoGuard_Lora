/**
 * @file
 * @brief Presentación de los datos del backend: batería, fechas, estados y texto seguro para HTML.
 *
 * El SDD deja estas conversiones a la capa de presentación.
 */
import type { EstadoIncidente } from './tipos';

/**
 * Carga restante de una celda LiPo 1S según su voltaje en reposo, en pares [mV, %]. La curva no es
 * lineal: casi toda la capacidad está entre 3.7 V y 4.0 V y por debajo de 3.7 V queda muy poco (por eso
 * el nodo envía mV y no porcentaje, SDD). El 0 % está en 3.3 V, donde RNF-05 da la celda por agotada.
 * Son valores típicos: la prueba de descarga de RNF-05 permite reemplazarlos por la curva real del nodo.
 */
const CURVA_LIPO: [number, number][] = [
	[3300, 0],
	[3610, 5],
	[3690, 10],
	[3710, 15],
	[3730, 20],
	[3750, 25],
	[3770, 30],
	[3790, 35],
	[3800, 40],
	[3820, 45],
	[3840, 50],
	[3850, 55],
	[3870, 60],
	[3910, 65],
	[3950, 70],
	[3980, 75],
	[4020, 80],
	[4080, 85],
	[4110, 90],
	[4150, 95],
	[4200, 100]
];

/**
 * @brief Convierte el voltaje de la batería en porcentaje de carga con la curva CURVA_LIPO.
 *
 * Se interpola linealmente entre los dos puntos de la curva que rodean al voltaje.
 * @param mv Voltaje en mV, o null si no se conoce.
 * @returns Carga de 0 a 100 %, o null.
 */
export function porcentajeBateria(mv: number | null): number | null {
	if (mv === null) return null;
	if (mv <= CURVA_LIPO[0][0]) return 0;
	for (let i = 1; i < CURVA_LIPO.length; i++) {
		const [mvAlto, pctAlto] = CURVA_LIPO[i];
		if (mv <= mvAlto) {
			const [mvBajo, pctBajo] = CURVA_LIPO[i - 1];
			return Math.round(pctBajo + ((mv - mvBajo) / (mvAlto - mvBajo)) * (pctAlto - pctBajo));
		}
	}
	return 100;
}

/**
 * @brief Minutos transcurridos desde una fecha.
 * @param fecha Fecha ISO 8601, o null.
 * @param ahora Hora actual en ms (reloj.ahora).
 * @returns Minutos completos (nunca negativos), o null si no hay fecha.
 */
export function minutosDesde(fecha: string | null, ahora: number): number | null {
	if (!fecha) return null;
	return Math.max(0, Math.floor((ahora - Date.parse(fecha)) / 60000));
}

/**
 * @brief Tiempo transcurrido en texto: "Hace un momento", "Hace 5 min", "Hace 2 h" o "Hace 3 d".
 * @param fecha Fecha ISO 8601, o null.
 * @param ahora Hora actual en ms (reloj.ahora).
 * @returns El texto, o "Sin contacto" si no hay fecha.
 */
export function hace(fecha: string | null, ahora: number): string {
	const minutos = minutosDesde(fecha, ahora);
	if (minutos === null) return 'Sin contacto';
	if (minutos < 1) return 'Hace un momento';
	if (minutos < 60) return `Hace ${minutos} min`;
	const horas = Math.floor(minutos / 60);
	return horas < 24 ? `Hace ${horas} h` : `Hace ${Math.floor(horas / 24)} d`;
}

/**
 * @brief Fecha y hora locales en formato corto, p. ej. 15/10/26, 10:32.
 * @param fecha Fecha ISO 8601.
 * @returns La fecha formateada para es-MX.
 */
export function fechaHora(fecha: string): string {
	return new Date(fecha).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' });
}

/**
 * @brief Escapa los caracteres especiales de HTML.
 *
 * Para textos que se insertan como HTML (popups de Leaflet): los nombres los capturan personas y
 * podrían contener etiquetas.
 * @param texto Texto a escapar.
 * @returns El texto con &, <, >, comillas y apóstrofos convertidos en entidades.
 */
export function escaparHtml(texto: string): string {
	const entidades: Record<string, string> = {
		'&': '&amp;',
		'<': '&lt;',
		'>': '&gt;',
		'"': '&quot;',
		"'": '&#39;'
	};
	return texto.replace(/[&<>"']/g, (c) => entidades[c]);
}

/**
 * @brief Fecha local en formato AAAA-MM-DD, el de los campos de fecha de HTML.
 * @param fecha Fecha ISO 8601.
 * @returns La fecha en la zona horaria del navegador.
 */
export function fechaLocal(fecha: string): string {
	const d = new Date(fecha);
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Nombre legible de cada estado de incidente. */
export const NOMBRE_ESTADO: Record<EstadoIncidente, string> = {
	ACTIVO: 'Activo',
	EN_ATENCION: 'En atención',
	RESUELTO: 'Resuelto',
	CANCELADO: 'Cancelado por el visitante',
	FALSA_ALARMA: 'Falsa alarma'
};
