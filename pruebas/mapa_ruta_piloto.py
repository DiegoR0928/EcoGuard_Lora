"""
Dibuja el mapa de la ruta piloto (figura del SDD) a partir de ruta_piloto.geojson.

    python mapa_ruta_piloto.py [salida.pdf]

Sin argumentos escribe ruta-piloto.pdf junto a este script. Para actualizar la figura del SDD:

    python mapa_ruta_piloto.py C:/Users/Diego/SeminarioTesis/SDD_LaTeX/imagenes/ruta-piloto.pdf

Vuelve a correrlo cuando se levanten los puntos en sitio y se actualice ruta_piloto.geojson.
El mapa base (edificios, andadores y vialidades) viene de campus_base.geojson, extraído de OpenStreetMap.
"""
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon

AQUI = Path(__file__).parent
SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI / 'ruta-piloto.pdf'

ruta = json.load(open(AQUI / 'ruta_piloto.geojson', encoding='utf-8'))
base = json.load(open(AQUI / 'campus_base.geojson', encoding='utf-8'))


def por_tipo(tipo):
    return [f for f in ruta['features'] if f['properties']['tipo'] == tipo]


gateway = por_tipo('gateway')[0]
puntos = sorted(por_tipo('punto_control'), key=lambda f: f['properties']['id'])
perimetro = por_tipo('perimetro')[0]

# Proyección local en metros (este, norte) con origen en el gateway: a esta escala
# la distorsión es despreciable y las distancias del mapa se leen directamente
LON0, LAT0 = gateway['geometry']['coordinates']
K = math.cos(math.radians(LAT0))


def metros(coords):
    return [((lon - LON0) * K * 111320, (lat - LAT0) * 111320) for lon, lat in coords]


GRIS_OSCURO, GRIS, GRIS_CLARO = '#5F5E5A', '#888780', '#D3D1C7'
MORADO, MORADO_CLARO = '#534AB7', '#CECBF6'
CORAL = '#D85A30'

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 7.5, 'pdf.fonttype': 42})
fig, ax = plt.subplots(figsize=(6.3, 5.4))
ax.set_aspect('equal')
ax.axis('off')

# --- Mapa base ---
for f in base['features']:
    capa, coords = f['properties']['capa'], f['geometry']['coordinates']
    if capa == 'edificio':
        es_gateway = f['properties']['osm_way'] == gateway['properties'].get('osm_way')
        ax.add_patch(Polygon(metros(coords[0]), closed=True, zorder=3, linewidth=0.4,
                             facecolor=MORADO_CLARO if es_gateway else '#E4E2DA',
                             edgecolor=MORADO if es_gateway else '#B4B2A9'))
    else:
        xs, ys = zip(*metros(coords))
        if capa == 'vialidad':
            ax.plot(xs, ys, color=GRIS_CLARO, linewidth=2.6, solid_capstyle='round', zorder=1)
        else:
            ax.plot(xs, ys, color=GRIS, linewidth=0.5, linestyle=(0, (1.5, 1.5)), zorder=2)

xs, ys = zip(*metros(perimetro['geometry']['coordinates'][0]))
ax.plot(xs, ys, color=GRIS_OSCURO, linewidth=0.9, linestyle=(0, (5, 3)), zorder=2)
x_min, x_max, y_min, y_max = min(xs) - 25, max(xs) + 25, min(ys) - 45, max(ys) + 15

# --- Distancia al gateway ---
for r in (200, 400, 600):
    ax.add_patch(Circle((0, 0), r, fill=False, linestyle=(0, (4, 3)), linewidth=0.7, color='#7F77DD', zorder=4))
    ax.text(-r, 0, f'{r} m', color=MORADO, ha='center', va='center', zorder=6,
            bbox=dict(boxstyle='round,pad=0.15', facecolor='white', edgecolor='none'))

# --- Ruta y puntos de control ---
pts = [metros([f['geometry']['coordinates']])[0] for f in puntos]
ax.plot(*zip(*pts), color=CORAL, linewidth=1.6, zorder=5, solid_joinstyle='round')

# Posición de cada etiqueta respecto a su punto (desplazamiento en puntos tipográficos, alineación)
POSICION = {'PC-1': ((-9, 0), 'right', 'center'), 'PC-2': ((9, 0), 'left', 'center'),
            'PC-3': ((-9, 0), 'right', 'center'), 'PC-4': ((0, -9), 'center', 'top'),
            'PC-5': ((0, -9), 'center', 'top'), 'PC-6': ((6, 9), 'right', 'bottom')}
for (x, y), f in zip(pts, puntos):
    p = f['properties']
    ax.plot(x, y, 'o', markersize=11, markerfacecolor=CORAL, markeredgecolor='white', markeredgewidth=0.8, zorder=7)
    ax.text(x, y, p['id'].split('-')[1], color='white', fontweight='bold', ha='center', va='center', zorder=8)
    desplazamiento, ha, va = POSICION.get(p['id'], ((9, 0), 'left', 'center'))
    ax.annotate(f"{p['nombre']}\n{p['distancia_gateway_m']} m", (x, y), xytext=desplazamiento,
                textcoords='offset points', ha=ha, va=va, zorder=8, linespacing=1.2,
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='none', alpha=0.85))

# --- Gateway ---
ax.plot(0, 0, '^', markersize=10, markerfacecolor=MORADO, markeredgecolor='white', markeredgewidth=0.8, zorder=8)
ax.annotate(f"Gateway LoRaWAN\n{gateway['properties']['edificio']}", (0, 0), xytext=(9, 0),
            textcoords='offset points', ha='left', va='center', color=MORADO, fontweight='bold', zorder=8,
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='none', alpha=0.85))

# --- Escala, norte y atribución ---
ex, ey = x_min + 15, y_min + 15
for i, color in enumerate(('black', 'white')):
    ax.add_patch(plt.Rectangle((ex + i * 100, ey), 100, 9, facecolor=color, edgecolor='black', linewidth=0.5, zorder=9))
for d in (0, 100, 200):
    ax.text(ex + d, ey + 15, f'{d}' if d else '0', ha='center', va='bottom', zorder=9)
ax.text(ex + 215, ey + 4, 'm', va='center', zorder=9)

nx, ny = x_max - 20, y_max - 95
ax.annotate('', xy=(nx, ny + 70), xytext=(nx, ny), zorder=9,
            arrowprops=dict(arrowstyle='-|>', color='black', linewidth=1.0, mutation_scale=10))
ax.text(nx, ny + 76, 'N', ha='center', va='bottom', fontweight='bold', zorder=9)

ax.text(x_max, y_min + 2, '© OpenStreetMap contributors', ha='right', va='bottom', fontsize=6, color=GRIS_OSCURO, zorder=9)

ax.set_xlim(x_min, x_max)
ax.set_ylim(y_min, y_max)
fig.savefig(SALIDA, bbox_inches='tight', pad_inches=0.02)
print(f'Mapa guardado en {SALIDA}')
