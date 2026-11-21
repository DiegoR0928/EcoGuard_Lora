"""
@brief Modelos de datos de EcoGuard: visitantes, vigilantes, nodos, préstamos, zonas, incidentes y tramas.

Cada clase es una tabla de PostgreSQL con PostGIS y sigue el diccionario de datos del SDD. Las
geometrías se guardan como `geography` con SRID 4326 (WGS 84): PostGIS mide así las distancias en
metros sobre el elipsoide y las coordenadas son las mismas que entrega el GPS del teléfono.

Relaciones principales:
- Un Visitante recibe nodos en préstamo (Asignacion); un Dispositivo solo puede tener un préstamo vigente.
- Un Dispositivo abre un Incidente con su primera trama SOS; el incidente agrupa los RegistroGPS que
  llegan mientras sigue abierto.
- Un Vigilante cierra el incidente desde el panel web.
"""
from django.conf import settings
from django.contrib.gis.db import models
from django.core.validators import RegexValidator
from django.utils import timezone

## Validador de los EUI de LoRaWAN (DevEUI y Gateway EUI): identificadores de 64 bits escritos con
## 16 dígitos hexadecimales. Se guardan en mayúsculas para que coincidan sin importar cómo los envíe
## el servidor de red.
validar_eui = RegexValidator(r'^[0-9A-Fa-f]{16}$', 'Debe tener exactamente 16 dígitos hexadecimales.')


class Visitante(models.Model):
    """
    @brief Turista que recibe un nodo en préstamo durante su recorrido por el parque.

    Sus datos de salud solo se muestran en el panel cuando su nodo tiene una emergencia abierta
    (RNF-12, privacidad de los datos del visitante).
    """
    ## Opciones del campo tipo_sangre: los ocho grupos ABO con factor Rh.
    TIPOS_SANGRE = [(t, t) for t in ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')]

    ## Clave primaria.
    id_visitante = models.AutoField(primary_key=True)
    ## Nombre(s) del visitante.
    nombre = models.CharField(max_length=60)
    ## Apellido(s) del visitante.
    apellido = models.CharField(max_length=60)

    ## Tipo de sangre (opcional). Es un dato de salud: su tratamiento se sujeta al plazo de retención
    ## que defina el parque.
    tipo_sangre = models.CharField(max_length=5, choices=TIPOS_SANGRE, blank=True)
    ## Nombre y teléfono de la persona a la que se avisa en una emergencia.
    contacto_emergencia = models.CharField(max_length=120, help_text="Nombre y teléfono de la persona a notificar")
    ## Alergias, padecimientos u otras condiciones útiles para el rescate (opcional).
    notas_medicas = models.TextField(blank=True, help_text="Alergias, padecimientos u otras condiciones relevantes para el rescate")

    class Meta:
        db_table = 'visitante'

    def __str__(self):
        """
        @brief Representación legible del visitante.
        @return Nombre y apellido.
        """
        return f"{self.nombre} {self.apellido}"


class Vigilante(models.Model):
    """
    @brief Operador del panel web que atiende las emergencias.

    Separa la identidad operativa (nombre del vigilante) de las credenciales de acceso, que viven en
    el usuario de Django (`auth_user`).
    """
    ## Clave primaria.
    id_vigilante = models.AutoField(primary_key=True)
    ## Usuario de Django con el que el vigilante inicia sesión. Al borrar el usuario se borra el vigilante.
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vigilante')
    ## Nombre(s) del vigilante.
    nombre = models.CharField(max_length=60)
    ## Apellido(s) del vigilante.
    apellido = models.CharField(max_length=60)

    class Meta:
        db_table = 'vigilante'

    def __str__(self):
        """
        @brief Representación legible del vigilante.
        @return Nombre y apellido.
        """
        return f"{self.nombre} {self.apellido}"


class Dispositivo(models.Model):
    """
    @brief Nodo Heltec WiFi LoRa 32 V4 físico que se presta a los visitantes.

    Se identifica por su DevEUI. Si llega una trama de un DevEUI desconocido, registrar_trama() lo
    da de alta automáticamente con el nombre "Heltec XXXX".
    """
    ## Clave primaria.
    id_dispositivo = models.AutoField(primary_key=True)
    ## Identificador LoRaWAN del nodo (16 dígitos hexadecimales, en mayúsculas). Es único.
    dev_eui = models.CharField(max_length=16, unique=True, validators=[validar_eui], help_text="Identificador LoRaWAN grabado de fábrica (16 dígitos hex)")
    ## Etiqueta legible que ve el vigilante, p. ej. "Nodo 07".
    nombre = models.CharField(max_length=80, help_text="Etiqueta legible, p. ej. Nodo 07")
    ## Falso si el nodo está inhabilitado (CU-07): no se presta, pero conserva su historial.
    activo = models.BooleanField(default=True, help_text="Un nodo inhabilitado se ignora en el panel sin borrar su historial")

    ## Voltaje de batería de la trama más reciente, en mV. Copia del último RegistroGPS para que el
    ## panel no tenga que consultarlo.
    ultima_bateria_mv = models.IntegerField(null=True, blank=True)
    ## Fecha y hora de la trama más reciente (copia del último RegistroGPS).
    ultimo_contacto = models.DateTimeField(null=True, blank=True)

    ## Fecha y hora de alta del nodo.
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dispositivo'

    def save(self, *args, **kwargs):
        """
        @brief Guarda el nodo con el DevEUI en mayúsculas.
        @param args Argumentos posicionales de Model.save().
        @param kwargs Argumentos con nombre de Model.save().
        """
        self.dev_eui = self.dev_eui.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        """
        @brief Representación legible del nodo.
        @return Nombre y DevEUI, p. ej. "Nodo 07 (A1B2C3D4E5F60708)".
        """
        return f"{self.nombre} ({self.dev_eui})"


class Gateway(models.Model):
    """
    @brief Concentrador LoRaWAN que recibe las tramas de los nodos.

    En el proyecto es una Raspberry Pi con un HAT Dragino que además ejecuta ChirpStack. Cada
    RegistroGPS guarda el gateway que lo recibió, si está registrado aquí.
    """
    ## Clave primaria.
    id_gateway = models.AutoField(primary_key=True)
    ## Gateway EUI (16 dígitos hexadecimales, en mayúsculas). Es el que reporta el servidor de red.
    gateway_eui = models.CharField(max_length=16, unique=True, validators=[validar_eui])
    ## Nombre legible, normalmente el sitio de instalación.
    nombre = models.CharField(max_length=80, help_text="Típicamente el sitio de instalación")

    ## Posición del gateway. Sirve para estimar la región probable de un nodo cuando no hay posición
    ## satelital y para medir la distancia de los puntos de control.
    ubicacion = models.PointField(geography=True, srid=4326)

    class Meta:
        db_table = 'gateway'

    def save(self, *args, **kwargs):
        """
        @brief Guarda el gateway con el EUI en mayúsculas.
        @param args Argumentos posicionales de Model.save().
        @param kwargs Argumentos con nombre de Model.save().
        """
        self.gateway_eui = self.gateway_eui.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        """
        @brief Representación legible del gateway.
        @return Nombre y Gateway EUI.
        """
        return f"{self.nombre} ({self.gateway_eui})"


class Asignacion(models.Model):
    """
    @brief Préstamo de un nodo a un visitante (tabla ASIGNACION_DIS_VIS).

    El préstamo está vigente mientras fecha_devolucion sea nula (CU-13 lo abre, CU-14 lo cierra).
    La restricción `asignacion_vigente_unica` impide prestar el mismo nodo dos veces a la vez, incluso
    si dos vigilantes lo intentan al mismo tiempo.
    """
    ## Clave primaria.
    id_asignacion = models.AutoField(primary_key=True)
    ## Visitante que recibe el nodo.
    visitante = models.ForeignKey(Visitante, on_delete=models.CASCADE, db_column='id_visitante', related_name='asignaciones')
    ## Nodo prestado. PROTECT: no se puede borrar un nodo con préstamos registrados.
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.PROTECT, db_column='id_dispositivo', related_name='asignaciones')
    ## Fecha y hora en que se entregó el nodo.
    fecha_asignacion = models.DateTimeField(default=timezone.now)

    ## Fecha y hora de la devolución; nula mientras el préstamo sigue vigente.
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
        """
        @brief Representación legible del préstamo.
        @return Nombre del nodo y del visitante.
        """
        return f"{self.dispositivo.nombre} → {self.visitante}"


class ZonaGeografica(models.Model):
    """
    @brief Sector del parque (sendero, mirador, zona de riesgo o área común).

    Es un polígono porque la zona de un incidente se determina por contención espacial: la primera
    posición conocida del nodo se busca dentro de las áreas (ST_Covers).
    """
    class Tipo(models.TextChoices):
        """
        @brief Clasificación de las zonas del parque.
        """
        ## Camino del recorrido.
        SENDERO = 'SENDERO', 'Sendero'
        ## Punto de observación.
        MIRADOR = 'MIRADOR', 'Mirador'
        ## Zona con un peligro conocido para el visitante.
        ZONA_RIESGO = 'ZONA_RIESGO', 'Zona de riesgo'
        ## Área de uso general del parque.
        AREA_COMUN = 'AREA_COMUN', 'Área común'

    ## Clave primaria.
    id_zona = models.AutoField(primary_key=True)
    ## Nombre de la zona, p. ej. "Sendero Norte".
    nombre = models.CharField(max_length=80, help_text="P. ej. Sendero Norte")
    ## Tipo de zona (ZonaGeografica.Tipo).
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    ## Polígono de la zona en WGS 84.
    area = models.PolygonField(geography=True, srid=4326)

    class Meta:
        db_table = 'zona_geografica'
        verbose_name = 'zona geográfica'
        verbose_name_plural = 'zonas geográficas'

    def __str__(self):
        """
        @brief Representación legible de la zona.
        @return Nombre de la zona.
        """
        return self.nombre


class PuntoControl(models.Model):
    """
    @brief Punto de la ruta piloto donde se validan la tasa de entrega y la exactitud de la ubicación.

    Sirve para las pruebas de RNF-02 (tasa de entrega) y RNF-07 (exactitud). Se carga desde
    `pruebas/ruta_piloto.geojson` con `manage.py cargar_ruta_piloto`, que mantiene la tabla igual
    que el archivo.
    """
    ## Clave primaria.
    id_punto = models.AutoField(primary_key=True)
    ## Código corto y único del punto, p. ej. "PC-1".
    codigo = models.CharField(max_length=8, unique=True, help_text="P. ej. PC-1")
    ## Nombre descriptivo del lugar.
    nombre = models.CharField(max_length=80)
    ## Posición del punto en el recorrido (1, 2, 3...).
    orden = models.PositiveSmallIntegerField(help_text="Posición en el recorrido de la ruta")
    ## Coordenada del punto en WGS 84.
    punto = models.PointField(geography=True, srid=4326)

    ## Falso mientras la coordenada sea la aproximada de OpenStreetMap: RNF-07 exige levantarla en sitio.
    levantado_en_sitio = models.BooleanField(default=False)

    class Meta:
        db_table = 'punto_control'
        ordering = ['orden']
        verbose_name = 'punto de control'
        verbose_name_plural = 'puntos de control'

    def __str__(self):
        """
        @brief Representación legible del punto.
        @return Código y nombre, p. ej. "PC-1 Entrada".
        """
        return f"{self.codigo} {self.nombre}"


class Incidente(models.Model):
    """
    @brief Emergencia abierta por un nodo.

    Se abre con la primera trama SOS del nodo y agrupa todas las posiciones (RegistroGPS) que llegan
    mientras dura. Ciclo de vida:
    - ACTIVO: recién abierto por el SOS.
    - EN_ATENCION: un vigilante lo está atendiendo (CU-04).
    - RESUELTO o FALSA_ALARMA: lo cierra el vigilante desde el panel.
    - CANCELADO: lo cierra el visitante desde la app (CU-12) con una trama de cancelación.
    """
    class Estado(models.TextChoices):
        """
        @brief Estados posibles de un incidente.
        """
        ## Recién abierto por la trama SOS; nadie lo atiende todavía.
        ACTIVO = 'ACTIVO', 'Activo'
        ## Un vigilante ya lo está atendiendo.
        EN_ATENCION = 'EN_ATENCION', 'En atención'
        ## Cerrado por el vigilante: el visitante fue rescatado.
        RESUELTO = 'RESUELTO', 'Resuelto'
        ## Cerrado por el visitante desde la app.
        CANCELADO = 'CANCELADO', 'Cancelado por el visitante'
        ## Cerrado por el vigilante: la alerta no correspondía a una emergencia.
        FALSA_ALARMA = 'FALSA_ALARMA', 'Falsa alarma'

    ## Estados en los que el incidente sigue abierto. Un nodo tiene a lo sumo un incidente abierto.
    ABIERTOS = [Estado.ACTIVO, Estado.EN_ATENCION]

    ## Clave primaria.
    id_incidente = models.AutoField(primary_key=True)
    ## Nodo que emitió la alerta.
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.PROTECT, db_column='id_dispositivo', related_name='incidentes')

    ## Préstamo vigente al momento de la alerta: permite recuperar los datos del visitante.
    asignacion = models.ForeignKey(Asignacion, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_asignacion', related_name='incidentes')

    ## Vigilante que cerró el incidente; nulo mientras sigue abierto.
    vigilante = models.ForeignKey(Vigilante, on_delete=models.PROTECT, null=True, blank=True, db_column='id_vigilante', related_name='incidentes_cerrados')

    ## Zona del parque donde ocurrió. Se resuelve automáticamente por contención espacial con la
    ## primera posición conocida.
    zona = models.ForeignKey(ZonaGeografica, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_zona', related_name='incidentes')

    ## Estado actual (Incidente.Estado).
    estado = models.CharField(max_length=14, choices=Estado.choices, default=Estado.ACTIVO)

    ## Última posición conocida, copiada aquí para que el panel no recorra los registros. Nula si la
    ## alerta llegó sin posición satelital.
    ultima_posicion = models.PointField(geography=True, srid=4326, null=True, blank=True)

    ## Fecha y hora de la primera trama SOS.
    abierto_en = models.DateTimeField(default=timezone.now)
    ## Fecha y hora de cierre; nula mientras el incidente sigue abierto.
    cerrado_en = models.DateTimeField(null=True, blank=True)
    ## Notas que escribe el vigilante sobre el rescate.
    notas_rescate = models.TextField(blank=True)

    class Meta:
        db_table = 'incidente'
        ordering = ['-abierto_en']

    def __str__(self):
        """
        @brief Representación legible del incidente.
        @return Número, nodo y estado, p. ej. "Incidente #3 · Nodo 07 (Activo)".
        """
        return f"Incidente #{self.id_incidente} · {self.dispositivo.nombre} ({self.get_estado_display()})"


class RegistroGPS(models.Model):
    """
    @brief Cada trama recibida de un nodo: posición, alerta SOS, batería y calidad de radio.

    Se guardan todas las tramas, también los reportes periódicos sin emergencia, para medir la tasa
    de entrega y la cobertura del gateway.
    """
    ## Clave primaria.
    id_registro = models.AutoField(primary_key=True)
    ## Nodo que envió la trama.
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.PROTECT, db_column='id_dispositivo', related_name='registros')

    ## Incidente al que pertenece la trama. Nulo cuando es un reporte periódico que no pertenece a
    ## ninguna emergencia.
    incidente = models.ForeignKey(Incidente, on_delete=models.CASCADE, null=True, blank=True, db_column='id_incidente', related_name='registros')

    ## Gateway que recibió la trama. Nulo si el servidor de red no lo reportó o no está registrado.
    gateway = models.ForeignKey(Gateway, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_gateway', related_name='registros')

    ## Posición del nodo. Nula si el teléfono no logró fijar posición: la interfaz debe indicar
    ## "ubicación desconocida" y nunca presentar el origen de coordenadas como una posición válida.
    punto = models.PointField(geography=True, srid=4326, null=True, blank=True)

    ## Verdadero si la trama lleva la bandera SOS.
    es_sos = models.BooleanField(default=False)

    ## Voltaje de la batería en mV. Se guarda el voltaje y no el porcentaje porque la curva de
    ## descarga de una LiPo no es lineal.
    bateria_mv = models.IntegerField(null=True, blank=True)

    ## Intensidad de la señal recibida, en dBm. La aporta el servidor de red, no la carga útil.
    rssi = models.SmallIntegerField(null=True, blank=True, help_text="dBm")
    ## Relación señal/ruido, en dB. La aporta el servidor de red.
    snr = models.FloatField(null=True, blank=True, help_text="dB")

    ## Contador de tramas de subida de LoRaWAN (FCnt): permite detectar duplicados y medir tramas perdidas.
    fcnt = models.IntegerField()

    ## Fecha y hora en que el servidor de red recibió la trama.
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
        """
        @brief Representación legible de la trama para el administrador de Django.
        @return Hora, DevEUI y si es SOS.
        """
        estado = "🔴 SOS" if self.es_sos else "🟢 OK"
        return f"[{self.recibido_en.strftime('%H:%M:%S')}] {self.dispositivo.dev_eui} - {estado}"
