"""Representatives, dual handwritten signatures and draft recipient guards."""
from datetime import date, timedelta
from email import policy
from email.parser import BytesParser
import io
import sqlite3
from fastapi.testclient import TestClient
from app.database import db, initialize
from app.main import create_app, PH, audit, utcnow
from app.followup import generate_followups
from tests.test_workflow import PASSWORD, login, post, valid_signed_pdf


def new_minor(client,csrf,authorized=True):
    student={
        'student_ref':'MIN-102', 'full_name':'Alumno menor de prueba',
        'course_group':'1.º GM', 'email':'menor@example.com',
        'minor':'on', 'guardian_name':'Representante del menor',
        'guardian_relation':'Madre con patria potestad',
        'guardian_email':'familia@example.org',
    }
    if authorized:student['guardian_contact_authorized']='on'
    assert post(client,'/alumnos',csrf,student).status_code==303
    assert post(client,'/equipos',csrf,{'asset_tag':'PC-102','serial_number':'S-102','brand':'HP','model':'ProBook'}).status_code==303
    due=(date.today()+timedelta(days=15)).isoformat()
    assert post(client,'/prestamos',csrf,{'student_id':'1','device_id':'1','due_date':due,'minor_data_reviewed':'on'}).status_code==303


def test_minor_document_guard_signatures_and_mail(tmp_path,monkeypatch):
    monkeypatch.setenv('PORTACUSTODIA_CORREO_ORIGEN','secretaria@canariaseducacion.es')
    app=create_app(tmp_path/'new',secure_cookie=False)
    with db(app.state.dbpath,write=True) as c:
        c.execute("INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)",
                  ('admin','Admin','admin',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        csrf=login(client)
        # Invalid family identification rejected.
        r=post(client,'/alumnos',csrf,{'student_ref':'INVALID','full_name':'Menor','course_group':'1.º GM','minor':'on','guardian_name':'Representante'})
        assert r.status_code==303
        with db(app.state.dbpath) as c:
            assert c.execute('SELECT COUNT(*) FROM students').fetchone()[0]==0
        new_minor(client,csrf)
        # Immutable data frozen on reservation.
        with db(app.state.dbpath) as c:
            row=c.execute('SELECT * FROM loans WHERE id=1').fetchone()
            assert row['minor_at_loan']==1 and row['guardian_email_at_loan']=='familia@example.org'
        assert post(client,'/prestamos/1/generar/contrato',csrf).status_code==303
        pdf=client.get('/documentos/1/descargar')
        assert pdf.status_code==200 and b'%PDF' in pdf.content[:10]
        import fitz
        text='\n'.join(p.get_text() for p in fitz.open(stream=pdf.content,filetype='pdf'))
        assert 'Firma manuscrita del alumno' in text
        assert 'Firma manuscrita del padre' in text
        assert 'Representante del menor' in text
        # Signed contract is required, but never alone sufficient.
        assert post(client,'/prestamos/1/activar',csrf,{'physical_delivery':'on'}).status_code==303
        assert post(client,'/prestamos/1/documentos',csrf,{'category':'contrato_firmado'},
              {'file':('contrato.pdf',io.BytesIO(valid_signed_pdf()),'application/pdf')}).status_code==303
        incomplete={'physical_delivery':'on','guardian_verified':'on','two_copies_signed':'on','recipient_copy_delivered':'on','copy_recipient':'representante_legal'}
        r=post(client,'/prestamos/1/activar',csrf,incomplete)
        assert r.status_code==303 and 'menores' in r.headers['location']
        valid={**incomplete,'two_copies_signed':'on','recipient_copy_delivered':'on','copy_recipient':'representante_legal','student_signature_verified':'on',
               'representation_method':'expediente_matricula','representative_role':'madre'}
        assert post(client,'/prestamos/1/activar',csrf,valid).status_code==303
        with db(app.state.dbpath,write=True) as c:
            r=c.execute('SELECT * FROM loans WHERE id=1').fetchone()
            assert r['representation_method']=='expediente_matricula'
            assert r['student_signature_checked']==1
            assert r['representation_verified_by'] is not None
            assert generate_followups(c,date.today(),audit,utcnow())==1
        draft=client.get('/agenda/1/borrador.eml')
        assert draft.status_code==200
        mail=BytesParser(policy=policy.default).parsebytes(draft.content)
        assert mail['From']=='secretaria@canariaseducacion.es'
        assert mail['To']=='familia@example.org'
        assert 'BORRADOR PENDIENTE' in mail.get_content()


def test_minor_email_not_prefilled_without_authorized_contact(tmp_path):
    app=create_app(tmp_path/'new',secure_cookie=False)
    with db(app.state.dbpath,write=True) as c:
        c.execute("INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)",
                  ('admin','Admin','admin',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        csrf=login(client)
        new_minor(client,csrf,authorized=False)
        with db(app.state.dbpath,write=True) as c:
            c.execute("UPDATE loans SET state='activo',activated_at=? WHERE id=1",(utcnow(),))
            c.execute("UPDATE devices SET status='prestado' WHERE id=1")
            assert generate_followups(c,date.today(),audit,utcnow())==1
        mail=BytesParser(policy=policy.default).parsebytes(client.get('/agenda/1/borrador.eml').content)
        assert mail['To'] is None


def test_migration_from_v021_preserves_students_and_loan(tmp_path):
    original=tmp_path/'legacy.sqlite3'
    # Create minimal old database then ensure normal initialization populates schema and migrations.
    c=sqlite3.connect(original)
    c.execute('CREATE TABLE students (id INTEGER PRIMARY KEY, student_ref TEXT UNIQUE, full_name TEXT, course_group TEXT, email TEXT, minor INTEGER, guardian_name TEXT, active INTEGER, created_at TEXT)')
    c.execute("INSERT INTO students VALUES (1,'L-1','Menor histórico','1.º GM','','1','Representante histórico',1,'2026-01-01')")
    c.commit();c.close()
    initialize(original)
    with db(original) as c:
        row=c.execute('SELECT * FROM students').fetchone()
        assert row['guardian_name']=='Representante histórico'
        assert row['guardian_email']==''
        assert row['guardian_contact_authorized']==0


def test_coming_of_age_preserves_loan_history(tmp_path):
    app=create_app(tmp_path/'data',secure_cookie=False)
    with db(app.state.dbpath,write=True) as c:
        c.execute("INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)",
                  ('admin','Admin','admin',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        csrf=login(client)
        new_minor(client,csrf)
        response=post(client,'/alumnos/mayoria-edad',csrf,{
            'student_id':'1','majority_verified':'on',
            'reason':'Mayoría de edad acreditada en registro institucional del centro'})
        assert response.status_code==303
        with db(app.state.dbpath) as c:
            s=c.execute('SELECT * FROM students WHERE id=1').fetchone()
            l=c.execute('SELECT * FROM loans WHERE id=1').fetchone()
            assert s['minor']==0 and s['guardian_name']==''
            assert l['minor_at_loan']==1 and l['guardian_name_at_loan']=='Representante del menor'
            assert c.execute('SELECT COUNT(*) FROM audit WHERE action="mayoria_edad_verificada"').fetchone()[0]==1
        detail=client.get('/prestamos/1')
        assert detail.status_code==200
        assert 'Representante del menor' in detail.text
        with db(app.state.dbpath,write=True) as c:
            c.execute("UPDATE loans SET state='activo',activated_at=? WHERE id=1",(utcnow(),))
            c.execute("UPDATE devices SET status='prestado' WHERE id=1")
            assert generate_followups(c,date.today(),audit,utcnow())==1
        mail=BytesParser(policy=policy.default).parsebytes(client.get('/agenda/1/borrador.eml').content)
        assert mail['To']=='menor@example.com'  # The former minor now gets their own correspondence.
