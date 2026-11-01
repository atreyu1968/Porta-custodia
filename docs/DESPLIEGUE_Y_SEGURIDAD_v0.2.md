# PortaCustodia 0.2 · Despliegue supervisado y seguridad

**Guía para responsables técnicos del IES Manuel Martín González. No ejecutar en el host Proxmox.**

## 1. Arquitectura propuesta

- **LXC dedicado Ubuntu/Debian** con IP fija solicitada institucionalmente a través de Secretaría/CAU_CE, fuera del rango DHCP.
- Aplicación FastAPI con Uvicorn como usuario de servicio `portacustodia`, proceso único y SQLite en almacenamiento persistente privado.
- Acceso por **HTTPS**, proxy o túnel Cloudflare en contenedor separado, con restricción de origen y control de acceso institucional. Configurar MFA en el perímetro si resulta viable.
- Documentos y BD bajo `/var/lib/portacustodia`; clave fuera de ese volumen bajo `/etc/portacustodia/document.key`.
- Timer para copia cifrada diaria y timer para la generación diaria de tareas de agenda. **No se envía correo desde estos servicios.**

## 2. Requisitos antes de usar datos reales

1. Disponer de autorización de Dirección, identificación de responsable del tratamiento, intervención del DPD y procedimiento de derechos y retención.
2. Definir clasificación de información y permisos, copias cifradas fuera del contenedor, plan de restauración, gestión de vulnerabilidades y notificación de incidentes.
3. Separar la clave de cifrado de las copias; custodiarla con redundancia y accesos limitados.
4. Reservar IP mediante los procedimientos del centro; limitar tráfico al proxy autorizado, puerto de origen no expuesto a Internet.
5. Probar en entorno aislado el ciclo completo con **datos ficticios** antes de pasar a producción.

## 3. Instalación inicial

Dentro del LXC, con código descargado del ZIP y permisos de root:

```bash
cd /ruta/PortaCustodia_IES_MMG_v0.2.0
bash scripts/install_lxc_ubuntu.sh
```

El script crea cuenta de servicio, entorno Python, unidad systemd, timer de copias, timer de seguimiento y clave AES-256-GCM de 32 bytes. La clave se almacena con permisos `root:portacustodia` 0640 y no se empaqueta en backups. **No copiar la clave a repositorios Git ni a carpetas compartidas.**

Crear una cuenta de administración, dentro del LXC (no existe clave predeterminada):

```bash
cd /opt/portacustodia
runuser -u portacustodia -- env PORTACUSTODIA_DATA=/var/lib/portacustodia /opt/portacustodia/.venv/bin/python manage.py create-admin
```

## 4. Comprobaciones

```bash
systemctl status portacustodia.service
systemctl list-timers 'portacustodia*'
journalctl -u portacustodia.service -n 100 --no-pager
cd /opt/portacustodia
runuser -u portacustodia -- env PORTACUSTODIA_DATA=/var/lib/portacustodia /opt/portacustodia/.venv/bin/python manage.py check-audit
```

Hacer una copia cifrada con el entorno del servicio y verificar su apertura. En una prueba controlada, desactivar temporalmente la ruta de la clave y comprobar que no puede abrirse. Restituir la clave y asegurar que la misma copia vuelve a verificar correctamente.

## 5. Actualización v0.1 → v0.2

Realizar mantenimiento con el servicio detenido y copia verificada del sistema original. La migración del esquema es automática al arrancar la versión nueva; las filas existentes se conservan. La conversión de documentos antiguos sin cifrar **no se hace silenciosamente**: con servicio detenido y clave resguardada, efectuar prueba en clon, luego ejecutar:

```bash
cd /opt/portacustodia
# Variables de entorno autorizadas; ajustar a sus rutas reales
PORTACUSTODIA_DATA=/var/lib/portacustodia PORTACUSTODIA_KEY_FILE=/etc/portacustodia/document.key .venv/bin/python -m scripts.migrate_custody
# Solamente tras copia verificada y aprobación de mantenimiento:
PORTACUSTODIA_DATA=/var/lib/portacustodia PORTACUSTODIA_KEY_FILE=/etc/portacustodia/document.key .venv/bin/python -m scripts.migrate_custody --apply
```

Nunca cambiar la clave automáticamente después de que existan archivos cifrados. Un cambio sin migración coordinada puede impedir el acceso a documentos y copias anteriores.

## 6. Copias y restauración

Un `.pcbak` es un ZIP interno de base de datos y archivos protegido con cifrado autenticado AES-GCM; **no puede abrirse con el descompresor habitual**. Para verificarlo ejecutar `python -m scripts.backup verify /ruta/archivo.pcbak` desde entorno con la clave disponible. Una copia no cifrada `.zip` pertenece a un estado de evaluación anterior y debe tratarse como dato sensible en claro.

Antes de cualquier restauración, crear copia del estado actual, verificar integridad de la copia origen y contar con autorización. La extracción debe hacerse en un directorio temporal restringido, sin exponer archivos descifrados en el directorio web. Restaurar **base de datos y documentos de la misma instantánea**, validar permisos y repetir la verificación de auditoría y accesos. No hay asistente automático de recuperación integrado: la restauración es una operación técnica supervisada.

El backup local no sustituye una copia **externa al LXC**, con control de acceso y protección contra borrado y cifrado malicioso. Se debe ensayar una recuperación completa, documentar resultado, RPO y RTO institucionalmente aceptados.

## 7. Límites de seguridad y alcance

El servicio protege archivos con controles de acceso, autenticación, auditoría y cifrado cuando se ha configurado. No proporciona: certificado de firma electrónica, archivo electrónico oficial, sello de tiempo cualificado, cumplimiento RGPD por sí solo, monitorización de seguridad externa ni gestión de permisos del sistema operativo de los dispositivos. La auditoría encadenada puede ser reescrita por un actor con control total de la infraestructura; para mayor fuerza probatoria es necesario depositar evidencias en un sistema institucional independiente.

El cifrado actual usa un único secreto por despliegue. Para grandes volúmenes debe estudiarse gestión de claves en KMS, rotación, pruebas de desastre y base PostgreSQL. Las copias `.pcbak` se generan en memoria antes del cifrado; comprobar los recursos disponibles según el volumen documental real.
