# Guía operativa rápida de PortaCustodia

## Primera puesta en marcha

1. Instalar en LXC autorizado y configurar acceso HTTPS con protección perimetral.
2. Crear la cuenta inicial de administración desde consola y cambiar su contraseña en el primer acceso.
3. Crear una cuenta nominal de Secretaría, una técnica para inventario y las tutorías que se vayan a utilizar, asignando grupo exacto.
4. Registrar los portátiles con inventario y número de serie (una sola vez).
5. Registrar el alumnado beneficiario con identificador interno, nombre y grupo; indicar representante en caso de menor.

## Cada préstamo (Secretaría)

1. **Préstamos → Formalizar préstamo**: seleccionar alumno, equipo disponible y fecha futura.
2. Abrir expediente **PC-00001**: el equipo aparece reservado, no entregado.
3. Pulsar **Generar contrato PDF** y descargarlo desde la sección Archivo documental.
4. Imprimir, formalizar firma presencial y comprobar identificaciones según normativa aprobada.
5. Escanear el original firmado, seleccionar **Compromiso de préstamo firmado**, adjuntar PDF o imagen y archivar.
6. Confirmar la **entrega física**; si hay menores, verificar la firma del representante y marcar casilla específica.
7. El préstamo pasa a «En préstamo» y el equipo a «Prestado»; ya no es elegible en un segundo expediente.

## Seguimiento y vencimientos

El panel identifica los vencidos y los que requieren atención. Secretaría puede generar un **requerimiento PDF**, anotar intentos de contacto y archivar acuse o evidencia. La anotación manual no demuestra que una notificación se haya practicado. Las tutorías solo visualizan expedientes de su grupo.

## Devolución

Registrar la recepción física, los accesorios y el resultado. Si hay desperfectos o incidencias sin resolver, el dispositivo pasa a «En revisión». Generar el acta de devolución y archivar su copia firmada. Se conserva el expediente íntegro sin eliminar el historial.

## Documentos y expedientes

Los PDF emitidos por el programa son **borradores para completar y firmar**, no documentos jurídicamente firmados por el software. Para comprobar un expediente se puede descargar el **ZIP** y verificar cada huella `sha256` declarada en `MANIFIESTO.json`. Solo el personal con rol de Secretaría o administración puede descargar el expediente completo.

## Copias de seguridad

Existe un temporizador diario para copias locales. Debe verificarse periódicamente y complementarse con réplica externa cifrada. Una copia debe restaurarse de manera de prueba antes de la puesta en producción, comprobando una ficha de préstamo y la descarga de un contrato archivado.

## Incidencias frecuentes

- **No aparece el portátil:** figura reservado, prestado, en revisión o de baja. Comprobar en Inventario y localizar el expediente activo.
- **No permite entregar:** falta el documento de compromiso firmado o la confirmación de representante legal.
- **No abre la cuenta desde internet:** comprobar el acceso HTTPS y la cookie segura; no deshabilitar `PORTACUSTODIA_SECURE_COOKIE` en producción.
- **No se puede descargar un archivo:** verificar permisos de la carpeta y huellas; un archivo alterado bloquea la descarga de forma expresa.
- **Se pierde el servidor:** recuperar base y documentos desde **la misma** copia validada, siguiendo README, con autorización.
- **Hay que rectificar un expediente:** no manipular la base manualmente. Registrar incidencia y coordinar un procedimiento de rectificación auditado; el piloto no dispone de edición libre de registros históricos.
