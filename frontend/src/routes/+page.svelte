<script lang="ts">
  import { onMount, tick } from 'svelte';

  // --- TIPOS ---
  interface Alerta { id: string; lat: number; lon: number; bateria: number; tiempo: string; mostrarDetalles: boolean; }
  interface Nodo { id: string; hex: string; activo: boolean; bateria: number; ultimoPing: number; sosActivo: boolean; }
  interface Historial { id: string; fecha: string; lat: number; lon: number; estado: string; }

  // --- ESTADO GLOBAL (SVELTE 5 RUNES) ---
  let pestañaActual = $state('monitoreo'); 

  let alertasActivas = $state<Alerta[]>([
    { id: 'Heltec-04', lat: 22.7758, lon: -102.5714, bateria: 12, tiempo: 'Hace 3 min', mostrarDetalles: false } 
  ]);

  let nodos = $state<Nodo[]>([
    { id: 'Heltec-04', hex: 'A1B2C3D4E5F67890', activo: true, bateria: 12, ultimoPing: 3, sosActivo: true },
    { id: 'Heltec-05', hex: 'FFFFFFFFFFFFFFFF', activo: true, bateria: 85, ultimoPing: 150, sosActivo: false }, 
    { id: 'Heltec-06', hex: '1234567890ABCDEF', activo: false, bateria: 0, ultimoPing: 999, sosActivo: false }
  ]);

  let nuevoNodoId = $state('');
  let nuevoNodoNombre = $state('');
  let mensajeGestion = $state({ texto: '', error: false });

  let historial = $state<Historial[]>([
    { id: 'Heltec-02', fecha: '2026-10-01', lat: 22.7810, lon: -102.5800, estado: 'Resuelto' }
  ]);
  let filtroFecha = $state('');

  // --- VARIABLE DERIVADA ---
  let historialFiltrado = $derived(
    filtroFecha 
      ? historial.filter(h => h.fecha === filtroFecha) 
      : historial
  );

  // --- MAPA LEAFLET ---
  let map: any;
  let marcadores: Record<string, any> = {};

  async function inicializarMapa() {
    if (pestañaActual !== 'monitoreo') return;
    await tick(); 
    
    if (!map) {
      const L = await import('leaflet');
      await import('leaflet/dist/leaflet.css');

      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
        iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
      });

      map = L.map('mapa').setView([22.7780, -102.5750], 14);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        className: 'map-tiles-dark' 
      }).addTo(map);
    }

    Object.values(marcadores).forEach(m => map.removeLayer(m));
    
    const L_local = await import('leaflet');
    alertasActivas.forEach(alerta => {
      marcadores[alerta.id] = L_local.marker([alerta.lat, alerta.lon]).addTo(map)
        .bindPopup(`<b style="color:red">${alerta.id}</b><br>¡SOS Activo!`);
    });
  }

  function cambiarPestaña(nueva: string) {
    pestañaActual = nueva;
    if (nueva === 'monitoreo') inicializarMapa();
  }

  function alternarDetalles(id: string) {
    alertasActivas = alertasActivas.map(a => a.id === id ? { ...a, mostrarDetalles: !a.mostrarDetalles } : a);
  }

  function marcarResuelto(id: string) {
    if (confirm("¿Seguro que desea cerrar este incidente?")) { 
      const alerta = alertasActivas.find(a => a.id === id);
      if (!alerta) return; 

      const fechaActual = new Date().toISOString().split('T')[0];
      historial = [...historial, { id: alerta.id, fecha: fechaActual, lat: alerta.lat, lon: alerta.lon, estado: 'Resuelto' }];
      
      alertasActivas = alertasActivas.filter(a => a.id !== id);
      const nodo = nodos.find(n => n.id === id);
      if (nodo) nodo.sosActivo = false;

      if (marcadores[id] && map) {
        map.removeLayer(marcadores[id]);
        delete marcadores[id];
      }
    }
  }

  function registrarDispositivo() {
    const hexRegex = /^[0-9A-Fa-f]{16}$/;
    
    if (!hexRegex.test(nuevoNodoId)) {
      mensajeGestion = { texto: 'Formato inválido. Debe ser hexadecimal de 64-bits.', error: true }; 
      return;
    }
    if (nodos.some(n => n.hex === nuevoNodoId)) {
      mensajeGestion = { texto: 'El dispositivo ya está registrado.', error: true }; 
      return;
    }
    
    nodos = [...nodos, { id: nuevoNodoNombre, hex: nuevoNodoId.toUpperCase(), activo: true, bateria: 100, ultimoPing: 0, sosActivo: false }];
    mensajeGestion = { texto: 'Dispositivo registrado con éxito.', error: false };
    nuevoNodoId = ''; nuevoNodoNombre = '';
  }

  function toggleInhabilitar(nodo: Nodo) {
    if (nodo.sosActivo && nodo.activo) {
      mensajeGestion = { texto: 'No se puede inhabilitar un nodo con una emergencia activa.', error: true }; 
      return;
    }
    nodos = nodos.map(n => n.hex === nodo.hex ? { ...n, activo: !n.activo } : n);
    mensajeGestion = { texto: `Dispositivo ${nodo.activo ? 'inhabilitado' : 'habilitado'} correctamente.`, error: false };
  }

  onMount(() => {
    inicializarMapa();
  });
</script>

<div class="flex h-screen w-full bg-slate-900 text-slate-300 font-sans overflow-hidden selection:bg-emerald-500 selection:text-white">
  
  <!-- MENU LATERAL (NAVEGACIÓN) -->
  <nav class="w-64 bg-slate-950 border-r border-slate-800 flex flex-col shadow-2xl z-20">
    <div class="p-6 border-b border-slate-800">
      <h1 class="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-600 tracking-wider">ECOGUARD</h1>
      <p class="text-xs text-slate-500 uppercase tracking-widest mt-1">Central Operativa</p>
    </div>
    
    <div class="flex-1 py-4 space-y-2 px-3">
      <button onclick={() => cambiarPestaña('monitoreo')} class="w-full text-left px-4 py-3 rounded-lg transition-all duration-200 font-semibold {pestañaActual === 'monitoreo' ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50' : 'hover:bg-slate-800 text-slate-400'}">
        📍 Monitoreo en Vivo
      </button>
      <button onclick={() => cambiarPestaña('salud')} class="w-full text-left px-4 py-3 rounded-lg transition-all duration-200 font-semibold {pestañaActual === 'salud' ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50' : 'hover:bg-slate-800 text-slate-400'}">
        📡 Salud de Red
      </button>
      <button onclick={() => cambiarPestaña('gestion')} class="w-full text-left px-4 py-3 rounded-lg transition-all duration-200 font-semibold {pestañaActual === 'gestion' ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50' : 'hover:bg-slate-800 text-slate-400'}">
        ⚙️ Gestión de Dispositivos
      </button>
      <button onclick={() => cambiarPestaña('historial')} class="w-full text-left px-4 py-3 rounded-lg transition-all duration-200 font-semibold {pestañaActual === 'historial' ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50' : 'hover:bg-slate-800 text-slate-400'}">
        📂 Historial
      </button>
    </div>
  </nav>

  <!-- CONTENIDO PRINCIPAL -->
  <main class="flex-1 relative flex flex-col bg-slate-900">
    
    <!-- PESTAÑA: MONITOREO -->
    {#if pestañaActual === 'monitoreo'}
      <div class="flex h-full w-full">
        <!-- Panel lateral de alertas -->
        <aside class="w-96 bg-slate-900 border-r border-slate-800 p-5 overflow-y-auto z-10 shadow-[10px_0_15px_-3px_rgba(0,0,0,0.5)]">
          <h2 class="text-lg font-bold text-white mb-4 flex items-center justify-between">
            Alertas Activas
            <span class="bg-red-500/20 text-red-400 px-2 py-1 rounded text-xs animate-pulse">{alertasActivas.length}</span>
          </h2>
          
          {#if alertasActivas.length === 0}
            <div class="p-4 bg-emerald-900/20 border border-emerald-800 text-emerald-400 rounded-lg text-sm font-medium">
              Zona libre de emergencias
            </div>
          {/if}

          {#each alertasActivas as alerta}
            <div class="mb-4 border border-slate-700 bg-slate-800/50 rounded-xl overflow-hidden backdrop-blur-sm transition hover:border-slate-500">
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <!-- svelte-ignore a11y_no_static_element_interactions -->
              <div class="p-4 cursor-pointer flex justify-between items-center bg-slate-800" onclick={() => alternarDetalles(alerta.id)}>
                <span class="font-bold text-red-500 flex items-center gap-2">
                  <span class="w-2 h-2 rounded-full bg-red-500 animate-ping"></span>
                  {alerta.id}
                </span>
                <span class="text-xs text-slate-400 bg-slate-900 px-2 py-1 rounded">{alerta.tiempo}</span>
              </div>

              {#if alerta.mostrarDetalles}
                <div class="p-4 border-t border-slate-700 bg-slate-800/30">
                  <div class="font-mono text-xs text-slate-300 space-y-1 bg-slate-900 p-3 rounded border border-slate-800">
                    <p>LAT: {alerta.lat}</p>
                    <p>LON: {alerta.lon}</p>
                  </div>
                  
                  <p class="mt-3 text-sm font-bold flex items-center gap-2 {alerta.bateria < 15 ? 'text-red-500 animate-pulse' : 'text-emerald-400'}">
                    Batería del Nodo: {alerta.bateria}%
                  </p>

                  <button onclick={() => marcarResuelto(alerta.id)} class="mt-4 w-full bg-slate-700 hover:bg-emerald-600 text-white font-semibold py-2.5 rounded-lg transition-colors border border-slate-600 hover:border-emerald-500">
                    Marcar como Resuelto
                  </button>
                </div>
              {/if}
            </div>
          {/each}
        </aside>

        <!-- Mapa Leaflet -->
        <div class="flex-1 relative bg-slate-950">
          <div id="mapa" class="w-full h-full z-0"></div>
          <div class="absolute top-4 right-4 bg-slate-900/80 backdrop-blur border border-slate-700 px-4 py-2 rounded-full z-[1000] text-xs font-mono text-emerald-400">
            Conexión: ESTABLE
          </div>
        </div>
      </div>
    {/if}

    <!-- PESTAÑA: SALUD DE RED -->
    {#if pestañaActual === 'salud'}
      <div class="p-8">
        <h2 class="text-3xl font-bold text-white mb-6">Monitoreo Salud de los Nodos</h2>
        <div class="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <table class="w-full text-left text-sm">
            <thead class="bg-slate-900 text-slate-400 border-b border-slate-700">
              <tr>
                <th class="p-4 font-semibold">Dispositivo</th>
                <th class="p-4 font-semibold">Batería</th>
                <th class="p-4 font-semibold">Último Ping</th>
                <th class="p-4 font-semibold">Estado</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-700/50">
              {#each nodos as nodo}
                <tr class="hover:bg-slate-700/30 transition-colors">
                  <td class="p-4 font-medium text-slate-200">{nodo.id}</td>
                  <td class="p-4 {nodo.bateria < 20 ? 'text-red-400' : 'text-emerald-400'}">{nodo.bateria}%</td>
                  <td class="p-4 text-slate-400">Hace {nodo.ultimoPing} min</td>
                  <td class="p-4">
                    {#if nodo.ultimoPing > 120}
                      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-900/30 text-red-400 border border-red-800/50">
                        Posiblemente apagado/fuera de rango
                      </span>
                    {:else if nodo.activo}
                      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-900/30 text-emerald-400 border border-emerald-800/50">
                        Operativo
                      </span>
                    {:else}
                      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-700 text-slate-300 border border-slate-600">
                        Inhabilitado
                      </span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    <!-- PESTAÑA: GESTIÓN DE DISPOSITIVOS -->
    {#if pestañaActual === 'gestion'}
      <div class="p-8 max-w-5xl">
        <h2 class="text-3xl font-bold text-white mb-6">Gestión de Dispositivos</h2>
        
        {#if mensajeGestion.texto}
          <div class="mb-6 p-4 rounded-lg border {mensajeGestion.error ? 'bg-red-900/20 border-red-800 text-red-400' : 'bg-emerald-900/20 border-emerald-800 text-emerald-400'}">
            {mensajeGestion.texto}
          </div>
        {/if}

        <div class="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-8 shadow-lg">
          <h3 class="text-lg font-semibold text-slate-200 mb-4">Registrar Nuevo Nodo</h3>
          <div class="flex gap-4 items-end">
            <div class="flex-1">
              <label class="block text-xs text-slate-400 mb-1 font-semibold uppercase">DevEUI (16 caracteres Hex)</label>
              <input bind:value={nuevoNodoId} type="text" placeholder="Ej. A1B2C3D4E5F67890" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-white focus:outline-none focus:border-emerald-500 font-mono text-sm uppercase">
            </div>
            <div class="flex-1">
              <label class="block text-xs text-slate-400 mb-1 font-semibold uppercase">Nombre Legible</label>
              <input bind:value={nuevoNodoNombre} type="text" placeholder="Ej. Heltec-08" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-white focus:outline-none focus:border-emerald-500 text-sm">
            </div>
            <button onclick={registrarDispositivo} class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 px-8 rounded-lg transition-colors">
              Guardar
            </button>
          </div>
        </div>

        <h3 class="text-lg font-semibold text-slate-200 mb-4">Nodos Registrados</h3>
        <div class="grid grid-cols-2 gap-4">
          {#each nodos as nodo}
            <div class="bg-slate-800 border border-slate-700 p-4 rounded-xl flex justify-between items-center">
              <div>
                <p class="font-bold text-white text-lg">{nodo.id}</p>
                <p class="text-xs font-mono text-slate-500">{nodo.hex}</p>
              </div>
              <button onclick={() => toggleInhabilitar(nodo)} class="px-4 py-2 rounded text-sm font-semibold border transition-colors {nodo.activo ? 'border-red-500/50 text-red-400 hover:bg-red-500/10' : 'border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/10'}">
                {nodo.activo ? 'Inhabilitar' : 'Habilitar'}
              </button>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- PESTAÑA: HISTORIAL -->
    {#if pestañaActual === 'historial'}
      <div class="p-8">
        <div class="flex justify-between items-center mb-6">
          <h2 class="text-3xl font-bold text-white">Historial de Incidentes</h2>
          <button class="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 transition border border-slate-600">
            Descargar reporte
          </button>
        </div>

        <div class="flex gap-4 mb-6">
          <input bind:value={filtroFecha} type="date" class="bg-slate-800 border border-slate-700 rounded-lg p-2.5 text-slate-300 focus:outline-none focus:border-emerald-500">
          <button onclick={() => filtroFecha = ''} class="text-slate-400 hover:text-white px-3">Limpiar filtro</button>
        </div>

        <div class="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          {#if historialFiltrado.length === 0}
            <div class="p-8 text-center text-slate-400 border-t border-slate-700">
              No se encontraron registros con ese filtro de búsqueda.
            </div>
          {:else}
            <table class="w-full text-left text-sm">
              <thead class="bg-slate-900 text-slate-400 border-b border-slate-700">
                <tr>
                  <th class="p-4 font-semibold">Fecha</th>
                  <th class="p-4 font-semibold">Dispositivo</th>
                  <th class="p-4 font-semibold">Coordenadas</th>
                  <th class="p-4 font-semibold">Estado Final</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700/50">
                {#each historialFiltrado as reg}
                  <tr class="hover:bg-slate-700/30">
                    <td class="p-4 text-slate-300">{reg.fecha}</td>
                    <td class="p-4 font-medium text-white">{reg.id}</td>
                    <td class="p-4 font-mono text-xs text-slate-400">{reg.lat}, {reg.lon}</td>
                    <td class="p-4">
                      <span class="bg-slate-700 text-slate-300 px-2 py-1 rounded text-xs font-semibold">{reg.estado}</span>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>
      </div>
    {/if}
  </main>
</div>

<style>
  :global(.map-tiles-dark) {
    filter: brightness(0.6) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.7);
  }
  :global(.leaflet-popup-content-wrapper), :global(.leaflet-popup-tip) {
    background-color: #1e293b !important;
    color: #f8fafc !important;
    border: 1px solid #334155;
  }
</style>