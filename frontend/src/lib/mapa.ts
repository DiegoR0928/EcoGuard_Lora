/**
 * @file
 * @brief Utilidades de Leaflet para el mapa del panel.
 */

/**
 * @brief Carga Leaflet y su hoja de estilo.
 *
 * Leaflet usa window, así que solo se carga en el navegador (nunca durante el SSR). Los íconos por
 * defecto se apuntan al CDN porque Vite reescribe sus rutas.
 * @returns El módulo de Leaflet (L).
 */
export async function cargarLeaflet() {
	const L = await import('leaflet');
	await import('leaflet/dist/leaflet.css');

	// Vite reescribe las rutas de los íconos por defecto de Leaflet; se apuntan al CDN
	delete (L.Icon.Default.prototype as any)._getIconUrl;
	L.Icon.Default.mergeOptions({
		iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
		iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
		shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png'
	});
	return L;
}

/**
 * @brief Dibuja la ruta piloto y centra el mapa en ella.
 *
 * Dibuja el perímetro (verde punteado), el recorrido entre los puntos de control (naranja), los
 * puntos numerados en orden y el gateway (GW). Cada punto muestra su distancia al gateway al pasar
 * el cursor.
 * @param L Módulo de Leaflet.
 * @param mapa Mapa de Leaflet.
 * @param ruta FeatureCollection de obtenerRutaPiloto().
 */
export function dibujarRutaPiloto(L: any, mapa: any, ruta: any) {
	const puntos = ruta.features.filter((f: any) => f.properties.tipo === 'punto_control');
	L.polyline(
		puntos.map((f: any) => [f.geometry.coordinates[1], f.geometry.coordinates[0]]),
		{ color: '#f97316', weight: 3, opacity: 0.9 }
	).addTo(mapa);

	const capa = L.geoJSON(ruta, {
		style: () => ({ color: '#34d399', weight: 2, dashArray: '6 6', fillOpacity: 0.04 }),
		pointToLayer: (f: any, latlng: any) => {
			const p = f.properties;
			const html =
				p.tipo === 'gateway'
					? '<div class="flex h-7 w-7 items-center justify-center rounded-md border-2 border-white bg-indigo-500 text-[10px] font-bold text-white shadow">GW</div>'
					: `<div class="flex h-6 w-6 items-center justify-center rounded-full border-2 border-white bg-orange-500 text-xs font-bold text-white shadow">${p.orden}</div>`;
			const tamaño = p.tipo === 'gateway' ? 28 : 24;
			return L.marker(latlng, {
				icon: L.divIcon({
					html,
					className: '',
					iconSize: [tamaño, tamaño],
					iconAnchor: [tamaño / 2, tamaño / 2]
				})
			});
		},
		onEachFeature: (f: any, capa: any) => {
			const p = f.properties;
			if (p.tipo === 'punto_control')
				capa.bindTooltip(
					`<b>${p.codigo}</b> · ${p.nombre}<br>${p.distancia_gateway_m} m del gateway`
				);
			else if (p.tipo === 'gateway') capa.bindTooltip(`<b>${p.nombre}</b><br>EUI ${p.gateway_eui}`);
			else capa.bindTooltip(p.nombre, { sticky: true });
		}
	}).addTo(mapa);

	mapa.fitBounds(capa.getBounds(), { padding: [20, 20] });
}
