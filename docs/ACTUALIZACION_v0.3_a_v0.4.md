# Actualización supervisada PortaCustodia 0.3 → 0.4

1. Programar una ventana de mantenimiento, informar al personal y cerrar todas las sesiones.
2. **Antes de instalar:** realizar copia de la base SQLite y de `/var/lib/portacustodia/private_documents`, además de verificar la copia cifrada `.pcbak` desde un entorno de pruebas. Conservar la clave `/etc/portacustodia/document.key` y el archivo de configuración separados y protegidos; no copiarlos en el ZIP de la aplicación.
3. Detener el servicio: `systemctl stop portacustodia`. Conservar el directorio de datos, el entorno y las copias anteriores. No sustituir `/var/lib/portacustodia`.
4. Desplegar el nuevo código en el directorio instalado; el instalador de Ubuntu LXC permite actualizar en el mismo contenedor, conserva los datos y añade `libzbar0`.
5. Al arrancar, se crea `device_photos` y, si se viene de 0.3, se actualiza la restricción de roles de `users` para permitir el nuevo `gestor` (reconstrucción transaccional; mantiene IDs).
6. Comprobar: `PRAGMA foreign_key_check`, `manage.py check-audit`, pruebas de lectura de expedientes anteriores y capacidad de generar contratos por duplicado.
7. Asignar a docentes usuarios individuales con dominio `@canariaseducacion.es`, rol **gestor** o **tutor** y un grupo que coincida literalmente con el registrado para el alumnado.
8. Verificar acceso por HTTPS desde Android e iPhone: permisos de cámara, foto de etiqueta y archivos adjuntos, lectura por lector USB/Bluetooth, fotografía de equipo y rechazo de accesos a otro grupo.
9. Probar exportación del expediente que contiene fotografías y verificación de SHA-256. Realizar backup cifrado y **restauración de prueba** en un LXC diferente.
10. Solo después de validar el piloto y obtener las autorizaciones institucionales se incorporarán datos personales reales.

**Advertencia:** no sustituir por completo los PDF de firma manuscrita ni los expedientes existentes. La 0.4 complementa la 0.3 y conserva la formalización de dos ejemplares por préstamo y devolución. El cifrado no se activa por instalar una PWA; se requiere la clave del servidor y el procedimiento de copias aprobado.
