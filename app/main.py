"""PortaCustodia: controlled loans, records, authenticated custody and auditability.

This software is intended for deployment within the school's authorised infrastructure.
"""
import csv
from email.message import EmailMessage
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher, exceptions as argon_exc
from pypdf import PdfReader
from PIL import Image, ImageOps, UnidentifiedImageError
try:
    from pyzbar.pyzbar import decode as decode_barcodes
except (ImportError,OSError):
    decode_barcodes=None
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .database import initialize, db
from .documents import make_pdf
from .custody import key_from_environment, encrypt_document, document_bytes
from .followup import generate_followups, STAGES
from .contact import configured_sender, valid_staff_email, OFFICIAL_DOMAIN

ROOT=Path(__file__).resolve().parent
LOCAL_TZ=ZoneInfo('Atlantic/Canary')
MAX_UPLOAD=10*1024*1024
MAX_FORM=11*1024*1024
PH=PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
ROLES=('admin','secretaria','tic','tutor','gestor','consulta')
WRITE_LOAN=('admin','secretaria','gestor')
DOC_CATEGORIES={
 'contrato_firmado':'Compromiso de préstamo firmado',
 'autorizacion_representante':'Autorización de representante',
 'acta_devolucion_firmada':'Acta de devolución firmada',
 'acuse_requerimiento':'Acuse o evidencia de notificación',
 'incidencia':'Informe o justificante de incidencia',
 'otro':'Otro documento del expediente',
 'contrato_generado':'Contrato preparado para firma',
 'devolucion_generada':'Acta preparada para firma',
 'requerimiento_generado':'Requerimiento preparado',
}


def utcnow(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def today(): return datetime.now(LOCAL_TZ).date().isoformat()
def show_date(dt):
    if not dt:return '—'
    try:return datetime.fromisoformat(dt).astimezone(LOCAL_TZ).strftime('%d/%m/%Y %H:%M')
    except ValueError:return dt

def trim(s,n=300):return str(s or '').strip()[:n]
def go(path, msg=None, error=False):
    if msg:path += ('&' if '?' in path else '?')+urlencode({'error' if error else 'ok':msg})
    return RedirectResponse(path,status_code=303)

def audit(c,user_id,action,subject,subject_id,payload=None):
    last=c.execute('SELECT event_hash FROM audit ORDER BY id DESC LIMIT 1').fetchone()
    prev=last['event_hash'] if last else '0'*64
    at=utcnow(); data=json.dumps(payload or {},ensure_ascii=False,sort_keys=True,separators=(',',':'))
    body='|'.join([prev,at,str(user_id or 0),action,subject,str(subject_id),data])
    digest=hashlib.sha256(body.encode()).hexdigest()
    c.execute('INSERT INTO audit(at,user_id,action,subject_type,subject_id,payload,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)',
              (at,user_id,action,subject,subject_id,data,prev,digest))


def verify_audit(c):
    prev='0'*64
    for row in c.execute('SELECT * FROM audit ORDER BY id'):
        content='|'.join([prev,row['at'],str(row['user_id'] or 0),row['action'],row['subject_type'],str(row['subject_id']),row['payload']])
        if row['previous_hash']!=prev or not hmac.compare_digest(row['event_hash'],hashlib.sha256(content.encode()).hexdigest()):
            return False,row['id']
        prev=row['event_hash']
    return True,None


def create_app(data_dir=None, secure_cookie=None):
    base=Path(data_dir or os.environ.get('PORTACUSTODIA_DATA','./data')).resolve()
    (base/'private_documents').mkdir(parents=True,exist_ok=True)
    try:os.chmod(base,0o700);os.chmod(base/'private_documents',0o700)
    except OSError:pass
    dbpath=base/'portacustodia.sqlite3'
    initialize(dbpath)
    key=key_from_environment()
    if os.environ.get('PORTACUSTODIA_REQUIRE_ENCRYPTION','0')=='1' and key is None:
        raise RuntimeError('Se exige cifrado pero falta PORTACUSTODIA_KEY_FILE.')
    if secure_cookie is None:secure_cookie=os.environ.get('PORTACUSTODIA_SECURE_COOKIE','1')!='0'
    sender_email=configured_sender()
    app=FastAPI(title='PortaCustodia · IES MMG',docs_url=None,redoc_url=None,openapi_url=None)
    app.mount('/static',StaticFiles(directory=str(ROOT/'static')),name='static')
    app.state.dbpath=dbpath; app.state.base=base;app.state.secure_cookie=secure_cookie;app.state.custody_key=key; app.state.sender_email=sender_email
    env=Environment(loader=FileSystemLoader(str(ROOT/'templates')),autoescape=select_autoescape(['html','xml']))
    env.filters['fecha']=show_date
    env.filters['estado']=lambda s: {'preparado':'Pendiente de firma','activo':'En préstamo','devuelto':'Devuelto','anulado':'Anulado'}.get(s,s)
    env.filters['tipo_doc']=lambda s:DOC_CATEGORIES.get(s,s)
    env.globals['hoy']=today

    def conn(request, write=False):return db(request.app.state.dbpath,write=write)

    @app.middleware('http')
    async def security_headers(request,call_next):
        # Auth and CSRF are applied at individual route entry points.
        if request.headers.get('content-length'):
            try:
                if int(request.headers['content-length'])>MAX_FORM:
                    return Response('El archivo supera el tamaño permitido.',status_code=413)
            except ValueError:return Response(status_code=400)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; worker-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
        response.headers['Permissions-Policy']='camera=(self), microphone=(), geolocation=()'
        return response

    def current(request):
        token=request.cookies.get('pc_session','')
        if len(token)<30:return None
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        with conn(request) as c:
            row=c.execute('''SELECT u.*,s.csrf,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND u.active=1 AND s.expires_at>?''',(token_hash,utcnow())).fetchone()
            return dict(row) if row else None

    def authenticated(request,roles=None,allow_change=False):
        u=current(request)
        if u is None:return None,go('/login')
        if u['must_change'] and not allow_change:return u,go('/mi-clave?error=Debes+cambiar+tu+clave+temporal')
        if roles and u['role'] not in roles:return u,Response('No tiene permisos para esta operación.',status_code=403)
        return u,None

    async def posted(request,user):
        form=await request.form(max_files=2,max_fields=40,max_part_size=MAX_UPLOAD)
        if not hmac.compare_digest(str(form.get('csrf','')),user['csrf']):
            return None,Response('Validación CSRF incorrecta.',status_code=403)
        return form,None

    def page(request,name,user=None,**kwargs):
        values={'request':request,'user':user,'today':today(),'ok':request.query_params.get('ok'),
                'error':request.query_params.get('error'),'categories':DOC_CATEGORIES,'roles':ROLES,
                'sender_email':request.app.state.sender_email,'official_domain':OFFICIAL_DOMAIN,**kwargs}
        return HTMLResponse(env.get_template(name).render(**values))

    def scoped_clause(user,alias='l'):
        return (f' AND s.course_group = ? ',[user['tutor_group']]) if user['role'] in ('tutor','gestor') else ('',[])

    def loan_record(c,loan_id):
        return c.execute('''SELECT l.*,s.full_name AS student_name,s.student_ref,s.course_group,s.email,
           COALESCE(l.minor_at_loan,s.minor) AS minor,
           COALESCE(l.guardian_name_at_loan,s.guardian_name) AS guardian_name,
           COALESCE(l.guardian_relation_at_loan,s.guardian_relation) AS guardian_relation,
           COALESCE(l.guardian_email_at_loan,s.guardian_email) AS guardian_email,
           l.guardian_contact_authorized_at_loan AS guardian_contact_authorized,
           d.asset_tag,d.serial_number,d.brand,d.model,d.accessories,d.condition_note,d.status AS device_status
           FROM loans l JOIN students s ON s.id=l.student_id JOIN devices d ON d.id=l.device_id WHERE l.id=?''',(loan_id,)).fetchone()

    def allowed_record(u,row):
        return row is not None and (u['role'] not in ('tutor','gestor') or row['course_group']==u['tutor_group'])

    def store_file(request,c,loan_id,user_id,category,content,name,mime,generated=False):
        if len(content)>MAX_UPLOAD or not content:raise ValueError('Tamaño de documento no admitido.')
        if mime=='application/pdf':
            if not content.startswith(b'%PDF-'):raise ValueError('El archivo no es un PDF válido.')
            try:
                reader=PdfReader(io.BytesIO(content),strict=True)
                if reader.is_encrypted or len(reader.pages)<1 or len(reader.pages)>100:
                    raise ValueError('El PDF está cifrado, no contiene páginas o supera 100 páginas.')
                # Force basic parsing now, before accepting the document as evidence.
                for page in reader.pages: _=page.mediabox
            except ValueError:raise
            except Exception as exc:raise ValueError('El PDF no se puede interpretar. Digitalice de nuevo el documento firmado.') from exc
            ext='pdf'
        elif mime=='image/jpeg':
            if not content.startswith(b'\xff\xd8\xff'):raise ValueError('Imagen JPEG inválida.')
            ext='jpg'
        elif mime=='image/png':
            if not content.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Imagen PNG inválida.')
            ext='png'
        else:raise ValueError('Únicamente se admiten PDF, JPG y PNG.')
        digest=hashlib.sha256(content).hexdigest()
        filename=f'{uuid.uuid4().hex}.{ext}'
        target=request.app.state.base/'private_documents'/filename
        encrypted='aes256gcm' if request.app.state.custody_key else 'none'
        stored=encrypt_document(content,filename,request.app.state.custody_key) if encrypted=='aes256gcm' else content
        with target.open('xb') as f:
            f.write(stored);f.flush();os.fsync(f.fileno())
        os.chmod(target,0o600)
        c.execute('''INSERT INTO documents(loan_id,created_by,created_at,category,original_name,stored_name,media_type,sha256,size_bytes,generated,encryption)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(loan_id,user_id,utcnow(),category,trim(name,180),filename,mime,digest,len(content),int(generated),encrypted))
        doc_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
        audit(c,user_id,'documento_archivado','documento',doc_id,{'loan_id':loan_id,'category':category,'sha256':digest,'size':len(content)})
        return doc_id

    def photo_access(u, photo, c):
        if u['role']=='consulta':return False
        if u['role'] in ('admin','secretaria','tic'):return True
        if photo['loan_id'] is None:return False
        loan=loan_record(c,photo['loan_id'])
        return allowed_record(u,loan)

    def photo_upload_permission(u, c, device_id, loan_id):
        device=c.execute('SELECT * FROM devices WHERE id=?',(device_id,)).fetchone()
        if not device:return None, Response(status_code=404)
        if loan_id is None:
            if u['role'] not in ('admin','secretaria','tic'):return None,Response(status_code=403)
            return device,None
        loan=loan_record(c,loan_id)
        if not allowed_record(u,loan) or loan['device_id']!=device_id:return None,Response(status_code=404)
        return device,None

    @app.get('/manifest.webmanifest')
    def manifest():
        return Response((ROOT/'static/manifest.webmanifest').read_bytes(),media_type='application/manifest+json')

    @app.get('/sw.js')
    def service_worker():
        return Response((ROOT/'static/sw.js').read_bytes(),media_type='text/javascript',headers={'Service-Worker-Allowed':'/','Cache-Control':'no-store'})

    @app.get('/movil')
    def mobile(request:Request):
        u,fail=authenticated(request)
        if fail:return fail
        with conn(request) as c:
            clause,args=scoped_clause(u)
            loans=c.execute('''SELECT l.id,l.state,l.due_date,d.asset_tag,d.serial_number,d.id AS device_id,
                s.full_name AS student_name,s.course_group FROM loans l JOIN devices d ON d.id=l.device_id
                JOIN students s ON s.id=l.student_id WHERE l.state IN ('activo','preparado')'''+clause+''' ORDER BY l.due_date LIMIT 50''',args).fetchall()
        return page(request,'mobile.html',u,loans=loans)

    @app.get('/api/equipos/buscar')
    def device_scan_lookup(request:Request,codigo:str=''):
        u,fail=authenticated(request)
        if fail:return fail
        value=trim(codigo,110)
        # Only exact matches; never infer that a manufacturer barcode equals its S/N.
        if not value:return JSONResponse({'found':False},status_code=400)
        with conn(request) as c:
            device=c.execute('SELECT * FROM devices WHERE serial_number=? COLLATE NOCASE OR asset_tag=? COLLATE NOCASE',(value,value)).fetchone()
            if device is None:return {'found':False}
            # A device record does not itself reveal borrower identities.
            response={'found':True,'id':device['id'],'asset_tag':device['asset_tag'],'serial_number':device['serial_number'],
                'brand':device['brand'],'model':device['model'],'status':device['status']}
            return response

    @app.post('/api/equipos/decodificar-codigo')
    async def decode_barcode_photo(request:Request):
        u,fail=authenticated(request)
        if fail:return fail
        form,fail=await posted(request,u)
        if fail:return fail
        if decode_barcodes is None:
            return JSONResponse({'error':'El servidor no tiene instalado el motor de lectura de códigos.'},status_code=503)
        file=form.get('photo')
        if file is None or not hasattr(file,'read'):
            return JSONResponse({'error':'Adjunte una imagen.'},status_code=400)
        data=await file.read(6*1024*1024+1)
        if len(data)>6*1024*1024 or not data:return JSONResponse({'error':'Imagen vacía o mayor de 6 MB.'},status_code=413)
        try:
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in ('JPEG','PNG','WEBP') or original.width*original.height>20_000_000:
                    raise ValueError()
                oriented=ImageOps.exif_transpose(original).convert('RGB')
                oriented.thumbnail((2200,2200),Image.Resampling.LANCZOS)
                found=decode_barcodes(oriented)
        except (ValueError,UnidentifiedImageError,OSError,Image.DecompressionBombError):
            return JSONResponse({'error':'Imagen no válida o resolución excesiva.'},status_code=400)
        # Do not log, store or cache input photographs. Return only the barcode text.
        values=[]
        for item in found[:6]:
            value=item.data.decode('utf-8','replace').strip()
            if value and len(value)<=110 and all(ord(char)>=32 for char in value):
                values.append({'value':value,'format':item.type})
        return JSONResponse({'codes':values},headers={'Cache-Control':'no-store'})

    @app.get('/equipos/{device_id}')
    def device_detail(request:Request,device_id:int):
        u,fail=authenticated(request)
        if fail:return fail
        with conn(request) as c:
            device=c.execute('SELECT * FROM devices WHERE id=?',(device_id,)).fetchone()
            if device is None:return Response(status_code=404)
            loans=c.execute('''SELECT l.id,l.state,l.due_date,s.course_group,s.full_name AS student_name
                FROM loans l JOIN students s ON s.id=l.student_id WHERE l.device_id=?
                ORDER BY l.id DESC LIMIT 30''',(device_id,)).fetchall()
            loans=[r for r in loans if u['role'] not in ('tutor','gestor') or r['course_group']==u['tutor_group']]
            photo_rows=c.execute('SELECT * FROM device_photos WHERE device_id=? ORDER BY id DESC',(device_id,)).fetchall()
            photos=[r for r in photo_rows if photo_access(u,r,c)]
            # Restricted staff do not receive the technical history of unrelated borrowed equipment.
        return page(request,'device_detail.html',u,device=device,loans=loans,photos=photos)

    @app.post('/equipos/{device_id}/fotos')
    async def device_photo_add(request:Request,device_id:int):
        u,fail=authenticated(request,('admin','secretaria','tic','tutor','gestor'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        category=trim(f.get('category'),20)
        if category not in ('inventario','entrega','revision','devolucion','incidencia'):
            return Response('Categoría de fotografía inválida.',status_code=400)
        note=trim(f.get('note'),500)
        if len(note)<4:return go(f'/equipos/{device_id}','Incluya una breve descripción del estado observado.',True)
        try:loan_id=int(f.get('loan_id')) if f.get('loan_id') else None
        except (ValueError,TypeError):return Response(status_code=400)
        upload=f.get('photo')
        if upload is None or not hasattr(upload,'read'):return go(f'/equipos/{device_id}','Seleccione una fotografía.',True)
        content=await upload.read(MAX_UPLOAD+1)
        if len(content)>MAX_UPLOAD:return go(f'/equipos/{device_id}','La imagen supera 10 MB.',True)
        try:
            if not content:raise ValueError('Imagen vacía.')
            with Image.open(io.BytesIO(content)) as img:
                if img.format not in ('JPEG','PNG','WEBP'):raise ValueError('Solo se admiten fotografías JPEG, PNG o WebP.')
                if img.width*img.height>25_000_000:raise ValueError('Resolución excesiva (máximo 25 MP).')
                img=ImageOps.exif_transpose(img)
                img.thumbnail((2400,2400),Image.Resampling.LANCZOS)
                if img.mode!='RGB':img=img.convert('RGB')
                output=io.BytesIO();img.save(output,format='JPEG',quality=86,optimize=True)
                data=output.getvalue();width,height=img.size
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError) as exc:
            return go(f'/equipos/{device_id}','Fotografía inválida o excesivamente grande.',True)
        # JPEG is normalized and EXIF/GPS removed to avoid collecting geolocation.
        name=uuid.uuid4().hex+'.jpg'
        with conn(request,True) as c:
            device,fail=photo_upload_permission(u,c,device_id,loan_id)
            if fail:return fail
            if u['role'] in ('tutor','gestor') and (loan_id is None or category=='inventario'):
                return Response('La fotografía docente debe vincularse a un préstamo del grupo.',status_code=403)
            file_count=c.execute('SELECT COUNT(*) FROM device_photos WHERE loan_id=?',(loan_id,)).fetchone()[0] if loan_id else 0
            if loan_id and file_count>=50:return go(f'/equipos/{device_id}','Límite de 50 fotografías por préstamo.',True)
            stored=encrypt_document(data,name,request.app.state.custody_key) if request.app.state.custody_key else data
            target=request.app.state.base/'private_documents'/name
            with target.open('xb') as stream:
                stream.write(stored);stream.flush();os.fsync(stream.fileno())
            os.chmod(target,0o600)
            c.execute('''INSERT INTO device_photos(device_id,loan_id,created_by,created_at,category,note,original_name,stored_name,
                 media_type,sha256,size_bytes,width,height,encryption) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (device_id,loan_id,u['id'],utcnow(),category,note,trim(upload.filename,160) or 'captura_movil.jpg',name,
                'image/jpeg',hashlib.sha256(data).hexdigest(),len(data),width,height,'aes256gcm' if request.app.state.custody_key else 'none'))
            pid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            audit(c,u['id'],'fotografia_equipo_archivada','foto',pid,{'device_id':device_id,'loan_id':loan_id,
                 'category':category,'sha256':hashlib.sha256(data).hexdigest(),'note':note})
        return go(f'/equipos/{device_id}','Fotografía archivada con fecha, autor y huella de integridad.')

    @app.get('/fotos/{photo_id}')
    def device_photo_view(request:Request,photo_id:int):
        u,fail=authenticated(request)
        if fail:return fail
        with conn(request) as c:
            photo=c.execute('SELECT * FROM device_photos WHERE id=?',(photo_id,)).fetchone()
            if photo is None or not photo_access(u,photo,c):return Response(status_code=404)
        path=request.app.state.base/'private_documents'/photo['stored_name']
        if not path.is_file():return Response('Imagen no disponible.',status_code=503)
        try:content=document_bytes(path,photo,request.app.state.custody_key)
        except Exception:return Response('Error al verificar la integridad de la fotografía.',status_code=409)
        with conn(request,True) as c:audit(c,u['id'],'fotografia_consultada','foto',photo_id)
        return Response(content,media_type='image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

    @app.get('/salud')
    def health():return {'estado':'ok','aplicacion':'PortaCustodia'}

    @app.get('/')
    def root():return go('/panel')

    @app.get('/login')
    def login_view(request:Request):
        if current(request):return go('/panel')
        return page(request,'login.html')

    @app.post('/login')
    async def login_post(request:Request):
        form=await request.form()
        username=trim(form.get('username'),100).lower()
        password=str(form.get('password',''))
        ip=request.client.host if request.client else 'unknown'
        ip_hash=hashlib.sha256((ip+os.environ.get('PORTACUSTODIA_RATE_SALT','school-login')).encode()).hexdigest()
        with conn(request,write=True) as c:
            recent=c.execute('''SELECT COUNT(*) FROM login_attempts WHERE username=? AND ip_hash=? AND successful=0 AND created_at > ?''',
                           (username,ip_hash,(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat())).fetchone()[0]
            if recent>=7:return go('/login','Demasiados intentos. Prueba dentro de 15 minutos.',True)
            row=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
            valid=False
            if row:
                try:valid=PH.verify(row['password_hash'],password)
                except (argon_exc.VerifyMismatchError,argon_exc.VerificationError,argon_exc.InvalidHashError):pass
            c.execute('INSERT INTO login_attempts(username,ip_hash,created_at,successful) VALUES(?,?,?,?)',
                      (username,ip_hash,utcnow(),int(valid)))
            if not valid:return go('/login','Credenciales incorrectas.',True)
            token=secrets.token_urlsafe(48); csrf=secrets.token_urlsafe(32)
            expire=(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()
            c.execute('INSERT INTO sessions(token_hash,user_id,csrf,created_at,expires_at) VALUES(?,?,?,?,?)',
                      (hashlib.sha256(token.encode()).hexdigest(),row['id'],csrf,utcnow(),expire))
            audit(c,row['id'],'inicio_sesion','usuario',row['id'])
        response=go('/mi-clave' if row['must_change'] else '/panel')
        response.set_cookie('pc_session',token,max_age=8*3600,httponly=True,secure=request.app.state.secure_cookie,samesite='lax',path='/')
        return response

    @app.post('/logout')
    async def logout(request:Request):
        u,fail=authenticated(request,allow_change=True)
        if fail:return fail
        form,fail=await posted(request,u)
        if fail:return fail
        with conn(request,write=True) as c:
            c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(request.cookies['pc_session'].encode()).hexdigest(),))
            audit(c,u['id'],'cierre_sesion','usuario',u['id'])
        response=go('/login','Sesión cerrada.');response.delete_cookie('pc_session',path='/')
        return response

    @app.get('/mi-clave')
    def account(request:Request):
        u,fail=authenticated(request,allow_change=True)
        if fail:return fail
        return page(request,'account.html',u)

    @app.post('/mi-clave')
    async def account_post(request:Request):
        u,fail=authenticated(request,allow_change=True)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        current_password=str(f.get('current',''));new=str(f.get('new',''))
        if len(new)<12 or len(new)>128:return go('/mi-clave','La nueva clave debe contener de 12 a 128 caracteres.',True)
        try:PH.verify(u['password_hash'],current_password)
        except (argon_exc.VerifyMismatchError,argon_exc.VerificationError):return go('/mi-clave','La contraseña actual no es correcta.',True)
        with conn(request,write=True) as c:
            c.execute('UPDATE users SET password_hash=?,must_change=0 WHERE id=?',(PH.hash(new),u['id']))
            c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash!=?',(u['id'],hashlib.sha256(request.cookies['pc_session'].encode()).hexdigest()))
            audit(c,u['id'],'cambio_clave','usuario',u['id'])
        return go('/panel','Contraseña actualizada.')

    @app.get('/panel')
    def dashboard(request:Request):
        u,fail=authenticated(request)
        if fail:return fail
        with conn(request) as c:
            clause,args=scoped_clause(u)
            stats={}
            for key,state in [('preparados','preparado'),('activos','activo'),('devueltos','devuelto')]:
                stats[key]=c.execute('''SELECT COUNT(*) FROM loans l JOIN students s ON s.id=l.student_id
                  WHERE l.state=?'''+clause,[state]+args).fetchone()[0]
            stats['vencidos']=c.execute('''SELECT COUNT(*) FROM loans l JOIN students s ON s.id=l.student_id
               WHERE l.state='activo' AND l.due_date<?'''+clause,[today()]+args).fetchone()[0]
            stats['cierres_pendientes']=c.execute('''SELECT COUNT(*) FROM loans l JOIN students s ON s.id=l.student_id
                WHERE l.state='devuelto' AND l.return_copies_checked_at IS NULL'''+clause,args).fetchone()[0]
            stats['equipos']=c.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
            loans=c.execute('''SELECT l.id,l.state,l.due_date,s.full_name student_name,s.course_group,d.asset_tag
                FROM loans l JOIN students s ON s.id=l.student_id JOIN devices d ON d.id=l.device_id
                WHERE l.state IN ('preparado','activo')'''+clause+''' ORDER BY CASE WHEN l.state='activo' AND l.due_date<? THEN 0 ELSE 1 END,l.due_date LIMIT 14''',args+[today()]).fetchall()
        return page(request,'dashboard.html',u,stats=stats,loans=loans)

    @app.get('/equipos')
    def devices(request:Request):
        u,fail=authenticated(request)
        if fail:return fail
        with conn(request) as c:
            rows=c.execute('SELECT * FROM devices ORDER BY asset_tag').fetchall()
        return page(request,'devices.html',u,rows=rows)

    @app.post('/equipos')
    async def device_add(request:Request):
        u,fail=authenticated(request,('admin','tic','secretaria'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        asset,serial=trim(f.get('asset_tag'),70),trim(f.get('serial_number'),100)
        brand,model=trim(f.get('brand'),90),trim(f.get('model'),90)
        if not all((asset,serial,brand,model)):return go('/equipos','Rellena los datos obligatorios.',True)
        try:
            with conn(request,True) as c:
                c.execute('INSERT INTO devices(asset_tag,serial_number,brand,model,accessories,condition_note) VALUES(?,?,?,?,?,?)',
                          (asset,serial,brand,model,trim(f.get('accessories'),500),trim(f.get('condition_note'),600)))
                did=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                audit(c,u['id'],'equipo_alta','equipo',did,{'asset':asset,'serial':serial})
        except sqlite3.IntegrityError:return go('/equipos','Inventario o número de serie ya registrado.',True)
        return go('/equipos','Equipo incorporado al inventario.')

    @app.post('/equipos/{device_id}/estado')
    async def device_status(request:Request,device_id:int):
        u,fail=authenticated(request,('admin','tic'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        status=trim(f.get('status'),30)
        if status not in ('disponible','revision','baja'):return Response(status_code=400)
        with conn(request,True) as c:
            row=c.execute('SELECT status FROM devices WHERE id=?',(device_id,)).fetchone()
            if not row:return Response(status_code=404)
            if row['status'] in ('reservado','prestado'):return go('/equipos','No se puede cambiar el estado de un equipo con expediente abierto.',True)
            c.execute('UPDATE devices SET status=? WHERE id=?',(status,device_id))
            audit(c,u['id'],'equipo_estado','equipo',device_id,{'old':row['status'],'new':status})
        return go('/equipos','Estado del equipo actualizado.')

    @app.get('/alumnos')
    def students(request:Request):
        u,fail=authenticated(request,('admin','secretaria','consulta'))
        if fail:return fail
        with conn(request) as c:rows=c.execute('SELECT * FROM students ORDER BY full_name').fetchall()
        return page(request,'students.html',u,rows=rows)

    @app.post('/alumnos')
    async def student_add(request:Request):
        u,fail=authenticated(request,('admin','secretaria'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        ref=trim(f.get('student_ref'),70);name=trim(f.get('full_name'),150);group=trim(f.get('course_group'),100)
        minor=int(str(f.get('minor',''))=='on');guardian=trim(f.get('guardian_name'),150)
        relation=trim(f.get('guardian_relation'),80)
        guardian_email=trim(f.get('guardian_email'),150).lower()
        guardian_contact_authorized=int(str(f.get('guardian_contact_authorized',''))=='on')
        email=trim(f.get('email'),150)
        email_pattern=r'[^\s@]+@[^\s@]+\.[^\s@]+'
        if not all((ref,name,group)) or (minor and (not guardian or not relation)):
            return go('/alumnos','Para menores, identifica al representante y su relación jurídica.',True)
        if email and not re.fullmatch(email_pattern,email):return go('/alumnos','Correo del alumno no válido.',True)
        if guardian_email and not re.fullmatch(email_pattern,guardian_email):return go('/alumnos','Correo familiar no válido.',True)
        if guardian_contact_authorized and (not minor or not guardian_email):
            return go('/alumnos','La dirección familiar debe constar y ser válida antes de habilitar su uso en borradores.',True)
        if not minor:
            guardian='';relation='';guardian_email='';guardian_contact_authorized=0
        try:
            with conn(request,True) as c:
                c.execute('''INSERT INTO students(student_ref,full_name,course_group,email,minor,guardian_name,guardian_relation,guardian_email,guardian_contact_authorized)
                    VALUES(?,?,?,?,?,?,?,?,?)''',(ref,name,group,email,minor,guardian,relation,guardian_email,guardian_contact_authorized))
                sid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                audit(c,u['id'],'alumno_alta','alumno',sid,{'reference':ref,'group':group,'minor':minor})
        except sqlite3.IntegrityError:return go('/alumnos','La referencia del alumno ya está registrada.',True)
        return go('/alumnos','Alumno/a dado de alta.')

    @app.post('/alumnos/mayoria-edad')
    async def student_became_adult(request:Request):
        u,fail=authenticated(request,('admin','secretaria'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        reason=trim(f.get('reason'),250)
        try:student_id=int(f.get('student_id',''))
        except (TypeError,ValueError):return go('/alumnos','Selecciona el alumno cuya mayoría de edad se ha verificado.',True)
        if str(f.get('majority_verified',''))!='on' or len(reason)<10:
            return go('/alumnos','Comprueba la mayoría de edad con los datos institucionales y documenta el motivo.',True)
        with conn(request,True) as c:
            row=c.execute('SELECT * FROM students WHERE id=?',(student_id,)).fetchone()
            if not row:return Response(status_code=404)
            if not row['minor']:return go('/alumnos','La ficha ya consta como mayor de edad.',True)
            # Previous loan records preserve their own historical legal-status snapshots.
            c.execute('''UPDATE students SET minor=0,guardian_name='',guardian_relation='',
                guardian_email='',guardian_contact_authorized=0 WHERE id=?''',(student_id,))
            audit(c,u['id'],'mayoria_edad_verificada','alumno',student_id,{'reason':reason})
        return go('/alumnos','Ficha actualizada: mayor de edad. Los préstamos anteriores conservan sus datos históricos.')

    @app.get('/prestamos')
    def loans(request:Request):
        u,fail=authenticated(request)
        if fail:return fail
        q=trim(request.query_params.get('q'),100)
        with conn(request) as c:
            clause,args=scoped_clause(u)
            extra=''
            if q:extra=' AND (s.full_name LIKE ? OR s.student_ref LIKE ? OR d.asset_tag LIKE ? OR s.course_group LIKE ?)';args += ['%'+q+'%']*4
            rows=c.execute('''SELECT l.id,l.state,l.due_date,l.activated_at,l.closed_at,l.return_copies_checked_at,s.full_name student_name,s.course_group,d.asset_tag
                FROM loans l JOIN students s ON s.id=l.student_id JOIN devices d ON d.id=l.device_id
                WHERE 1=1'''+clause+extra+''' ORDER BY CASE l.state WHEN 'activo' THEN 0 WHEN 'preparado' THEN 1 ELSE 2 END,l.id DESC LIMIT 300''',args).fetchall()
        return page(request,'loans.html',u,rows=rows,q=q)

    @app.get('/prestamos/nuevo')
    def new_loan(request:Request):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        with conn(request) as c:
            students=c.execute('SELECT * FROM students WHERE active=1'+(' AND course_group=?' if u['role']=='gestor' else '')+' ORDER BY full_name',([u['tutor_group']] if u['role']=='gestor' else [])).fetchall()
            devices=c.execute("SELECT * FROM devices WHERE status='disponible' ORDER BY asset_tag").fetchall()
        return page(request,'new_loan.html',u,students=students,devices=devices)

    @app.post('/prestamos')
    async def loan_add(request:Request):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        try:student_id=int(f.get('student_id',''));device_id=int(f.get('device_id',''))
        except (ValueError,TypeError):return go('/prestamos/nuevo','Selecciona alumno y dispositivo.',True)
        due=trim(f.get('due_date'),10)
        try:due_dt=date.fromisoformat(due)
        except ValueError:return go('/prestamos/nuevo','Indica una fecha válida de devolución.',True)
        if due_dt<=datetime.now(LOCAL_TZ).date() or due_dt>datetime.now(LOCAL_TZ).date()+timedelta(days=550):
            return go('/prestamos/nuevo','El vencimiento debe ser futuro y no superar 550 días.',True)
        try:
            with conn(request,True) as c:
                student=c.execute('SELECT * FROM students WHERE id=? AND active=1',(student_id,)).fetchone()
                device=c.execute("SELECT * FROM devices WHERE id=? AND status='disponible'",(device_id,)).fetchone()
                if not student or not device or (u['role']=='gestor' and student['course_group']!=u['tutor_group']):return go('/prestamos/nuevo','Alumno o dispositivo no disponible para su grupo.',True)
                now=utcnow()
                if student['minor'] and str(f.get('minor_data_reviewed',''))!='on':
                    return go('/prestamos/nuevo','Verifica la situación de minoría de edad y representación vigente antes de crear el préstamo.',True)
                c.execute('''INSERT INTO loans(student_id,device_id,created_by,created_at,due_date,purpose,delivery_condition,last_modified,
                   minor_at_loan,guardian_name_at_loan,guardian_relation_at_loan,guardian_email_at_loan,guardian_contact_authorized_at_loan)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(student_id,device_id,u['id'],now,due,trim(f.get('purpose'),250),trim(f.get('delivery_condition'),700),now,
                   student['minor'],student['guardian_name'],student['guardian_relation'],student['guardian_email'],student['guardian_contact_authorized']))
                lid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                c.execute("UPDATE devices SET status='reservado' WHERE id=?",(device_id,))
                audit(c,u['id'],'prestamo_preparado','prestamo',lid,{'student_id':student_id,'device_id':device_id,'due':due})
        except sqlite3.IntegrityError:return go('/prestamos/nuevo','El equipo ya tiene un préstamo abierto.',True)
        return go('/prestamos/'+str(lid),'Expediente creado. Genera el contrato y archiva la copia firmada antes de la entrega.')

    @app.get('/prestamos/{loan_id}')
    def loan_detail(request:Request,loan_id:int):
        u,fail=authenticated(request)
        if fail:return fail
        with conn(request) as c:
            row=loan_record(c,loan_id)
            if not allowed_record(u,row):return Response(status_code=404)
            docs_all=c.execute('''SELECT d.*,u.full_name AS owner FROM documents d JOIN users u ON u.id=d.created_by WHERE loan_id=? ORDER BY d.id DESC''',(loan_id,)).fetchall()
            docs=docs_all if u['role'] in ('admin','secretaria','gestor') else ([d for d in docs_all if d['category'] in ('incidencia','otro')] if u['role'] in ('tic','tutor') else [])
            incidents=c.execute('''SELECT i.*,u.full_name AS owner FROM incidents i JOIN users u ON u.id=i.created_by WHERE loan_id=? ORDER BY i.id DESC''',(loan_id,)).fetchall()
            notices=c.execute('''SELECT n.*,u.full_name AS owner FROM notices n JOIN users u ON u.id=n.created_by WHERE loan_id=? ORDER BY n.id DESC''',(loan_id,)).fetchall()
            inspections=c.execute('''SELECT i.*,u.full_name AS owner FROM inspections i JOIN users u ON u.id=i.created_by WHERE loan_id=? ORDER BY i.id DESC''',(loan_id,)).fetchall()
            photos=c.execute('''SELECT p.*,u.full_name AS owner FROM device_photos p JOIN users u ON u.id=p.created_by WHERE p.loan_id=? ORDER BY p.id DESC''',(loan_id,)).fetchall()
        signed=any(d['category']=='contrato_firmado' for d in docs_all)
        return_signed=any(d['category']=='acta_devolucion_firmada' for d in docs_all)
        return page(request,'loan_detail.html',u,loan=row,docs=docs,incidents=incidents,notices=notices,inspections=inspections,photos=photos,signed=signed,return_signed=return_signed)

    @app.post('/prestamos/{loan_id}/activar')
    async def activate(request:Request,loan_id:int):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        if str(f.get('physical_delivery',''))!='on':return go(f'/prestamos/{loan_id}','Confirma la entrega presencial.',True)
        with conn(request,True) as c:
            loan=loan_record(c,loan_id)
            if not allowed_record(u,loan):return Response(status_code=404)
            if loan['state']!='preparado':return Response(status_code=409)
            signed=c.execute("SELECT COUNT(*) FROM documents WHERE loan_id=? AND category='contrato_firmado'",(loan_id,)).fetchone()[0]
            if not signed:return go(f'/prestamos/{loan_id}','Primero debe archivarse el contrato firmado.',True)
            if str(f.get('two_copies_signed',''))!='on' or str(f.get('recipient_copy_delivered',''))!='on':
                return go(f'/prestamos/{loan_id}','Es obligatorio comprobar las dos copias firmadas y entregar una a la persona interesada.',True)
            copy_recipient=trim(f.get('copy_recipient'),35)
            if copy_recipient not in ('alumno','representante_legal'):
                return go(f'/prestamos/{loan_id}','Indique quién recibe el segundo ejemplar del contrato.',True)
            if loan['due_date']<=today():
                return go(f'/prestamos/{loan_id}','El plazo ha vencido: hay que preparar un nuevo préstamo.',True)
            method=trim(f.get('representation_method'),40)
            representative_role=trim(f.get('representative_role'),80)
            if loan['minor']:
                if (str(f.get('guardian_verified',''))!='on' or
                    str(f.get('student_signature_verified',''))!='on' or
                    method not in ('expediente_matricula','documentacion_exhibida','resolucion_representacion') or
                    representative_role not in ('madre','padre','tutoria_legal','representante_entidad','otro_acreditado')):
                    return go(f'/prestamos/{loan_id}','Para menores es obligatorio verificar representación y ambas firmas.',True)
            if not loan['minor'] and copy_recipient!='alumno':
                return go(f'/prestamos/{loan_id}','La copia para un alumno mayor de edad debe entregarse a él.',True)
            now=utcnow()
            if loan['minor']:
                c.execute("""UPDATE loans SET state='activo',activated_at=?,activated_by=?,last_modified=?,
                    representation_verified_at=?,representation_verified_by=?,representation_method=?,
                    representative_role=?,student_signature_checked=1,
                    two_copies_checked_at=?,two_copies_checked_by=?,copy_recipient=? WHERE id=?""",
                    (now,u['id'],now,now,u['id'],method,representative_role,now,u['id'],copy_recipient,loan_id))
            else:
                c.execute("UPDATE loans SET state='activo',activated_at=?,activated_by=?,last_modified=?,two_copies_checked_at=?,two_copies_checked_by=?,copy_recipient=? WHERE id=?",(now,u['id'],now,now,u['id'],copy_recipient,loan_id))
            c.execute("UPDATE devices SET status='prestado' WHERE id=?",(loan['device_id'],))
            audit(c,u['id'],'entrega_confirmada','prestamo',loan_id,{'contract_signed':True,
                'guardian_verified':bool(loan['minor']),'student_signature_checked':bool(loan['minor']),
                'representation_method':method if loan['minor'] else None,
                'representative_role':representative_role if loan['minor'] else None,
                'two_copies_signed_confirmed':True,'copy_delivered':True,'copy_recipient':copy_recipient})
        return go(f'/prestamos/{loan_id}','Entrega formalizada y dispositivo en préstamo.')

    @app.post('/prestamos/{loan_id}/anular')
    async def cancel(request:Request,loan_id:int):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        reason=trim(f.get('reason'),500)
        if len(reason)<10:return go(f'/prestamos/{loan_id}','Indica un motivo de al menos 10 caracteres.',True)
        with conn(request,True) as c:
            row=loan_record(c,loan_id)
            if not allowed_record(u,row):return Response(status_code=404)
            if row['state']!='preparado':return Response(status_code=409)
            c.execute("UPDATE loans SET state='anulado',cancellation_reason=?,last_modified=? WHERE id=?",(reason,utcnow(),loan_id))
            c.execute("UPDATE devices SET status='disponible' WHERE id=?",(row['device_id'],))
            audit(c,u['id'],'prestamo_anulado','prestamo',loan_id,{'reason':reason})
        return go(f'/prestamos/{loan_id}','Préstamo anulado. El historial permanece registrado.')

    @app.post('/prestamos/{loan_id}/devolver')
    async def return_loan(request:Request,loan_id:int):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        condition=trim(f.get('condition'),650);accessories=trim(f.get('accessories'),400)
        result=trim(f.get('result'),20)
        if result not in ('correcto','incidencia') or not condition or not accessories:
            return go(f'/prestamos/{loan_id}','Indica el estado, los accesorios y el resultado.',True)
        with conn(request,True) as c:
            row=loan_record(c,loan_id)
            if not allowed_record(u,row):return Response(status_code=404)
            if row['state']!='activo':return Response(status_code=409)
            now=utcnow()
            c.execute('''UPDATE loans SET state='devuelto',closed_at=?,closed_by=?,return_condition=?,return_accessories=?,return_result=?,last_modified=? WHERE id=?''',
                     (now,u['id'],condition,accessories,result,now,loan_id))
            open_issues=c.execute("SELECT COUNT(*) FROM incidents WHERE loan_id=? AND status='abierta'",(loan_id,)).fetchone()[0]
            new_status='revision' if result=='incidencia' or open_issues else 'disponible'
            c.execute('UPDATE devices SET status=? WHERE id=?',(new_status,row['device_id']))
            if result=='incidencia':
                c.execute('''INSERT INTO incidents(loan_id,created_by,created_at,kind,description) VALUES(?,?,?,?,?)''',
                          (loan_id,u['id'],now,'dano','Incidencia detectada en recepción: '+condition+'; accesorios: '+accessories))
            audit(c,u['id'],'devolucion_confirmada','prestamo',loan_id,{'condition':condition,'accessories':accessories,'result':result,'device_status':new_status})
        return go(f'/prestamos/{loan_id}','Devolución registrada. Genera el acta y archívala cuando esté firmada.')

    @app.post('/prestamos/{loan_id}/cerrar-documentacion')
    async def close_documentation(request:Request,loan_id:int):
        # The physical return is already complete; here we verify signed copies.
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        if str(f.get('return_two_copies_signed',''))!='on' or str(f.get('return_copy_delivered',''))!='on':
            return go(f'/prestamos/{loan_id}','Comprueba las dos actas firmadas y entrega una copia.',True)
        recipient=trim(f.get('return_copy_recipient'),35)
        if recipient not in ('alumno','representante_legal'):
            return go(f'/prestamos/{loan_id}','Indique el destinatario del acta de devolución.',True)
        with conn(request,True) as c:
            loan=loan_record(c,loan_id)
            if not allowed_record(u,loan):return Response(status_code=404)
            if loan['state']!='devuelto':return Response(status_code=409)
            if loan['return_copies_checked_at']:
                return go(f'/prestamos/{loan_id}','El cierre documental ya se ha registrado.',True)
            if not loan['minor'] and recipient!='alumno':
                return go(f'/prestamos/{loan_id}','Un alumno mayor de edad recibe su propio ejemplar.',True)
            signed=c.execute("SELECT COUNT(*) FROM documents WHERE loan_id=? AND category='acta_devolucion_firmada'",(loan_id,)).fetchone()[0]
            if not signed:
                return go(f'/prestamos/{loan_id}','Debe archivarse primero el acta de devolución manuscrita firmada.',True)
            now=utcnow()
            c.execute('''UPDATE loans SET return_copies_checked_at=?,return_copies_checked_by=?,
                return_copy_recipient=?,last_modified=? WHERE id=?''',
                (now,u['id'],recipient,now,loan_id))
            audit(c,u['id'],'devolucion_documentacion_completa','prestamo',loan_id,
                  {'two_signed_copies':True,'recipient_copy_delivered':True,'recipient':recipient})
        return go(f'/prestamos/{loan_id}','Cierre documental de la devolución completado; dos ejemplares firmados.')

    @app.post('/prestamos/{loan_id}/incidencias')
    async def incident_add(request:Request,loan_id:int):
        u,fail=authenticated(request,('admin','secretaria','tic','tutor','gestor'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        kind=trim(f.get('kind'),40);desc=trim(f.get('description'),1800)
        if kind not in ('averia','perdida','dano','uso','otro') or len(desc)<8:return go(f'/prestamos/{loan_id}','Selecciona tipo y describe la incidencia.',True)
        with conn(request,True) as c:
            loan=loan_record(c,loan_id)
            if not allowed_record(u,loan):return Response(status_code=404)
            c.execute('INSERT INTO incidents(loan_id,created_by,created_at,kind,description) VALUES(?,?,?,?,?)',(loan_id,u['id'],utcnow(),kind,desc))
            iid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            audit(c,u['id'],'incidencia_creada','incidencia',iid,{'loan_id':loan_id,'kind':kind})
        return go(f'/prestamos/{loan_id}','Incidencia archivada.')

    @app.post('/incidencias/{incident_id}/resolver')
    async def incident_resolve(request:Request,incident_id:int):
        u,fail=authenticated(request,('admin','secretaria','tic','gestor'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        resolution=trim(f.get('resolution'),1800)
        if len(resolution)<8:return Response('Es necesario describir la resolución.',status_code=400)
        with conn(request,True) as c:
            row=c.execute('SELECT * FROM incidents WHERE id=? AND status=?',(incident_id,'abierta')).fetchone()
            if not row:return Response(status_code=404)
            if not allowed_record(u,loan_record(c,row['loan_id'])):return Response(status_code=404)
            c.execute("UPDATE incidents SET status='resuelta',resolution=?,resolved_at=?,resolved_by=? WHERE id=?",(resolution,utcnow(),u['id'],incident_id))
            audit(c,u['id'],'incidencia_resuelta','incidencia',incident_id,{'resolution':resolution})
        return go(f'/prestamos/{row["loan_id"]}','Incidencia cerrada con trazabilidad.')

    @app.post('/prestamos/{loan_id}/avisos')
    async def notice_add(request:Request,loan_id:int):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        channel=trim(f.get('channel'),30);recipient=trim(f.get('recipient'),200);detail=trim(f.get('detail'),900)
        if channel not in ('correo','telefono','presencial','notificacion_formal','otro') or not recipient:
            return go(f'/prestamos/{loan_id}','Completa el destinatario y el canal.',True)
        with conn(request,True) as c:
            loan=loan_record(c,loan_id)
            if not allowed_record(u,loan):return Response(status_code=404)
            c.execute('INSERT INTO notices(loan_id,created_by,created_at,channel,recipient,detail) VALUES(?,?,?,?,?,?)',
                     (loan_id,u['id'],utcnow(),channel,recipient,detail))
            notice_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            audit(c,u['id'],'gestion_aviso_registrada','aviso',notice_id,{'loan_id':loan_id,'channel':channel,'recipient':recipient,'note':'No acredita envío o recepción'})
        return go(f'/prestamos/{loan_id}','Gestión de aviso anotada. Adjunta el acuse si existe; anotar no equivale a notificar.')

    @app.post('/prestamos/{loan_id}/documentos')
    async def document_upload(request:Request,loan_id:int):
        u,fail=authenticated(request,('admin','secretaria','tic','gestor'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        category=trim(f.get('category'),60)
        if category not in ('contrato_firmado','autorizacion_representante','acta_devolucion_firmada','acuse_requerimiento','incidencia','otro'):
            return Response('Tipo documental no admitido.',status_code=400)
        if u['role']=='tic' and category not in ('incidencia','otro'):return Response(status_code=403)
        upload=f.get('file')
        if upload is None or not hasattr(upload,'read'):return go(f'/prestamos/{loan_id}','Selecciona un archivo.',True)
        content=await upload.read(MAX_UPLOAD+1)
        name=Path(upload.filename or 'documento').name
        # MIME checked against file header; extension of the original is not trusted.
        mime={'application/pdf':'application/pdf','image/jpeg':'image/jpeg','image/png':'image/png'}.get(upload.content_type,'')
        try:
            with conn(request,True) as c:
                row=loan_record(c,loan_id)
                if not allowed_record(u,row):return Response(status_code=404)
                store_file(request,c,loan_id,u['id'],category,content,name,mime)
        except ValueError as ex:return go(f'/prestamos/{loan_id}',str(ex),True)
        return go(f'/prestamos/{loan_id}','Documento archivado con huella SHA-256 y asiento de auditoría.')

    @app.post('/prestamos/{loan_id}/generar/{kind}')
    async def document_generate(request:Request,loan_id:int,kind:str):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        if kind not in ('contrato','devolucion','requerimiento'):return Response(status_code=404)
        with conn(request,True) as c:
            row=loan_record(c,loan_id)
            if not allowed_record(u,row):return Response(status_code=404)
            if kind=='devolucion' and row['state']!='devuelto':return go(f'/prestamos/{loan_id}','Todavía no consta una devolución.',True)
            try:
                content=make_pdf(kind,row,datetime.now(LOCAL_TZ).strftime('%d/%m/%Y %H:%M'))
            except ValueError as exc:
                return go(f'/prestamos/{loan_id}',str(exc),True)
            store_file(request,c,loan_id,u['id'],kind+'_generado',content,f'{kind}_PC-{loan_id:05d}.pdf','application/pdf',True)
        return go(f'/prestamos/{loan_id}','PDF generado y archivado. Descárgalo para tramitar su firma o notificación.')

    @app.get('/documentos/{doc_id}/descargar')
    def document_download(request:Request,doc_id:int):
        u,fail=authenticated(request)
        if fail:return fail
        with conn(request) as c:
            item=c.execute('''SELECT d.*,s.course_group FROM documents d JOIN loans l ON l.id=d.loan_id
                               JOIN students s ON s.id=l.student_id WHERE d.id=?''',(doc_id,)).fetchone()
        if not item or (u['role'] in ('tutor','gestor') and item['course_group']!=u['tutor_group']):return Response(status_code=404)
        if u['role']=='consulta' or (u['role'] in ('tic','tutor') and item['category'] not in ('incidencia','otro')):
            return Response(status_code=403)
        path=request.app.state.base/'private_documents'/item['stored_name']
        if not path.is_file():return Response('Documento no disponible: revisar restauración o copia de seguridad.',status_code=503)
        try:
            content=document_bytes(path,item,request.app.state.custody_key)
        except Exception:
            return Response('Alerta: no se ha podido verificar o descifrar el documento.',status_code=409)
        # Downloads are independently audited: reading a file is an access to personal data.
        with conn(request,True) as c:audit(c,u['id'],'documento_descargado','documento',doc_id,{'loan_id':item['loan_id']})
        filename=re.sub(r'[^A-Za-z0-9._-]','_',item['original_name'])[:110] or 'documento.pdf'
        return Response(content,media_type=item['media_type'],headers={'Content-Disposition':f'attachment; filename="{filename}"'})

    @app.get('/prestamos/{loan_id}/expediente.zip')
    def case_export(request:Request,loan_id:int):
        u,fail=authenticated(request,('admin','secretaria','gestor'))
        if fail:return fail
        with conn(request) as c:
            loan=loan_record(c,loan_id)
            if not allowed_record(u,loan):return Response(status_code=404)
            docs=c.execute('SELECT * FROM documents WHERE loan_id=? ORDER BY id',(loan_id,)).fetchall()
            photos=c.execute('SELECT * FROM device_photos WHERE loan_id=? ORDER BY id',(loan_id,)).fetchall()
            incidents=[dict(r) for r in c.execute('SELECT * FROM incidents WHERE loan_id=?',(loan_id,)).fetchall()]
            notices=[dict(r) for r in c.execute('SELECT * FROM notices WHERE loan_id=?',(loan_id,)).fetchall()]
            inspections=[dict(r) for r in c.execute('SELECT * FROM inspections WHERE loan_id=?',(loan_id,)).fetchall()]
            followups=[dict(r) for r in c.execute('SELECT * FROM followups WHERE loan_id=?',(loan_id,)).fetchall()]
            manifest={'application':'PortaCustodia','exported_at':utcnow(),'case_id':loan_id,
                      'loan':dict(loan),'documents':[],'photos':[],'incidents':incidents,'notices':notices,'inspections':inspections,'followups':followups,
                      'warning':'El hash no es una firma electrónica ni un sello de tiempo cualificado. El expediente contiene datos personales.'}
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for document in docs:
                    path=request.app.state.base/'private_documents'/document['stored_name']
                    if not path.is_file():return Response('Falta un archivo del expediente: revise la custodia.',status_code=503)
                    try:content=document_bytes(path,document,request.app.state.custody_key)
                    except Exception:return Response('Integridad o descifrado documental comprometidos.',status_code=409)
                    filename=f"documentos/{document['id']:05d}_{document['stored_name']}"
                    z.writestr(filename,content)
                    entry=dict(document);entry['zip_path']=filename
                    manifest['documents'].append(entry)
                for photo in photos:
                    path=request.app.state.base/'private_documents'/photo['stored_name']
                    if not path.is_file():return Response('Falta una fotografía del expediente.',status_code=503)
                    try:content=document_bytes(path,photo,request.app.state.custody_key)
                    except Exception:return Response('Fotografía alterada o no descifrable.',status_code=409)
                    filename=f"fotografias/{photo['id']:05d}_{photo['stored_name']}"
                    z.writestr(filename,content)
                    entry=dict(photo);entry['zip_path']=filename
                    manifest['photos'].append(entry)
                z.writestr('MANIFIESTO.json',json.dumps(manifest,indent=2,ensure_ascii=False))
        with conn(request,True) as c:audit(c,u['id'],'expediente_exportado','prestamo',loan_id,{'files':len(docs)})
        return Response(archive.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="expediente_PC-{loan_id:05d}.zip"'})

    @app.get('/informes/pendientes.csv')
    def csv_report(request:Request):
        u,fail=authenticated(request,('admin','secretaria','consulta'))
        if fail:return fail
        with conn(request) as c:
            rows=c.execute('''SELECT l.id,s.student_ref,s.full_name,s.course_group,d.asset_tag,d.serial_number,l.due_date,
               l.state,l.activated_at FROM loans l JOIN students s ON s.id=l.student_id JOIN devices d ON d.id=l.device_id
               WHERE l.state IN ('preparado','activo') ORDER BY l.due_date''').fetchall()
        buf=io.StringIO();writer=csv.writer(buf,delimiter=';')
        writer.writerow(['Expediente','Referencia','Alumno/a','Grupo','Inventario','Serie','Vencimiento','Estado','Entrega'])
        for r in rows:
            # Prevent spreadsheet formula execution from untrusted free-text fields.
            vals=[r['id'],r['student_ref'],r['full_name'],r['course_group'],r['asset_tag'],r['serial_number'],r['due_date'],r['state'],r['activated_at']]
            writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v for v in vals])
        with conn(request,True) as c:audit(c,u['id'],'informe_descargado','informe',0,{'type':'pendientes'})
        return Response('\ufeff'+buf.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="prestamos_pendientes.csv"'})

    @app.get('/auditoria')
    def audit_view(request:Request):
        u,fail=authenticated(request,('admin',))
        if fail:return fail
        with conn(request) as c:
            entries=c.execute('''SELECT a.*,u.full_name AS actor FROM audit a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200''').fetchall()
            good,broken=verify_audit(c)
        return page(request,'audit.html',u,entries=entries,good=good,broken=broken)

    @app.get('/auditoria/exportar.json')
    def audit_export(request:Request):
        u,fail=authenticated(request,('admin',))
        if fail:return fail
        with conn(request) as c:
            entries=[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id').fetchall()]
            good,broken=verify_audit(c)
        with conn(request,True) as c:audit(c,u['id'],'auditoria_exportada','auditoria',0,{'rows':len(entries)})
        return Response(json.dumps({'validated':good,'broken_at':broken,'exported_at':utcnow(),'events':entries},ensure_ascii=False,indent=2),
                        media_type='application/json',headers={'Content-Disposition':'attachment; filename="auditoria.json"'})

    @app.get('/agenda')
    def agenda(request:Request):
        u,fail=authenticated(request,('admin','secretaria','consulta','gestor'))
        if fail:return fail
        if u['role'] in ('admin','secretaria','gestor'):
            with conn(request,True) as c:
                generate_followups(c,datetime.now(LOCAL_TZ).date(),audit,utcnow())
        with conn(request) as c:
            clause,args=scoped_clause(u)
            tasks=c.execute("""SELECT f.*,s.full_name AS student_name,s.student_ref,s.course_group,
                s.email,d.asset_tag,l.state,l.due_date FROM followups f
                JOIN loans l ON l.id=f.loan_id JOIN students s ON s.id=l.student_id
                JOIN devices d ON d.id=l.device_id
                WHERE f.status='pendiente' AND l.state='activo'"""+clause+" ORDER BY l.due_date ASC,f.id DESC",args).fetchall()
            history=c.execute("""SELECT f.*,s.full_name AS student_name FROM followups f
                JOIN loans l ON l.id=f.loan_id JOIN students s ON s.id=l.student_id
                WHERE f.status!='pendiente'"""+clause+" ORDER BY f.handled_at DESC LIMIT 50",args).fetchall()
        return page(request,'agenda.html',u,tasks=tasks,history=history,stages=STAGES)

    @app.post('/agenda/{followup_id}/gestionar')
    async def handle_followup(request:Request,followup_id:int):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        status=trim(f.get('status'),20)
        note=trim(f.get('note'),900)
        channel=trim(f.get('channel'),30)
        recipient=trim(f.get('recipient'),200)
        if status not in ('gestionada','descartada') or len(note)<8:
            return go('/agenda','Indica resultado y explicación de al menos 8 caracteres.',True)
        if status=='gestionada' and (channel not in ('correo','telefono','presencial','notificacion_formal','otro') or not recipient):
            return go('/agenda','Para registrar una gestión identifica el canal y el destinatario.',True)
        with conn(request,True) as c:
            task=c.execute("""SELECT f.*,l.state FROM followups f JOIN loans l ON l.id=f.loan_id
                WHERE f.id=?""",(followup_id,)).fetchone()
            if not task or task['status']!='pendiente' or task['state']!='activo':return Response(status_code=409)
            if not allowed_record(u,loan_record(c,task['loan_id'])):return Response(status_code=404)
            c.execute("""UPDATE followups SET status=?,handled_by=?,handled_at=?,handling_note=? WHERE id=?""",
                      (status,u['id'],utcnow(),note,followup_id))
            if status=='gestionada':
                c.execute("""INSERT INTO notices(loan_id,created_by,created_at,channel,recipient,detail)
                    VALUES(?,?,?,?,?,?)""",(task['loan_id'],u['id'],utcnow(),channel,recipient,
                      'Gestión de tarea '+task['stage']+': '+note))
                notice_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                audit(c,u['id'],'gestion_aviso_registrada','aviso',notice_id,
                     {'loan_id':task['loan_id'],'channel':channel,'note':'No acredita recepción'})
            audit(c,u['id'],'seguimiento_resuelto','seguimiento',followup_id,
                 {'loan_id':task['loan_id'],'result':status,'note':note})
        return go('/agenda','Tarea registrada. Si hubo comunicación formal, archive también el justificante en el expediente.')

    @app.get('/agenda/{followup_id}/borrador.eml')
    def followup_draft(request:Request,followup_id:int):
        u,fail=authenticated(request,WRITE_LOAN)
        if fail:return fail
        with conn(request) as c:
            item=c.execute("""SELECT f.*,s.full_name student_name,s.email,s.student_ref,
                s.minor AS current_minor, s.guardian_email AS current_guardian_email,
                s.guardian_contact_authorized AS current_guardian_contact_authorized,
                d.asset_tag,l.due_date FROM followups f JOIN loans l ON l.id=f.loan_id
                JOIN students s ON s.id=l.student_id JOIN devices d ON d.id=l.device_id
                WHERE f.id=?""",(followup_id,)).fetchone()
            if not item:return Response(status_code=404)
            if not allowed_record(u,loan_record(c,item['loan_id'])):return Response(status_code=404)
        msg=EmailMessage()
        # Never assume mailbox ownership or the ability to send from it.
        if request.app.state.sender_email:
            msg['From']=request.app.state.sender_email
        # Minors: use a previously checked family contact only for a DRAFT,
        # otherwise leave To blank for staff to choose the verified recipient.
        # Current legal situation governs contact; an old minor loan does NOT
        # authorise correspondence to parents after verified majority of age.
        candidate=(item['current_guardian_email'] if item['current_minor'] and item['current_guardian_contact_authorized']
                   else (item['email'] if not item['current_minor'] else ''))
        if candidate and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',candidate):
            msg['To']=candidate
        msg['Subject']='IES Manuel Martín González - devolución de equipo en préstamo'
        body=(f"Estimado/a alumno/a o representante legal:\n\nSegún el registro interno de préstamos del centro, "
              f"la fecha prevista de devolución del equipo {item['asset_tag']} es {item['due_date']}.\n\n"
              'Le rogamos que contacte con Secretaría para confirmar la entrega y resolver incidencias.\n\n'
              'Enviar únicamente desde una cuenta institucional @canariaseducacion.es autorizada. '
              'Comprobar antes el destinatario y la representación legal cuando corresponda.\n\n'
              'BORRADOR PENDIENTE DE REVISIÓN Y ENVÍO. Su generación no acredita comunicación ni recepción.\n\n'
              'IES Manuel Martín González\n')
        msg.set_content(body)
        with conn(request,True) as c:
            audit(c,u['id'],'borrador_correo_descargado','seguimiento',followup_id,
                  {'loan_id':item['loan_id'],'sent':False})
        return Response(msg.as_bytes(),media_type='message/rfc822',headers={
            'Content-Disposition':f'attachment; filename="borrador_PC-{item["loan_id"]:05d}.eml"'})

    @app.post('/prestamos/{loan_id}/revisiones')
    async def inspection_add(request:Request,loan_id:int):
        u,fail=authenticated(request,('admin','secretaria','tic','tutor','gestor'))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        result=trim(f.get('result'),25);notes=trim(f.get('notes'),1000)
        if result not in ('correcto','incidencia','no_presentado') or len(notes)<8:
            return go(f'/prestamos/{loan_id}','Indica resultado y observación verificable.',True)
        with conn(request,True) as c:
            loan=loan_record(c,loan_id)
            if not allowed_record(u,loan):return Response(status_code=404)
            if loan['state']!='activo':return Response(status_code=409)
            c.execute("""INSERT INTO inspections(loan_id,created_by,checked_at,physical_present,result,notes)
                VALUES(?,?,?,?,?,?)""",(loan_id,u['id'],utcnow(),int(result!='no_presentado'),result,notes))
            inspection_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            if result=='incidencia':
                c.execute("""INSERT INTO incidents(loan_id,created_by,created_at,kind,description) VALUES(?,?,?,?,?)""",
                          (loan_id,u['id'],utcnow(),'otro','Revisión de equipo: '+notes))
            audit(c,u['id'],'revision_periodica','revision',inspection_id,
                  {'loan_id':loan_id,'result':result})
        return go(f'/prestamos/{loan_id}','Revisión registrada; compruebe la incidencia cuando proceda.')

    @app.get('/usuarios')
    def users(request:Request):
        u,fail=authenticated(request,('admin',))
        if fail:return fail
        with conn(request) as c:rows=c.execute('SELECT id,username,full_name,role,tutor_group,institutional_email,active,must_change FROM users ORDER BY full_name').fetchall()
        return page(request,'users.html',u,rows=rows)

    @app.post('/usuarios')
    async def user_add(request:Request):
        u,fail=authenticated(request,('admin',))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        name=trim(f.get('full_name'),140);username=trim(f.get('username'),100).lower()
        role=trim(f.get('role'),25);tutor_group=trim(f.get('tutor_group'),100)
        institutional_email=trim(f.get('institutional_email'),150).lower()
        if not valid_staff_email(institutional_email):
            return go('/usuarios','El correo del personal debe pertenecer a @canariaseducacion.es.',True)
        password=str(f.get('password',''))
        if not name or not re.fullmatch(r'[a-z0-9._-]{3,100}',username) or role not in ROLES or len(password)<12 or len(password)>128:
            return go('/usuarios','Revisa el usuario, rol y contraseña (mínimo 12 caracteres).',True)
        if role in ('tutor','gestor') and not tutor_group:return go('/usuarios','Este perfil docente requiere un grupo asignado.',True)
        try:
            with conn(request,True) as c:
                c.execute('INSERT INTO users(username,full_name,role,tutor_group,institutional_email,password_hash) VALUES(?,?,?,?,?,?)',
                          (username,name,role,tutor_group if role in ('tutor','gestor') else '',institutional_email,PH.hash(password)))
                uid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                audit(c,u['id'],'usuario_alta','usuario',uid,{'role':role,'group':tutor_group if role in ('tutor','gestor') else ''})
        except sqlite3.IntegrityError:return go('/usuarios','Este nombre de usuario ya existe.',True)
        return go('/usuarios','Usuario creado. Debe cambiar la clave en el primer acceso.')

    @app.post('/usuarios/{user_id}/correo')
    async def update_staff_mail(request:Request,user_id:int):
        u,fail=authenticated(request,('admin',))
        if fail:return fail
        form,fail=await posted(request,u)
        if fail:return fail
        institutional_email=trim(form.get('institutional_email'),150).lower()
        if not valid_staff_email(institutional_email):
            return go('/usuarios','El correo del personal debe pertenecer a @canariaseducacion.es.',True)
        with conn(request,True) as c:
            if not c.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone():
                return Response(status_code=404)
            c.execute('UPDATE users SET institutional_email=? WHERE id=?',(institutional_email,user_id))
            audit(c,u['id'],'correo_institucional_actualizado','usuario',user_id)
        return go('/usuarios','Correo institucional actualizado.')

    @app.post('/usuarios/{user_id}/clave')
    async def reset_password(request:Request,user_id:int):
        u,fail=authenticated(request,('admin',))
        if fail:return fail
        f,fail=await posted(request,u)
        if fail:return fail
        new=str(f.get('password',''))
        if len(new)<12 or len(new)>128:return go('/usuarios','La contraseña temporal debe tener 12 caracteres o más.',True)
        with conn(request,True) as c:
            row=c.execute('SELECT id FROM users WHERE id=?',(user_id,)).fetchone()
            if not row:return Response(status_code=404)
            c.execute('UPDATE users SET password_hash=?,must_change=1 WHERE id=?',(PH.hash(new),user_id))
            c.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            audit(c,u['id'],'clave_restablecida','usuario',user_id)
        return go('/usuarios','Clave temporal asignada. Se han cerrado las sesiones de esa cuenta.')

    return app

app=create_app()
