#!/bin/bash

# Crear y activar el entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "Creando entorno virtual 'venv'..."
    python -m venv venv
    echo "Entorno virtual 'venv' activado."
fi

source venv/bin/activate

# Actualizar pip si es necesario
echo "Actualizando pip..."
python -m pip install --upgrade pip

# Instalar dependencias
echo "Instalando dependencias..."
pip install -r requirements.txt

# Iniciar la base de datos (asumiendo que Docker está instalado)
echo "Iniciando base de datos PostgreSQL..."
cd db && docker-compose up -d
cd ..

# Esperar a que la base de datos esté lista
echo "Esperando a que la base de datos esté lista..."
sleep 10

# Realizar migraciones
echo "Realizando migraciones..."
python manage.py makemigrations
python manage.py migrate

# Crear un superusuario (opcional)
echo "¿Deseas crear un superusuario para el panel de administración? (s/n)"
read crear_usuario

if [ "$crear_usuario" = "s" ] || [ "$crear_usuario" = "S" ]; then
    python manage.py createsuperuser
fi

echo "Configuración completada. Ahora puedes ejecutar el bot con:"
echo "python manage.py run_bot"
echo ""
echo "O iniciar el servidor de desarrollo:"
echo "python manage.py runserver" 