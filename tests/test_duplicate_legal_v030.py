"""Version 0.3: print two complete signed copies and test custody before activation."""
from datetime import date, timedelta
from pathlib import Path
import io
import os
import fitz
import pytest
from fastapi.testclient import TestClient
from app.database import db, initialize
from app.documents import make_pdf
from app.main import create_app, PH, verify_audit
from tests.test_workflow import PASSWORD, login, post, seed_lending, valid_signed_pdf
from tests.test_minors_v022 import new_minor


def sample_loan(minor=False):
    return dict(id=33,student_name='Alumna ficticia',student_ref='FICTICIA-1',course_group='1.° GM',
        minor=int(minor),guardian_name='Representante ficticio' if minor else '',
        guardian_relation='Madre con patria potestad' if minor else '',brand='HP',model='ProBook',
        asset_tag='FICTICIO-001',serial_number='DEMO-00001',accessories='Portátil y cargador',
        due_date='2027-06-20',purpose='Aprendizaje',delivery_condition='Buen estado',condition_note='',
        closed_at='2027-06-20',return_condition='Correcto',return_accessories='Cargador',return_result='correcto')


@pytest.mark.parametrize('minor', [False, True])
@pytest.mark.parametrize('kind', ['contrato','devolucion','requerimiento'])
def test_each_document_has_two_complete_separately_signable_copies(kind,minor):
    b=make_pdf(kind,sample_loan(minor),'01/11/2026 14:00')
    doc=fitz.open(stream=b,filetype='pdf')
    parts=[];current=[];part_ids=[]
    for page in doc:
        txt=page.get_text()
        # A given page belongs to one (and only one) exemplar.
        assert ('EJEMPLAR 1 DE 2' in txt) != ('EJEMPLAR 2 DE 2' in txt)
        identifier=1 if 'EJEMPLAR 1 DE 2' in txt else 2
        if part_ids and identifier!=part_ids[-1]:
            parts.append(' '.join(current));current=[]
        part_ids.append(identifier);current.append(txt)
        for bb in page.get_text('blocks'):
            # No content should reach beyond the physical A4 page.
            assert 0 <= bb[0] < bb[2] <= page.rect.width-15
            assert 0 <= bb[1] < bb[3] <= page.rect.height-15
    parts.append(' '.join(current))
    assert len(parts)==2 and part_ids == sorted(part_ids)
    for piece in parts:
        assert 'Alumna ficticia' in piece
        assert 'FICTICIO-001' in piece
        if kind=='contrato':
            assert '114/2011' in piece and '1746' in piece
            assert 'Firma manuscrita del alumno' in piece
            assert 'protección de datos' in piece
            if minor:
                assert 'Firma manuscrita del padre' in piece
                assert 'Autorización del representante legal' in piece
                assert '1903' in piece
        elif kind=='devolucion':
            assert 'Firma de la persona que devuelve' in piece
            assert 'Firma de la persona receptora' in piece
        else:
            assert 'Firma y constancia de comunicación' in piece


def test_do_not_activate_without_two_signed_originals_and_copy_given(tmp_path):
    app=create_app(tmp_path/'test',secure_cookie=False)
    with db(app.state.dbpath,True) as c:
        c.execute('INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)',
                  ('admin','Secretaría de prueba','admin',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        csrf=login(client);seed_lending(client,csrf)
        post(client,'/prestamos/1/documentos',csrf,{'category':'contrato_firmado'},
             {'file':('firmado.pdf',io.BytesIO(valid_signed_pdf()),'application/pdf')})
        incomplete={'physical_delivery':'on','two_copies_signed':'on'}
        assert 'dos+copias' in post(client,'/prestamos/1/activar',csrf,incomplete).headers['location']
        with db(app.state.dbpath) as c:assert c.execute('SELECT state FROM loans WHERE id=1').fetchone()['state']=='preparado'
        valid={**incomplete,'recipient_copy_delivered':'on','copy_recipient':'alumno'}
        assert post(client,'/prestamos/1/activar',csrf,valid).status_code==303
        with db(app.state.dbpath) as c:
            row=c.execute('SELECT * FROM loans WHERE id=1').fetchone()
            assert row['state']=='activo'
            assert row['two_copies_checked_by'] and row['two_copies_checked_at']
            assert row['copy_recipient']=='alumno'
            assert verify_audit(c)[0]


def test_return_documents_remain_pending_until_signed_copies_confirmed(tmp_path):
    app=create_app(tmp_path/'test',secure_cookie=False)
    with db(app.state.dbpath,True) as c:
        c.execute('INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)',
                  ('admin','Secretaría de prueba','admin',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        csrf=login(client);seed_lending(client,csrf)
        post(client,'/prestamos/1/documentos',csrf,{'category':'contrato_firmado'},
             {'file':('firmado.pdf',io.BytesIO(valid_signed_pdf()),'application/pdf')})
        valid={'physical_delivery':'on','two_copies_signed':'on','recipient_copy_delivered':'on','copy_recipient':'alumno'}
        post(client,'/prestamos/1/activar',csrf,valid)
        post(client,'/prestamos/1/devolver',csrf,{'condition':'Buen estado','accessories':'Cargador y portátil','result':'correcto'})
        assert 'cierre documental' in client.get('/prestamos/1').text.lower()
        data={'return_two_copies_signed':'on','return_copy_delivered':'on','return_copy_recipient':'alumno'}
        r=post(client,'/prestamos/1/cerrar-documentacion',csrf,data)
        assert 'archivarse+primero' in r.headers['location']
        post(client,'/prestamos/1/documentos',csrf,{'category':'acta_devolucion_firmada'},
             {'file':('recepcion.pdf',io.BytesIO(valid_signed_pdf()),'application/pdf')})
        assert post(client,'/prestamos/1/cerrar-documentacion',csrf,data).status_code==303
        with db(app.state.dbpath) as c:
            row=c.execute('SELECT * FROM loans WHERE id=1').fetchone()
            assert row['state']=='devuelto' and row['return_copies_checked_at']
            assert row['return_copy_recipient']=='alumno' and verify_audit(c)[0]
        assert 'Cierre documental completado' in client.get('/prestamos/1').text


def test_legal_notice_is_required_in_server_production_mode(tmp_path,monkeypatch):
    monkeypatch.setenv('PORTACUSTODIA_REQUIRE_LEGAL_CONFIG','1')
    with pytest.raises(ValueError,match='Configurar responsable'):
        make_pdf('contrato',sample_loan(), '01/11/2026')
    for name,value in {'RESPONSABLE_DATOS':'Órgano responsable verificado',
                       'CONTACTO_DPD':'dpd@example.org','PRIVACIDAD_URL':'https://example.org/privacidad',
                       'RETENCION':'Plazo aprobado con revisión periódica'}.items():
        monkeypatch.setenv('PORTACUSTODIA_'+name,value)
    pdf=make_pdf('contrato',sample_loan(),'01/11/2026')
    assert pdf.startswith(b'%PDF-')
