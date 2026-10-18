#!/usr/bin/env bash
set -euo pipefail
trap 'echo "No se completó la instalación. Revisa el error anterior; puedes repetir el mismo comando." >&2' ERR

if [[ "$(uname -s)" != Linux ]]; then
    echo 'Ejecuta este instalador en Bazzite Linux, sin sudo.' >&2
    exit 1
fi
if [[ "$EUID" -eq 0 ]]; then
    echo 'Ejecuta el instalador con tu usuario normal, sin sudo.' >&2
    exit 1
fi
for program in distrobox podman; do
    if ! command -v "$program" >/dev/null 2>&1; then
        echo "Falta $program. Este instalador requiere las herramientas Distrobox/Podman de Bazzite." >&2
        exit 1
    fi
done

app_dir="$HOME/.local/share/voz-clara-linux"
host_distrobox="$(command -v distrobox)"
box_name='voz-clara-linux'
packages='git python3 python3-venv pulseaudio-utils libegl1 libopengl0 libgl1 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libdbus-1-3 libglib2.0-0t64'

echo 'Preparando Voz Clara Linux para Bazzite (la primera vez puede tardar varios minutos)…'
if ! podman container exists "$box_name"; then
    distrobox create --yes --name "$box_name" --image docker.io/library/ubuntu:24.04 \
        --additional-packages "$packages"
else
    # Do not enter an unrelated container with a coincidentally identical name.
    container_image="$(podman inspect --format '{{.Config.Image}}' "$box_name")"
    if [[ "$container_image" != *ubuntu:24.04 ]]; then
        echo "Ya existe un contenedor $box_name con otra imagen. No se modificó." >&2
        exit 1
    fi
fi

# Distrobox shares the desktop/audio sockets and the user's home directory.
# All apt packages live inside this container, never in the Bazzite host image.
distrobox enter --no-tty --name "$box_name" -- bash -s -- "$app_dir" "$host_distrobox" <<'CONTAINER'
set -euo pipefail
app_dir="$1"
host_distrobox="$2"
repository='https://github.com/VoodKaRL/voz-clara-linux.git'
if [[ -d "$app_dir/.git" ]]; then
    if [[ "$(git -C "$app_dir" remote get-url origin)" != "$repository" ]]; then
        echo 'La carpeta de instalación pertenece a otro repositorio. No se modificó.' >&2
        exit 1
    fi
    if [[ -n "$(git -C "$app_dir" status --porcelain)" ]]; then
        echo 'Hay cambios locales en la instalación. Guárdalos antes de actualizar.' >&2
        exit 1
    fi
    git -C "$app_dir" pull --ff-only
else
    git clone "$repository" "$app_dir"
fi

cd -- "$app_dir"
if [[ ! -x .venv-bazzite/bin/python ]]; then
    python3 -m venv .venv-bazzite
fi
.venv-bazzite/bin/python -m pip install -r requirements.txt
.venv-bazzite/bin/python -c 'from PySide6.QtWidgets import QApplication; import numpy, scipy; from noise import RNNoiseBackend; RNNoiseBackend().close()'
if ! .venv-bazzite/bin/python -c 'from audio import configure_audio; configure_audio()'; then
    echo 'No se pudo conectar con el audio de Bazzite. No se creará el acceso hasta que esté disponible.' >&2
    exit 1
fi

python3 - "$app_dir" "$host_distrobox" <<'PYTHON'
import os
from pathlib import Path
import shlex
import sys

app = Path(sys.argv[1])
distrobox = sys.argv[2]
home = Path.home()
bin_dir = home / '.local/bin'
desktop_dir = home / '.local/share/applications'
bin_dir.mkdir(parents=True, exist_ok=True)
desktop_dir.mkdir(parents=True, exist_ok=True)
launcher = bin_dir / 'voz-clara-linux'
command = [distrobox, 'enter', '--no-tty', '--name', 'voz-clara-linux', '--',
           str(app / '.venv-bazzite/bin/python'), str(app / 'main.py')]
launcher.write_text('#!/usr/bin/env bash\nexec ' + shlex.join(command) + '\n', encoding='utf-8')
launcher.chmod(0o755)
# Desktop Entry Exec has its own quoting rules, separate from shell quoting.
escaped = str(launcher).replace('%', '%%')
for char in ('\\', '"', '`', '$'):
    escaped = escaped.replace(char, '\\' + char)
desktop = ('[Desktop Entry]\nType=Application\nName=Voz Clara Linux\n'
           'Comment=Micrófono virtual, gate, compresor y escucha con ecualizador\n'
           f'Exec="{escaped}"\nIcon=audio-input-microphone\n'
           'Terminal=false\nCategories=AudioVideo;Audio;Mixer;\nStartupNotify=false\n')
(desktop_dir / 'voz-clara-linux.desktop').write_text(desktop, encoding='utf-8')
print('Instalado. Busca «Voz Clara Linux» en el menú de aplicaciones de GNOME.')
PYTHON
CONTAINER

echo 'Listo. Para futuras actualizaciones, cierra la app y repite este mismo instalador.'
