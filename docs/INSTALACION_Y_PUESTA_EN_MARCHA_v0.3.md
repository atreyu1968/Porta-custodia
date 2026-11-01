# Instalación, actualización y validación de PortaCustodia 0.3

**Entorno previsto:** LXC Ubuntu/Debian dentro de Proxmox; instalación supervisada por coordinación TIC. No ejecutar en el host Proxmox. Sin dependencia de firma electrónica. El personal del centro utiliza direcciones `@canariaseducacion.es`; las familias pueden tener contactos externos verificados.

## 1. Instalación nueva

1. Solicitar a Secretaría la tramitación con CAU_CE de IP dedicadas fuera del DHCP si el centro utiliza direccionamiento oficial, para el host, el LXC y el túnel/proxy que corresponda. Obtener la autorización de instalación y de publicación del servicio.
2. Crear un LXC aislado Ubuntu/Debian con recursos suficientes para el número previsto de usuarios, persistencia de datos y copias de seguridad segregadas.
3. Copiar el proyecto al contenedor; ejecutar `bash scripts/install_lxc_ubuntu.sh` como root **dentro del LXC**, no en Proxmox host.
4. Revisar `/etc/portacustodia/environment`, conservando permisos `0600`, e incorporar los datos institucionales verificados de protección de datos:

```ini
PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=1
PORTACUSTODIA_RESPONSABLE_DATOS="Denominación confirmada por el responsable del tratamiento"
PORTACUSTODIA_CONTACTO_DPD="Dirección de contacto publicada del DPD"
PORTACUSTODIA_PRIVACIDAD_URL="https://pagina-oficial-con-informacion-completa"
PORTACUSTODIA_RETENCION="Criterio o plazo institucional aprobado"
```

Los cuatro campos no deben rellenarse con datos inventados; solicítelos a Dirección y al DPD. La instalación **impide generar compromisos de préstamo** si está activado `PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=1` y faltan estos campos. En modo local sin esa bandera los PDF identifican los datos pendientes: solo para pruebas ficticias.

5. Reiniciar y revisar `systemctl restart portacustodia && systemctl status portacustodia --no-pager`. Crear administrador mediante `manage.py create-admin` con las variables de entorno indicadas en el README. No existen claves por defecto.
6. Probar acceso detrás de HTTPS y de autenticación perimetral autorizada. Revisar restricciones del cortafuegos, protección CSRF, sesiones, cifrado y rol de cada cuenta.
7. Realizar una prueba con alumnado y equipos ficticios: contrato por duplicado, firmas simuladas, archivo de la copia del centro, segunda copia entregada, devolución, acta por duplicado y cierre documental.
8. Verificar la copia `.pcbak` y una restauración en un **contenedor distinto**. Custodiar la clave AES-256-GCM fuera de los backups, con copia de emergencia controlada.

## 2. Actualización desde 0.2.2

1. Identificar la versión, detener el servicio y generar copia verificable de base de datos y documentos. Asegurar que también se custodia la clave de cifrado y el fichero de entorno.
2. Actualizar **solo el código**, manteniendo `/var/lib/portacustodia`, `/etc/portacustodia` y `/var/backups/portacustodia` en sus ubicaciones.
3. El sistema incorpora automáticamente campos nuevos a la tabla de préstamos, sin eliminar expedientes existentes. **Los préstamos heredados no pueden demostrar retroactivamente la entrega de dos ejemplares**; no deben rellenarse estos campos por inferencia.
4. Configurar las cuatro variables institucionales y comprobar que `PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=1` está habilitada. Reiniciar el servicio.
5. Ejecutar pruebas de regresión desde una copia de trabajo: `PYTHONPATH=. pytest -q` (instalar dependencias de pruebas). Verificar que se puede leer y exportar un expediente anterior y restaurar un respaldo.

## 3. Modos documentales

| Proceso | Se genera | Copias manuscritas | Archivo digital |
|---|---|---|---|
| Entrega | Compromiso y autorización | Original centro + original interesado; firman ambos | Centro: contrato_firmado |
| Devolución | Acta de recepción | Original centro + original interesado; firman ambos | Centro: acta_devolucion_firmada |
| Requerimiento | Requerimiento | Dos ejemplares para firma y gestión | Acuse/justificante, si existe |

**Importante:** un documento generado no es un documento firmado; un correo descargado como `.eml` no es un envío; un SHA-256 no acredita por sí solo la autoría de una firma.

## 4. Seguridad documental y límites

- Archivos privados con identificador aleatorio y huella de integridad; cifrado AES-256-GCM cuando existe clave; instalación LXC lo exige.
- Validación básica de la estructura del PDF cargado (PDF legible, no cifrado, entre 1 y 100 páginas), sin reconocimiento ni validación automática de firma manuscrita.
- Una devolución física no queda oculta aunque no se haya firmado el acta; se distingue como cierre documental pendiente.
- Auditoría de accesos, descargas y transiciones; política de retención, certificación de archivo, recuperación ante desastres y auditoría externa **pendientes de aprobación y verificación real**.
- Sin envío SMTP, sin firma electrónica, sin MDM y sin conexión a plataformas oficiales de archivo, inventario o registro. Comprobar la normativa e instrucciones aplicables antes de sustituir procedimientos institucionales.
