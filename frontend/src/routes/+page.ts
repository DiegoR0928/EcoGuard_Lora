/**
 * @file
 * @brief Página raíz del panel: redirige a la sección de monitoreo.
 */
import { redirect } from '@sveltejs/kit';

/**
 * @brief Función load de SvelteKit: la sección inicial del panel es el monitoreo en vivo.
 *
 * Redirige a /monitoreo con el código 307 (redirección temporal).
 */
export function load() {
	redirect(307, '/monitoreo');
}
