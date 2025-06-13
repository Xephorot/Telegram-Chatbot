# Script para configurar el entorno de desarrollo en PowerShell

# Verificar si el entorno virtual existe, si no, crearlo
if (-not (Test-Path -Path ".\venv" -PathType Container)) {
    Write-Host "Creando entorno virtual 'venv'..." -ForegroundColor Cyan
    python -m venv venv
}

# Activar el entorno virtual para la sesión actual del script
.\venv\Scripts\Activate.ps1

# Actualizar pip si es necesario
Write-Host "Actualizando pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# Instalar dependencias
Write-Host "Instalando dependencias..." -ForegroundColor Cyan
pip install -r requirements.txt

# Iniciar la base de datos (asumiendo que Docker está instalado)
Write-Host "Iniciando base de datos PostgreSQL..." -ForegroundColor Cyan
Push-Location db
docker-compose up -d
Pop-Location

# Esperar a que la base de datos esté lista
Write-Host "Esperando a que la base de datos esté lista..." -ForegroundColor Cyan
Start-Sleep -Seconds 10

# Realizar migraciones
Write-Host "Realizando migraciones..." -ForegroundColor Cyan
python manage.py makemigrations
python manage.py migrate

# Crear un superusuario (opcional)
$crearUsuario = Read-Host "¿Deseas crear un superusuario para el panel de administración? (s/n)"

if ($crearUsuario -eq "s" -or $crearUsuario -eq "S") {
    python manage.py createsuperuser
}

Write-Host "`nConfiguración completada. Ahora puedes ejecutar el bot con:" -ForegroundColor Green
Write-Host "python manage.py run_bot" -ForegroundColor Yellow
Write-Host "`nO iniciar el servidor de desarrollo:" -ForegroundColor Green
Write-Host "python manage.py runserver" -ForegroundColor Yellow 