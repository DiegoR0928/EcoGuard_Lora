<!--
	@component
	@brief Estructura común del panel: menú lateral, aviso de error de carga y la sección activa.

	Al montarse abre una sola conexión con el backend para todas las secciones (iniciarPanel()) y la
	cierra al salir del panel. El área principal se desplaza por separado del menú.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import MenuLateral from '$lib/componentes/MenuLateral.svelte';
	import { iniciarPanel, panel } from '$lib/estado.svelte';

	let {
		/** Contenido de la sección activa: la página de la ruta. */
		children
	} = $props();

	// Una sola conexión al backend para todas las secciones; se cierra al salir del panel
	onMount(() => iniciarPanel());
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<div
	class="flex h-screen w-full overflow-hidden bg-slate-900 font-sans text-slate-300 selection:bg-emerald-500 selection:text-white"
>
	<MenuLateral />

	<!-- Las secciones largas (préstamos, gestión, historial) se desplazan dentro del área principal -->
	<main class="relative flex min-h-0 flex-1 flex-col overflow-y-auto bg-slate-900">
		{#if panel.errorCarga}
			<div
				role="alert"
				class="border-b border-red-800 bg-red-900/30 px-6 py-3 text-sm text-red-300"
			>
				{panel.errorCarga}
			</div>
		{/if}
		{@render children()}
	</main>
</div>
