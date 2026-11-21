<!--
	@component
	@brief Sección "Gestión de dispositivos": registrar nodos (CU-06) y habilitarlos o inhabilitarlos (CU-07).

	Lista los nodos registrados con su DevEUI y a quién están prestados. El backend no permite
	inhabilitar un nodo con una emergencia abierta; su mensaje de error se muestra arriba.
-->
<script lang="ts">
	import { alternarHabilitado, panel, registrarNodo } from '$lib/estado.svelte';
	import type { Mensaje } from '$lib/tipos';

	/** DevEUI escrito en el formulario de registro. */
	let nuevoNodoId = $state('');
	/** Nombre escrito en el formulario de registro. */
	let nuevoNodoNombre = $state('');
	/** Resultado de la última acción (registro o cambio de estado). */
	let mensaje = $state<Mensaje>({ texto: '', error: false });

	/**
	 * @brief Registra el nodo del formulario y, si tuvo éxito, limpia los campos.
	 * @returns Promesa que se cumple al terminar el registro.
	 */
	async function registrar() {
		mensaje = await registrarNodo(nuevoNodoId, nuevoNodoNombre);
		if (!mensaje.error) {
			nuevoNodoId = '';
			nuevoNodoNombre = '';
		}
	}
</script>

<svelte:head><title>Gestión de dispositivos · EcoGuard</title></svelte:head>

<div class="max-w-5xl p-8">
	<h2 class="mb-6 text-3xl font-bold text-white">Gestión de Dispositivos</h2>

	{#if mensaje.texto}
		<div
			class="mb-6 rounded-lg border p-4 {mensaje.error
				? 'border-red-800 bg-red-900/20 text-red-400'
				: 'border-emerald-800 bg-emerald-900/20 text-emerald-400'}"
		>
			{mensaje.texto}
		</div>
	{/if}

	<div class="mb-8 rounded-xl border border-slate-700 bg-slate-800 p-6 shadow-lg">
		<h3 class="mb-4 text-lg font-semibold text-slate-200">Registrar Nuevo Nodo</h3>
		<div class="flex items-end gap-4">
			<div class="flex-1">
				<label for="dev-eui" class="mb-1 block text-xs font-semibold text-slate-400 uppercase"
					>DevEUI (16 caracteres Hex)</label
				>
				<input
					id="dev-eui"
					bind:value={nuevoNodoId}
					type="text"
					placeholder="Ej. A1B2C3D4E5F67890"
					class="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 font-mono text-sm text-white uppercase focus:border-emerald-500 focus:outline-none"
				/>
			</div>
			<div class="flex-1">
				<label for="nombre-nodo" class="mb-1 block text-xs font-semibold text-slate-400 uppercase"
					>Nombre Legible</label
				>
				<input
					id="nombre-nodo"
					bind:value={nuevoNodoNombre}
					type="text"
					placeholder="Ej. Heltec-08"
					class="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm text-white focus:border-emerald-500 focus:outline-none"
				/>
			</div>
			<button
				onclick={registrar}
				class="rounded-lg bg-emerald-600 px-8 py-3 font-bold text-white transition-colors hover:bg-emerald-500"
			>
				Guardar
			</button>
		</div>
	</div>

	<h3 class="mb-4 text-lg font-semibold text-slate-200">Nodos Registrados</h3>
	<div class="grid grid-cols-2 gap-4">
		{#each panel.nodos as nodo (nodo.devEui)}
			<div
				class="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-800 p-4"
			>
				<div>
					<p class="text-lg font-bold text-white">{nodo.nombre}</p>
					<p class="font-mono text-xs text-slate-500">{nodo.devEui}</p>
					<p class="mt-1 text-sm {nodo.prestadoA ? 'text-sky-300' : 'text-slate-500'}">
						{nodo.prestadoA ? `Prestado a ${nodo.prestadoA}` : 'Sin préstamo'}
					</p>
				</div>
				<button
					onclick={async () => (mensaje = await alternarHabilitado(nodo))}
					class="rounded border px-4 py-2 text-sm font-semibold transition-colors {nodo.activo
						? 'border-red-500/50 text-red-400 hover:bg-red-500/10'
						: 'border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/10'}"
				>
					{nodo.activo ? 'Inhabilitar' : 'Habilitar'}
				</button>
			</div>
		{:else}
			<p class="text-slate-400">No hay nodos registrados.</p>
		{/each}
	</div>
</div>
