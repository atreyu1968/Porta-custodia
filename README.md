# PortaCustodia · IES Manuel Martín González

**Aplicación funcional (versión piloto 0.4.0) para gestionar préstamos de ordenadores portátiles, devoluciones y expedientes documentales.** Pensada para Secretaría y el Departamento de Administración y Gestión del IES Manuel Martín González, en Canarias.

> **Importante**: esta entrega es un piloto verificable, no un sistema homologado de archivo electrónico administrativo ni un sistema de firma electrónica. Antes de utilizar datos reales, la Dirección del centro, la Secretaría, la coordinación TIC y el delegado/a de protección de datos deben validar sus condiciones de uso, seguridad, política de conservación, ubicación del servidor y procedimiento documental.

## Qué se puede hacer

- Dar de alta equipos con número de inventario, serie, marca, modelo, accesorios y estado físico.
- Identificar alumnado mediante **referencia interna** (no se requiere DNI); indicar grupo, minoría de edad y representante legal cuando corresponda.
- Preparar un préstamo y **reservar** el portátil, evitando la doble asignación por restricción de base de datos.
- Generar el **contrato de préstamo** en PDF listo para firma presencial; archivar copia digitalizada de la firma.
- **Bloquear la activación** hasta que se archive el compromiso firmado y se confirme expresamente la entrega física; con menores, confirmar la firma del representante legal.
- Consultar préstamos, próximos vencimientos y vencimientos superados.
- Registrar incidencias, gestión de avisos, requerimientos PDF y justificantes de notificación.
- Registrar devoluciones, estado y accesorios, generar acta de devolución PDF y apartar dispositivos deteriorados para revisión.
- Custodiar PDF, JPEG y PNG en carpeta **no servida por la web**; con clave de LXC, cifrado AES-256-GCM, nombre interno aleatorio, metadatos y huella **SHA-256**.
- Descargar un **ZIP por expediente** con archivos originales y manifiesto de integridad verificable.
- Mantener auditoría encadenada y exportarla a JSON; descargar CSV de préstamos pendientes.
- Administrar usuarios individuales y roles con contraseña Argon2, sesiones de 8 horas, CSRF, protección contra intentos reiterados, permisos y cookies seguras.
- Realizar copia coherente (base de datos + documentos), con manifiesto y verificación; con clave configurada se cifra como **.pcbak**.

## Flujo del préstamo

`Equipo disponible → Reserva / expediente preparado → PDF → Firma presencial → Archivo del PDF firmado → Confirmación de entrega → Préstamo activo → Avisos / incidencias → Devolución → Acta PDF / archivo firmado → Equipo disponible (o en revisión)`

No se envían correos automáticamente: la anotación de un aviso **no equivale** a la práctica o recepción de una notificación. El sistema permite adjuntar el justificante o acuse cuando exista.

## Permisos por perfil

| Función | Admin | Secretaría | TIC | Tutoría | Consulta |
|---|---:|---:|---:|---:|---:|
| Inventario (consulta) | Sí | Sí | Sí | Sí | Sí |
| Alta de equipos | Sí | Sí | Sí | No | No |
| Cambio de estado técnico | Sí | No | Sí | No | No |
| Alta de alumnado | Sí | Sí | No | No | No |
| Crear, activar, anular y devolver préstamos | Sí | Sí | No | No | No |
| Ver expedientes | Todos | Todos | Todos | Solo grupo asignado | Todos |
| Crear incidencias | Sí | Sí | Sí | Solo grupo asignado | No |
| Subir documentos | Todos | Todos | Técnicos | No | No |
| Descargar documentos | Todos | Todos | Técnicos | Técnicos del grupo | No |
| Exportar ZIP del expediente | Sí | Sí | No | No | No |
| Gestionar usuarios y auditoría | Sí | No | No | No | No |

La interfaz de tutoría restringe por coincidencia exacta con la cadena del grupo asignado. Evite utilizar nombres de grupo distintos para el mismo curso.

## Arranque local para evaluación, sin publicar datos reales

Requiere Python 3.10+ y un equipo con acceso a instalar dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PORTACUSTODIA_DATA="$(pwd)/data"
export PORTACUSTODIA_SECURE_COOKIE=0  # SOLO localhost; jamás en servicio público
python manage.py create-admin
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Abra `http://127.0.0.1:8765`. No hay credenciales predefinidas. El primer acceso obliga a cambiar la contraseña.

## Instalación en Ubuntu LXC (Proxmox)

La instalación se ejecuta **dentro de un contenedor LXC Ubuntu/Debian**, nunca en el host Proxmox:

```bash
cd /ruta/al/proyecto/PortaCustodia_IES_MMG
bash scripts/install_lxc_ubuntu.sh
```

El instalador crea usuario de servicio restringido, entorno virtual, servicio `portacustodia.service`, clave documental AES-256-GCM, temporizador `portacustodia-backup.timer` (copias cifradas) y `portacustodia-followup.timer` (tareas, sin envío automático), con copias privadas en `/var/backups/portacustodia`.

Cree la primera cuenta (comando con solicitud interactiva de clave):

```bash
cd /opt/portacustodia
runuser -u portacustodia -- env PORTACUSTODIA_DATA=/var/lib/portacustodia /opt/portacustodia/.venv/bin/python manage.py create-admin
```

Por defecto solo escucha en `127.0.0.1:8765`. Si el túnel Cloudflare se aloja en **otro contenedor**, antes de instalar configure `PORTACUSTODIA_BIND=IP_FIJA_DEL_LXC` y restrinja en el cortafuegos el acceso al puerto 8765 exclusivamente a la IP del contenedor del túnel y a la red de administración autorizada. **Debe instalarse detrás de HTTPS** mediante un proxy inverso o un túnel institucional con autorización. No exponer ese puerto directamente a internet. La cookie `Secure` está habilitada para uso por HTTPS; sin HTTPS no funcionará correctamente el acceso desde un navegador externo, deliberadamente.

En el entorno del centro, Secretaría puede solicitar a **CAU_CE** IP fijas dedicadas **fuera del DHCP**, una para el host Proxmox y otra para cada contenedor LXC, incluido el túnel en contenedor separado, si la infraestructura lo requiere. Esta aplicación no cambia la configuración de red ni asigna IP automáticamente.

## Copias de seguridad y restauración

Una copia diaria se almacena en el contenedor por el temporizador. No sustituye a una **copia externa, cifrada, comprobada y con control de acceso**, protegida frente al fallo o compromiso del servidor.

```bash
# Desde la carpeta de proyecto con las variables PORTACUSTODIA_DATA y PORTACUSTODIA_BACKUPS
python -m scripts.backup backup
python -m scripts.backup verify /ruta/a/portacustodia_20261101_032000.pcbak
python manage.py check-audit
```

Para restaurar una copia cifrada `.pcbak` será necesario descifrarla en un entorno controlado con la **clave externa**, comprobar el contenido y restaurar conjuntamente la base de datos y los documentos. Es una operación técnica supervisada; consulte `docs/DESPLIEGUE_Y_SEGURIDAD_v0.2.md`. No descomprima el contenido en una carpeta pública ni intente mezclar instantáneas.

## Seguridad y límites que deben atenderse antes de puesta en producción

1. **Aprobación interna y cumplimiento**: determinar base legitimadora, responsable del tratamiento, usuarios autorizados, información al alumnado, política de custodia, plazos y eliminación; revisión del DPD y procedimientos de Secretaría. Valorar registro de actividad y análisis de riesgos.
2. **Firma**: los PDF generados **no están firmados**; deben recogerse las firmas válidas mediante el procedimiento aprobado. Un PDF escaneado no se transforma automáticamente en firma electrónica cualificada.
3. **Integridad**: la huella SHA-256 detecta cambios en documentos y la cadena audita operaciones. Un administrador de infraestructura con acceso total podría alterar la base y recalcular la cadena. Si se necesita prueba robusta, integrar sellado de tiempo o archivo electrónico institucional y custodia externa.
4. **Cifrado**: con clave activada, los **documentos nuevos** se cifran mediante AES-256-GCM y las copias completas se cifran. Una actualización mantiene los documentos históricos sin cifrar hasta la migración expresa. La **base SQLite activa no se cifra** por esta versión, por lo que se requiere estudiar cifrado de volumen, permisos del sistema y protección de clave.
5. **Conservación**: la interfaz no implementa borrado para evitar alteraciones accidentales; **esto no exime de cumplir los plazos de conservación y supresión aplicables**. La administración debe definir y ejecutar el procedimiento de eliminación autorizado.
6. **Operación**: mantener SO y bibliotecas al día, limitar accesos SSH, usar 2FA en el acceso perimetral si es posible, separar entornos, gestionar vulnerabilidades y probar recuperación; **no incluye SSO/LDAP/2FA nativo**.
7. **Autoridad documental**: esta aplicación no reemplaza las plataformas oficiales de gestión patrimonial o registro de la Consejería si su uso resulta preceptivo.
8. **Escalabilidad**: SQLite es apropiado para una gestión de baja concurrencia y un único proceso servidor; para múltiples centros o uso intensivo debe estudiarse PostgreSQL, KMS, copias en streaming y almacenamiento de objetos controlado.
9. **Correcciones de datos**: las altas son inicialmente inmutables en la interfaz. Las correcciones administrativas y la gestión del ciclo de vida de los datos requieren un procedimiento supervisado y auditable antes del uso generalizado.

## Estructura del proyecto

```text
app/
  custody.py           Cifrado AES-256-GCM y comprobación
  followup.py          Motor de tareas idempotente
  main.py              Rutas, validaciones, sesiones, permisos y custodia
  database.py          Esquema SQLite, índices y transacciones
  documents.py         Generación de contratos, requerimientos y actas PDF
  templates/           Interfaz HTML en castellano
  static/              Estilos responsive
scripts/
  install_lxc_ubuntu.sh  Instalación en contenedor
  backup.py              Copia verificable (cifrada si hay clave)
  followup.py             Preparación diaria de tareas
  migrate_custody.py      Conversión supervisada de documentos v0.1
manage.py              Alta inicial y auditoría
requirements.txt
README.md
tests/test_workflow.py  Pruebas del ciclo de vida y accesos
```

## Comprobaciones automáticas

```bash
pip install pytest httpx
PYTHONPATH=. pytest -q
```

**Estado del desarrollo:** piloto funcional. Es imprescindible realizar pruebas con personal de Secretaría/TIC, ajustar el texto del compromiso a las NOF y obtener validación de la política de protección de datos antes de habilitar producción.

---

## Novedades v0.2.0 (1 de noviembre de 2026)

Esta versión amplía el piloto 0.1 sin eliminar su información. Los cambios se han probado con una base de datos temporal (sin datos personales reales).

### Agenda de devoluciones, sin envío automático

La opción **«Agenda de devoluciones»** presenta tareas según la fecha de devolución:

- Del día 30 al 16 previo al vencimiento: aviso de 30 días.
- Del día 15 al 8: aviso de 15 días.
- Del día 7 al vencimiento: aviso de 7 días.
- Del día 1 al 6 después del vencimiento: primer seguimiento.
- Desde el séptimo día después del vencimiento: segundo seguimiento.

La generación es **idempotente**, de modo que no duplica la misma tarea y etapa para una misma fecha de vencimiento. No se trata de una cola de notificaciones electrónicas legalmente acreditadas. Se crea una tarea interna, que Secretaría puede documentar como realizada o descartada justificadamente. Si se registra como realizada, debe consignarse medio, destinatario y observación; los justificantes se archivarán en el expediente.

El botón «Borrador correo» descarga un archivo `.eml` para revisar en el programa de correo del centro. **No lo envía.** El registro de descarga del borrador incluye `sent=false` en auditoría. La fecha de vencimiento y los datos del alumno se revisan antes del envío real por un medio institucional autorizado.

El proceso automático de preparación de tareas se realiza mediante `portacustodia-followup.timer`, a las 08:05 (hora local del servidor). La aplicación también prepara nuevas tareas al abrir la agenda con perfil de Secretaría o Administración.

### Revisiones periódicas

Cada expediente en curso permite anotar si el dispositivo se ha presentado, se ha observado una incidencia o no ha sido presentado. La revisión no accede a archivos personales del equipo. Si se registra una incidencia, se abre automáticamente la incidencia asociada. Las revisiones se incluyen en el manifiesto del ZIP del expediente.

### Cifrado de documentos y copias

En la instalación LXC, el instalador genera una clave **AES-256-GCM** en `/etc/portacustodia/document.key`, propiedad de `root`, con lectura solo para el grupo del servicio. Se conserva **fuera del directorio de la aplicación y de los archivos de copia**. Los documentos **nuevos** se cifran antes de almacenarse. Al descargarlos un usuario autorizado se descifran en memoria y se vuelve a verificar su SHA-256 original.

Cuando la clave está configurada, la copia completa de base de datos y documentos se guarda como archivo **`.pcbak` cifrado y autenticado**. No se incluye la clave en el paquete de copia. **Perder la clave implica la imposibilidad de descifrar los documentos y backups cifrados.** Su custodia, duplicado separado y rotación supervisada son responsabilidades operativas del centro.

La configuración del piloto sin clave conserva compatibilidad con su estado previo, pero solo debe utilizarse con datos ficticios. El instalador de LXC habilita el requisito de cifrado (`PORTACUSTODIA_REQUIRE_ENCRYPTION=1`) y falla si falta la clave. Las exportaciones descargadas en ZIP contienen **documentos descifrados** para su tramitación; deben tratarse como material sensible y almacenarse en repositorios institucionales protegidos.

### Actualización desde v0.1

1. **No se actualiza automáticamente ninguna instalación.** Antes, obtener y verificar una copia del entorno anterior, conservarla bajo control autorizado y documentar la ventana de mantenimiento.
2. Detener el servicio de la aplicación e instalar el código v0.2 dentro de LXC. El sistema crea las tablas de revisiones y seguimiento y añade el atributo `encryption` a los documentos sin borrarlos.
3. La versión 0.2 leerá archivos históricos **sin cifrar** y nuevos **cifrados**. Para convertir los antiguos, y solo después de una copia verificada y con el servicio detenido, ejecutar `python -m scripts.migrate_custody --apply` con variables `PORTACUSTODIA_DATA` y `PORTACUSTODIA_KEY_FILE` correctas. Sin `--apply`, el comando solo cuenta documentos por convertir.
4. Reiniciar, comprobar la cadena de auditoría, acceder a expedientes antiguos, verificar integridad y generar una nueva copia `.pcbak` comprobando que puede abrirse con la clave custodiada.
5. Considerar que **los antiguos soportes y copias no cifradas siguen conteniendo datos legibles**; su conservación y eliminación se harán conforme a la política que apruebe la institución, nunca automáticamente.

Consultar además [DESPLIEGUE_Y_SEGURIDAD_v0.2.md](docs/DESPLIEGUE_Y_SEGURIDAD_v0.2.md) y [GUIA_OPERATIVA_v0.2.md](docs/GUIA_OPERATIVA_v0.2.md).

### Validación

`PYTHONPATH=. pytest -q` verifica el préstamo, firma escaneada, devolución, privilegios, integridad del archivo, migración del esquema v0.1, creación sin duplicados de tareas, registro de revisiones, generación de borradores `.eml`, cifrado de documento y copia `.pcbak`.

**Límites**: no hay integración SMTP o correo corporativo, firma electrónica avanzada, sello de tiempo cualificado, gestión archivística homologada, retención automática, control MDM del hardware, ni despliegue ya realizado. Deben validarse las medidas de seguridad, el cumplimiento de protección de datos y la continuidad operativa antes de registrar datos reales.

## Novedades v0.2.2 (1 de noviembre de 2026) — Préstamos a menores

Se mantiene el modelo de **firma manuscrita en papel**, con digitalización posterior. No se requiere ni se ofrece firma electrónica. El correo de los empleados es del dominio institucional `@canariaseducacion.es`; las familias pueden utilizar direcciones externas y la app **no envía correos**.

- Alta de menores con nombre y vínculo del representante; correo de familia opcional y marcado de canal verificado para borradores.
- Instantánea de los datos legales de la persona receptora y de su representación al reservar cada equipo.
- PDF con firma manuscrita diferenciada del alumno, el representante legal y la persona que entrega el portátil.
- Bloqueo de entrega hasta que se archive la copia firmada y Secretaría confirme las dos firmas y el medio de comprobación de representación.
- Registro trazable de persona verificadora, método, condición del representante y fecha.
- Borradores `.eml` dirigidos al contacto familiar **solo cuando siga siendo menor y ese contacto conste verificado**; tras constatar la mayoría de edad, los avisos futuros se dirigirán al alumno, no automáticamente a la familia.
- Procedimiento para actualizar la condición de mayoría de edad sin alterar el contenido histórico de los expedientes, conservando una anotación de auditoría. Las situaciones de emancipación y representación discutida exigen estudio manual.
- Migración incremental de bases anteriores. Las instantáneas de expedientes antiguos se reconstruyen a partir de los datos actuales de la ficha **al migrar**, de modo que deben verificarse los casos históricos porque la aplicación no puede reconstruir hechos anteriores no registrados.

Consultar [PROCEDIMIENTO_MENORES_v0.2.2.md](docs/PROCEDIMIENTO_MENORES_v0.2.2.md) antes de usar esta modalidad con datos reales.

---

## Versión 0.3.0 — contrato y actas por duplicado

**Versión de este paquete: 0.3.0.** La aplicación mantiene las funciones del piloto 0.2.2 y añade documentación íntegra, por duplicado, con condiciones legales y referencias a legislación vigente de España y Canarias. Cada PDF tiene «Ejemplar 1/2 — Centro» y «Ejemplar 2/2 — Alumno/a o representante»; las firmas manuscritas deben constar en **los dos** ejemplares. Se conserva una copia escaneada del ejemplar del centro y se deja constancia de quién recibió el segundo.

El contrato para menores incorpora además la autorización del representante y el régimen de responsabilidad legal **sin cláusulas de pago automático**. La recepción física de un equipo queda separada del cierre documental de su acta. El panel indica los cierres pendientes.

**Configuración obligatoria antes de producción:** el instalador LXC establece `PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=1`. Los documentos de contrato no podrán emitirse hasta configurar el responsable de tratamiento, contacto DPD, información RGPD completa y criterio de conservación oficialmente confirmados, mediante el fichero de entorno de la instalación. Los ejemplos incluidos identifican estos campos como pendientes y **no se deben distribuir a personas reales para firmar**.

Para instrucciones, lea:

- `docs/PROTOCOLO_PRESTAMO_DOBLE_EJEMPLAR_v0.3.md`: propuesta formal para aprobación por Dirección, Secretaría y DPD, referencias legales y procedimiento de custodia.
- `docs/INSTALACION_Y_PUESTA_EN_MARCHA_v0.3.md`: instalación y actualización de LXC, variables RGPD, seguridad y verificación.
- `docs/EJEMPLO_CONTRATO_MAYOR_DOS_COPIAS.pdf` y `docs/EJEMPLO_CONTRATO_MENOR_DOS_COPIAS.pdf`: ejemplos ficticios de las hojas para firma.

Los originales de 0.2.2 pueden migrarse sin destrucción de datos; para expedientes ya formalizados no se inventa retrospectivamente una comprobación de doble ejemplar. Conserve el backup anterior, valide el nuevo en entorno separado y nunca exponga datos personales a un servidor de pruebas.


## Versión 0.4.0 · Lectura de códigos, PWA y fotografías del equipo

- **PWA instalable** para Android/iPhone, iconos, manifest y Service Worker limitado a recursos estáticos públicos. Abrir `/movil` desde una URL HTTPS autorizada.
- **Lector USB/Bluetooth** en modo teclado para identificar códigos de serie e inventario; lectura directa mediante cámara con `BarcodeDetector` cuando el navegador lo soporte.
- **Foto de etiqueta como alternativa**: descodificación en servidor usando `pyzbar`/`libzbar0`, sin almacenar la fotografía temporal. No requiere servicios de terceros.
- **Archivo fotográfico** asociado al inventario y, cuando corresponde, a un préstamo concreto. Las imágenes normalizadas se guardan sin EXIF/GPS, con huella SHA-256, fecha, usuario y estado. Se incluyen en el ZIP del expediente.
- **Rol `gestor`** para profesorado delegado, limitado a un grupo. Conserva el bloqueo de entrega sin contrato en doble ejemplar y firma manuscrita, incluido el representante legal cuando corresponda.
- **Migración no destructiva** desde la versión 0.3 de SQLite, con creación de tabla fotográfica y actualización controlada de la tabla de usuarios para el nuevo rol. Realizar backup antes de instalar.
- **Limitaciones**: cámara en directo no universal, PWA sin acceso offline a datos privados, JPEG normalizado no es original forense, la cámara no reemplaza firmas manuscritas y debe aprobarse BYOD/fotografías con Dirección y DPD.

Documentos complementarios: `docs/MANUAL_PWA_ESCANEO_FOTOS_v0.4.md` y `docs/ACTUALIZACION_v0.3_a_v0.4.md`. Dependencias añadidas: Pillow, pyzbar y `libzbar0` (instalador LXC).
