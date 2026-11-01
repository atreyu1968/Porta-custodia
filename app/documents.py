"""Dossiers PDF de préstamo en DOS ejemplares íntegros para firma manuscrita.

Cada ejemplar contiene las mismas condiciones; no presupone firma ni notificación.
El texto jurídico es un modelo sujeto a aprobación institucional.
"""
import os
from io import BytesIO
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
if Path(FONT).exists() and Path(FONT_BOLD).exists():
    pdfmetrics.registerFont(TTFont('Institutional', FONT))
    pdfmetrics.registerFont(TTFont('InstitutionalBold', FONT_BOLD))
    REGULAR,BOLD='Institutional','InstitutionalBold'
else:
    REGULAR,BOLD='Helvetica','Helvetica-Bold'

LEGAL_URLS = (
 'Decreto 114/2011 (BOC 108/2011): https://www.gobiernodecanarias.org/boc/2011/108/001.html',
 'Código Civil (BOE-A-1889-4763): https://www.boe.es/buscar/act.php?id=BOE-A-1889-4763',
 'RGPD (DOUE-L-2016-80807): https://www.boe.es/buscar/doc.php?id=DOUE-L-2016-80807',
 'LO 3/2018 (BOE-A-2018-16673): https://www.boe.es/buscar/act.php?id=BOE-A-2018-16673',
)

TERMS = [
 ('1. Naturaleza y titularidad',
  'El equipo identificado en este expediente se facilita gratuitamente y de manera temporal para el aprendizaje. Su propiedad continúa correspondiendo a la Administración o titular público que resulte competente. El presente documento no transmite la propiedad, ni autoriza su venta, cesión, empeño o entrega a terceras personas. Referencias orientativas: artículos 1740 y 1741 del Código Civil, sin perjuicio del régimen aplicable a los bienes públicos.'),
 ('2. Finalidad y personas autorizadas',
  'El uso se limita a las actividades formativas vinculadas al ciclo y a las tareas académicas autorizadas. La persona receptora no debe facilitar a terceras personas el uso o las credenciales asignadas, ni modificar identificadores de inventario. Se utilizará software y recursos conformes a las instrucciones del centro.'),
 ('3. Plazo de préstamo y devolución anticipada',
  'La fecha límite de devolución es la indicada en la ficha de este documento. Al término del plazo deberá entregarse el equipo con sus accesorios. La baja en el ciclo, el traslado, la finalización de estudios o una causa de retirada prevista en el protocolo aprobado darán lugar a la solicitud de devolución mediante comunicación del centro. Toda ampliación debe registrarse de forma expresa antes del vencimiento.'),
 ('4. Custodia y conservación diligente',
  'La persona receptora se compromete a transportar y guardar cuidadosamente el portátil, evitar humedad, golpes o exposición a terceros, seguir las pautas de seguridad y no realizar intervenciones técnicas ni abrir el equipo sin autorización. Cualquier anomalía se comunicará a Secretaría o al servicio TIC del centro sin demora.'),
 ('5. Averías, incidencias y pérdida',
  'Toda avería, extravío, robo o daño se comunicará tan pronto sea conocido, indicando las circunstancias verificables y aportando justificantes disponibles, sin facilitar datos excesivos. El centro registrará los hechos y determinará, mediante el procedimiento que corresponda, si existe responsabilidad. No se exige indemnización automática por una avería, pérdida o sustracción; se valorarán la conducta, la prueba disponible y la normativa aplicable.'),
 ('6. Desgaste y daños imputables',
  'El desgaste ordinario derivado del uso correcto no genera por sí solo obligación de reparación (artículo 1746 del Código Civil, como referencia orientativa). Los daños intencionados, el uso indebido o la sustracción podrán dar lugar a restitución, reparación o reclamación según el artículo 58 del Decreto 114/2011 de Canarias y, cuando proceda, la normativa civil y administrativa aplicable.'),
 ('7. Retención tras el vencimiento',
  'La persona receptora debe devolver el equipo al llegar el vencimiento, y atender los requerimientos legítimos del centro. La retención injustificada o el uso distinto del convenido podrá dar lugar a actuaciones de recuperación y a las responsabilidades previstas legalmente; artículo 1744 del Código Civil como referencia, sujeto al régimen público de los bienes.'),
 ('8. Entrega de accesorios, comprobación y recibí',
  'La devolución se realizará físicamente en el lugar que indique el centro, con cargador y demás accesorios reseñados. Se expedirá un acta de recepción por duplicado que describa el estado aparente del equipo. La existencia de una incidencia no impedirá documentar la entrega efectiva, pero el equipo podrá pasar a revisión.'),
 ('9. Datos personales almacenados en el portátil',
  'Antes de devolver el equipo, la persona usuaria debe guardar su trabajo académico en los medios autorizados. El centro gestionará, conforme a su protocolo y a la protección de datos, la eliminación de cuentas y archivos locales cuando proceda. Este compromiso no autoriza la inspección indiscriminada de archivos personales ni la activación de cámara, micrófono o geolocalización continua.'),
 ('10. Avisos y requerimientos',
  'Los recordatorios podrán prepararse por medios institucionales, incluido el correo del personal @canariaseducacion.es. La mera generación de un aviso o de un borrador de correo no acredita su envío ni su recepción. Cuando sea necesaria una comunicación formal, se utilizará el cauce institucional procedente y se archivará la evidencia disponible.'),
 ('11. Medidas no autorizadas',
  'Este compromiso no establece fianzas, cargos automáticos, sanciones económicas privadas ni retención de títulos, notas, certificados o documentación académica por impago o falta de devolución. Las eventuales medidas administrativas o legales se adoptarán por el órgano competente conforme al procedimiento aplicable.'),
 ('12. Firma en dos ejemplares',
  'Este documento se imprime en dos ejemplares íntegros e iguales: uno para el centro y otro para la persona interesada o su representante legal. Ambos se firman de puño y letra. El centro conserva el suyo, digitaliza una copia para el expediente y registra que el segundo ejemplar firmado se entrega a la persona indicada.'),
]

MINOR_TERMS = [
 ('13. Autorización del representante legal',
  'Quien firma como representante legal declara ostentar facultades suficientes para autorizar el préstamo y la salida del equipo del centro, haber leído todas sus condiciones y autorizar al alumno o alumna identificado a recibirlo materialmente. Esta autorización no sustituye la comprobación administrativa de la representación, que realizará el centro antes de entregar el portátil.'),
 ('14. Alcance de la responsabilidad familiar',
  'La firma no equivale a una garantía ilimitada ni a una obligación incondicional de pago. La responsabilidad civil de los representantes legales, cuando proceda, se determinará conforme al artículo 58.3 del Decreto 114/2011 y al artículo 1903 del Código Civil, junto con la normativa y las circunstancias del caso. La representación del menor se rige, según corresponda, por los artículos 154, 156 y 162 del Código Civil.'),
]

class Page:
    def __init__(self,title,code,issued):
        self.buf=BytesIO();self.c=canvas.Canvas(self.buf,pagesize=A4)
        self.w,self.h=A4;self.title=title;self.code=code;self.issued=issued
        self.exemplar_number=1;self.exemplar_label='CENTRO EDUCATIVO';self.page=1;self.header()

    def header(self):
        c=self.c;w=self.w
        c.setFillColorRGB(.065,.145,.25);c.rect(0,self.h-107,w,107,fill=1,stroke=0)
        c.setFillColorRGB(1,1,1);c.setFont(BOLD,11)
        c.drawString(43,self.h-31,'IES MANUEL MARTÍN GONZÁLEZ')
        c.setFont(REGULAR,8);c.drawString(43,self.h-46,'Departamento de Administración y Gestión · Préstamo de equipos TIC')
        c.setFont(BOLD,12);c.drawString(43,self.h-69,self.title)
        c.setFillColorRGB(.85,.93,1);c.setFont(BOLD,8)
        c.drawString(43,self.h-91,f'EJEMPLAR {self.exemplar_number} DE 2 · {self.exemplar_label}')
        self.y=self.h-129

    def footer(self):
        c=self.c;c.setStrokeColorRGB(.68,.75,.82);c.line(43,52,self.w-43,52)
        c.setFillColorRGB(.3,.35,.4);c.setFont(REGULAR,7.2)
        c.drawString(43,39,f'PC-{self.code} · Emitido: {self.issued} · Ejemplar {self.exemplar_number}/2')
        c.drawRightString(self.w-43,39,f'Hoja {self.page} · Sin validez de firma hasta su suscripción manuscrita')

    def ensure(self,pts=55):
        if self.y-pts < 74:
            self.footer();self.c.showPage();self.page+=1;self.header()

    def next_exemplar(self):
        self.footer();self.c.showPage();self.exemplar_number=2
        self.exemplar_label='ALUMNO/A O REPRESENTANTE LEGAL';self.page=1;self.header()

    def sub(self,txt):
        self.ensure(38);self.y-=5
        self.c.setFont(BOLD,9.5);self.c.setFillColorRGB(.08,.28,.49)
        self.c.drawString(43,self.y,txt);self.y-=20

    def para(self,txt):
        lines=simpleSplit(str(txt),REGULAR,8.3,self.w-86)
        self.ensure(len(lines)*11+6)
        self.c.setFont(REGULAR,8.3);self.c.setFillColorRGB(.17,.2,.25)
        for line in lines:self.c.drawString(43,self.y,line);self.y-=11
        self.y-=6

    def field(self,label,value):
        txt=str(value or 'NO CONSTA')
        labels=simpleSplit(txt,REGULAR,8.3,self.w-226)
        self.ensure(len(labels)*11+12)
        self.c.setFont(BOLD,8.3);self.c.setFillColorRGB(.1,.24,.39)
        self.c.drawString(43,self.y,label)
        self.c.setFont(REGULAR,8.3);self.c.setFillColorRGB(.15,.16,.18)
        for line in labels:self.c.drawString(186,self.y,line);self.y-=11
        self.y-=4

    def signature(self,label):
        self.ensure(70);self.y-=37
        self.c.setStrokeColorRGB(.48,.54,.6);self.c.line(43,self.y,self.w-43,self.y)
        self.y-=13;self.c.setFont(REGULAR,8);self.c.setFillColorRGB(.18,.22,.28)
        self.c.drawString(43,self.y,label);self.y-=18

    def finish(self):
        self.footer();self.c.save();return self.buf.getvalue()


def _privacy(p):
    p.sub('Información básica sobre protección de datos')
    responsible=(os.getenv('PORTACUSTODIA_RESPONSABLE_DATOS') or 'PENDIENTE DE VALIDACIÓN EN EL REGISTRO DE ACTIVIDADES DEL RESPONSABLE')
    dpd=(os.getenv('PORTACUSTODIA_CONTACTO_DPD') or 'PENDIENTE DE CONFIGURACIÓN POR EL CENTRO')
    link=(os.getenv('PORTACUSTODIA_PRIVACIDAD_URL') or 'PENDIENTE DE INCORPORAR LA INFORMACIÓN COMPLETA')
    retention=(os.getenv('PORTACUSTODIA_RETENCION') or 'Según tabla de conservación institucional pendiente de validación')
    p.para('Responsable: '+responsible+'; contacto DPD: '+dpd+'.')
    p.para('Finalidad: inventariar los equipos, gestionar el préstamo, entrega, uso, incidencias, devolución, reclamaciones y custodia de justificantes. Base jurídica propuesta para validar por el responsable: misión de interés público o cumplimiento de obligaciones legales, según artículo 6.1.e/c del RGPD y normativa educativa aplicable; no se basa en un consentimiento genérico del alumno.')
    p.para('Destinatarios: unidades y personal autorizado, y organismos competentes cuando sea legalmente necesario. Plazo o criterio de conservación: '+retention+'. Derechos de protección de datos: podrán ejercerse ante el responsable por los canales publicados en la información completa: '+link+'. Referencias: artículos 5, 6, 13 y 32 del RGPD y LO 3/2018.')
    if 'PENDIENTE' in (responsible+dpd+link):
        p.para('IMPORTANTE: el centro deberá completar y validar los datos de esta cláusula informativa antes de utilizar documentos con alumnado real.')


def _loan_details(p,loan):
    p.sub('Identificación del préstamo y del equipo')
    for key,value in [
        ('Alumno/a',loan['student_name']),('Referencia interna',loan['student_ref']),
        ('Ciclo / grupo',loan['course_group']),
        ('Persona representante',loan['guardian_name'] if loan['minor'] else 'No procede'),
        ('Condición legal',loan['guardian_relation'] if loan['minor'] else 'Mayor de edad'),
        ('Equipo',f'{loan["brand"]} {loan["model"]}'),('N.º de inventario',loan['asset_tag']),
        ('Número de serie',loan['serial_number']),('Accesorios',loan['accessories']),
        ('Vencimiento',loan['due_date']),('Finalidad',loan['purpose'] or 'Uso educativo'),
    ]:p.field(key,value)


def _one_copy(p,kind,loan):
    _loan_details(p,loan)
    if kind=='contrato':
        p.field('Estado inicial',loan['delivery_condition'] or loan['condition_note'] or 'Pendiente de comprobación en entrega')
        p.sub('Condiciones legales, materiales y de devolución')
        for heading,body in TERMS+(MINOR_TERMS if loan['minor'] else []):
            p.ensure(42+11*len(simpleSplit(body,REGULAR,8.3,p.w-86)))
            p.sub(heading);p.para(body)
        p.sub('Normativa y fuentes oficiales')
        for line in LEGAL_URLS:p.para(line)
        _privacy(p)
        p.ensure(280 if loan['minor'] else 210)
        p.sub('Recibí, autorización y compromiso de firma manuscrita')
        p.para('En este ejemplar, la firma acredita haber leído las condiciones y la entrega/recepción material cuando ésta se efectúe. Se firmarán AMBOS ejemplares, cada uno en su integridad. No se presume recepción del dispositivo por la mera generación del PDF.')
        p.signature('Firma manuscrita del alumno o alumna (persona receptora) y fecha')
        if loan['minor']:
            p.signature('Firma manuscrita del padre, madre o representante legal y fecha')
        p.signature('Persona que entrega el equipo (centro) · Firma y fecha')
        p.para('Ejemplar '+str(p.exemplar_number)+'/2 para '+('el centro (custodia)' if p.exemplar_number==1 else 'el alumnado o representante legal')+'.')
    elif kind=='devolucion':
        p.sub('Recepción física y comprobación inicial')
        p.field('Devolución registrada',loan['closed_at'] or 'No se ha registrado')
        p.field('Estado observado',loan['return_condition'])
        p.field('Accesorios recibidos',loan['return_accessories'])
        p.field('Resultado',loan['return_result'])
        p.para('Se deja constancia de la entrega material y del estado aparente, sin prejuzgar la responsabilidad por averías o daños. La eventual revisión técnica posterior se documentará por separado. El desgaste ordinario por uso correcto no implica indemnización automática (art. 1746 CC; art. 58 Decreto 114/2011 para los supuestos previstos).')
        p.para('Se extiende por duplicado, se firman los dos ejemplares y se entrega uno a la persona que devuelve o a su representante. Cada ejemplar identifica el mismo equipo y contiene las mismas condiciones de recepción.')
        p.ensure(190)
        p.sub('Firmas de recepción y devolución')
        p.signature('Firma de la persona que devuelve el equipo')
        p.signature('Firma de la persona receptora del centro')
        if loan['minor']:p.para('En caso de incidencia, el centro informará a la persona representante cuando corresponda.')
    elif kind=='requerimiento':
        p.sub('Requerimiento de restitución')
        p.para('Se requiere la devolución del equipo y los accesorios identificados, que constan en préstamo temporal para fines educativos. Fecha de vencimiento registrada: '+loan['due_date']+'. La devolución se gestionará a través de la Secretaría del centro.')
        p.para('El fundamento de la obligación de devolución se encuentra en las condiciones de préstamo aceptadas. Como referencia general: artículos 1740, 1741 y 1744 del Código Civil, y artículo 58 del Decreto 114/2011 para los supuestos que contempla, sin perjuicio del régimen jurídico de los bienes públicos.')
        p.para('La emisión de este requerimiento no acredita por sí misma su envío ni recepción. Deberá notificarse por el medio institucional legalmente procedente, conservando el justificante correspondiente. Se emiten dos copias para custodia y acuse, sin sustituir las garantías de un procedimiento administrativo cuando sea exigible.')
        if loan['minor']:p.para('Dirigido a la persona representante identificada, previa verificación de la representación vigente y del destinatario.')
        p.ensure(170);p.sub('Firma y constancia de comunicación')
        p.signature('Dirección / persona autorizada del centro · Firma y fecha')
        p.signature('Recibí o acuse de comunicación, si procede · Firma y fecha')


def make_pdf(kind,loan,now):
    """Devuelve un PDF con ejemplares 1/2 y 2/2 completos e independientes."""
    titles={'contrato':'COMPROMISO DE PRÉSTAMO Y AUTORIZACIÓN',
            'devolucion':'ACTA DE DEVOLUCIÓN DEL EQUIPO',
            'requerimiento':'REQUERIMIENTO DE DEVOLUCIÓN'}
    if kind not in titles:raise ValueError('Tipo documental inválido')
    if kind=='contrato' and os.getenv('PORTACUSTODIA_REQUIRE_LEGAL_CONFIG')=='1':
        required=('PORTACUSTODIA_RESPONSABLE_DATOS','PORTACUSTODIA_CONTACTO_DPD',
                  'PORTACUSTODIA_PRIVACIDAD_URL','PORTACUSTODIA_RETENCION')
        if any(not os.getenv(k,'').strip() for k in required):
            raise ValueError('Configurar responsable de datos, DPD, información de privacidad y retención antes de generar contratos reales.')
    p=Page(titles[kind],f'{loan["id"]:05d}',now)
    _one_copy(p,kind,loan)
    p.next_exemplar()
    _one_copy(p,kind,loan)
    return p.finish()
