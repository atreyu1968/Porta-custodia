# Historial de versiones

## 0.4.0 — 1 de noviembre de 2026

- PWA instalada en pantalla de inicio con interfaz adaptada a móvil, manifest e iconos. Caché solo de recursos estáticos.
- Consulta de inventario por código exacto de número de serie o inventario.
- Lectores USB/Bluetooth y cámara con BarcodeDetector cuando esté disponible.
- Fotografía temporal de etiqueta descodificada en el servidor con pyzbar/libzbar0, sin conservación.
- Fotografías de estado con autor, fecha, observación, fase, equipo, préstamo y SHA-256, con control de acceso y cifrado según clave.
- Nuevo rol docente gestor limitado a su grupo y migración desde 0.3.
- Exportación de fotografías en el expediente ZIP con manifiesto de integridad.
- Pruebas de permisos cruzados, CSRF, integridad, código QR y migración de roles.

**Aviso:** proyecto piloto; acceso móvil requiere HTTPS y validación DPD, sin homologación institucional ni autenticación corporativa unificada.


## 0.3.0 — 1 de noviembre de 2026

- Contrato de préstamo, acta de devolución y requerimiento generados en **dos ejemplares completos e independientes en un mismo PDF** (centro e interesado).
- Condiciones de uso, conservación, notificación, devolución, responsabilidad, representación legal de menores, protección de datos y referencias normativas verificables incorporadas al PDF del préstamo.
- Contrato de menores con autorización expresa del representante legal y tres firmas manuscritas separadas en cada ejemplar.
- Bloqueo de la entrega hasta registrar doble firma, entrega de segundo ejemplar y copia del centro escaneada y archivada.
- Confirmación auditable de a quién se entregó el segundo ejemplar, conservada en el préstamo; migración incremental no destructiva del esquema.
- Devolución física separada del cierre documental: para completar el expediente se requiere acta firmada archivada y comprobación de ambas copias con entrega de una al interesado.
- Aviso en el panel y en el listado de expedientes para devoluciones con cierre documental pendiente.
- Configuración institucional de la información RGPD, con modo de bloqueo de generación de contratos si faltan los campos oficiales en producción.
- Validación estructural adicional de PDF incorporados a custodia mediante pypdf.
- Modelos ficticios para comprobar la impresión (adulto y menor) y protocolos de aprobación, instalación y funcionamiento.
- 21 pruebas automatizadas (ciclo de préstamo, menores, cifrado, copia, avisos, duplicados, retención documental y privacidad parametrizada).

**Limitaciones:** No hay envío real de correo, firma electrónica, sello de tiempo cualificado, reconocimiento de firma manuscrita, homologación archivística ni instalación ya efectuada en servidores del centro. El asesoramiento y aprobación institucional siguen siendo imprescindibles.

## 0.4.1 — Instalación Ubuntu vacía y manual ilustrado

- Nuevo bootstrap HTTPS para Ubuntu LXC sin curl, wget ni git, basado en Python estándar y APT.
- Corrección de permisos del directorio de clave y fichero de entorno para el servicio restringido.
- Provisionamiento desatendido del administrador con contraseña aleatoria y cambio obligatorio.
- Prueba aislada de flujo real con datos ficticios, generación de contrato PDF, acceso PWA y cifrado.
- Comprobación correcta de `/salud`, servicio systemd y auditoría tras la instalación.
- README completamente documentado y manual PDF ilustrado con páginas reales de prueba.

**Instalación en entorno real pendiente de pilotaje:** no presupone dominio ni proxy HTTPS configurados.

- Corrección adicional: creación explícita de grupo de servicio en Ubuntu minimal.
- Corrección de autodiagnóstico: se especifica el directorio persistente de datos antes de importar FastAPI en un directorio de código de solo lectura.