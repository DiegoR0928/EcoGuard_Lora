"""
@brief Receptores de señales de Django: avisan a los paneles de los cambios en la base de datos.

apps.GeolocalizacionConfig.ready() importa este módulo al arrancar para que los receptores se registren.
"""
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Asignacion, Dispositivo, Incidente, Visitante
from .tiempo_real import emitir_actualizacion


@receiver([post_save, post_delete], sender=Dispositivo)
@receiver([post_save, post_delete], sender=Incidente)
@receiver([post_save, post_delete], sender=Asignacion)
@receiver([post_save, post_delete], sender=Visitante)
def avisar_paneles(sender, instance, signal, **kwargs):
    """
    @brief Avisa a los paneles de cualquier cambio en nodos, incidentes, préstamos o visitantes.

    El cambio puede venir de la API, del webhook, del administrador de Django o de la consola. El
    aviso sale al confirmarse la transacción (transaction.on_commit), para que el panel, al recargar,
    ya encuentre el cambio guardado.
    @param sender Clase del modelo que cambió.
    @param instance Objeto guardado o eliminado.
    @param signal Señal recibida: post_save o post_delete.
    @param kwargs Resto de argumentos de la señal (created, update_fields...), no se usan.
    """
    datos = {'modelo': sender._meta.model_name, 'id': instance.pk, 'eliminado': signal is post_delete}
    transaction.on_commit(lambda: emitir_actualizacion(datos))


@receiver(post_save, sender=Asignacion)
def vincular_alerta_abierta(sender, instance, **kwargs):
    """
    @brief Vincula un préstamo recién registrado a la alerta abierta de su nodo.

    registrar_trama() vincula el préstamo vigente al abrir la alerta. Si el préstamo se registra
    después (p. ej. se capturó tarde en la entrada), se vincula aquí para que el panel muestre al
    visitante.
    @param sender Clase Asignacion.
    @param instance Préstamo guardado.
    @param kwargs Resto de argumentos de la señal, no se usan.
    """
    if instance.fecha_devolucion is None:
        Incidente.objects.filter(
            dispositivo_id=instance.dispositivo_id,
            estado__in=Incidente.ABIERTOS,
            asignacion__isnull=True,
        ).update(asignacion=instance)
