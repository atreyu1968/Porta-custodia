import io
import json
import hashlib
import zipfile
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app, PH, verify_audit
from app.database import db

PASSWORD='ContraseñaInicialMuySegura!2026'

@pytest.fixture
def setup(tmp_path):
    app=create_app(tmp_path,secure_cookie=False)
    with db(app.state.dbpath,write=True) as c:
        c.execute("INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)",('admin','Admin Prueba','admin',PH.hash(PASSWORD)))
        c.execute("INSERT INTO users(username,full_name,role,tutor_group,password_hash,must_change) VALUES(?,?,?,?,?,0)",('tutor','Tutor Prueba','tutor','2º Diferente',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        yield client,app


def login(client,username='admin'):
    r=client.post('/login',data={'username':username,'password':PASSWORD},follow_redirects=False)
    assert r.status_code==303
    assert 'pc_session' in client.cookies
    with db(client.app.state.dbpath) as c:
        from app.main import hashlib
        sid=hashlib.sha256(client.cookies['pc_session'].encode()).hexdigest()
        token=c.execute('SELECT csrf FROM sessions WHERE token_hash=?',(sid,)).fetchone()['csrf']
    return token


def valid_signed_pdf():
    # Test-only scanned-document stand-in: structurally valid PDF, NOT a real signature.
    from reportlab.pdfgen import canvas
    buffer=io.BytesIO()
    pdf=canvas.Canvas(buffer,pagesize=(595,842))
    pdf.drawString(50,750,'Documento ficticio firmado en papel (simulacion de prueba)')
    pdf.save()
    return buffer.getvalue()


def post(client,path,csrf,data=None,files=None):
    payload=dict(data or {},csrf=csrf)
    return client.post(path,data=payload,files=files,follow_redirects=False)


def seed_lending(client,csrf):
    r=post(client,'/equipos',csrf,{'asset_tag':'MMG-001','serial_number':'SERIE-001','brand':'HP','model':'ProBook','accessories':'Cargador','condition_note':'Correcto'})
    assert r.status_code==303
    r=post(client,'/alumnos',csrf,{'student_ref':'AL-100','full_name':'Alumna Ejemplo','course_group':'1.º Gestión Administrativa','email':'alumna@example.edu'})
    assert r.status_code==303
    due=(date.today()+timedelta(days=200)).isoformat()
    r=post(client,'/prestamos',csrf,{'student_id':'1','device_id':'1','due_date':due,'purpose':'Estudio','delivery_condition':'Correcto'})
    assert r.status_code==303 and '/prestamos/1' in r.headers['location']


def test_complete_flow_and_archive(setup):
    client,app=setup;csrf=login(client)
    seed_lending(client,csrf)
    # A device cannot be loaned twice, even in preparation.
    assert client.get('/prestamos/nuevo').status_code==200
    with db(app.state.dbpath) as c:
        assert c.execute("SELECT status FROM devices WHERE id=1").fetchone()['status']=='reservado'
    # Must be signed, not simply PDF-generated.
    r=post(client,'/prestamos/1/activar',csrf,{'physical_delivery':'on'})
    assert 'Primero' in r.headers['location']
    assert post(client,'/prestamos/1/generar/contrato',csrf).status_code==303
    with db(app.state.dbpath) as c:
        row=c.execute('SELECT * FROM documents WHERE category=?',('contrato_generado',)).fetchone()
        assert row and row['sha256']
    doc_response=client.get('/documentos/1/descargar')
    assert doc_response.status_code==200 and doc_response.content.startswith(b'%PDF-')
    fake_pdf=valid_signed_pdf()
    r=post(client,'/prestamos/1/documentos',csrf,{'category':'contrato_firmado'},
           {'file':('firmado.pdf',io.BytesIO(fake_pdf),'application/pdf')})
    assert r.status_code==303
    assert post(client,'/prestamos/1/activar',csrf,{'physical_delivery':'on','two_copies_signed':'on','recipient_copy_delivered':'on','copy_recipient':'alumno'}).status_code==303
    with db(app.state.dbpath) as c:
        assert c.execute('SELECT state FROM loans WHERE id=1').fetchone()['state']=='activo'
        assert c.execute('SELECT status FROM devices WHERE id=1').fetchone()['status']=='prestado'
    assert post(client,'/prestamos/1/avisos',csrf,{'channel':'correo','recipient':'Familia','detail':'Mensaje enviado'}).status_code==303
    assert post(client,'/prestamos/1/devolver',csrf,{'condition':'Pantalla en buen estado','accessories':'Portátil y cargador','result':'correcto'}).status_code==303
    assert post(client,'/prestamos/1/generar/devolucion',csrf).status_code==303
    exported=client.get('/prestamos/1/expediente.zip')
    assert exported.status_code==200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        manifest=json.loads(z.read('MANIFIESTO.json'))
        assert manifest['case_id']==1
        assert len(manifest['documents'])==3
        for d in manifest['documents']:
            assert hashlib.sha256(z.read(d['zip_path'])).hexdigest()==d['sha256']
    with db(app.state.dbpath) as c:
        assert c.execute('SELECT state FROM loans WHERE id=1').fetchone()['state']=='devuelto'
        assert c.execute('SELECT status FROM devices WHERE id=1').fetchone()['status']=='disponible'
        assert verify_audit(c)[0]


def test_csrf_permissions_and_integrity(setup):
    client,app=setup;csrf=login(client)
    seed_lending(client,csrf)
    assert client.post('/prestamos/1/generar/contrato',data={'csrf':'invalido'}).status_code==403
    assert post(client,'/prestamos/1/documentos',csrf,{'category':'contrato_firmado'},
           {'file':('payload.txt',io.BytesIO(b'<script>danger</script>'),'text/plain')}).status_code==303
    with db(app.state.dbpath) as c:
        assert c.execute('SELECT COUNT(*) FROM documents').fetchone()[0]==0
    assert post(client,'/prestamos/1/generar/contrato',csrf).status_code==303
    with db(app.state.dbpath) as c: doc=c.execute('SELECT * FROM documents').fetchone()
    (app.state.base/'private_documents'/doc['stored_name']).write_bytes(b'TAMPERED')
    assert client.get('/documentos/1/descargar').status_code==409
    assert client.get('/prestamos/1/expediente.zip').status_code==409
    # A tutor assigned to a different teaching group must not see the loan.
    assert post(client,'/logout',csrf).status_code==303
    csrf_tutor=login(client,'tutor')
    assert client.get('/prestamos/1').status_code==404
    assert client.get('/documentos/1/descargar').status_code==404
    assert client.get('/usuarios').status_code==403
    assert post(client,'/prestamos/1/incidencias',csrf_tutor,{'kind':'uso','description':'No pertenece al grupo'}).status_code==404


def test_mandatory_guardian_and_cancellation(setup):
    client,app=setup;csrf=login(client)
    assert post(client,'/alumnos',csrf,{'student_ref':'M1','full_name':'Menor','course_group':'2º','minor':'on'}).status_code==303
    with db(app.state.dbpath) as c:assert c.execute('SELECT COUNT(*) FROM students').fetchone()[0]==0
    assert post(client,'/alumnos',csrf,{'student_ref':'M1','full_name':'Menor','course_group':'2º','minor':'on','guardian_name':'Representante Ejemplo','guardian_relation':'Madre con patria potestad'}).status_code==303
    post(client,'/equipos',csrf,{'asset_tag':'A1','serial_number':'S1','brand':'Lenovo','model':'ThinkPad'})
    due=(date.today()+timedelta(days=70)).isoformat()
    post(client,'/prestamos',csrf,{'student_id':'1','device_id':'1','due_date':due,'minor_data_reviewed':'on'})
    # Without guardian acknowledgement, activation must fail even with signed document.
    post(client,'/prestamos/1/documentos',csrf,{'category':'contrato_firmado'},
         {'file':('firmado.pdf',io.BytesIO(valid_signed_pdf()),'application/pdf')})
    r=post(client,'/prestamos/1/activar',csrf,{'physical_delivery':'on','two_copies_signed':'on','recipient_copy_delivered':'on','copy_recipient':'representante_legal'})
    assert 'menores' in r.headers['location']
    assert post(client,'/prestamos/1/anular',csrf,{'reason':'Entrega cancelada por traslado'}).status_code==303
    with db(app.state.dbpath) as c:
        assert c.execute('SELECT state FROM loans WHERE id=1').fetchone()['state']=='anulado'
        assert c.execute('SELECT status FROM devices WHERE id=1').fetchone()['status']=='disponible'
