# PortaCustodia 0.4 · Manual de la aplicación móvil (PWA)

**Centro:** IES Manuel Martín González · Departamento de Administración y Gestión.
**Destinatarios:** Dirección, Secretaría, coordinación TIC, profesorado autorizado.
**Estado:** aplicación piloto funcional, pendiente de autorización y validación institucional en la infraestructura real.

## 1. Acceso a la PWA

1. Instalar la versión 0.4.0 en un LXC Ubuntu/Debian a través de HTTPS. La dirección exacta la proporcionará el centro; no se presupone ningún dominio nuevo.
2. Iniciar sesión con cuenta individual. El correo del personal registrado debe pertenecer a `@canariaseducacion.es`; el programa **no envía correos automáticamente**.
3. Abrir la sección **Aplicación móvil** (`/movil`).
4. **Android/Chrome:** menú del navegador → *Instalar aplicación* o *Añadir a pantalla de inicio*.
5. **iPhone:** abrir en Safari, tocar *Compartir* → *Añadir a pantalla de inicio* (otras versiones y navegadores pueden variar).
6. El icono permite abrir PortaCustodia en modo aplicación. No constituye una aplicación nativa instalada desde una tienda.

**Conectividad:** la aplicación debe estar conectada al servidor para mostrar expedientes, consultar inventario, subir fotos o cerrar devoluciones. Se guardan en caché solo recursos estáticos (estilos, JavaScript e iconos); jamás documentos, fotografías, expedientes o respuestas de API. La instalación en pantalla de inicio no garantiza servicio sin conexión.

## 2. Leer el número de serie

### Lector USB o Bluetooth (modo teclado)

1. Vincular el lector al equipo o móvil de acuerdo con sus instrucciones.
2. En `Inventario` → `Incorporar un portátil`, situar el cursor en **N.º serie**, o en `/movil` → **N.º de serie o inventario**.
3. Escanear la etiqueta; el valor se introduce en el campo. El programa evita envíos involuntarios por un `Enter` automático cuando está en ese campo.
4. Comprobar visualmente que la etiqueta leída es **S/N, Serial Number o número de inventario** y no el identificador de producto, IMEI, etiqueta de garantía u otro código.
5. En la pantalla móvil, pulsar **Buscar equipo** para abrir su ficha.

### Lectura directa mediante cámara

1. Pulsar **Abrir cámara** en `/movil` o en el alta del inventario.
2. Autorizar el uso de cámara cuando el navegador lo solicite.
3. Enfocar un código Code 128/39/93, EAN, ITF, QR o Data Matrix, según los formatos que soporte el navegador.
4. Comprobar el valor leído. Si el número no está en el inventario, comprobar la etiqueta antes de dar de alta otro portátil.

> La detección en directo depende de `BarcodeDetector`, API que no funciona en todos los navegadores. **No debe presentarse como universal.** Funciona únicamente en contexto seguro HTTPS (o localhost durante las pruebas).

### Alternativa compatible con navegadores sin detector en directo

1. En el campo «fotografiar la etiqueta», abrir la cámara y tomar una fotografía enfocada exclusivamente al código.
2. La imagen se envía al servidor para descodificación con `pyzbar` y `libzbar0`.
3. La imagen de la etiqueta se procesa **en memoria y no se incorpora a los documentos ni a las fotografías del equipo**.
4. Se devuelve el valor detectado. Si se reconocen varios códigos, la aplicación solicita comprobarlos para no confundir el S/N con la referencia de producto. Ante duda, usar un lector Bluetooth/USB o entrada manual.

## 3. Fotografías de la unidad

1. Abrir la ficha del portátil, ya sea por el código leído o pulsando su número de inventario.
2. Seleccionar el expediente del préstamo al que se refiere la foto. Para alumnado y profesorado, deben permanecer asociados a la autorización de su grupo. Solo Secretaría/TIC/administración pueden adjuntar una foto general de inventario.
3. Identificar el momento: inventario, entrega, revisión, devolución o incidencia.
4. Escribir una observación objetiva y breve: «Pantalla apagada sin grietas», «cargador recibido», «rotura en bisagra derecha», etc.
5. Pulsar el campo de foto para abrir la cámara trasera o seleccionar un archivo JPEG/PNG/WebP (hasta 10 MB; máximo 25 megapíxeles).
6. Revisar la vista previa y archivar. La aplicación orienta y limita la resolución a 2400 px, convierte a JPEG y **elimina metadatos EXIF** (incluidas coordenadas GPS). La fotografía normalizada queda en almacén privado con huella SHA-256, usuario, hora de servidor, etapa, número de equipo y préstamo vinculado.
7. El archivo fotográfico puede consultarse desde la ficha del portátil y desde el expediente. Se incluye en el ZIP exportado por personal con permisos.

**Limitaciones de evidencia:** el archivo archivado se normaliza y no es el bitstream original de la cámara; es un registro documental didáctico/administrativo de estado, no una pericia forense de fotografía. La huella SHA-256 verifica integridad de esa versión normalizada, pero no demuestra por sí sola la autenticidad del hecho fotografiado. No fotografiar alumnado, rostros, documentos de identidad, pantallas encendidas, mensajes privados ni contraseñas.

## 4. Reglas de permisos

| Perfil | Alcance en el móvil |
|---|---|
| Administración | Gestión de todo el inventario, usuarios, préstamos, documentos y fotografías. |
| Secretaría | Gestión integral administrativa y documental. |
| TIC | Gestión técnica, fotos de inventario y fotos ligadas a expedientes; no formaliza préstamos. |
| Tutoría | Consulta y revisión de préstamos de su grupo; puede añadir fotografías e incidencias **solo en préstamos de su grupo**. |
| Docente gestor | Gestiona préstamos, documentos, firmas manuscritas, devoluciones, incidencias y fotos **solo de su grupo**. Requiere autorización y asignación de grupo por el administrador. |
| Consulta | Lectura según los permisos existentes, sin acceso a las fotografías privadas. |

La entrega a menores requiere igualmente representación acreditada y las dos copias manuscritas firmadas. **La cámara o una fotografía no sustituye la firma ni el procedimiento de doble ejemplar.**

## 5. Seguridad operativa

- Acceder exclusivamente mediante HTTPS autorizado; nunca abrir el puerto de Uvicorn al exterior.
- No compartir credenciales personales; cerrar la sesión, especialmente en móviles compartidos.
- Mantener los móviles actualizados y protegidos con bloqueo de pantalla.
- La autorización de la app al profesorado no equivale a autorización para descargar expedientes masivamente o fotografiar al alumnado.
- Respetar minimización, finalidad educativa, política de custodia y plazo de conservación aprobado por Dirección y el DPD.
- Las imágenes se guardan junto a los documentos y forman parte de copias cifradas. Custodiar externamente los backups y la clave de cifrado.
- En dispositivos personales (BYOD) consultar previamente la política del centro y el DPD; la fotografía puede generarse temporalmente en la galería o la aplicación de cámara del sistema operativo. Evitar guardar fotos fuera del sistema. Preferir dispositivos del centro.
