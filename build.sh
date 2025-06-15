#!/usr/bin/env bash
# Exit on error
set -o errexit

# Instalar las dependencias de Python
pip install -r requirements.txt

# Verificar explícitamente la instalación de psycopg2
echo "Verificando que psycopg2 se haya instalado correctamente..."
python -c "import psycopg2"
echo "Verificación de psycopg2 exitosa."

# Recolectar archivos estáticos para producción
# WhiteNoise los servirá automáticamente.
python manage.py collectstatic --no-input

# Aplicar las migraciones de la base de datos
python manage.py migrate

# Crear el superusuario en producción
python manage.py create_superuser_on_deploy 