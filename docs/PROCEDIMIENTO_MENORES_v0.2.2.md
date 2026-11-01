# Protocolo propuesto de préstamo de portátiles a alumnado menor de edad

**Centro:** IES Manuel Martín González — Departamento de Administración y Gestión  
**Aplicación:** PortaCustodia 0.2.2 (piloto)  
**Fecha:** 1 de noviembre de 2026  
**Estado:** borrador sujeto a aprobación por Dirección, Secretaría y validación de protección de datos.

## 1. Personas destinatarias

Se aplica al alumnado **menor de 18 años no emancipado** que necesite recibir un portátil del centro para fines educativos. El procedimiento para el alumnado mayor de edad se establece en el protocolo general. Las situaciones de emancipación, tutela institucional, discrepancias sobre patria potestad o conflictos de representación **no se resolverán automáticamente** y requieren revisión individual por Secretaría/Dirección conforme a su documentación.

## 2. Identificación del representante

Secretaría comprobará quién está facultado para intervenir como representante del menor, usando preferentemente los datos que ya constan legítimamente en los sistemas educativos. Cuando sea preciso, podrá pedir la exhibición de documentación acreditativa, **sin almacenar copias del DNI ni documentos familiares completos** por defecto. Si existe constancia de limitaciones judiciales, oposición o duda razonable sobre la facultad de representación, no se formalizará la entrega hasta resolverla.

La intervención de uno de los progenitores puede resultar suficiente en una gestión ordinaria cuando ostente patria potestad y no conste oposición u otra limitación relevante, pero no debe presumirse para todas las situaciones familiares. La representación de menores se regula en el artículo 162 del Código Civil.

## 3. Expediente y documento de compromiso

Se generará un expediente único con referencia `PC-00000`, vinculado al equipo de inventario y su número de serie. Se confeccionará un **acta de préstamo de tres firmas manuscritas diferenciadas**:

1. Alumno/a menor (recepción y conocimiento de condiciones).
2. Padre, madre o representante legal acreditado (intervención en el préstamo).
3. Personal del centro que efectúa la entrega.

Las firmas se recogerán presencialmente o mediante el procedimiento de obtención de firmas manuscritas autorizado por el centro; la app **no verifica la autenticidad de la firma**. Se escaneará o fotografiará el documento completo de manera legible y se incorporará a la categoría «Compromiso de préstamo firmado». El archivo digital conserva su huella de integridad; no sustituye al documento original que, en su caso, deba conservarse en soporte físico.

## 4. Bloqueos automáticos en PortaCustodia

No se podrá activar un préstamo a menor mientras falte cualquiera de estos requisitos:

- Documento firmado digitalizado y archivado en el expediente.
- Confirmación de la entrega presencial.
- Comprobación de firma manuscrita del alumno/a.
- Comprobación de firma manuscrita del representante.
- Selección de método de verificación de la representación (expediente de matrícula, documentación exhibida o resolución acreditativa).
- Selección de la condición jurídica de quien actúa como representante.

La aplicación registrará la cuenta del usuario que confirma, fecha/hora y método. Esta información es una **declaración administrativa de la comprobación**, no una validación biométrica o notarial. Los datos del menor y del representante quedan fijados en una instantánea asociada al préstamo para evitar que posteriores cambios en la ficha alteren la historia del expediente.

## 5. Comunicaciones

Las comunicaciones del personal del centro se prepararán desde su correo autorizado bajo el dominio `@canariaseducacion.es`. El correo de la familia puede ser de otro dominio.

Cuando el alumno siga siendo menor y se haya verificado que el correo familiar registrado es un canal adecuado para las comunicaciones del préstamo, el borrador `.eml` podrá incorporar dicho correo como destinatario. En caso contrario, se dejará el destinatario en blanco para que Secretaría utilice el canal válido disponible. **Generar un borrador no significa enviarlo, y enviar un correo no acredita automáticamente una notificación administrativa fehaciente**.

Una vez constatado que el alumno ha cumplido 18 años, se actualizará su situación en la ficha, previa comprobación institucional. Los préstamos históricos mantendrán el régimen de firma existente cuando se formalizaron. Los **nuevos borradores** pasarán a dirigirse al alumno mayor de edad, si existe un correo propio adecuado, en vez de conservar automáticamente a la familia como destinataria.

## 6. Incidencias y responsabilidades

La familia **no asume de manera automática** el valor de reposición del equipo por el mero hecho de firmar el compromiso. Las reclamaciones económicas requieren determinar los hechos, el daño, la conducta y la responsabilidad aplicable. El artículo 58 del Decreto 114/2011 de Canarias contempla la reparación por daños intencionados o uso indebido y la restitución de bienes sustraídos, así como la responsabilidad civil subsidiaria en los términos del artículo 1903 del Código Civil.

No se retendrán notas, títulos, certificados ni otros documentos académicos como medida de presión. Cuando corresponda reclamar el equipo formalmente se seguirá el procedimiento institucional aprobado.

## 7. Protección de datos y custodia

Se recogerán únicamente los datos de identidad, representación y contacto necesarios para este fin. La utilización de los datos estrictamente necesarios para la función educativa **no requiere con carácter general consentimiento de protección de datos**; se deberá facilitar la información preceptiva sobre el tratamiento y consultar al delegado de protección de datos.

Los documentos estarán disponibles solo para los perfiles autorizados. No se incorporarán datos sobre litigios familiares, resoluciones íntegras o documentación de identidad salvo que exista necesidad justificada y procedimiento aprobado. Los originales en papel y las copias digitalizadas deberán sujetarse a las normas de custodia y conservación establecidas por el centro y la Consejería.

## 8. Situaciones especiales

- **Cumple 18 años durante el ciclo:** Secretaría verifica la mayoría de edad en los datos institucionales, registra el cambio y usa la modalidad de firma de adulto en los préstamos nuevos. El contrato anterior no se altera retrospectivamente.
- **Menor emancipado:** el artículo 247 del Código Civil establece un régimen especial de capacidad. No debe confundirse un préstamo gratuito de equipo con tomar dinero a préstamo. Se deriva la valoración de capacidad y formalización a Dirección/Secretaría, con asesoramiento jurídico si fuera necesario.
- **Acogimiento o tutela institucional:** verificar la persona o entidad facultada para intervenir; no asumir que la persona de contacto habitual es necesariamente representante legal.
- **Separación o desacuerdo de progenitores:** verificar quién ejerce la patria potestad y atender las limitaciones o discrepancias acreditadas antes de la firma.

## 9. Base normativa y referencias

- [Código Civil, artículos 162, 1903 y 239 a 247](https://www.boe.es/buscar/act.php?id=BOE-A-1889-4763).
- [Decreto 114/2011, de 11 de mayo, de convivencia escolar, artículo 58](https://www.gobiernodecanarias.org/boc/2011/108/001.html).
- [AEPD: criterios para tratar datos personales en centros educativos](https://www.aepd.es/infografias/criterios-tratamiento-datos-personales-centros-educativos.pdf).

**Antes del despliegue real:** validar las cláusulas, la base legitimadora, las medidas de seguridad, el régimen de archivo y los medios de notificación con Dirección, Secretaría y la persona delegada de protección de datos.
