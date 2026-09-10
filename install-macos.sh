#!/bin/bash
# Установка без git; Python 3.9+ должен быть установлен на устройстве.
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
    echo "Использование: bash install-macos.sh"
    echo "Скачивает проект, устанавливает зависимости и включает автозапуск. Нужен Python 3.9+."
    exit 0
fi
if [[ $# -gt 0 ]]; then
    echo "Неизвестные аргументы. Используйте --help." >&2
    exit 1
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Этот установщик предназначен только для macOS." >&2
    exit 1
fi

python_bin=""
for candidate in python3 /usr/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
        'import sys, venv, xml.parsers.expat; assert sys.version_info >= (3, 9)' >/dev/null 2>&1; then
        python_bin="$(command -v "$candidate")"
        break
    fi
done
if [[ -z "$python_bin" ]]; then
    echo "Нужен рабочий Python 3.9 или новее. Установите его с https://www.python.org/downloads/macos/ и повторите команду." >&2
    exit 1
fi

install_root="${BREAK_COMP_INSTALL_DIR:-$HOME/Library/Application Support/break_comp}"
if [[ -e "$install_root" && ! -f "$install_root/.installed-by-break-comp" ]]; then
    echo "Папка уже существует и не принадлежит этому установщику: $install_root" >&2
    echo "Существующие файлы не изменены." >&2
    exit 1
fi

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/break-comp-install.XXXXXX")"
trap 'rm -rf "$temp_dir"' EXIT
echo "Скачиваю проект…"
curl --fail --location --silent --show-error --retry 2 \
    https://github.com/Mat1ro/break_comp/archive/refs/heads/main.zip \
    --output "$temp_dir/project.zip"
ditto -x -k "$temp_dir/project.zip" "$temp_dir/unpacked"
source_dir="$temp_dir/unpacked/break_comp-main"
for name in main.py audio_player.py assets/farts-8.mp3 autostart.py requirements.txt README.md; do
    if [[ ! -f "$source_dir/$name" ]]; then
        echo "Архив не содержит $name; установка отменена." >&2
        exit 1
    fi
done

# Отдельная папка версии сохраняет предыдущую установку при сбое скачивания/зависимостей.
archive_hash="$(shasum -a 256 "$temp_dir/project.zip" | awk '{print $1}')"
version_dir="$install_root/versions/$archive_hash"
mkdir -p "$version_dir/assets"
touch "$install_root/.installed-by-break-comp"
for name in main.py audio_player.py assets/farts-8.mp3 autostart.py requirements.txt README.md; do
    cp "$source_dir/$name" "$version_dir/$name"
done
echo "Устанавливаю зависимости…"
"$python_bin" -m venv "$version_dir/.venv"
"$version_dir/.venv/bin/python" -m pip install --disable-pip-version-check -r "$version_dir/requirements.txt"

echo "Включаю автозапуск…"
"$version_dir/.venv/bin/python" "$version_dir/autostart.py" install
ln -sfn "$version_dir" "$install_root/current"
echo "Готово. Программа запущена и добавлена в автозапуск."
echo "Остановить:"
printf '  %q %q stop\n' "$install_root/current/.venv/bin/python" "$install_root/current/autostart.py"
echo "Остановить и отключить автозапуск:"
printf '  %q %q uninstall\n' "$install_root/current/.venv/bin/python" "$install_root/current/autostart.py"
