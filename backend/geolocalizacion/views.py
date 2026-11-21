# backend/geolocalizacion/views.py
"""
@brief Vistas HTTP del backend: el webhook de ChirpStack y la API REST del panel.

Rutas (definidas en urls.py, todas bajo /api/):
- POST `webhook/`: tramas de los nodos que entrega la integración HTTP de ChirpStack.
- GET `incidentes/activos/` e `incidentes/historial/`; POST `incidentes/<id>/estado/`.
- GET y POST `dispositivos/`; PATCH `dispositivos/<dev_eui>/`.
- GET y POST `prestamos/`; POST `prestamos/<id>/devolucion/`.
- GET `ruta-piloto/`: gateways, zonas y puntos de control en GeoJSON.

Los errores se responden con un JSON {"error": "mensaje"} y el código HTTP correspondiente.
"""
import hmac
import json

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.gis.db.models.functions import Distance
from django.utils.timezone import now

from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import (
    DispositivoSerializer, IncidenteActivoSerializer, IncidenteSerializer, NuevoPrestamoSerializer,
    PrestamoVigenteSerializer,
)

from .models import Asignacion, Dispositivo, Gateway, ZonaGeografica, PuntoControl, Incidente
from .tramas import TramaInvalida, desde_chirpstack, registrar_trama

@csrf_exempt
def chirpstack_webhook(request):
    """
    @brief Recibe las tramas de la integración HTTP de ChirpStack.

    ChirpStack hace un POST por cada evento del dispositivo e indica el tipo en el parámetro
    `?event=`. Solo se procesan los de subida de datos (`up`); los demás (join, ack, status...) se
    responden con 200 para que ChirpStack no los reintente.

    Si `CHIRPSTACK_TOKEN` está definido, la petición debe traer la cabecera
    `Authorization: Bearer <token>`: en la red local cualquiera podría inventar una alerta. La
    comparación usa hmac.compare_digest() para no filtrar el token por tiempos de respuesta.

    @param request Petición HTTP con el JSON del evento de ChirpStack v4.
    @return JsonResponse con uno de estos códigos:
      - 201: trama guardada y alerta emitida a los paneles.
      - 200: evento distinto de `up`, o trama sin datos del nodo (otro puerto o solo comandos MAC).
      - 400: JSON inválido o trama incompleta (TramaInvalida).
      - 401: falta el token o no coincide.
      - 405: método distinto de POST.
      - 500: error inesperado al guardar.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Solo se acepta POST'}, status=405)

    # Con CHIRPSTACK_TOKEN definido solo se aceptan tramas con ese token, que ChirpStack manda en una
    # cabecera de su integración HTTP: en la red local cualquiera podría inventar una alerta
    token = settings.CHIRPSTACK_TOKEN
    if token and not hmac.compare_digest(request.headers.get('Authorization', ''), f'Bearer {token}'):
        return JsonResponse({'error': 'No autorizado'}, status=401)

    try:
        data = json.loads(request.body)

        # Ignorar cualquier evento de ChirpStack que no sea de subida de datos ("up")
        event = request.GET.get('event', '')
        if event and event != 'up':
            return JsonResponse({'status': f'Evento {event} ignorado'}, status=200)

        trama = desde_chirpstack(data)
        if trama is None:
            return JsonResponse({'status': 'Trama sin datos del nodo: ignorada'}, status=200)
        registrar_trama(trama)
        return JsonResponse({'status': 'success', 'mensaje': 'Trama guardada y alerta emitida'}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    except TramaInvalida as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@api_view(['GET'])
def listar_incidentes_activos(request):
    """
    @brief Devuelve los incidentes abiertos (ACTIVO o EN_ATENCION) para el mapa del panel.

    Incluye los de nodos inhabilitados: un SOS nunca se oculta, y el campo nodo_activo le indica al
    panel que lo señale. Cada incidente trae la ficha completa del visitante (IncidenteActivoSerializer).
    @param request Petición GET.
    @return Lista de incidentes abiertos.
    """
    incidentes = (
        Incidente.objects
        .filter(estado__in=Incidente.ABIERTOS)
        .select_related('dispositivo', 'zona', 'asignacion__visitante')
    )
    serializer = IncidenteActivoSerializer(incidentes, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def historial_incidentes(request):
    """
    @brief Devuelve los incidentes cerrados, del más reciente al más antiguo (CU-08).

    Se limita a los 500 más recientes para que la respuesta no crezca sin control.
    @param request Petición GET.
    @return Lista de incidentes cerrados (IncidenteSerializer, sin datos de salud).
    """
    incidentes = (
        Incidente.objects
        .exclude(estado__in=Incidente.ABIERTOS)
        .select_related('dispositivo', 'zona', 'asignacion__visitante')
        .order_by('-cerrado_en')[:500]
    )
    return Response(IncidenteSerializer(incidentes, many=True).data)

@api_view(['POST'])
def cambiar_estado_incidente(request, id_incidente):
    """
    @brief Cambia el estado de un incidente abierto desde el panel (CU-04).

    Estados permitidos: EN_ATENCION, RESUELTO y FALSA_ALARMA. Los dos últimos cierran el incidente y
    guardan la hora de cierre. La cancelación no está permitida aquí: la emite el visitante desde la
    app (CU-12). La fila se bloquea (select_for_update) para que dos vigilantes no la cambien a la vez.
    @param request Petición POST con {"estado": ..., "notas_rescate": ... (opcional)}.
    @param id_incidente Clave primaria del incidente.
    @return El incidente actualizado (IncidenteSerializer); 400 si el estado no es válido, 404 si
            el incidente no existe y 409 si ya estaba cerrado.
    """
    PERMITIDOS = [Incidente.Estado.EN_ATENCION, Incidente.Estado.RESUELTO, Incidente.Estado.FALSA_ALARMA]
    estado = request.data.get('estado')
    if estado not in PERMITIDOS:
        return Response({'error': f'Estado inválido. Usa uno de: {", ".join(PERMITIDOS)}'}, status=400)

    with transaction.atomic():
        incidente = Incidente.objects.select_for_update().select_related('dispositivo').filter(id_incidente=id_incidente).first()
        if incidente is None:
            return Response({'error': 'El incidente no existe.'}, status=404)
        if incidente.estado not in Incidente.ABIERTOS:
            return Response({'error': 'El incidente ya está cerrado.'}, status=409)

        incidente.estado = estado
        campos = ['estado']
        if estado != Incidente.Estado.EN_ATENCION:
            incidente.cerrado_en = now()
            campos.append('cerrado_en')
        if 'notas_rescate' in request.data:
            incidente.notas_rescate = request.data['notas_rescate']
            campos.append('notas_rescate')
        incidente.save(update_fields=campos)

    return Response(IncidenteSerializer(incidente).data)

@api_view(['GET', 'POST'])
def dispositivos(request):
    """
    @brief Lista los nodos registrados (GET, CU-05) o registra uno nuevo (POST, CU-06).

    El DevEUI se guarda en mayúsculas para detectar duplicados aunque se escriba en minúsculas.
    @param request Petición GET, o POST con {"dev_eui": ..., "nombre": ...}.
    @return GET: lista de nodos ordenada por nombre. POST: el nodo creado (201), o 400 con los
            errores de validación.
    """
    if request.method == 'GET':
        return Response(DispositivoSerializer(Dispositivo.objects.order_by('nombre'), many=True).data)

    # El DevEUI se guarda en mayúsculas: se compara igual para detectar duplicados
    datos = {**request.data, 'dev_eui': str(request.data.get('dev_eui', '')).strip().upper()}
    serializer = DispositivoSerializer(data=datos)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=201)

@api_view(['PATCH'])
def dispositivo_detalle(request, dev_eui):
    """
    @brief Habilita o inhabilita un nodo, o cambia su nombre (CU-07).

    Un nodo con una emergencia abierta no se puede inhabilitar.
    @param request Petición PATCH con los campos a cambiar, p. ej. {"activo": false}.
    @param dev_eui DevEUI del nodo (se acepta en minúsculas).
    @return El nodo actualizado; 404 si no existe y 409 si se intenta inhabilitar con un SOS abierto.
    """
    dispositivo = Dispositivo.objects.filter(dev_eui=dev_eui.upper()).first()
    if dispositivo is None:
        return Response({'error': 'El dispositivo no existe.'}, status=404)

    serializer = DispositivoSerializer(dispositivo, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    if serializer.validated_data.get('activo') is False and dispositivo.incidentes.filter(estado__in=Incidente.ABIERTOS).exists():
        return Response({'error': 'No se puede inhabilitar un nodo con una emergencia activa.'}, status=409)

    serializer.save()
    return Response(serializer.data)

@api_view(['GET', 'POST'])
def prestamos(request):
    """
    @brief Lista los préstamos vigentes (GET) o presta un nodo a un visitante (POST, CU-13).

    Los datos de salud se guardan pero no se devuelven aquí: solo se muestran con una emergencia
    abierta (RNF-12).
    @param request Petición GET, o POST con los campos de NuevoPrestamoSerializer.
    @return GET: préstamos vigentes, del más reciente al más antiguo. POST: el préstamo creado (201),
            400 con los errores de validación o 409 si el nodo se prestó al mismo tiempo desde otro panel.
    """
    if request.method == 'GET':
        vigentes = (
            Asignacion.objects
            .filter(fecha_devolucion__isnull=True)
            .select_related('visitante', 'dispositivo')
            .order_by('-fecha_asignacion')
        )
        return Response(PrestamoVigenteSerializer(vigentes, many=True).data)

    serializer = NuevoPrestamoSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        prestamo = serializer.save()
    except IntegrityError:
        # Dos vigilantes prestaron el mismo nodo a la vez: la base de datos rechaza el segundo
        return Response({'error': 'El nodo ya está prestado.'}, status=409)
    return Response(PrestamoVigenteSerializer(prestamo).data, status=201)

@api_view(['POST'])
def registrar_devolucion(request, id_asignacion):
    """
    @brief Cierra el préstamo cuando el visitante entrega el nodo (CU-14).

    Si el nodo tiene una emergencia abierta, el vigilante debe cerrarla primero.
    @param request Petición POST (sin cuerpo).
    @param id_asignacion Clave primaria del préstamo.
    @return El préstamo cerrado; 404 si no existe y 409 si ya fue devuelto o el nodo tiene una
            emergencia abierta.
    """
    with transaction.atomic():
        prestamo = (
            Asignacion.objects.select_for_update()
            .select_related('visitante', 'dispositivo')
            .filter(id_asignacion=id_asignacion)
            .first()
        )
        if prestamo is None:
            return Response({'error': 'El préstamo no existe.'}, status=404)
        if prestamo.fecha_devolucion is not None:
            return Response({'error': 'El nodo ya fue devuelto.'}, status=409)
        if prestamo.dispositivo.incidentes.filter(estado__in=Incidente.ABIERTOS).exists():
            return Response(
                {'error': 'El nodo tiene una emergencia abierta. Ciérrela antes de registrar la devolución.'},
                status=409,
            )
        prestamo.fecha_devolucion = now()
        prestamo.save(update_fields=['fecha_devolucion'])
    return Response(PrestamoVigenteSerializer(prestamo).data)

@api_view(['GET'])
def ruta_piloto(request):
    """
    @brief Devuelve la ruta piloto como GeoJSON para el mapa del panel.

    Incluye los gateways, las zonas y los puntos de control en el orden del recorrido. Cada punto
    trae su distancia al primer gateway en metros (distancia_gateway_m), útil para las pruebas de
    cobertura.
    @param request Petición GET.
    @return FeatureCollection de GeoJSON. La propiedad "tipo" de cada Feature indica si es
            "gateway", "zona" o "punto_control".
    """
    def feature(geometria, propiedades):
        return {'type': 'Feature', 'geometry': json.loads(geometria.geojson), 'properties': propiedades}

    features = [
        feature(g.ubicacion, {'tipo': 'gateway', 'nombre': g.nombre, 'gateway_eui': g.gateway_eui})
        for g in Gateway.objects.all()
    ]
    features += [
        feature(z.area, {'tipo': 'zona', 'nombre': z.nombre, 'tipo_zona': z.tipo})
        for z in ZonaGeografica.objects.all()
    ]

    puntos = PuntoControl.objects.all()
    gateway = Gateway.objects.first()
    if gateway:
        # En geography, PostGIS mide la distancia en metros sobre el elipsoide
        puntos = puntos.annotate(distancia=Distance('punto', gateway.ubicacion))
    features += [
        feature(p.punto, {
            'tipo': 'punto_control', 'codigo': p.codigo, 'nombre': p.nombre, 'orden': p.orden,
            'levantado_en_sitio': p.levantado_en_sitio,
            'distancia_gateway_m': round(p.distancia.m) if gateway else None,
        })
        for p in puntos
    ]
    return Response({'type': 'FeatureCollection', 'features': features})
