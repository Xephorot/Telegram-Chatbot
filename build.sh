#!/usr/bin/env bash
# Exit on error
set -o errexit

# Instalar las dependencias de Python
pip install -r requirements.txt

# Recolectar archivos estáticos para producción
# WhiteNoise los servirá automáticamente.
python manage.py collectstatic --no-input

# Aplicar las migraciones de la base de datos
python manage.py migrate 