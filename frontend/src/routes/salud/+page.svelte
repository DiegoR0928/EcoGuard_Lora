<!--
	@component
	@brief Sección "Salud de red": batería, último reporte y estado de cada nodo.

	Un nodo está "Operativo" si reportó en los últimos MINUTOS_SIN_CONTACTO minutos; si no, "Posiblemente
	apagado/fuera de rango". Los inhabilitados se marcan aparte. La batería se pinta en rojo por debajo de 20 %.
-->
<script lang="ts">
	import { panel, reloj } from '$lib/estado.svelte';
	import { hace, minutosDesde, porcentajeBateria } from '$lib/formato';

	/**
	 * Minutos sin reportes para marcar un nodo fuera de contacto. El firmware reporta cada 10 min:
	 * tres reportes perdidos seguidos marcan al nodo fuera de contacto.
	 */
	const MINUTOS_SIN_CONTACTO = 30;
</script>

<svelte:head><title>Salud de red · EcoGuard</title></svelte:head>

<div class="p-8">
	<h2 class="mb-6 text-3xl font-bold text-white">Monitoreo Salud de los Nodos</h2>
	<div class="overflow-hidden rounded-xl border border-slate-700 bg-slate-800">
		<table class="w-full text-left text-sm">
			<thead class="border-b border-slate-700 bg-slate-900 text-slate-400">
				<tr>
					<th class="p-4 font-semibold">Dispositivo</th>
					<th class="p-4 font-semibold">Batería</th>
					<th class="p-4 font-semibold">Último Ping</th>
					<th class="p-4 font-semibold">Estado</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-slate-700/50">
				{#each panel.nodos as nodo (nodo.devEui)}
					{@const bateria = porcentajeBateria(nodo.bateriaMv)}
					{@const minutos = minutosDesde(nodo.ultimoContacto, reloj.ahora)}
					<tr class="transition-colors hover:bg-slate-700/30">
						<td class="p-4 font-medium text-slate-200">{nodo.nombre}</td>
						<td class="p-4 {bateria !== null && bateria < 20 ? 'text-red-400' : 'text-emerald-400'}"
							>{bateria === null ? '—' : `${bateria}%`}</td
						>
						<td class="p-4 text-slate-400">{hace(nodo.ultimoContacto, reloj.ahora)}</td>
						<td class="p-4">
							{#if !nodo.activo}
								<span
									class="inline-flex items-center gap-1.5 rounded-full border border-slate-600 bg-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300"
								>
									Inhabilitado
								</span>
							{:else if minutos === null || minutos > MINUTOS_SIN_CONTACTO}
								<span
									class="inline-flex items-center gap-1.5 rounded-full border border-red-800/50 bg-red-900/30 px-2.5 py-1 text-xs font-medium text-red-400"
								>
									Posiblemente apagado/fuera de rango
								</span>
							{:else}
								<span
									class="inline-flex items-center gap-1.5 rounded-full border border-emerald-800/50 bg-emerald-900/30 px-2.5 py-1 text-xs font-medium text-emerald-400"
								>
									Operativo
								</span>
							{/if}
						</td>
					</tr>
				{:else}
					<tr
						><td colspan="4" class="p-8 text-center text-slate-400">No hay nodos registrados.</td
						></tr
					>
				{/each}
			</tbody>
		</table>
	</div>
</div>
