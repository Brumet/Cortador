#!/usr/bin/env bash
# Cortador - by Brumet.  Abre la aplicacion (instala la primera vez).
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Instalando Cortador por primera vez..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -e ".[web,app]"
fi

exec .venv/bin/python -m cortador.cli app "$@"
