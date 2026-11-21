<!--
	@component
	@brief Sección "Historial": incidentes cerrados, con filtro por fecha de cierre y descarga en CSV (CU-08).
-->
<script lang="ts">
	import { panel } from '$lib/estado.svelte';
	import { fechaLocal, NOMBRE_ESTADO } from '$lib/formato';
	import type { Incidente } from '$lib/tipos';

	/** Fecha de cierre a mostrar (AAAA-MM-DD); vacía muestra todo el historial. */
	let filtroFecha = $state('');
	/** Incidentes del historial cerrados en filtroFecha (todos si no hay filtro). */
	let historialFiltrado = $derived(
		filtroFecha
			? panel.historial.filter((h) => h.cerradoEn && fechaLocal(h.cerradoEn) === filtroFecha)
			: panel.historial
	);

	/**
	 * @brief Descarga las filas visibles como archivo CSV (CU-08).
	 *
	 * El archivo lleva BOM para que Excel abra los acentos correctamente; su nombre incluye la fecha
	 * del filtro, si hay.
	 * @param incidentes Incidentes a exportar.
	 */
	function descargarReporte(incidentes: Incidente[]) {
		const columnas = [
			'id_incidente',
			'dispositivo',
			'dev_eui',
			'visitante',
			'estado',
			'zona',
			'latitud',
			'longitud',
			'abierto_en',
			'cerrado_en'
		];
		const filas = incidentes.map((i) =>
			[
				i.idIncidente,
				i.nombre,
				i.devEui,
				i.visitante,
				NOMBRE_ESTADO[i.estado],
				i.zona,
				i.lat,
				i.lon,
				i.abiertoEn,
				i.cerradoEn
			]
				.map((valor) => `"${String(valor ?? '').replaceAll('"', '""')}"`)
				.join(',')
		);
		// El BOM hace que Excel abra el archivo con los acentos correctos
		const archivo = new Blob(['\uFEFF' + [columnas.join(','), ...filas].join('\n')], {
			type: 'text/csv'
		});
		const enlace = document.createElement('a');
		enlace.href = URL.createObjectURL(archivo);
		enlace.download = `historial-incidentes${filtroFecha ? '-' + filtroFecha : ''}.csv`;
		enlace.click();
		URL.revokeObjectURL(enlace.href);
	}
</script>

<svelte:head><title>Historial · EcoGuard</title></svelte:head>

<div class="p-8">
	<div class="mb-6 flex items-center justify-between">
		<h2 class="text-3xl font-bold text-white">Historial de Incidentes</h2>
		<button
			onclick={() => descargarReporte(historialFiltrado)}
			disabled={historialFiltrado.length === 0}
			class="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-50"
		>
			Descargar reporte
		</button>
	</div>

	<div class="mb-6 flex gap-4">
		<input
			bind:value={filtroFecha}
			type="date"
			aria-label="Filtrar por fecha de cierre"
			class="rounded-lg border border-slate-700 bg-slate-800 p-2.5 text-slate-300 focus:border-emerald-500 focus:outline-none"
		/>
		<button onclick={() => (filtroFecha = '')} class="px-3 text-slate-400 hover:text-white"
			>Limpiar filtro</button
		>
	</div>

	<div class="overflow-hidden rounded-xl border border-slate-700 bg-slate-800">
		{#if historialFiltrado.length === 0}
			<div class="border-t border-slate-700 p-8 text-center text-slate-400">
				{filtroFecha
					? 'No se encontraron registros con ese filtro de búsqueda.'
					: 'Todavía no hay incidentes cerrados.'}
			</div>
		{:else}
			<table class="w-full text-left text-sm">
				<thead class="border-b border-slate-700 bg-slate-900 text-slate-400">
					<tr>
						<th class="p-4 font-semibold">Fecha</th>
						<th class="p-4 font-semibold">Dispositivo</th>
						<th class="p-4 font-semibold">Visitante</th>
						<th class="p-4 font-semibold">Coordenadas</th>
						<th class="p-4 font-semibold">Estado Final</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-slate-700/50">
					{#each historialFiltrado as reg (reg.idIncidente)}
						<tr class="hover:bg-slate-700/30">
							<td class="p-4 text-slate-300">{reg.cerradoEn ? fechaLocal(reg.cerradoEn) : '—'}</td>
							<td class="p-4 font-medium text-white">{reg.nombre}</td>
							<td class="p-4 {reg.visitante ? 'text-slate-300' : 'text-slate-500 italic'}"
								>{reg.visitante ?? 'Sin registrar'}</td
							>
							<td class="p-4 font-mono text-xs text-slate-400"
								>{reg.lat !== null && reg.lon !== null
									? `${reg.lat}, ${reg.lon}`
									: 'Desconocida'}</td
							>
							<td class="p-4">
								<span class="rounded bg-slate-700 px-2 py-1 text-xs font-semibold text-slate-300"
									>{NOMBRE_ESTADO[reg.estado]}</span
								>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>
