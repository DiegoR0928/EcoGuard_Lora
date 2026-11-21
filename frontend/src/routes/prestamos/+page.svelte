<!--
	@component
	@brief Sección "Préstamos": prestar un nodo a un visitante (CU-13) y registrar su devolución (CU-14).

	El formulario captura los datos del visitante, incluidos los de salud; la lista de préstamos
	vigentes no los muestra (RNF-12). Un nodo con una emergencia abierta no se puede devolver.
-->
<script lang="ts">
	import { devolverNodo, panel, prestarNodo, reloj } from '$lib/estado.svelte';
	import { fechaHora, hace } from '$lib/formato';
	import type { Mensaje, NuevoPrestamo, PrestamoVigente } from '$lib/tipos';

	/** Opciones del campo de tipo de sangre. */
	const TIPOS_SANGRE = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];

	/**
	 * @brief Formulario vacío.
	 * @returns Un NuevoPrestamo con todos los campos vacíos.
	 */
	const vacio = (): NuevoPrestamo => ({
		devEui: '',
		nombre: '',
		apellido: '',
		contactoEmergencia: '',
		tipoSangre: '',
		notasMedicas: ''
	});

	/** Datos del formulario de préstamo. */
	let nuevo = $state(vacio());
	/** Resultado de la última acción (préstamo o devolución). */
	let mensaje = $state<Mensaje>({ texto: '', error: false });
	/** Verdadero mientras se guarda el préstamo: desactiva el botón. */
	let guardando = $state(false);

	/**
	 * Nodos que se pueden prestar: habilitados y que nadie lleva. Uno con una alerta abierta sin
	 * préstamo también aparece: registrar el préstamo vincula al visitante con la alerta (CU-13, FA1).
	 */
	let disponibles = $derived(panel.nodos.filter((n) => n.activo && !n.prestadoA));

	/**
	 * @brief Registra el préstamo del formulario y, si tuvo éxito, lo limpia.
	 * @returns Promesa que se cumple al terminar el registro.
	 */
	async function registrar() {
		guardando = true;
		mensaje = await prestarNodo(nuevo);
		guardando = false;
		if (!mensaje.error) nuevo = vacio();
	}

	/**
	 * @brief Registra la devolución de un nodo, previa confirmación del vigilante (CU-14).
	 * @param prestamo Préstamo vigente.
	 * @returns Promesa que se cumple al registrar la devolución o al cancelar la confirmación.
	 */
	async function devolver(prestamo: PrestamoVigente) {
		if (!confirm(`¿Confirma que ${prestamo.visitante} devolvió ${prestamo.nodo}?`)) return;
		mensaje = await devolverNodo(prestamo);
	}

	/** Clases de Tailwind de los campos del formulario. */
	const CAMPO =
		'w-full rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm text-white focus:border-emerald-500 focus:outline-none';
	/** Clases de Tailwind de las etiquetas del formulario. */
	const ETIQUETA = 'mb-1 block text-xs font-semibold text-slate-400 uppercase';
</script>

<svelte:head><title>Préstamos · EcoGuard</title></svelte:head>

<div class="max-w-5xl p-8">
	<h2 class="mb-6 text-3xl font-bold text-white">Préstamos de Nodos</h2>

	{#if mensaje.texto}
		<div
			role={mensaje.error ? 'alert' : 'status'}
			class="mb-6 rounded-lg border p-4 {mensaje.error
				? 'border-red-800 bg-red-900/20 text-red-400'
				: 'border-emerald-800 bg-emerald-900/20 text-emerald-400'}"
		>
			{mensaje.texto}
		</div>
	{/if}

	<!-- CU-13: el vigilante entrega el nodo en la entrada y registra a quién -->
	<form
		class="mb-8 rounded-xl border border-slate-700 bg-slate-800 p-6 shadow-lg"
		onsubmit={(evento) => {
			evento.preventDefault();
			registrar();
		}}
	>
		<h3 class="mb-4 text-lg font-semibold text-slate-200">Registrar Préstamo</h3>

		<div class="grid grid-cols-2 gap-4">
			<div class="col-span-2">
				<label for="nodo" class={ETIQUETA}>Nodo</label>
				<select id="nodo" bind:value={nuevo.devEui} class={CAMPO}>
					<option value="">
						{disponibles.length ? 'Selecciona un nodo disponible' : 'No hay nodos disponibles'}
					</option>
					{#each disponibles as nodo (nodo.devEui)}
						<option value={nodo.devEui}>{nodo.nombre} · {nodo.devEui}</option>
					{/each}
				</select>
			</div>
			<div>
				<label for="nombre" class={ETIQUETA}>Nombre</label>
				<input id="nombre" bind:value={nuevo.nombre} maxlength="60" class={CAMPO} />
			</div>
			<div>
				<label for="apellido" class={ETIQUETA}>Apellidos</label>
				<input id="apellido" bind:value={nuevo.apellido} maxlength="60" class={CAMPO} />
			</div>
			<div>
				<label for="contacto" class={ETIQUETA}>Contacto de emergencia</label>
				<input
					id="contacto"
					bind:value={nuevo.contactoEmergencia}
					maxlength="120"
					placeholder="Nombre y teléfono"
					class={CAMPO}
				/>
			</div>
			<div>
				<label for="sangre" class={ETIQUETA}>Tipo de sangre (opcional)</label>
				<select id="sangre" bind:value={nuevo.tipoSangre} class={CAMPO}>
					<option value="">No lo indicó</option>
					{#each TIPOS_SANGRE as tipo (tipo)}
						<option value={tipo}>{tipo}</option>
					{/each}
				</select>
			</div>
			<div class="col-span-2">
				<label for="notas" class={ETIQUETA}>Notas médicas (opcional)</label>
				<textarea
					id="notas"
					bind:value={nuevo.notasMedicas}
					rows="2"
					placeholder="Alergias, padecimientos o medicamentos relevantes para un rescate"
					class={CAMPO}></textarea>
			</div>
		</div>

		<div class="mt-5 flex items-center justify-between gap-4">
			<p class="text-xs text-slate-500">
				Los datos de salud solo se muestran si el visitante emite una alerta.
			</p>
			<button
				type="submit"
				disabled={guardando}
				class="shrink-0 rounded-lg bg-emerald-600 px-8 py-3 font-bold text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
			>
				Registrar préstamo
			</button>
		</div>
	</form>

	<!-- CU-14: préstamos vigentes y devolución -->
	<h3 class="mb-4 text-lg font-semibold text-slate-200">
		Préstamos Vigentes
		<span class="ml-2 rounded bg-slate-800 px-2 py-0.5 text-sm text-slate-400"
			>{panel.prestamos.length}</span
		>
	</h3>

	{#if panel.prestamos.length === 0}
		<p class="text-slate-400">No hay nodos prestados en este momento.</p>
	{:else}
		<div class="overflow-hidden rounded-xl border border-slate-700 bg-slate-800">
			<table class="w-full text-left text-sm">
				<thead class="border-b border-slate-700 bg-slate-900 text-slate-400">
					<tr>
						<th class="p-4 font-semibold">Nodo</th>
						<th class="p-4 font-semibold">Visitante</th>
						<th class="p-4 font-semibold">Contacto de emergencia</th>
						<th class="p-4 font-semibold">Entregado</th>
						<th class="p-4"></th>
					</tr>
				</thead>
				<tbody class="divide-y divide-slate-700/50">
					{#each panel.prestamos as prestamo (prestamo.idAsignacion)}
						<tr class="hover:bg-slate-700/30">
							<td class="p-4 font-medium text-white">{prestamo.nodo}</td>
							<td class="p-4 text-slate-200">{prestamo.visitante}</td>
							<td class="p-4 text-slate-300">{prestamo.contactoEmergencia}</td>
							<td class="p-4 text-slate-400">
								{fechaHora(prestamo.desde)}
								<span class="block text-xs">{hace(prestamo.desde, reloj.ahora)}</span>
							</td>
							<td class="p-4 text-right whitespace-nowrap">
								<!-- CU-14, FE1: con una emergencia abierta la devolución espera a que se cierre -->
								<button
									onclick={() => devolver(prestamo)}
									disabled={prestamo.emergenciaAbierta}
									class="rounded border border-sky-500/50 px-4 py-2 text-sm font-semibold text-sky-300 transition-colors hover:bg-sky-500/10 disabled:cursor-not-allowed disabled:border-slate-600 disabled:text-slate-500 disabled:hover:bg-transparent"
								>
									Registrar devolución
								</button>
								{#if prestamo.emergenciaAbierta}
									<a
										href="/monitoreo"
										class="mt-1 block text-xs font-semibold text-red-400 hover:underline"
										>Emergencia abierta: ciérrela en Monitoreo</a
									>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
