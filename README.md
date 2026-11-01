# PortaCustodia · IES Manuel Martín González

**Versión 0.4.1 — aplicación web y PWA de control de préstamos de ordenadores portátiles, expedientes, firma manuscrita y custodia documental.** Proyecto diseñado para el Departamento de Administración y Gestión y el personal autorizado del IES Manuel Martín González (Canarias).

> **Estado del proyecto:** piloto operativo y probado automáticamente. No es un gestor documental administrativo homologado ni incorpora firma electrónica o SMTP. **Antes de usar expedientes reales** deben autorizarse la implantación y las medidas de seguridad por Dirección y el delegado de protección de datos (DPD). El instalador no inventa los datos legales que debe aprobar el centro.

## 1. Documentación

- **[Manual de uso ilustrado — PDF, 13 páginas](docs/MANUAL_USO_PORTACUSTODIA.pdf)**: incluye imágenes obtenidas de las páginas reales de la aplicación con personas y números de serie ficticios; acceso, inventario, alumnos, menores, contratos, gestión móvil, fotos, devoluciones, avisos y custodia.
- [Guía de la PWA, lectores y fotografías](docs/MANUAL_PWA_ESCANEO_FOTOS_v0.4.md).
- [Protocolo de doble ejemplar para firma manuscrita](docs/PROTOCOLO_PRESTAMO_DOBLE_EJEMPLAR_v0.3.md).
- [Procedimiento para alumnado menor de edad](docs/PROCEDIMIENTO_MENORES_v0.2.2.md).
- [Despliegue y seguridad](docs/DESPLIEGUE_Y_SEGURIDAD_v0.2.md).
- [Historial de cambios](CHANGELOG.md).

## 2. Funciones disponibles

| Área | Funciones |
|---|---|
| Inventario | Código patrimonial, serie, marca, modelo, accesorios, estado, lector USB/Bluetooth o cámara. |
| Préstamo | Reserva única, plazo, finalidad, contrato PDF, entrega controlada, seguimiento y devolución. |
| Firma | Dos ejemplares completos en papel (centro/interesado), archivo del original firmado por el centro, registro de entrega de copia. |
| Menores | Representante legal, autorización previa, firma manuscrita del alumno y de su representante cuando proceda. |
| Archivo | Documentos privados, SHA-256, auditoría, exportación ZIP con manifiesto; AES-256-GCM en instalación LXC. |
| PWA | Interfaz para Android/iPhone, consultas, escaneo compatible, captura de imágenes y actuaciones según rol. |
| Seguimiento | Revisiones de equipos, incidentes, avisos, borradores de correo y fechas de devolución. |
| Administración | Usuarios, roles, permisos por grupo, controles de acceso, copias de seguridad y diagnósticos. |

Los correos del personal se validan con **`@canariaseducacion.es`**. La aplicación **no envía correos automáticamente**: descargar un borrador `.eml` nunca acredita su envío ni recepción.

## 3. Topología recomendada

```text
Profesorado / Secretaría / móvil (HTTPS)
                  |
       Dominio autorizado del centro
                  |
    Cloudflare Tunnel o proxy HTTPS
     (LXC separado, acceso restringido)
                  |
       172.16.x.x:8765 (origen)
                  |
     LXC Ubuntu 22.04/24.04 LTS
            PortaCustodia
        /opt/portacustodia
        /var/lib/portacustodia
        /etc/portacustodia
        /var/backups/portacustodia
```

**Nunca instalar en el host Proxmox.** Instalar exclusivamente en un **contenedor LXC Ubuntu** con `systemd`. Secretaría puede solicitar a CAU_CE una **IP fija dedicada fuera del rango DHCP** para el host y otra para cada LXC (incluido un LXC distinto para el túnel), conforme al procedimiento del centro. La aplicación no configura la red institucional ni crea automáticamente un túnel o certificado HTTPS.

### Requisitos del contenedor vacío

- Ubuntu Server LTS 22.04 o 24.04, con `systemd`, `apt-get` y conexión a Internet; instalación como **root dentro del LXC**.
- Propuesta de recursos para piloto: **2 vCPU, 2 GB RAM, 10 GB de disco o más**, ajustando el almacenamiento a fotos, documentos y copias. No son umbrales de rendimiento certificados.
- Resolución DNS, salida HTTPS a GitHub/PyPI y acceso a los repositorios APT de Ubuntu. La instalación no funciona sin acceso a estas fuentes ni sin los repositorios configurados.
- **No hace falta haber actualizado Ubuntu ni disponer de `curl`, `wget`, `git`, `pip` o `venv`.** El instalador instala Python, CA y demás dependencias de forma automática. Sí realiza `apt-get update` para cargar los índices de paquetes; **no ejecuta `apt-get upgrade` de todo el sistema**.
- URL **HTTPS** institucional para el uso habitual. Por seguridad, las cookies son `Secure`; la cámara y la instalación PWA requieren origen seguro.

## 4. Instalación completamente desatendida desde Ubuntu vacío

**Paso único para el operador:** abra la consola del **contenedor Ubuntu**, entre como `root` y pegue el bloque completo. No requiere intervención durante el proceso, credenciales predefinidas ni `curl`/`git`:

```bash
apt-get update && \
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 ca-certificates && \
python3 -c 'import urllib.request; urllib.request.urlretrieve("https://raw.githubusercontent.com/atreyu1968/Porta-custodia/main/scripts/bootstrap_ubuntu.sh", "/root/portacustodia-bootstrap.sh")' && \
bash /root/portacustodia-bootstrap.sh
```

**¿Qué hace?** Usa exclusivamente Python estándar y conexiones HTTPS verificadas para descargar de GitHub el código de la rama `main` (sin Git), comprueba la estructura del archivo, instala dependencias de Ubuntu, crea usuario y directorios de servicio, entorno Python privado, clave de custodia, base de datos, administrador inicial con contraseña aleatoria, servicio `systemd`, temporizadores de copias y de seguimiento. Ejecuta una **prueba funcional sobre una base temporal ficticia** y comprueba `/salud` y la integridad de auditoría. Si falla una comprobación crítica, el instalador termina con error en vez de anunciar éxito.

> **Precaución de suministro de software:** el comando descarga y ejecuta código del repositorio indicado, que puede cambiar con la rama `main`. Para producción, la organización deberá revisar el código, fijar una revisión/tag y verificar su huella antes de ejecutar instalaciones automatizadas.

### Opcional: conexión desde el túnel de otro contenedor

Por defecto el servicio solo escucha en `127.0.0.1:8765` dentro del LXC. Si la IP del LXC ya está asignada y un proxy/túnel **separado** debe llegar al servidor, **antes del bloque anterior** exporte la IP real autorizada:

```bash
export PORTACUSTODIA_BIND=172.16.180.XX   # SUSTITUIR por la IP fija REAL de este LXC
export PORTACUSTODIA_PORT=8765
```

**Nunca use literalmente `.XX`**: solicite y verifique la dirección dedicada del LXC. Abra el puerto 8765 **solo** al contenedor de túnel/proxy y red de administración; no lo exponga a Internet. Si ya instaló y desea cambiar el bind, edite `ExecStart` del servicio de forma supervisada y reinicie; no ejecute el instalador a ciegas sobre expedientes de producción.

### Archivos instalados

| Ruta | Finalidad / permisos |
|---|---|
| `/opt/portacustodia` | Código y entorno Python del servicio (no escribible por la aplicación). |
| `/var/lib/portacustodia` | Base SQLite y custodia privada de documentos. Solo cuenta de servicio. |
| `/etc/portacustodia/document.key` | Clave AES-256-GCM, `root:portacustodia`, modo `0640`, directorio restringido. |
| `/etc/portacustodia/environment` | Variables de funcionamiento y seguridad, `root:portacustodia`, modo `0640`. |
| `/var/backups/portacustodia` | Copias automáticas cifradas de aplicación, fuera del directorio público. |
| `/root/portacustodia-initial-credentials.txt` | Credenciales temporales de primer acceso, `root`, modo `0600`. |
| `/etc/systemd/system/portacustodia*.{service,timer}` | Servicio web, copia diaria y preparación de alertas. |

## 5. Primer acceso y validación de instalación

**Credenciales:** el instalador crea una cuenta `administrador` exclusivamente si la base está vacía, con contraseña aleatoria de alta entropía guardada en el fichero protegido siguiente. No existen credenciales de demostración por defecto:

```bash
cat /root/portacustodia-initial-credentials.txt
```

Entregue la contraseña temporal únicamente al responsable designado. **En el primer inicio se exige sustituirla.** Una cuenta ya existente no se restablece automáticamente.

Compruebe los servicios:

```bash
systemctl --no-pager --full status portacustodia.service
systemctl list-timers --all | grep portacustodia
journalctl -u portacustodia -n 80 --no-pager
python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8765/salud",timeout=5).read().decode())'
```

El último comando sirve **solo si el bind predeterminado es `127.0.0.1`**; con IP personalizada, sustitúyala. La respuesta esperada es `{"estado":"ok","aplicacion":"PortaCustodia"}`. Compruebe adicionalmente:

```bash
cd /opt/portacustodia
runuser -u portacustodia -- env PORTACUSTODIA_DATA=/var/lib/portacustodia \
  /opt/portacustodia/.venv/bin/python manage.py check-audit
```

Para repetir una prueba funcional sin alterar datos reales:

```bash
cd /opt/portacustodia
runuser -u portacustodia -- env \
  PORTACUSTODIA_KEY_FILE=/etc/portacustodia/document.key \
  PORTACUSTODIA_REQUIRE_ENCRYPTION=1 \
  /opt/portacustodia/.venv/bin/python -m scripts.selfcheck
```

Este diagnóstico crea y elimina una base temporal de datos ficticios; verifica autenticación, permisos, expediente, PDF, PWA, archivo y cifrado AES-256-GCM.

### Información legal obligatoria para generar contratos reales

El instalador **no puede inventar** el responsable del tratamiento, el contacto del DPD, la URL informativa o el plazo de conservación. Por eso deja **`PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=1`**: mientras estos campos estén pendientes, el programa permite configurar y gestionar el sistema, pero **bloquea la generación de nuevos documentos legales**.

Tras la aprobación institucional, edite como `root` `/etc/portacustodia/environment` y establezca los cuatro valores **oficiales** (ejemplo de sintaxis; no copie los textos de ejemplo como datos reales):

```ini
PORTACUSTODIA_RESPONSABLE_DATOS="DENOMINACIÓN OFICIAL DEL RESPONSABLE"
PORTACUSTODIA_CONTACTO_DPD="CONTACTO INSTITUCIONAL VERIFICADO DEL DPD"
PORTACUSTODIA_PRIVACIDAD_URL="https://URL-INSTITUCIONAL-REAL/privacidad"
PORTACUSTODIA_RETENCION="CRITERIO DE CONSERVACIÓN APROBADO"
```

A continuación ejecute `systemctl restart portacustodia.service`. **No establezca `PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=0` en producción.** Recuerde validar también textos legales, fichas de tratamiento, roles, retención, copias y almacenamiento con los responsables competentes.

## 6. Guía rápida de uso

1. **Inventario:** cree ficha con inventario/serie; opcional lector de código de barras o cámara. Incorpore fotografías objetivas del estado de la unidad.
2. **Alumno/a:** registre referencia interna y grupo; para menores, identifique y documente al representante legal que corresponda.
3. **Reserva:** elija equipo disponible, fecha de devolución, finalidad educativa y observaciones de entrega.
4. **Contrato:** genere PDF, imprima **dos originales**, recoja firmas manuscritas y archive la digitalización del ejemplar del centro.
5. **Entrega:** confirme ambas firmas y que se proporcionó al interesado su ejemplar; con menores, autorización de representación legal. Solo entonces active préstamo.
6. **Seguimiento:** registre revisiones, estado, fotografías, incidencias y avisos. El mensaje `.eml` es un borrador; no prueba envío.
7. **Devolución:** identifique equipo, registre estado y accesorios, genere acta por duplicado, digitalice la copia firmada del centro y cierre la documentación.
8. **Archivo:** verifique documentos y auditoría; exporte el ZIP solo cuando exista necesidad legítima y trasládelo a custodia institucional.

Para pantallas e instrucciones paso a paso, consulte el **[manual ilustrado PDF](docs/MANUAL_USO_PORTACUSTODIA.pdf)**.

## 7. Instalación PWA Android/iPhone

Abra el dominio **HTTPS** institucional de PortaCustodia. En Android (Chrome u otro navegador compatible), abra el menú y seleccione **Instalar aplicación** o **Añadir a pantalla de inicio**. En iPhone (Safari), utilice **Compartir → Añadir a pantalla de inicio**. Las funciones de cámara dependen del navegador y sus permisos; existe alternativa de foto de etiqueta o lector Bluetooth. **No hay modo offline para expedientes sensibles.**

El personal autorizado podrá añadir fotografías, registrar inspecciones y gestionar préstamos según su rol/grupo. La PWA no debe utilizarse para fotografiar rostros, DNI, conversaciones ni pantallas con datos personales. Consulte [manual PWA](docs/MANUAL_PWA_ESCANEO_FOTOS_v0.4.md).

## 8. Copias de seguridad, vigilancia y recuperación

```bash
# Estado y últimos registros
systemctl is-active portacustodia.service
journalctl -u portacustodia-backup.service -n 40 --no-pager
systemctl list-timers --all | grep portacustodia

# Lanzamiento controlado de una copia (recomendable en mantenimiento)
systemctl start portacustodia-backup.service
ls -lah /var/backups/portacustodia

# Auditoría
cd /opt/portacustodia
runuser -u portacustodia -- env PORTACUSTODIA_DATA=/var/lib/portacustodia \
  /opt/portacustodia/.venv/bin/python manage.py check-audit
```

Las copias automáticas del LXC no sustituyen una **copia externa cifrada**, ni la restauración ensayada y autorizada. **Conserve de forma separada y protegida `/etc/portacustodia/document.key`: perder la clave puede impedir recuperar todos los documentos y backups cifrados.** Antes de actualizar, consulte el procedimiento de migración y realice copias verificadas. No publique claves, backups, fotos ni bases SQLite en GitHub.

## 9. Seguridad y limitaciones importantes

- **Uso con datos reales:** Dirección/Secretaría/DPD deben aprobar tratamiento, conservación, acceso, supresión, alojamiento, política de móviles y respuesta a incidentes.
- **Sin firma electrónica:** se usan dos originales impresos, firmados y escaneados. SHA-256 no certifica quién firma ni constituye sello de tiempo cualificado.
- **Sin SMTP institucional configurado:** el correo `@canariaseducacion.es` se emplea para registro y borradores. El sistema no hace envíos automáticos.
- **PWA segura:** HTTPS indispensable; la instalación no crea dominio, certificado ni Cloudflare Tunnel de forma autónoma.
- **Protección documental:** documentos nuevos y backups cifrados si se configura la clave. La base SQLite activa no está cifrada por la propia aplicación: se debe valorar cifrado de volumen y copias aisladas.
- **No hay homologación de archivo electrónico administrativo ni integración con sistemas oficiales**, firma cualificada, SSO institucional o MDM.
- **Mantenimiento:** actualizar Ubuntu, Python y dependencias de forma supervisada; establecer plan de parches y probar recuperación. `apt-get update` durante la instalación inicial no equivale a mantener el servidor actualizado.
- **No prometer disponibilidad sin ensayo real:** se han ejecutado **26 pruebas automáticas**, más autodiagnóstico aislado, comprobación de sintaxis de instaladores y generación/inspección del manual PDF. La instalación aún debe probarse en el LXC Ubuntu definitivo y con cámaras reales antes de entrar en producción.

## 10. Solución de problemas

| Síntoma | Comprobación |
|---|---|
| `apt-get update` falla | DNS, gateway, proxy de salida y repositorios Ubuntu del LXC. |
| No puede descargarse GitHub | Acceso saliente HTTPS, certificados, DNS y URL exacta del repositorio. |
| `systemd` no está disponible | El contenedor debe arrancar con systemd; no ejecutar en host Proxmox. |
| Fallo en `pip` o librerías | Revise `journalctl` y salida del instalador; confirme arquitectura y Python de la LTS. |
| Servicio no inicia | `journalctl -u portacustodia -n 100 --no-pager`; compruebe clave y permisos de `/etc/portacustodia`. |
| `/salud` no responde | Revisar dirección bind/puerto, servicio y reglas de cortafuegos. |
| Login no persiste por HTTP | Se requiere HTTPS y cookies Secure; no desactivar en producción. |
| PDF legal bloqueado | Complete los cuatro valores oficiales RGPD y reinicie. |
| PWA/cámara no funcionan | HTTPS, permisos, navegador; usar lector USB/Bluetooth como alternativa. |
| Foto o expediente no aparecen | Roles/grupo exacto, archivo válido y estado del expediente. |

## 11. Código y pruebas

```text
app/                 API FastAPI, HTML/CSS, PWA, gestión y custodia
scripts/
  bootstrap_ubuntu.sh     Descarga HTTPS de GitHub sin curl ni git
  install_lxc_ubuntu.sh   Instalación en Ubuntu LXC con systemd
  selfcheck.py            Autotest con datos totalmente ficticios
  backup.py               Copias cifradas y verificables
  followup.py             Preparación de alertas internas
docs/
  MANUAL_USO_PORTACUSTODIA.pdf   Manual ilustrado
  ...                         Protocolos y otros manuales
manage.py             Alta de administrador y verificación de auditoría
requirements.txt      Dependencias Python de la aplicación
 tests/                Pruebas automatizadas del flujo y permisos
```

Para ejecutar la batería de desarrollo fuera de producción:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt pytest
PYTHONPATH=. pytest -q
```

---

**Uso recomendado:** empezar con un **LXC piloto aislado y datos ficticios**, revisar el manual PDF, validar el circuito completo de contrato/entrega/devolución y obtener la aprobación institucional antes de dar de alta alumnado real.
