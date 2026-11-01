#!/usr/bin/env bash
# Run ONLY inside an Ubuntu/Debian LXC, never on the Proxmox host.
set -Eeuo pipefail
APP_DIR=/opt/portacustodia
DATA_DIR=/var/lib/portacustodia
BACKUP_DIR=/var/backups/portacustodia
ENV_DIR=/etc/portacustodia
PORT=${PORTACUSTODIA_PORT:-8765}
BIND=${PORTACUSTODIA_BIND:-127.0.0.1}
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $EUID -ne 0 ]]; then echo 'Ejecutar como root dentro del contenedor LXC.';exit 1;fi
if command -v pveversion >/dev/null 2>&1 || [[ -d /etc/pve ]]; then
  echo 'BLOQUEADO: parece el host Proxmox. Instale ÚNICAMENTE dentro de un contenedor LXC.';exit 1
fi
if [[ ! -f /etc/debian_version ]]; then echo 'Este instalador está diseñado para Ubuntu/Debian.';exit 1;fi
if ! [[ "$PORT" =~ ^[0-9]{2,5}$ ]] || ((PORT<1024 || PORT>65535)); then echo 'Puerto no válido.';exit 1;fi
if [[ "$BIND" != '127.0.0.1' ]] && ! [[ "$BIND" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then echo 'Indica una IP IPv4 del contenedor.';exit 1;fi
if [[ "$BIND" != '127.0.0.1' ]]; then
  echo "ATENCIÓN: escucha en $BIND. Proteja el puerto con firewall para que solo el túnel/proxy autorizado pueda llegar a él."
fi
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip fonts-dejavu-core ca-certificates libzbar0 >/dev/null
# En Ubuntu minimal useradd --system NO garantiza grupo privado: crearlo explícitamente.
if ! getent group portacustodia >/dev/null 2>&1; then
  groupadd --system portacustodia
fi
if ! id portacustodia >/dev/null 2>&1; then
  useradd --system --gid portacustodia --home-dir "$DATA_DIR" --shell /usr/sbin/nologin portacustodia
else
  usermod --gid portacustodia portacustodia
fi
install -d -m 0750 -o root -g portacustodia "$APP_DIR"
install -d -m 0700 -o portacustodia -g portacustodia "$DATA_DIR" "$DATA_DIR/private_documents" "$BACKUP_DIR"
install -d -m 0750 -o root -g portacustodia "$ENV_DIR"
chmod 0750 "$ENV_DIR"
chown root:portacustodia "$ENV_DIR"
tar -C "$SOURCE_DIR" --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc' --exclude='.git' --exclude='.venv' --exclude='.env' --exclude='data' --exclude='backups' --exclude='tests' -cf - . | tar -C "$APP_DIR" -xf -
chown -R root:portacustodia "$APP_DIR"
find "$APP_DIR" -type d -exec chmod 0750 {} +
find "$APP_DIR" -type f -exec chmod 0640 {} +
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$APP_DIR/requirements.txt" -q
chown -R root:portacustodia "$APP_DIR/.venv"
chmod 0750 "$APP_DIR/scripts/install_lxc_ubuntu.sh"
# The key is not part of the application archive or backups.
# For upgrades, retain the existing key; never rotate it automatically.
KEY_FILE="$ENV_DIR/document.key"
if [[ ! -f "$KEY_FILE" ]]; then
  python3 - "$KEY_FILE" <<'PYKEY'
import base64,secrets,sys
with open(sys.argv[1],'x',encoding='ascii') as f:
    f.write(base64.b64encode(secrets.token_bytes(32)).decode('ascii')+'\n')
PYKEY
fi
chown root:portacustodia "$KEY_FILE"
chmod 0640 "$KEY_FILE"
if [[ ! -f "$ENV_DIR/environment" ]]; then
  SALT=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
  cat > "$ENV_DIR/environment" <<EOF
PORTACUSTODIA_DATA=$DATA_DIR
PORTACUSTODIA_BACKUPS=$BACKUP_DIR
PORTACUSTODIA_SECURE_COOKIE=1
PORTACUSTODIA_RATE_SALT=$SALT
PORTACUSTODIA_KEY_FILE=$KEY_FILE
PORTACUSTODIA_REQUIRE_ENCRYPTION=1
PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=1
# Antes de generar documentos reales, configurar los 4 campos siguientes:
# PORTACUSTODIA_RESPONSABLE_DATOS="Denominacion verificada del responsable"
# PORTACUSTODIA_CONTACTO_DPD="Contacto oficial del DPD"
# PORTACUSTODIA_PRIVACIDAD_URL="https://url-institucional-informacion-privacidad"
# PORTACUSTODIA_RETENCION="Plazo o criterio aprobado por el responsable"
EOF
  chmod 0640 "$ENV_DIR/environment"
fi
# El servicio debe leer el fichero de variables, pero el resto del sistema no.
chown root:portacustodia "$ENV_DIR/environment"
chmod 0640 "$ENV_DIR/environment"
# Prueba integral con un expediente ficticio como usuario restringido y cifrado REAL.
(cd "$APP_DIR" && runuser -u portacustodia -- env PORTACUSTODIA_KEY_FILE="$KEY_FILE" PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=0 PORTACUSTODIA_REQUIRE_ENCRYPTION=1 PYTHONDONTWRITEBYTECODE=1 "$APP_DIR/.venv/bin/python" -m scripts.selfcheck)
# Upgrade v0.1 without replacing configured environment secrets.
if ! grep -q '^PORTACUSTODIA_KEY_FILE=' "$ENV_DIR/environment";then
  printf '\nPORTACUSTODIA_KEY_FILE=%s\n' "$KEY_FILE" >> "$ENV_DIR/environment"
fi
if ! grep -q '^PORTACUSTODIA_REQUIRE_ENCRYPTION=' "$ENV_DIR/environment";then
  printf 'PORTACUSTODIA_REQUIRE_ENCRYPTION=1\n' >> "$ENV_DIR/environment"
fi
if ! grep -q '^PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=' "$ENV_DIR/environment";then
  printf 'PORTACUSTODIA_REQUIRE_LEGAL_CONFIG=1\n' >> "$ENV_DIR/environment"
fi
cat > /etc/systemd/system/portacustodia.service <<EOF
[Unit]
Description=PortaCustodia IES MMG (prestamos portatiles)
After=network.target

[Service]
Type=simple
User=portacustodia
Group=portacustodia
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_DIR/environment
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host $BIND --port $PORT --workers 1
Restart=on-failure
RestartSec=4
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/portacustodia-backup.service <<EOF
[Unit]
Description=Copia verificada de PortaCustodia
After=portacustodia.service
[Service]
Type=oneshot
User=portacustodia
Group=portacustodia
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_DIR/environment
ExecStart=$APP_DIR/.venv/bin/python -m scripts.backup backup
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DATA_DIR $BACKUP_DIR
EOF
cat > /etc/systemd/system/portacustodia-backup.timer <<'EOF'
[Unit]
Description=Copia diaria de PortaCustodia
[Timer]
OnCalendar=*-*-* 03:20:00
Persistent=true
RandomizedDelaySec=15m
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/portacustodia-followup.service <<EOF
[Unit]
Description=Generación interna de alertas de préstamo (sin enviar correos)
After=portacustodia.service
[Service]
Type=oneshot
User=portacustodia
Group=portacustodia
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_DIR/environment
ExecStart=$APP_DIR/.venv/bin/python -m scripts.followup
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DATA_DIR
EOF
cat > /etc/systemd/system/portacustodia-followup.timer <<'EOF'
[Unit]
Description=Control diario de vencimientos de PortaCustodia
[Timer]
OnCalendar=*-*-* 08:05:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable portacustodia.service >/dev/null
systemctl restart portacustodia.service
# Alta completamente desatendida en una base vacía; nunca se reescribe un administrador existente.
if ! test -f /root/portacustodia-initial-credentials.txt; then
  # No se incluyen contraseñas predefinidas ni en el repositorio ni en comandos de procesos.
  if ! runuser -u portacustodia -- env PORTACUSTODIA_DATA="$DATA_DIR" "$APP_DIR/.venv/bin/python" -c 'import sqlite3; from pathlib import Path; p=Path("/var/lib/portacustodia/portacustodia.sqlite3"); print(sqlite3.connect(p).execute("SELECT COUNT(*) FROM users").fetchone()[0])' | grep -qx 0; then
    echo 'Hay usuarios existentes; no se genera un nuevo administrador.'
  else
    CREDENTIAL_FILE=/root/portacustodia-initial-credentials.txt
    UMASK_OLD="$(umask)"; umask 077
    "$APP_DIR/.venv/bin/python" - <<'PYCREDS' > "$CREDENTIAL_FILE"
import secrets
print('PORTACUSTODIA - ACCESO INICIAL (USO INTERNO DE SECRETARÍA)')
print('Usuario: administrador')
print('Contraseña temporal: '+secrets.token_urlsafe(24))
print('Cambie la contraseña al primer acceso; custodie o destruya este documento.')
PYCREDS
    umask "$UMASK_OLD"
    PASS="$(sed -n 's/^Contraseña temporal: //p' "$CREDENTIAL_FILE")"
    printf '%s\n' "$PASS" | runuser -u portacustodia -- env PORTACUSTODIA_DATA="$DATA_DIR" "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" create-admin --username administrador --password-stdin
    unset PASS
    chmod 0600 "$CREDENTIAL_FILE"
  fi
fi
# Comprobación interna por loopback o dirección IP configurada: falla si el servicio no funciona.
PC_CHECK_HOST="$BIND" PC_CHECK_PORT="$PORT" "$APP_DIR/.venv/bin/python" - <<'PYHEALTH'
import os,time,urllib.request,json
host=os.environ['PC_CHECK_HOST'];port=os.environ['PC_CHECK_PORT']
url=f'http://{host}:{port}/salud'
for attempt in range(20):
    try:
        with urllib.request.urlopen(url,timeout=3) as r:
            data=json.loads(r.read())
        if data.get('estado')=='ok':
            print('SALUD OK: '+url)
            break
    except Exception:time.sleep(1)
else:raise SystemExit('ERROR: servicio sin respuesta; journalctl -u portacustodia -n 100')
PYHEALTH
runuser -u portacustodia -- env PORTACUSTODIA_DATA="$DATA_DIR" "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" check-audit
systemctl enable --now portacustodia-backup.timer
systemctl enable --now portacustodia-followup.timer
printf '\nINSTALACIÓN COMPLETADA EN LXC\n' 
printf 'Aplicación (origen del proxy): http://%s:%s\n' "$BIND" "$PORT"
printf 'Estado: systemctl status portacustodia\n'
printf 'Registro: journalctl -u portacustodia -f\n'
printf 'Credenciales iniciales (SOLO root): /root/portacustodia-initial-credentials.txt\n'
printf 'Si existen usuarios previos, el instalador no los modifica.\n'
printf '\nAcceso al usuario final solo por HTTPS en proxy/túnel institucional; nunca exponga el origen a internet.\n'
