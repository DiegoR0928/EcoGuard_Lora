<!--
	@component
	@brief Sección "Monitoreo en vivo": mapa con las alertas activas y una tarjeta por alerta.

	Cada tarjeta muestra el nodo, la zona, la batería y el tiempo transcurrido; al desplegarla
	aparece la ficha del visitante. El vigilante cierra la alerta con "Marcar resuelto" (CU-04).
	El indicador de conexión muestra el estado del WebSocket.
-->
<script lang="ts">
	import FichaVisitante from '$lib/componentes/FichaVisitante.svelte';
	import MapaMonitoreo from '$lib/componentes/MapaMonitoreo.svelte';
	import { panel, reloj, resolverAlerta } from '$lib/estado.svelte';
	import { hace, porcentajeBateria } from '$lib/formato';

	/** Qué tarjetas de alerta están desplegadas, por idIncidente: es estado de esta vista, no del sistema. */
	let desplegadas = $state<Record<number, boolean>>({});
	/** Error de la última acción; vacío si no hubo. */
	let error = $state('');

	/** Texto y color del indicador de conexión para cada estado del WebSocket. */
	const CONEXION = {
		conectado: { texto: 'Conexión: ESTABLE', clase: 'text-emerald-400' },
		conectando: { texto: 'Conectando…', clase: 'text-amber-400' },
		desconectado: { texto: 'Sin conexión: reintentando…', clase: 'text-red-400' }
	};

	/**
	 * @brief Cierra un incidente como resuelto, previa confirmación del vigilante (CU-04).
	 * @param idIncidente Clave del incidente.
	 * @returns Promesa que se cumple al cerrar el incidente o al cancelar la confirmación.
	 */
	async function marcarResuelto(idIncidente: number) {
		if (!confirm('¿Seguro que desea cerrar este incidente?')) return;
		const resultado = await resolverAlerta(idIncidente);
		error = resultado.error ? resultado.texto : '';
	}
</script>

<svelte:head><title>Monitoreo en vivo · EcoGuard</title></svelte:head>

<div class="flex h-full w-full">
	<!-- Panel lateral de alertas -->
	<aside
		class="z-10 w-96 overflow-y-auto border-r border-slate-800 bg-slate-900 p-5 shadow-[10px_0_15px_-3px_rgba(0,0,0,0.5)]"
	>
		<h2 class="mb-4 flex items-center justify-between text-lg font-bold text-white">
			Alertas Activas
			<span class="animate-pulse rounded bg-red-500/20 px-2 py-1 text-xs text-red-400"
				>{panel.alertasActivas.length}</span
			>
		</h2>

		{#if error}
			<div
				role="alert"
				class="mb-4 rounded-lg border border-red-800 bg-red-900/20 p-3 text-sm text-red-400"
			>
				{error}
			</div>
		{/if}

		{#if panel.alertasActivas.length === 0}
			<div
				class="rounded-lg border border-emerald-800 bg-emerald-900/20 p-4 text-sm font-medium text-emerald-400"
			>
				Zona libre de emergencias
			</div>
		{/if}

		{#each panel.alertasActivas as alerta (alerta.idIncidente)}
			{@const bateria = porcentajeBateria(alerta.bateriaMv)}
			<div
				class="mb-4 overflow-hidden rounded-xl border border-slate-700 bg-slate-800/50 backdrop-blur-sm transition hover:border-slate-500"
			>
				<button
					type="button"
					class="flex w-full cursor-pointer items-center justify-between bg-slate-800 p-4 text-left"
					aria-expanded={!!desplegadas[alerta.idIncidente]}
					onclick={() => (desplegadas[alerta.idIncidente] = !desplegadas[alerta.idIncidente])}
				>
					<span class="min-w-0">
						<span class="flex items-center gap-2 font-bold text-red-500">
							<span class="h-2 w-2 shrink-0 animate-ping rounded-full bg-red-500"></span>
							{alerta.nombre}
						</span>
						<span class="mt-0.5 block truncate pl-4 text-sm text-slate-300">
							{alerta.visitante ?? 'Visitante sin registrar'}
						</span>
					</span>
					<span class="shrink-0 rounded bg-slate-900 px-2 py-1 text-xs text-slate-400"
						>{hace(alerta.abiertoEn, reloj.ahora)}</span
					>
				</button>

				{#if !alerta.nodoActivo}
					<p
						class="border-t border-amber-800/50 bg-amber-900/20 px-4 py-2 text-xs font-semibold text-amber-400"
					>
						Nodo inhabilitado: no debería estar en uso
					</p>
				{/if}

				{#if !alerta.prestamo}
					<p
						class="border-t border-amber-800/50 bg-amber-900/20 px-4 py-2 text-xs font-semibold text-amber-400"
					>
						Sin préstamo registrado: se desconoce quién lleva el nodo
					</p>
				{/if}

				{#if desplegadas[alerta.idIncidente]}
					<div class="border-t border-slate-700 bg-slate-800/30 p-4">
						{#if alerta.prestamo}<FichaVisitante prestamo={alerta.prestamo} />{/if}

						<div
							class="space-y-1 rounded border border-slate-800 bg-slate-900 p-3 font-mono text-xs text-slate-300"
						>
							{#if alerta.lat !== null && alerta.lon !== null}
								<p>LAT: {alerta.lat}</p>
								<p>LON: {alerta.lon}</p>
							{:else}
								<p class="text-amber-400">Ubicación desconocida (sin señal GPS)</p>
							{/if}
							{#if alerta.zona}<p>ZONA: {alerta.zona}</p>{/if}
						</div>

						<p
							class="mt-3 flex items-center gap-2 text-sm font-bold {bateria !== null &&
							bateria < 15
								? 'animate-pulse text-red-500'
								: 'text-emerald-400'}"
						>
							Batería del Nodo: {bateria === null ? 'sin dato' : `${bateria}%`}
						</p>

						<button
							onclick={() => marcarResuelto(alerta.idIncidente)}
							class="mt-4 w-full rounded-lg border border-slate-600 bg-slate-700 py-2.5 font-semibold text-white transition-colors hover:border-emerald-500 hover:bg-emerald-600"
						>
							Marcar como Resuelto
						</button>
					</div>
				{/if}
			</div>
		{/each}
	</aside>

	<!-- Mapa Leaflet -->
	<div class="relative flex-1 bg-slate-950">
		<MapaMonitoreo alertas={panel.alertasActivas} />
		<div
			class="absolute top-4 right-4 z-[1000] rounded-full border border-slate-700 bg-slate-900/80 px-4 py-2 font-mono text-xs backdrop-blur {CONEXION[
				panel.conexion
			].clase}"
		>
			{CONEXION[panel.conexion].texto}
		</div>
	</div>
</div>
