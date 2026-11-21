<!--
	@component
	@brief Menú lateral con las secciones del panel.

	Resalta la sección de la ruta actual (aria-current="page").
-->
<script lang="ts">
	import { page } from '$app/state';

	/** Secciones del menú: ruta, ícono y nombre visible. */
	const secciones = [
		{ href: '/monitoreo', icono: '📍', nombre: 'Monitoreo en Vivo' },
		{ href: '/prestamos', icono: '📋', nombre: 'Préstamos' },
		{ href: '/salud', icono: '📡', nombre: 'Salud de Red' },
		{ href: '/gestion', icono: '⚙️', nombre: 'Gestión de Dispositivos' },
		{ href: '/historial', icono: '📂', nombre: 'Historial' }
	];
</script>

<nav class="z-20 flex w-64 flex-col border-r border-slate-800 bg-slate-950 shadow-2xl">
	<div class="border-b border-slate-800 p-6">
		<h1
			class="bg-gradient-to-r from-emerald-400 to-teal-600 bg-clip-text text-2xl font-black tracking-wider text-transparent"
		>
			ECOGUARD
		</h1>
		<p class="mt-1 text-xs tracking-widest text-slate-500 uppercase">Central Operativa</p>
	</div>

	<div class="flex-1 space-y-2 px-3 py-4">
		{#each secciones as seccion (seccion.href)}
			{@const activa = page.url.pathname.startsWith(seccion.href)}
			<a
				href={seccion.href}
				aria-current={activa ? 'page' : undefined}
				class="block w-full rounded-lg px-4 py-3 text-left font-semibold transition-all duration-200 {activa
					? 'border border-emerald-800/50 bg-emerald-900/40 text-emerald-400'
					: 'text-slate-400 hover:bg-slate-800'}"
			>
				{seccion.icono}
				{seccion.nombre}
			</a>
		{/each}
	</div>
</nav>
