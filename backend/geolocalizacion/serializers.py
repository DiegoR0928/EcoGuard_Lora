# backend/geolocalizacion/serializers.py
"""
@brief Serializadores de Django REST Framework: convierten los modelos a JSON para el panel y la app.

También validan los datos que llegan en las peticiones POST y PATCH. Los datos de salud del
visitante solo viajan en IncidenteActivoSerializer, es decir, mientras su nodo tiene una emergencia
abierta (RNF-12).
"""
from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .models import Asignacion, Dispositivo, Incidente, Visitante, validar_eui

class DispositivoSerializer(serializers.ModelSerializer):
    """
    @brief Nodo en la sección de dispositivos del panel (CU-05, CU-06 y CU-07).

    Al registrar un nodo valida que el DevEUI tenga 16 dígitos hexadecimales y que no esté repetido.
    """
    ## Verdadero si el nodo tiene una emergencia abierta. Un nodo así no se puede inhabilitar (CU-07).
    sos_activo = serializers.SerializerMethodField()
    ## Nombre del visitante que lleva el nodo ahora; nulo si está disponible.
    prestado_a = serializers.SerializerMethodField()

    class Meta:
        model = Dispositivo
        fields = ['id_dispositivo', 'dev_eui', 'nombre', 'activo', 'ultima_bateria_mv', 'ultimo_contacto', 'creado_en', 'sos_activo', 'prestado_a']
        read_only_fields = ['id_dispositivo', 'ultima_bateria_mv', 'ultimo_contacto', 'creado_en']
        extra_kwargs = {
            'dev_eui': {'validators': [
                validar_eui,
                UniqueValidator(queryset=Dispositivo.objects.all(), message='El dispositivo ya está registrado.'),
            ]},
            'nombre': {'error_messages': {'blank': 'Escribe un nombre para el nodo.', 'required': 'Escribe un nombre para el nodo.'}},
        }

    def get_sos_activo(self, obj):
        """
        @brief Calcula el campo sos_activo.
        @param obj Dispositivo que se serializa.
        @return Verdadero si el nodo tiene un incidente ACTIVO o EN_ATENCION.
        """
        return obj.incidentes.filter(estado__in=Incidente.ABIERTOS).exists()

    def get_prestado_a(self, obj):
        """
        @brief Calcula el campo prestado_a.
        @param obj Dispositivo que se serializa.
        @return Nombre y apellido del visitante del préstamo vigente, o None si el nodo está disponible.
        """
        prestamo = obj.asignaciones.filter(fecha_devolucion__isnull=True).select_related('visitante').first()
        return str(prestamo.visitante) if prestamo else None


class VisitanteSerializer(serializers.ModelSerializer):
    """
    @brief Ficha completa del visitante, incluidos sus datos de salud.

    Solo se usa dentro de PrestamoSerializer, que a su vez solo aparece en los incidentes abiertos.
    """
    class Meta:
        model = Visitante
        fields = ['id_visitante', 'nombre', 'apellido', 'tipo_sangre', 'contacto_emergencia', 'notas_medicas']


class PrestamoSerializer(serializers.ModelSerializer):
    """
    @brief Préstamo con la ficha completa del visitante, para la brigada de rescate.
    """
    ## Ficha completa del visitante (VisitanteSerializer).
    visitante = VisitanteSerializer(read_only=True)

    class Meta:
        model = Asignacion
        fields = ['id_asignacion', 'visitante', 'fecha_asignacion', 'fecha_devolucion']


class PrestamoVigenteSerializer(serializers.ModelSerializer):
    """
    @brief Préstamo en la sección de préstamos del panel.

    No incluye datos de salud: esos solo se muestran mientras el nodo tiene una emergencia abierta
    (RNF-12).
    """
    ## DevEUI del nodo prestado.
    dev_eui = serializers.CharField(source='dispositivo.dev_eui', read_only=True)
    ## Nombre legible del nodo prestado.
    nombre_dispositivo = serializers.CharField(source='dispositivo.nombre', read_only=True)
    ## Nombre y apellido del visitante.
    visitante = serializers.StringRelatedField()
    ## Contacto de emergencia del visitante (no es un dato de salud).
    contacto_emergencia = serializers.CharField(source='visitante.contacto_emergencia', read_only=True)
    ## Verdadero si el nodo tiene una emergencia abierta: la devolución no se permite hasta cerrarla (CU-14).
    emergencia_abierta = serializers.SerializerMethodField()

    class Meta:
        model = Asignacion
        fields = ['id_asignacion', 'dev_eui', 'nombre_dispositivo', 'visitante', 'contacto_emergencia',
                  'fecha_asignacion', 'fecha_devolucion', 'emergencia_abierta']

    def get_emergencia_abierta(self, obj):
        """
        @brief Calcula el campo emergencia_abierta.
        @param obj Asignacion que se serializa.
        @return Verdadero si el nodo del préstamo tiene un incidente abierto.
        """
        return obj.dispositivo.incidentes.filter(estado__in=Incidente.ABIERTOS).exists()


def _obligatorio(texto, maximo):
    """
    @brief Mensajes de error en español para un campo de texto obligatorio.
    @param texto Descripción del campo en la frase, p. ej. "el nombre del visitante".
    @param maximo Longitud máxima del campo, en caracteres.
    @return Diccionario para el argumento error_messages de un CharField.
    """
    return {
        'required': f'Escribe {texto}.',
        'blank': f'Escribe {texto}.',
        'max_length': f'Máximo {maximo} caracteres para {texto}.',
    }


class NuevoPrestamoSerializer(serializers.Serializer):
    """
    @brief Datos que captura el vigilante al entregar un nodo en la entrada (CU-13).

    Cada préstamo registra un visitante nuevo: los turistas no tienen cuenta y sus datos de salud
    pueden cambiar entre visitas.
    """
    ## DevEUI del nodo que se presta. validate_dev_eui() lo convierte en el Dispositivo.
    dev_eui = serializers.CharField(error_messages={
        'required': 'Elige el nodo que se prestará.',
        'blank': 'Elige el nodo que se prestará.',
    })
    ## Nombre(s) del visitante.
    nombre = serializers.CharField(max_length=60, error_messages=_obligatorio('el nombre del visitante', 60))
    ## Apellido(s) del visitante.
    apellido = serializers.CharField(max_length=60, error_messages=_obligatorio('los apellidos del visitante', 60))
    ## Nombre y teléfono de la persona a notificar.
    contacto_emergencia = serializers.CharField(max_length=120, error_messages=_obligatorio('el contacto de emergencia', 120))
    ## Tipo de sangre (opcional), uno de Visitante.TIPOS_SANGRE.
    tipo_sangre = serializers.ChoiceField(
        choices=Visitante.TIPOS_SANGRE, required=False, allow_blank=True, default='',
        error_messages={'invalid_choice': 'Tipo de sangre no válido.'},
    )
    ## Alergias o padecimientos (opcional).
    notas_medicas = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_dev_eui(self, valor):
        """
        @brief Comprueba que el nodo exista, esté habilitado y no esté prestado.
        @param valor DevEUI escrito por el vigilante (se aceptan minúsculas y espacios alrededor).
        @return El Dispositivo, que sustituye al texto en los datos validados.
        @exception serializers.ValidationError Si el nodo no existe, está inhabilitado o ya está prestado.
        """
        dispositivo = Dispositivo.objects.filter(dev_eui=valor.strip().upper()).first()
        if dispositivo is None:
            raise serializers.ValidationError('El nodo no está registrado.')
        if not dispositivo.activo:
            raise serializers.ValidationError('El nodo está inhabilitado.')
        if dispositivo.asignaciones.filter(fecha_devolucion__isnull=True).exists():
            raise serializers.ValidationError('El nodo ya está prestado.')
        return dispositivo

    def create(self, datos):
        """
        @brief Registra al visitante y el préstamo en una sola transacción.

        Si el préstamo falla (por ejemplo, otro vigilante prestó el mismo nodo un instante antes) no
        queda un visitante suelto.
        @param datos Datos validados; dev_eui ya es un Dispositivo.
        @return La Asignacion creada.
        @exception django.db.IntegrityError Si el nodo ya tiene un préstamo vigente.
        """
        dispositivo = datos.pop('dev_eui')
        with transaction.atomic():
            visitante = Visitante.objects.create(**datos)
            return Asignacion.objects.create(visitante=visitante, dispositivo=dispositivo)


class IncidenteSerializer(serializers.ModelSerializer):
    """
    @brief Incidente en el historial del panel (CU-08) y respuesta de los cambios de estado.

    Del visitante solo incluye el nombre: sus datos de salud no salen en el historial.
    """
    ## Latitud de la última posición; nula si la alerta llegó sin posición satelital.
    latitud = serializers.SerializerMethodField()
    ## Longitud de la última posición; nula si la alerta llegó sin posición satelital.
    longitud = serializers.SerializerMethodField()
    ## Nombre de la zona del parque; nulo si la posición no cae en ninguna.
    zona = serializers.SerializerMethodField()
    ## Nombre legible del nodo.
    nombre_dispositivo = serializers.CharField(source='dispositivo.nombre', read_only=True)
    ## DevEUI del nodo.
    dev_eui = serializers.CharField(source='dispositivo.dev_eui', read_only=True)
    ## Nombre y apellido del visitante; nulo si el nodo no tenía préstamo registrado.
    visitante = serializers.SerializerMethodField()

    class Meta:
        model = Incidente
        fields = [
            'id_incidente',
            'dispositivo',
            'nombre_dispositivo',
            'dev_eui',
            'visitante',
            'estado',
            'latitud',
            'longitud',
            'zona',
            'abierto_en',
            'cerrado_en'
        ]

    def get_latitud(self, obj):
        """
        @brief Calcula el campo latitud.

        Es nula si la alerta llegó sin posición satelital: la interfaz debe mostrar "ubicación
        desconocida".
        @param obj Incidente que se serializa.
        @return Latitud en grados, o None.
        """
        return obj.ultima_posicion.y if obj.ultima_posicion else None  # En PostGIS, Y es la Latitud

    def get_longitud(self, obj):
        """
        @brief Calcula el campo longitud.
        @param obj Incidente que se serializa.
        @return Longitud en grados, o None si no hay posición.
        """
        return obj.ultima_posicion.x if obj.ultima_posicion else None  # En PostGIS, X es la Longitud

    def get_zona(self, obj):
        """
        @brief Calcula el campo zona.
        @param obj Incidente que se serializa.
        @return Nombre de la zona, o None.
        """
        return obj.zona.nombre if obj.zona else None

    def get_visitante(self, obj):
        """
        @brief Calcula el campo visitante.
        @param obj Incidente que se serializa.
        @return Nombre y apellido del visitante del préstamo, o None.
        """
        return str(obj.asignacion.visitante) if obj.asignacion else None


class IncidenteActivoSerializer(IncidenteSerializer):
    """
    @brief Incidente abierto en el mapa del panel: agrega batería, estado del nodo y ficha del visitante.
    """
    ## Voltaje de batería de la trama más reciente del nodo, en mV.
    bateria_mv = serializers.IntegerField(source='dispositivo.ultima_bateria_mv', read_only=True)
    ## Falso si el SOS viene de un nodo inhabilitado: se muestra igual, pero señalado.
    nodo_activo = serializers.BooleanField(source='dispositivo.activo', read_only=True)
    ## Ficha completa del visitante para la brigada; solo viaja mientras la emergencia está abierta.
    ## Nula si el nodo no tenía un préstamo registrado.
    asignacion = PrestamoSerializer(read_only=True)

    class Meta(IncidenteSerializer.Meta):
        fields = IncidenteSerializer.Meta.fields + ['bateria_mv', 'nodo_activo', 'asignacion']
