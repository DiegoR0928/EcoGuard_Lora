/**
 * @file
 * @brief Tipos del panel. api.ts los arma a partir de las respuestas del backend.
 *
 * Usan camelCase; el backend responde en snake_case y api.ts hace la conversión.
 */

/** @brief Estados de un incidente, iguales a Incidente.Estado del backend. */
export type EstadoIncidente = 'ACTIVO' | 'EN_ATENCION' | 'RESUELTO' | 'CANCELADO' | 'FALSA_ALARMA';

/** @brief Incidente del historial (CU-08): una emergencia y cómo terminó. */
export interface Incidente {
	/** Clave del incidente en el backend. */
	idIncidente: number;
	/** DevEUI del nodo que emitió la alerta. */
	devEui: string;
	/** Nombre legible del nodo. */
	nombre: string;
	/** Nombre del visitante que llevaba el nodo; nulo si no había un préstamo registrado. */
	visitante: string | null;
	/** Estado actual. */
	estado: EstadoIncidente;
	/** Latitud de la última posición; nula si la alerta llegó sin posición satelital. */
	lat: number | null;
	/** Longitud de la última posición; nula si la alerta llegó sin posición satelital. */
	lon: number | null;
	/** Zona del parque donde ocurrió; nula si la posición no cae en ninguna. */
	zona: string | null;
	/** Fecha y hora de la primera trama SOS (ISO 8601). */
	abiertoEn: string;
	/** Fecha y hora de cierre (ISO 8601); nula mientras sigue abierto. */
	cerradoEn: string | null;
}

/** @brief Incidente abierto en el monitoreo: agrega la batería, el estado del nodo y la ficha del visitante. */
export interface Alerta extends Incidente {
	/** Voltaje de la batería del nodo en mV; nulo si no se conoce. */
	bateriaMv: number | null;
	/** Falso si el SOS viene de un nodo inhabilitado: se muestra igual, pero señalado. */
	nodoActivo: boolean;
	/** Ficha del visitante; nula si el nodo no tenía un préstamo registrado. */
	prestamo: Prestamo | null;
}

/**
 * @brief Ficha del visitante que lleva el nodo, para la brigada de rescate.
 *
 * Sus datos de salud solo llegan mientras la emergencia está abierta; el historial guarda
 * únicamente el nombre (RNF-12).
 */
export interface Prestamo {
	/** Nombre y apellido del visitante. */
	nombre: string;
	/** Tipo de sangre; vacío si no se registró. */
	tipoSangre: string; // Vacío si no se registró
	/** Nombre y teléfono de la persona a notificar. */
	contactoEmergencia: string;
	/** Alergias o padecimientos; vacío si no se registraron. */
	notasMedicas: string;
	/** Fecha y hora en que recibió el nodo (ISO 8601). */
	desde: string;
}

/** @brief Nodo registrado, con su último reporte (CU-05). */
export interface Nodo {
	/** DevEUI del nodo (16 dígitos hexadecimales). */
	devEui: string;
	/** Nombre legible. */
	nombre: string;
	/** Falso si está inhabilitado (CU-07). */
	activo: boolean;
	/** Voltaje de la batería en el último reporte, en mV; nulo si nunca reportó. */
	bateriaMv: number | null;
	/** Fecha y hora del último reporte (ISO 8601); nula si nunca reportó. */
	ultimoContacto: string | null;
	/** Verdadero si tiene una emergencia abierta. */
	sosActivo: boolean;
	/** Visitante que lleva el nodo ahora; nulo si está disponible. */
	prestadoA: string | null;
}

/** @brief Préstamo vigente en la sección de préstamos: sin datos de salud (RNF-12). */
export interface PrestamoVigente {
	/** Clave del préstamo en el backend. */
	idAsignacion: number;
	/** DevEUI del nodo prestado. */
	devEui: string;
	/** Nombre del nodo prestado. */
	nodo: string;
	/** Nombre y apellido del visitante. */
	visitante: string;
	/** Contacto de emergencia del visitante. */
	contactoEmergencia: string;
	/** Fecha y hora del préstamo (ISO 8601). */
	desde: string;
	/** Con una emergencia abierta no se puede registrar la devolución (CU-14). */
	emergenciaAbierta: boolean;
}

/** @brief Datos que captura el vigilante al prestar un nodo (CU-13). */
export interface NuevoPrestamo {
	/** DevEUI del nodo que se presta. */
	devEui: string;
	/** Nombre(s) del visitante. */
	nombre: string;
	/** Apellido(s) del visitante. */
	apellido: string;
	/** Nombre y teléfono de la persona a notificar. */
	contactoEmergencia: string;
	/** Tipo de sangre (opcional: cadena vacía). */
	tipoSangre: string;
	/** Alergias o padecimientos (opcional: cadena vacía). */
	notasMedicas: string;
}

/** @brief Resultado de una acción del vigilante, para mostrarlo en pantalla. */
export interface Mensaje {
	/** Texto a mostrar; vacío si no hay mensaje. */
	texto: string;
	/** Verdadero si la acción falló. */
	error: boolean;
}
