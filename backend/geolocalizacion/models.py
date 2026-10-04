from django.conf import settings
from django.contrib.gis.db import models
from django.core.validators import RegexValidator
from django.utils import timezone

# Los EUI de LoRaWAN son identificadores de 64 bits (16 dígitos hexadecimales).
# Se guardan en mayúsculas para que coincidan sin importar cómo los envíe ChirpStack.
validar_eui = RegexValidator(r'^[0-9A-Fa-f]{16}$', 'Debe tener exactamente 16 dígitos hexadecimales.')


class Visitante(models.Model):
    """
    Turista que recibe un nodo en préstamo durante su recorrido por el parque.
    """
    TIPOS_SANGRE = [(t, t) for t in ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')]

    id_visitante = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=60)
    apellido = models.CharField(max_length=60)

    # Datos de salud: su tratamiento se sujeta al plazo de retención que defina el parque
    tipo_sangre = models.CharField(max_length=5, choices=TIPOS_SANGRE, blank=True)
    contacto_emergencia = models.CharField(max_length=120, help_text="Nombre y teléfono de la persona a notificar")
    notas_medicas = models.TextField(blank=True, help_text="Alergias, padecimientos u otras condiciones relevantes para el rescate")

    class Meta:
        db_table = 'visitante'

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Vigilante(models.Model):
    """
    Operador del panel web. Separa la identidad operativa de las credenciales (auth_user).
    """
    id_vigilante = models.AutoField(primary_key=True)
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vigilante')
    nombre = models.CharField(max_length=60)
    apellido = models.CharField(max_length=60)

    class Meta:
        db_table = 'vigilante'

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Dispositivo(models.Model):
    """
    Representa un nodo Heltec físico que se presta a los visitantes.
    """
    id_dispositivo = models.AutoField(primary_key=True)
    dev_eui = models.CharField(max_length=16, unique=True, validators=[validar_eui], help_text="Identificador LoRaWAN grabado de fábrica (16 dígitos hex)")
    nombre = models.CharField(max_length=80, help_text="Etiqueta legible, p. ej. Nodo 07")
    activo = models.BooleanField(default=True, help_text="Un nodo inhabilitado se ignora en el panel sin borrar su historial")

    # Valores denormalizados, replicados del registro más reciente
    ultima_bateria_mv = models.IntegerField(null=True, blank=True)
    ultimo_contacto = models.DateTimeField(null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dispositivo'

    def save(self, *args, **kwargs):
        self.dev_eui = self.dev_eui.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} ({self.dev_eui})"


class Gateway(models.Model):
    """
    Concentrador LoRaWAN que recibe las tramas de los nodos.
    """
    id_gateway = models.AutoField(primary_key=True)
    gateway_eui = models.CharField(max_length=16, unique=True, validators=[validar_eui])
    nombre = models.CharField(max_length=80, help_text="Típicamente el sitio de instalación")

    # Necesaria para estimar la región probable de un nodo cuando no hay posición satelital
    ubicacion = models.PointField(geography=True, srid=4326)

    class Meta:
        db_table = 'gateway'

    def save(self, *args, **kwargs):
        self.gateway_eui = self.gateway_eui.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} ({self.gateway_eui})"


class Asignacion(models.Model):
    """
    Préstamo de un nodo a un visitante (ASIGNACION_DIS_VIS).
    """
    id_asignacion = models.AutoField(primary_key=True)
    visitante = models.ForeignKey(Visitante, on_delete=models.CASCADE, db_column='id_visitante', related_name='asignaciones')
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.PROTECT, db_column='id_dispositivo', related_name='asignaciones')
    fecha_asignacion = models.DateTimeField(default=timezone.now)

    # Nulo mientras el préstamo sigue vigente
    fecha_devolucion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'asignacion_dis_vis'
        verbose_name = 'asignación'
        verbose_name_plural = 'asignaciones'
        constraints = [
            # Un nodo no puede estar prestado a dos visitantes a la vez
            models.UniqueConstraint(
                fields=['dispositivo'],
                condition=models.Q(fecha_devolucion__isnull=True),
                name='asignacion_vigente_unica',
                violation_error_message='Este nodo ya tiene un préstamo vigente.',
            ),
        ]

    def __str__(self):
        return f"{self.dispositivo.nombre} → {self.visitante}"


class ZonaGeografica(models.Model):
    """
    Sector del parque. Es un polígono porque la zona de un incidente se determina por contención espacial.
    """
    class Tipo(models.TextChoices):
        SENDERO = 'SENDERO', 'Sendero'
        MIRADOR = 'MIRADOR', 'Mirador'
        ZONA_RIESGO = 'ZONA_RIESGO', 'Zona de riesgo'
        AREA_COMUN = 'AREA_COMUN', 'Área común'

    id_zona = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=80, help_text="P. ej. Sendero Norte")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    area = models.PolygonField(geography=True, srid=4326)

    class Meta:
        db_table = 'zona_geografica'
        verbose_name = 'zona geográfica'
        verbose_name_plural = 'zonas geográficas'

    def __str__(self):
        return self.nombre


class Incidente(models.Model):
    """
    Emergencia abierta por un nodo. Agrupa todas las posiciones que se reciben mientras dura.
    """
    class Estado(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        EN_ATENCION = 'EN_ATENCION', 'En atención'
        RESUELTO = 'RESUELTO', 'Resuelto'
        CANCELADO = 'CANCELADO', 'Cancelado por el visitante'
        FALSA_ALARMA = 'FALSA_ALARMA', 'Falsa alarma'

    ABIERTOS = [Estado.ACTIVO, Estado.EN_ATENCION]

    id_incidente = models.AutoField(primary_key=True)
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.PROTECT, db_column='id_dispositivo', related_name='incidentes')

    # Préstamo vigente al momento de la alerta: permite recuperar los datos del visitante
    asignacion = models.ForeignKey(Asignacion, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_asignacion', related_name='incidentes')

    # Operador que cerró el incidente; nulo mientras sigue abierto
    vigilante = models.ForeignKey(Vigilante, on_delete=models.PROTECT, null=True, blank=True, db_column='id_vigilante', related_name='incidentes_cerrados')

    # Se resuelve automáticamente por contención espacial con la primera posición conocida
    zona = models.ForeignKey(ZonaGeografica, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_zona', related_name='incidentes')

    estado = models.CharField(max_length=14, choices=Estado.choices, default=Estado.ACTIVO)

    # Denormalizada para que el panel no recorra los registros; nula si la alerta llegó sin posición satelital
    ultima_posicion = models.PointField(geography=True, srid=4326, null=True, blank=True)

    abierto_en = models.DateTimeField(default=timezone.now)
    cerrado_en = models.DateTimeField(null=True, blank=True)
    notas_rescate = models.TextField(blank=True)

    class Meta:
        db_table = 'incidente'
        ordering = ['-abierto_en']

    def __str__(self):
        return f"Incidente #{self.id_incidente} · {self.dispositivo.nombre} ({self.get_estado_display()})"


class RegistroGPS(models.Model):
    """
    Almacena cada trama recibida de un nodo: posición, alerta SOS y calidad de radio.
    """
    id_registro = models.AutoField(primary_key=True)
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.PROTECT, db_column='id_dispositivo', related_name='registros')

    # Nulo cuando la trama es un reporte pasivo de telemetría que no pertenece a ningún incidente
    incidente = models.ForeignKey(Incidente, on_delete=models.CASCADE, null=True, blank=True, db_column='id_incidente', related_name='registros')

    # Nulo si el servidor de red no reportó el concentrador o este no está registrado
    gateway = models.ForeignKey(Gateway, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_gateway', related_name='registros')

    # Nulo si el teléfono no logró fijar posición: la interfaz debe indicar "ubicación desconocida"
    # y nunca presentar el origen de coordenadas como una posición válida
    punto = models.PointField(geography=True, srid=4326, null=True, blank=True)

    es_sos = models.BooleanField(default=False)

    # Voltaje en mV y no porcentaje: la curva de descarga de una LiPo no es lineal
    bateria_mv = models.IntegerField(null=True, blank=True)

    # Calidad de radio aportada por el servidor de red, no por la carga útil
    rssi = models.SmallIntegerField(null=True, blank=True, help_text="dBm")
    snr = models.FloatField(null=True, blank=True, help_text="dB")

    # Contador de trama LoRaWAN: permite detectar duplicados y medir tramas perdidas
    fcnt = models.IntegerField()

    recibido_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'registro_gps'
        verbose_name = 'registro GPS'
        verbose_name_plural = 'registros GPS'
        ordering = ['-recibido_en']
        indexes = [
            models.Index(fields=["dispositivo", "-recibido_en"]),
        ]

    def __str__(self):
        estado = "🔴 SOS" if self.es_sos else "🟢 OK"
        return f"[{self.recibido_en.strftime('%H:%M:%S')}] {self.dispositivo.dev_eui} - {estado}"
