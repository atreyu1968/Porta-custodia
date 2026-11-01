"""Persistent SQLite database: foreign keys, WAL and append-only audit journal."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 full_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','secretaria','tic','tutor','gestor','consulta')),
 institutional_email TEXT NOT NULL DEFAULT '',
 tutor_group TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
 must_change INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL, ip_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, successful INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(username,created_at);
CREATE TABLE IF NOT EXISTS students (
 id INTEGER PRIMARY KEY, student_ref TEXT NOT NULL UNIQUE COLLATE NOCASE,
 full_name TEXT NOT NULL, course_group TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
 minor INTEGER NOT NULL DEFAULT 0, guardian_name TEXT NOT NULL DEFAULT '',
 guardian_relation TEXT NOT NULL DEFAULT '', guardian_email TEXT NOT NULL DEFAULT '',
 guardian_contact_authorized INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS devices (
 id INTEGER PRIMARY KEY, asset_tag TEXT NOT NULL UNIQUE COLLATE NOCASE,
 serial_number TEXT NOT NULL UNIQUE COLLATE NOCASE,
 brand TEXT NOT NULL, model TEXT NOT NULL, accessories TEXT NOT NULL DEFAULT 'Cargador',
 condition_note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'disponible'
 CHECK(status IN ('disponible','reservado','prestado','revision','baja')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS loans (
 id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
 device_id INTEGER NOT NULL REFERENCES devices(id),
 created_by INTEGER NOT NULL REFERENCES users(id), activated_by INTEGER REFERENCES users(id),
 closed_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL, activated_at TEXT, closed_at TEXT,
 due_date TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT 'Uso educativo del ciclo formativo',
 state TEXT NOT NULL DEFAULT 'preparado' CHECK(state IN ('preparado','activo','devuelto','anulado')),
 delivery_condition TEXT NOT NULL DEFAULT '', return_condition TEXT NOT NULL DEFAULT '',
 return_accessories TEXT NOT NULL DEFAULT '', return_result TEXT NOT NULL DEFAULT '',
 cancellation_reason TEXT NOT NULL DEFAULT '', last_modified TEXT NOT NULL,
 minor_at_loan INTEGER, guardian_name_at_loan TEXT, guardian_relation_at_loan TEXT,
 guardian_email_at_loan TEXT, guardian_contact_authorized_at_loan INTEGER NOT NULL DEFAULT 0,
 representation_verified_at TEXT, representation_verified_by INTEGER REFERENCES users(id),
 representation_method TEXT, representative_role TEXT, student_signature_checked INTEGER NOT NULL DEFAULT 0,
 two_copies_checked_at TEXT, two_copies_checked_by INTEGER REFERENCES users(id),
 copy_recipient TEXT,
 return_copies_checked_at TEXT, return_copies_checked_by INTEGER REFERENCES users(id),
 return_copy_recipient TEXT,
 CHECK (state != 'activo' OR activated_at IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_device_open ON loans(device_id) WHERE state IN ('preparado','activo');
CREATE TABLE IF NOT EXISTS incidents (
 id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('averia','perdida','dano','uso','otro')),
 description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'abierta' CHECK(status IN ('abierta','resuelta')),
 resolution TEXT NOT NULL DEFAULT '', resolved_at TEXT, resolved_by INTEGER REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS notices (
 id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 channel TEXT NOT NULL, recipient TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
 proof TEXT NOT NULL DEFAULT 'sin_justificante'
 CHECK(proof IN ('sin_justificante','justificante_archivado'))
);
CREATE TABLE IF NOT EXISTS documents (
 id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 category TEXT NOT NULL, original_name TEXT NOT NULL,
 stored_name TEXT NOT NULL UNIQUE, media_type TEXT NOT NULL,
 sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, generated INTEGER NOT NULL DEFAULT 0,
 encryption TEXT NOT NULL DEFAULT 'none' CHECK(encryption IN ('none','aes256gcm'))
);
CREATE INDEX IF NOT EXISTS idx_docs_loan ON documents(loan_id);
CREATE TABLE IF NOT EXISTS followups (
 id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id),
 stage TEXT NOT NULL CHECK(stage IN ('previo30','previo15','previo7','vencido1','vencido7')),
 deadline_date TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pendiente'
 CHECK(status IN ('pendiente','gestionada','descartada')),
 handled_by INTEGER REFERENCES users(id), handled_at TEXT, handling_note TEXT NOT NULL DEFAULT '',
 UNIQUE(loan_id,stage,deadline_date)
);
CREATE INDEX IF NOT EXISTS idx_followups_status ON followups(status,deadline_date);
CREATE TABLE IF NOT EXISTS inspections (
 id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id),
 created_by INTEGER NOT NULL REFERENCES users(id), checked_at TEXT NOT NULL,
 physical_present INTEGER NOT NULL CHECK(physical_present IN (0,1)),
 result TEXT NOT NULL CHECK(result IN ('correcto','incidencia','no_presentado')),
 notes TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inspections_loan ON inspections(loan_id,checked_at);
CREATE TABLE IF NOT EXISTS device_photos (
 id INTEGER PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices(id),
 loan_id INTEGER REFERENCES loans(id), created_by INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL, category TEXT NOT NULL CHECK(category IN ('inventario','entrega','revision','devolucion','incidencia')),
 note TEXT NOT NULL, original_name TEXT NOT NULL, stored_name TEXT NOT NULL UNIQUE,
 media_type TEXT NOT NULL DEFAULT 'image/jpeg', sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 encryption TEXT NOT NULL DEFAULT 'none' CHECK(encryption IN ('none','aes256gcm'))
);
CREATE INDEX IF NOT EXISTS idx_device_photos_device ON device_photos(device_id,created_at);
CREATE INDEX IF NOT EXISTS idx_device_photos_loan ON device_photos(loan_id);


CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, at TEXT NOT NULL, user_id INTEGER REFERENCES users(id),
 action TEXT NOT NULL, subject_type TEXT NOT NULL, subject_id INTEGER NOT NULL,
 payload TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL
);
"""


def connect(path):
    c = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys = ON')
    c.execute('PRAGMA busy_timeout = 15000')
    return c


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    c = connect(path)
    try:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript(SCHEMA)
        # Incremental migration for existing v0.1 databases; never drop existing records.
        columns={r['name'] for r in c.execute('PRAGMA table_info(documents)')}
        if 'encryption' not in columns:
            c.execute("ALTER TABLE documents ADD COLUMN encryption TEXT NOT NULL DEFAULT 'none'")
        user_columns = {r['name'] for r in c.execute('PRAGMA table_info(users)')}
        if 'institutional_email' not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN institutional_email TEXT NOT NULL DEFAULT ''")
        # Non-destructive v0.2.2 migration; legacy loans keep historical fallback values.
        required_student_columns={
            'guardian_relation':"TEXT NOT NULL DEFAULT ''",
            'guardian_email':"TEXT NOT NULL DEFAULT ''",
            'guardian_contact_authorized':'INTEGER NOT NULL DEFAULT 0',
        }
        existing={row['name'] for row in c.execute('PRAGMA table_info(students)')}
        for col,typ in required_student_columns.items():
            if col not in existing:c.execute(f'ALTER TABLE students ADD COLUMN {col} {typ}')
        required_loan_columns={
            'minor_at_loan':'INTEGER', 'guardian_name_at_loan':'TEXT',
            'guardian_relation_at_loan':'TEXT', 'guardian_email_at_loan':'TEXT',
            'guardian_contact_authorized_at_loan':'INTEGER NOT NULL DEFAULT 0',
            'representation_verified_at':'TEXT', 'representation_verified_by':'INTEGER REFERENCES users(id)',
            'representation_method':'TEXT', 'representative_role':'TEXT',
            'student_signature_checked':'INTEGER NOT NULL DEFAULT 0',
            'two_copies_checked_at':'TEXT',
            'two_copies_checked_by':'INTEGER REFERENCES users(id)',
            'copy_recipient':'TEXT',
            'return_copies_checked_at':'TEXT',
            'return_copies_checked_by':'INTEGER REFERENCES users(id)',
            'return_copy_recipient':'TEXT',
        }
        existing={row['name'] for row in c.execute('PRAGMA table_info(loans)')}
        for col,typ in required_loan_columns.items():
            if col not in existing:c.execute(f'ALTER TABLE loans ADD COLUMN {col} {typ}')
        # Backfill a snapshot from current student records for v0.2.1 loans.
        # Historical representation cannot be independently reconstructed: verify legacy cases.
        c.execute('''UPDATE loans SET
            minor_at_loan=(SELECT minor FROM students WHERE students.id=loans.student_id),
            guardian_name_at_loan=(SELECT guardian_name FROM students WHERE students.id=loans.student_id),
            guardian_relation_at_loan=(SELECT guardian_relation FROM students WHERE students.id=loans.student_id),
            guardian_email_at_loan=(SELECT guardian_email FROM students WHERE students.id=loans.student_id),
            guardian_contact_authorized_at_loan=(SELECT guardian_contact_authorized FROM students WHERE students.id=loans.student_id)
            WHERE minor_at_loan IS NULL''')
        # v0.4: SQLite cannot ALTER a CHECK constraint. Rebuild users once,
        # preserving stable user IDs referenced by sessions, loans and audit.
        create_sql=c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()['sql']
        if "'gestor'" not in create_sql:
            c.execute('PRAGMA foreign_keys=OFF')
            try:
                c.execute('BEGIN IMMEDIATE')
                c.execute("""CREATE TABLE users_v04 (
                 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                 full_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','secretaria','tic','tutor','gestor','consulta')),
                 institutional_email TEXT NOT NULL DEFAULT '', tutor_group TEXT NOT NULL DEFAULT '',
                 password_hash TEXT NOT NULL, must_change INTEGER NOT NULL DEFAULT 1,
                 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
                c.execute("""INSERT INTO users_v04(id,username,full_name,role,institutional_email,tutor_group,
                    password_hash,must_change,active,created_at)
                    SELECT id,username,full_name,role,institutional_email,tutor_group,
                    password_hash,must_change,active,created_at FROM users""")
                c.execute('DROP TABLE users')
                c.execute('ALTER TABLE users_v04 RENAME TO users')
                c.execute('COMMIT')
            except Exception:
                c.execute('ROLLBACK')
                raise
            finally:
                c.execute('PRAGMA foreign_keys=ON')
            if c.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('La migración de perfiles detectó referencias inconsistentes: restaurar copia.')
    finally:
        c.close()


@contextmanager
def db(path, write=False):
    c = connect(path)
    try:
        if write:
            c.execute('BEGIN IMMEDIATE')
        yield c
        if write:
            c.commit()
    except Exception:
        if write:
            c.rollback()
        raise
        # v0.4: SQLite cannot ALTER a CHECK constraint. Rebuild users once,
        # preserving stable user IDs referenced by sessions, loans and audit.
        create_sql=c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()['sql']
        if "'gestor'" not in create_sql:
            c.execute('PRAGMA foreign_keys=OFF')
            try:
                c.execute('BEGIN IMMEDIATE')
                c.execute("""CREATE TABLE users_v04 (
                 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                 full_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','secretaria','tic','tutor','gestor','consulta')),
                 institutional_email TEXT NOT NULL DEFAULT '', tutor_group TEXT NOT NULL DEFAULT '',
                 password_hash TEXT NOT NULL, must_change INTEGER NOT NULL DEFAULT 1,
                 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
                c.execute("""INSERT INTO users_v04(id,username,full_name,role,institutional_email,tutor_group,
                    password_hash,must_change,active,created_at)
                    SELECT id,username,full_name,role,institutional_email,tutor_group,
                    password_hash,must_change,active,created_at FROM users""")
                c.execute('DROP TABLE users')
                c.execute('ALTER TABLE users_v04 RENAME TO users')
                c.execute('COMMIT')
            except Exception:
                c.execute('ROLLBACK')
                raise
            finally:
                c.execute('PRAGMA foreign_keys=ON')
            if c.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('La migración de perfiles detectó referencias inconsistentes: restaurar copia.')
    finally:
        c.close()
