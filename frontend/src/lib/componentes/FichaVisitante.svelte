<!--
	@component
	@brief Ficha del visitante para la brigada de rescate: a quién buscar y qué debe saber al encontrarlo.

	Muestra nombre, tipo de sangre, contacto de emergencia, desde cuándo lleva el nodo y las notas
	médicas. Solo se usa en las alertas abiertas: los datos de salud no salen en el historial (RNF-12).
-->
<script lang="ts">
	import { reloj } from '$lib/estado.svelte';
	import { fechaHora, hace } from '$lib/formato';
	import type { Prestamo } from '$lib/tipos';

	let {
		prestamo
	}: {
		/** Ficha del visitante que lleva el nodo de la alerta. */
		prestamo: Prestamo;
	} = $props();
</script>

<section
	aria-label="Datos del visitante"
	class="mb-3 rounded border border-slate-700 bg-slate-900 p-3 text-sm"
>
	<h3 class="mb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">Visitante</h3>
	<p class="text-base font-bold text-white">{prestamo.nombre}</p>

	<dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
		<dt class="text-slate-500">Tipo de sangre</dt>
		<dd class="font-semibold {prestamo.tipoSangre ? 'text-red-300' : 'text-slate-400'}">
			{prestamo.tipoSangre || 'No registrado'}
		</dd>
		<dt class="text-slate-500">Contacto</dt>
		<dd class="text-slate-200">{prestamo.contactoEmergencia}</dd>
		<dt class="text-slate-500">Con el nodo</dt>
		<dd class="text-slate-200">
			{fechaHora(prestamo.desde)} · {hace(prestamo.desde, reloj.ahora).toLowerCase()}
		</dd>
	</dl>

	{#if prestamo.notasMedicas}
		<p
			class="mt-3 rounded border border-amber-800/60 bg-amber-900/20 p-2 whitespace-pre-line text-amber-200"
		>
			<span class="font-semibold text-amber-400">Notas médicas:</span>
			{prestamo.notasMedicas}
		</p>
	{:else}
		<p class="mt-3 text-xs text-slate-500">Sin notas médicas registradas</p>
	{/if}
</section>
