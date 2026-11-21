/**
 * @file
 * @brief Comunicación con la API REST del backend de Django.
 *
 * Las respuestas llegan en snake_case y se convierten aquí a los tipos del panel (tipos.ts), para
 * que los componentes no dependan de la forma del JSON. Si el backend responde con error, las
 * funciones lanzan un Error con su mensaje.
 */
import type {
	Alerta,
	EstadoIncidente,
	Incidente,
	Nodo,
	NuevoPrestamo,
	Prestamo,
	PrestamoVigente
} from './tipos';

/** Dirección del backend: la variable VITE_API_URL o, por defecto, http://localhost:8000. */
export const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
/** Dirección del WebSocket de avisos en tiempo real: la de la API con ws:// y la ruta /ws/alertas/. */
export const URL_WEBSOCKET = `${API.replace(/^http/, 'ws')}/ws/alertas/`;

/**
 * @brief Hace una petición al backend y devuelve el cuerpo de la respuesta.
 * @param ruta Ruta de la API, p. ej. /api/dispositivos/.
 * @param opciones Opciones de fetch (método, cuerpo). Siempre se envía Content-Type: application/json.
 * @returns El JSON de la respuesta, o null si no trae cuerpo.
 * @throws Error Con el mensaje del backend si la respuesta no es exitosa.
 */
async function pedir(ruta: string, opciones: RequestInit = {}) {
	const respuesta = await fetch(`${API}${ruta}`, {
		...opciones,
		headers: { 'Content-Type': 'application/json' }
	});
	const cuerpo = await respuesta.json().catch(() => null);
	if (!respuesta.ok)
		throw new Error(mensajeDeError(cuerpo) ?? `Error ${respuesta.status} del servidor`);
	return cuerpo;
}

/**
 * @brief Extrae el mensaje de error de una respuesta del backend.
 *
 * El backend responde {error: '...'} o, si falla la validación, {campo: ['...']}.
 * @param cuerpo JSON de la respuesta.
 * @returns El mensaje, o null si no se reconoce el formato.
 */
function mensajeDeError(cuerpo: any): string | null {
	if (!cuerpo) return null;
	if (typeof cuerpo.error === 'string') return cuerpo.error;
	const primero = Object.values(cuerpo)[0];
	return Array.isArray(primero) ? String(primero[0]) : null;
}

/**
 * @brief Convierte un incidente del backend al tipo Incidente.
 * @param i Incidente en snake_case (IncidenteSerializer).
 * @returns El incidente.
 */
function aIncidente(i: any): Incidente {
	return {
		idIncidente: i.id_incidente,
		devEui: i.dev_eui,
		nombre: i.nombre_dispositivo,
		visitante: i.visitante,
		estado: i.estado,
		lat: i.latitud,
		lon: i.longitud,
		zona: i.zona,
		abiertoEn: i.abierto_en,
		cerradoEn: i.cerrado_en
	};
}

/**
 * @brief Convierte un dispositivo del backend al tipo Nodo.
 * @param d Dispositivo en snake_case (DispositivoSerializer).
 * @returns El nodo.
 */
function aNodo(d: any): Nodo {
	return {
		devEui: d.dev_eui,
		nombre: d.nombre,
		activo: d.activo,
		bateriaMv: d.ultima_bateria_mv,
		ultimoContacto: d.ultimo_contacto,
		sosActivo: d.sos_activo,
		prestadoA: d.prestado_a
	};
}

/**
 * @brief Convierte el préstamo de un incidente abierto en la ficha del visitante (Prestamo).
 * @param a Préstamo con el visitante completo (PrestamoSerializer).
 * @returns La ficha del visitante.
 */
function aPrestamo(a: any): Prestamo {
	return {
		nombre: `${a.visitante.nombre} ${a.visitante.apellido}`,
		tipoSangre: a.visitante.tipo_sangre,
		contactoEmergencia: a.visitante.contacto_emergencia,
		notasMedicas: a.visitante.notas_medicas,
		desde: a.fecha_asignacion
	};
}

/**
 * @brief Incidentes abiertos con la ficha completa del visitante (GET /api/incidentes/activos/).
 * @returns Las alertas activas.
 */
export async function obtenerIncidentesActivos(): Promise<Alerta[]> {
	const datos = await pedir('/api/incidentes/activos/');
	return datos.map((i: any) => ({
		...aIncidente(i),
		bateriaMv: i.bateria_mv,
		nodoActivo: i.nodo_activo,
		prestamo: i.asignacion ? aPrestamo(i.asignacion) : null
	}));
}

/**
 * @brief Incidentes cerrados, del más reciente al más antiguo (GET /api/incidentes/historial/).
 * @returns El historial (hasta 500 incidentes).
 */
export async function obtenerHistorial(): Promise<Incidente[]> {
	return (await pedir('/api/incidentes/historial/')).map(aIncidente);
}

/**
 * @brief Cambia el estado de un incidente abierto (POST /api/incidentes/{id}/estado/, CU-04).
 * @param idIncidente Clave del incidente.
 * @param estado EN_ATENCION, RESUELTO o FALSA_ALARMA.
 * @returns Promesa que se cumple cuando el backend guardó el cambio.
 */
export async function cambiarEstadoIncidente(idIncidente: number, estado: EstadoIncidente) {
	await pedir(`/api/incidentes/${idIncidente}/estado/`, {
		method: 'POST',
		body: JSON.stringify({ estado })
	});
}

/**
 * @brief Nodos registrados, ordenados por nombre (GET /api/dispositivos/, CU-05).
 * @returns Los nodos.
 */
export async function obtenerDispositivos(): Promise<Nodo[]> {
	return (await pedir('/api/dispositivos/')).map(aNodo);
}

/**
 * @brief Registra un nodo nuevo (POST /api/dispositivos/, CU-06).
 * @param devEui DevEUI de 16 dígitos hexadecimales.
 * @param nombre Nombre legible.
 * @returns Promesa que se cumple cuando el backend registró el nodo.
 */
export async function registrarDispositivo(devEui: string, nombre: string) {
	await pedir('/api/dispositivos/', {
		method: 'POST',
		body: JSON.stringify({ dev_eui: devEui, nombre })
	});
}

/**
 * @brief Habilita o inhabilita un nodo (PATCH /api/dispositivos/{dev_eui}/, CU-07).
 * @param devEui DevEUI del nodo.
 * @param activo true para habilitarlo, false para inhabilitarlo.
 * @returns Promesa que se cumple cuando el backend guardó el cambio.
 */
export async function cambiarHabilitado(devEui: string, activo: boolean) {
	await pedir(`/api/dispositivos/${devEui}/`, {
		method: 'PATCH',
		body: JSON.stringify({ activo })
	});
}

/**
 * @brief Préstamos vigentes, sin datos de salud (GET /api/prestamos/).
 * @returns Los préstamos vigentes, del más reciente al más antiguo.
 */
export async function obtenerPrestamos(): Promise<PrestamoVigente[]> {
	return (await pedir('/api/prestamos/')).map((p: any) => ({
		idAsignacion: p.id_asignacion,
		devEui: p.dev_eui,
		nodo: p.nombre_dispositivo,
		visitante: p.visitante,
		contactoEmergencia: p.contacto_emergencia,
		desde: p.fecha_asignacion,
		emergenciaAbierta: p.emergencia_abierta
	}));
}

/**
 * @brief Presta un nodo a un visitante (POST /api/prestamos/, CU-13).
 * @param datos Datos del visitante y DevEUI del nodo.
 * @returns Promesa que se cumple cuando el backend registró el préstamo.
 */
export async function prestarNodo(datos: NuevoPrestamo) {
	await pedir('/api/prestamos/', {
		method: 'POST',
		body: JSON.stringify({
			dev_eui: datos.devEui,
			nombre: datos.nombre,
			apellido: datos.apellido,
			contacto_emergencia: datos.contactoEmergencia,
			tipo_sangre: datos.tipoSangre,
			notas_medicas: datos.notasMedicas
		})
	});
}

/**
 * @brief Registra la devolución de un nodo (POST /api/prestamos/{id}/devolucion/, CU-14).
 * @param idAsignacion Clave del préstamo.
 * @returns Promesa que se cumple cuando el backend registró la devolución.
 */
export async function registrarDevolucion(idAsignacion: number) {
	await pedir(`/api/prestamos/${idAsignacion}/devolucion/`, { method: 'POST' });
}

/**
 * @brief Ruta piloto definida en el backend (pruebas/ruta_piloto.geojson), como GeoJSON (GET /api/ruta-piloto/).
 * @returns FeatureCollection con el gateway, el perímetro y los puntos de control.
 */
export async function obtenerRutaPiloto() {
	return pedir('/api/ruta-piloto/');
}
