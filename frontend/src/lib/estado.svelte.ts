/**
 * @file
 * @brief Estado compartido del panel y acciones del vigilante.
 *
 * Usa las runas de Svelte 5 ($state): al cambiar el estado se actualizan todas las secciones que lo
 * muestran. Las acciones llaman a la API, recargan los datos y devuelven un Mensaje para la pantalla.
 */
import * as api from './api';
import type { Alerta, Incidente, Mensaje, Nodo, NuevoPrestamo, PrestamoVigente } from './tipos';

/**
 * @brief Estado compartido por todas las secciones del menú, cargado desde el backend.
 *
 * - alertasActivas: incidentes abiertos con la ficha del visitante.
 * - nodos: nodos registrados.
 * - historial: incidentes cerrados.
 * - prestamos: préstamos vigentes.
 * - conexion: estado del WebSocket: 'conectando', 'conectado' o 'desconectado'.
 * - errorCarga: mensaje si falló la última carga; null si fue correcta.
 */
export const panel = $state({
	alertasActivas: [] as Alerta[],
	nodos: [] as Nodo[],
	historial: [] as Incidente[],
	prestamos: [] as PrestamoVigente[],
	conexion: 'conectando' as 'conectando' | 'conectado' | 'desconectado',
	errorCarga: null as string | null
});

/** Hora compartida (en ms) para los "Hace X min": se actualiza cada 30 s para que avancen sin recargar. */
export const reloj = $state({ ahora: Date.now() });

/** Número de la carga más reciente: descarta las respuestas de cargas anteriores que lleguen tarde. */
let ultimaCarga = 0;

/**
 * @brief Carga alertas, nodos, historial y préstamos del backend en paralelo y actualiza panel.
 *
 * Si llegan varios eventos seguidos, solo se aplica la respuesta de la carga más reciente. Si falla,
 * deja el mensaje en panel.errorCarga.
 * @returns Promesa que se cumple al terminar la carga, con o sin error.
 */
export async function cargarDatos() {
	// Si llegan varios eventos seguidos, solo se aplica la respuesta de la carga más reciente
	const estaCarga = ++ultimaCarga;
	try {
		const [alertas, nodos, historial, prestamos] = await Promise.all([
			api.obtenerIncidentesActivos(),
			api.obtenerDispositivos(),
			api.obtenerHistorial(),
			api.obtenerPrestamos()
		]);
		if (estaCarga !== ultimaCarga) return;
		panel.alertasActivas = alertas;
		panel.nodos = nodos;
		panel.historial = historial;
		panel.prestamos = prestamos;
		panel.errorCarga = null;
	} catch (error) {
		if (estaCarga !== ultimaCarga) return;
		panel.errorCarga = `No se pudo cargar la información del backend (${(error as Error).message})`;
	}
}

/**
 * @brief Carga los datos y los mantiene al día mientras el panel está abierto.
 *
 * Los mensajes del WebSocket (trama nueva o cualquier cambio en nodos e incidentes) recargan todo;
 * los avisos seguidos se agrupan en una sola recarga. Si se cae la conexión reintenta cada 3 s, y al
 * reconectar recarga por si se perdieron eventos. También actualiza reloj cada 30 s.
 * @returns Función que cierra el WebSocket y detiene los temporizadores.
 */
export function iniciarPanel(): () => void {
	let socket: WebSocket | null = null;
	let reintento: ReturnType<typeof setTimeout>;
	let recarga: ReturnType<typeof setTimeout>;
	let detenido = false;

	function conectar() {
		panel.conexion = 'conectando';
		socket = new WebSocket(api.URL_WEBSOCKET);
		socket.onopen = () => {
			panel.conexion = 'conectado';
			cargarDatos();
		};
		// Una trama genera varios avisos seguidos (nodo, incidente, alerta): se agrupan en una sola recarga
		socket.onmessage = () => {
			clearTimeout(recarga);
			recarga = setTimeout(cargarDatos, 100);
		};
		socket.onclose = () => {
			panel.conexion = 'desconectado';
			if (!detenido) reintento = setTimeout(conectar, 3000);
		};
	}

	cargarDatos();
	conectar();
	const intervaloReloj = setInterval(() => (reloj.ahora = Date.now()), 30_000);

	return () => {
		detenido = true;
		clearTimeout(reintento);
		clearTimeout(recarga);
		clearInterval(intervaloReloj);
		socket?.close();
	};
}

/**
 * @brief Ejecuta una acción del vigilante y recarga los datos.
 * @param accion Llamada a la API.
 * @param exito Mensaje a mostrar si la acción tuvo éxito.
 * @returns Mensaje de éxito, o el error del backend.
 */
async function ejecutar(accion: () => Promise<void>, exito: string): Promise<Mensaje> {
	try {
		await accion();
		await cargarDatos();
		return { texto: exito, error: false };
	} catch (error) {
		return { texto: (error as Error).message, error: true };
	}
}

/**
 * @brief Marca un incidente como resuelto (CU-04).
 * @param idIncidente Clave del incidente.
 * @returns Promesa con el Mensaje para la pantalla.
 */
export function resolverAlerta(idIncidente: number) {
	return ejecutar(() => api.cambiarEstadoIncidente(idIncidente, 'RESUELTO'), 'Incidente resuelto.');
}

/**
 * @brief Registra un nodo nuevo (CU-06).
 * @param devEui DevEUI de 16 dígitos hexadecimales.
 * @param nombre Nombre legible.
 * @returns Promesa con el Mensaje para la pantalla.
 */
export function registrarNodo(devEui: string, nombre: string) {
	return ejecutar(
		() => api.registrarDispositivo(devEui, nombre),
		'Dispositivo registrado con éxito.'
	);
}

/**
 * @brief Presta un nodo a un visitante (CU-13).
 * @param datos Datos del visitante y DevEUI del nodo.
 * @returns Promesa con el Mensaje para la pantalla.
 */
export function prestarNodo(datos: NuevoPrestamo) {
	return ejecutar(() => api.prestarNodo(datos), 'Préstamo registrado.');
}

/**
 * @brief Registra la devolución de un nodo (CU-14).
 * @param prestamo Préstamo vigente.
 * @returns Promesa con el Mensaje para la pantalla.
 */
export function devolverNodo(prestamo: PrestamoVigente) {
	return ejecutar(
		() => api.registrarDevolucion(prestamo.idAsignacion),
		`Devolución de ${prestamo.nodo} registrada.`
	);
}

/**
 * @brief Habilita un nodo inhabilitado o inhabilita uno habilitado (CU-07).
 * @param nodo Nodo a cambiar.
 * @returns Promesa con el Mensaje para la pantalla.
 */
export function alternarHabilitado(nodo: Nodo) {
	const activo = !nodo.activo;
	return ejecutar(
		() => api.cambiarHabilitado(nodo.devEui, activo),
		`Dispositivo ${activo ? 'habilitado' : 'inhabilitado'} correctamente.`
	);
}
