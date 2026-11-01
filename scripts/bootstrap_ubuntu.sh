#!/usr/bin/env bash
# Bootstrap sin curl, wget ni git. Requiere Ubuntu LXC con red, APT y root.
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
REPO='https://github.com/atreyu1968/Porta-custodia/archive/refs/heads/main.tar.gz'
WORK=''
trap 'test -z "$WORK" || rm -rf "$WORK"' EXIT
fail(){ echo "ERROR: $*" >&2; exit 1; }
[[ "${EUID}" -eq 0 ]] || fail 'Acceda como root al CONTENEDOR Ubuntu.'
[[ -r /etc/os-release ]] || fail 'No se reconoce Ubuntu.'
. /etc/os-release
[[ "$ID" = 'ubuntu' ]] || fail 'Instalación automática diseñada para Ubuntu (no para el host Proxmox).'
[[ ! -d /etc/pve ]] && ! command -v pveversion >/dev/null 2>&1 || fail 'No ejecute el instalador sobre el host Proxmox.'
[[ -d /run/systemd/system ]] || fail 'Se necesita un contenedor Ubuntu con systemd operativo.'
command -v apt-get >/dev/null || fail 'No existe apt-get.'
apt-get update
apt-get install -y --no-install-recommends ca-certificates python3
WORK="$(mktemp -d /tmp/portacustodia.XXXXXXXX)"
export PC_ARCHIVE_PATH="$WORK/source.tar.gz" PC_UNPACK_DIR="$WORK/source"
mkdir -m 0700 "$PC_UNPACK_DIR"
python3 - <<'PY'
from urllib.request import Request,urlopen
from pathlib import Path
from io import BytesIO
import os,tarfile,ssl
url='https://github.com/atreyu1968/Porta-custodia/archive/refs/heads/main.tar.gz'
req=Request(url,headers={'User-Agent':'PortaCustodia-Ubuntu-Installer/1.0'})
with urlopen(req,timeout=120,context=ssl.create_default_context()) as response:
    data=response.read(30*1024*1024+1)
if len(data)>30*1024*1024:raise SystemExit('Paquete de código demasiado grande')
p=Path(os.environ['PC_ARCHIVE_PATH']);p.write_bytes(data)
out=Path(os.environ['PC_UNPACK_DIR'])
with tarfile.open(fileobj=BytesIO(data),mode='r:gz') as tar:
    members=tar.getmembers()
    prefixes={m.name.split('/')[0] for m in members}
    if len(prefixes)!=1:raise SystemExit('Estructura de paquete inesperada')
    prefix=next(iter(prefixes))
    for member in members:
        parts=Path(member.name).parts
        if not parts or parts[0]!=prefix or '..' in parts:raise SystemExit('Ruta insegura en paquete')
        if not (member.isfile() or member.isdir()):raise SystemExit('Tipo de archivo no admitido')
        if member.isdir():continue
        rel=Path(*parts[1:]); target=out/rel
        if not rel.parts:continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with tar.extractfile(member) as src,target.open('wb') as dest:
            import shutil;shutil.copyfileobj(src,dest)
for must in ('requirements.txt','manage.py','scripts/install_lxc_ubuntu.sh','app/main.py'):
    if not (out/must).is_file():raise SystemExit('Falta '+must+' en GitHub')
print('Descarga HTTPS validada estructuralmente: código de la rama main.')
PY
bash "$PC_UNPACK_DIR/scripts/install_lxc_ubuntu.sh"
echo 'Instalador descargado y ejecutado. Consulte /root/portacustodia-initial-credentials.txt.'
