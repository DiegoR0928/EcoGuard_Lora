<!--
	@component
	@brief Mapa de Leaflet con la ruta piloto y un marcador por cada alerta activa.

	- Al montarse carga Leaflet, centra el mapa en el Campus UAZ Siglo XXI y dibuja la ruta piloto del backend.
	- Cada vez que cambian las alertas redibuja sus marcadores. Las alertas sin posición satelital no se
	  dibujan: RNF-07 prohíbe presentarlas en una ubicación inventada.
	- Al salir de la sección destruye el mapa.
-->
<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { obtenerRutaPiloto } from '$lib/api';
	import { escaparHtml } from '$lib/formato';
	import { cargarLeaflet, dibujarRutaPiloto } from '$lib/mapa';
	import type { Alerta } from '$lib/tipos';

	let {
		alertas
	}: {
		/** Alertas activas a marcar en el mapa. */
		alertas: Alerta[];
	} = $props();

	/** Elemento del DOM donde Leaflet dibuja el mapa. */
	let contenedor: HTMLDivElement;
	/** Módulo de Leaflet, cargado al montar el componente. */
	let L: any;
	/** Capa con los marcadores de las alertas; se vacía y se vuelve a llenar en cada cambio. */
	let capaAlertas: any;
	/** Mapa de Leaflet; null hasta que termina de cargarse. Al asignarlo se dibujan los marcadores. */
	let mapa = $state.raw<any>(null);
	/** Verdadero si se salió de la sección mientras Leaflet cargaba: entonces no se crea el mapa. */
	let destruido = false;

	onMount(async () => {
		L = await cargarLeaflet();
		if (destruido) return; // Se salió de la sección mientras Leaflet cargaba

		// Campus UAZ Siglo XXI; dibujarRutaPiloto ajusta el encuadre al recibir la ruta
		const nuevo = L.map(contenedor).setView([22.7716, -102.643], 16);
		L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
			attribution: '© OpenStreetMap contributors',
			className: 'map-tiles-dark'
		}).addTo(nuevo);
		capaAlertas = L.layerGroup().addTo(nuevo);
		mapa = nuevo;

		try {
			dibujarRutaPiloto(L, nuevo, await obtenerRutaPiloto());
		} catch (error) {
			console.error('No se pudo cargar la ruta piloto del backend', error);
		}
	});

	// Un marcador por alerta activa: se redibujan cada vez que cambia la lista. Las alertas sin
	// posición satelital no se dibujan: RNF-07 prohíbe presentarlas en una ubicación inventada
	$effect(() => {
		if (!mapa) return;
		capaAlertas.clearLayers();
		for (const alerta of alertas) {
			if (alerta.lat === null || alerta.lon === null) continue;
			L.marker([alerta.lat, alerta.lon])
				.bindPopup(
					`<b style="color:red">${escaparHtml(alerta.nombre)}</b><br>` +
						(alerta.visitante ? `${escaparHtml(alerta.visitante)}<br>` : '') +
						`¡SOS Activo!${alerta.nodoActivo ? '' : '<br>Nodo inhabilitado'}`
				)
				.addTo(capaAlertas);
		}
	});

	onDestroy(() => {
		destruido = true;
		mapa?.remove();
	});
</script>

<div bind:this={contenedor} class="z-0 h-full w-full"></div>
