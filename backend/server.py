from fastapi import FastAPI, APIRouter, HTTPException, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
import hashlib
import base64
import json
import asyncio
import aiofiles
import io
import shutil
import websockets
import subprocess
import socket

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(title="VNC Management System", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# VNC Configuration
VNC_PASSWORD = "vnc123pass"  # Статичный пароль для всех подключений
VNC_PORT = 5900
DEMO_MODE = True  # Режим демонстрации для университета

# ================== MODELS ==================

class VNCConnection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    ip_address: Optional[str] = None
    location: str
    country: str = "Russia"
    city: str = "Moscow"
    status: str = "inactive"  # active, inactive, installing
    last_seen: Optional[datetime] = None
    installation_key: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    vnc_port: int = VNC_PORT
    vnc_password: str = VNC_PASSWORD

class VNCConnectionCreate(BaseModel):
    name: str
    location: str
    country: str = "Russia"
    city: str = "Moscow"

class InstallationKey(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str
    machine_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    used: bool = False
    used_at: Optional[datetime] = None
    connection_id: Optional[str] = None

class FileTransfer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    connection_id: str
    filename: str
    file_size: int
    file_path: str
    transfer_type: str  # upload, download
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    checksum: str

class ActivityLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    connection_id: str
    action: str  # connect, disconnect, file_transfer, status_check
    details: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None

class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

# ================== HELPER FUNCTIONS ==================

def generate_installation_key():
    """Генерирует уникальный ключ установки"""
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:16]

def generate_powershell_script(installation_key: str):
    """Генерирует PowerShell скрипт для установки TightVNC"""
    server_url = os.environ.get('REACT_APP_BACKEND_URL', 'localhost:8001').replace('https://', '').replace('http://', '')
    
    script_content = f'''# VNC Auto-Installation Script
# Generated for University IT Support
# Installation Key: {installation_key}

# Configuration
$VNC_PASSWORD = "{VNC_PASSWORD}"
$INSTALLATION_KEY = "{installation_key}"
$SERVER_URL = "{server_url}"

Write-Host "=== VNC АВТОУСТАНОВКА ===" -ForegroundColor Green
Write-Host "Установка и настройка TightVNC для удаленного управления" -ForegroundColor Yellow

# Функция для установки TightVNC автоматически
function Install-TightVNC {{
    try {{
        # Создаем временную директорию
        $TempDir = "$env:TEMP\\VNCInstaller"
        if (!(Test-Path $TempDir)) {{
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
        }}
        
        Write-Host "Загрузка TightVNC..." -ForegroundColor Yellow
        
        # URL для скачивания TightVNC
        $TightVNC_URL = "https://www.tightvnc.com/download/2.8.59/tightvnc-2.8.59-gpl-setup-64bit.msi"
        $InstallerPath = "$TempDir\\tightvnc-setup.msi"
        
        # Скачиваем установщик
        Invoke-WebRequest -Uri $TightVNC_URL -OutFile $InstallerPath -UseBasicParsing -TimeoutSec 60
        
        Write-Host "Установка TightVNC..." -ForegroundColor Yellow
        
        # Автоматическая установка с настройками
        $Arguments = @(
            "/i", "`"$InstallerPath`"",
            "/quiet", "/norestart",
            "SET_USEVNCAUTHENTICATION=1",
            "SET_PASSWORD=$VNC_PASSWORD",
            "SET_USECONTROLAUTHENTICATION=1", 
            "SET_CONTROLPASSWORD=$VNC_PASSWORD",
            "SET_RUNCONTROLINTERFACE=1",
            "SET_REMOVEWALLPAPER=1"
        )
        
        Start-Process -FilePath "msiexec.exe" -ArgumentList $Arguments -Wait -NoNewWindow
        
        Write-Host "Настройка VNC сервера..." -ForegroundColor Yellow
        
        # Настройка через реестр
        $RegPath = "HKLM:\\SOFTWARE\\TightVNC\\Server"
        if (Test-Path $RegPath) {{
            # Базовые настройки VNC
            Set-ItemProperty -Path $RegPath -Name "QueryTimeout" -Value 10 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "QueryAcceptOnTimeout" -Value 0 -Type DWord -ErrorAction SilentlyContinue  
            Set-ItemProperty -Path $RegPath -Name "LocalInputPriority" -Value 0 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "LocalInputPriorityTimeout" -Value 3 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "BlockRemoteInput" -Value 0 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "BlockLocalInput" -Value 0 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "IpAccessControl" -Value 0 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "RfbPort" -Value 5900 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "HttpPort" -Value 5800 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "AcceptRfbConnections" -Value 1 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $RegPath -Name "AcceptHttpConnections" -Value 1 -Type DWord -ErrorAction SilentlyContinue
        }}
        
        # Запуск и настройка службы
        Write-Host "Запуск VNC службы..." -ForegroundColor Yellow
        
        # Останавливаем службу если запущена
        Stop-Service -Name "tvnserver" -Force -ErrorAction SilentlyContinue
        
        # Устанавливаем автозапуск и запускаем
        Set-Service -Name "tvnserver" -StartupType Automatic
        Start-Service -Name "tvnserver"
        
        # Проверяем что служба запустилась
        $Service = Get-Service -Name "tvnserver" -ErrorAction SilentlyContinue
        if ($Service.Status -eq "Running") {{
            Write-Host "✓ VNC сервер успешно запущен" -ForegroundColor Green
        }} else {{
            Write-Host "⚠ Служба VNC запущена, но статус неизвестен" -ForegroundColor Yellow
        }}
        
        # Очистка временных файлов
        Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
        
        return $true
        
    }} catch {{
        Write-Host "❌ Ошибка установки: $_" -ForegroundColor Red
        return $false
    }}
}}

# Функция регистрации в системе управления
function Register-WithServer {{
    try {{
        Write-Host "Регистрация в системе управления..." -ForegroundColor Yellow
        
        # Получаем информацию о машине
        $MachineName = $env:COMPUTERNAME
        $IPAddresses = @()
        
        # Получаем все IP адреса (исключая localhost)
        Get-NetIPAddress -AddressFamily IPv4 | Where-Object {{
            $_.IPAddress -ne "127.0.0.1" -and 
            $_.PrefixOrigin -in @("Dhcp", "Manual")
        }} | ForEach-Object {{
            $IPAddresses += $_.IPAddress
        }}
        
        $PrimaryIP = $IPAddresses[0]
        if (-not $PrimaryIP) {{
            $PrimaryIP = "192.168.1.100"  # Fallback IP
        }}
        
        # Данные для регистрации
        $RegistrationData = @{{
            installation_key = $INSTALLATION_KEY
            machine_name = $MachineName
            ip_address = $PrimaryIP
            status = "active"
        }} | ConvertTo-Json
        
        # Отправляем регистрацию
        $Headers = @{{ "Content-Type" = "application/json" }}
        $RegisterUrl = "https://$SERVER_URL/api/register-machine"
        
        Write-Host "Отправка регистрации на: $RegisterUrl" -ForegroundColor Gray
        
        $Response = Invoke-RestMethod -Uri $RegisterUrl -Method POST -Body $RegistrationData -Headers $Headers -TimeoutSec 30
        
        Write-Host "✓ Регистрация успешна!" -ForegroundColor Green
        Write-Host "Машина: $MachineName" -ForegroundColor Cyan  
        Write-Host "IP адрес: $PrimaryIP" -ForegroundColor Cyan
        Write-Host "Ключ: $INSTALLATION_KEY" -ForegroundColor Cyan
        
        return $true
        
    }} catch {{
        Write-Host "⚠ Регистрация не удалась: $_" -ForegroundColor Yellow
        Write-Host "VNC сервер работает, но не зарегистрирован в системе" -ForegroundColor Yellow
        return $false
    }}
}}

# Функция проверки подключения
function Test-VNCConnection {{
    try {{
        $Socket = New-Object System.Net.Sockets.TcpClient
        $Socket.Connect("127.0.0.1", 5900)
        $Socket.Close()
        return $true
    }} catch {{
        return $false
    }}
}}

# ОСНОВНОЙ ПРОЦЕСС УСТАНОВКИ
Write-Host ""
Write-Host "Начинаем автоматическую установку..." -ForegroundColor Green

# Проверяем права администратора
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {{
    Write-Host "❌ ОШИБКА: Требуются права администратора!" -ForegroundColor Red
    Write-Host "Запустите PowerShell от имени администратора и повторите установку." -ForegroundColor Yellow
    Read-Host "Нажмите Enter для выхода"
    exit 1
}}

# Шаг 1: Установка TightVNC
Write-Host "📦 Шаг 1: Установка TightVNC" -ForegroundColor Blue
if (Install-TightVNC) {{
    Write-Host "✓ TightVNC установлен успешно" -ForegroundColor Green
}} else {{
    Write-Host "❌ Не удалось установить TightVNC" -ForegroundColor Red
    Read-Host "Нажмите Enter для выхода"
    exit 1
}}

# Ожидание запуска службы
Write-Host "⏳ Ожидание запуска VNC сервера..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Проверка подключения
if (Test-VNCConnection) {{
    Write-Host "✓ VNC сервер доступен на порту 5900" -ForegroundColor Green
}} else {{
    Write-Host "⚠ VNC сервер может быть недоступен" -ForegroundColor Yellow
}}

# Шаг 2: Регистрация в системе
Write-Host "📡 Шаг 2: Регистрация в системе управления" -ForegroundColor Blue  
Register-WithServer | Out-Null

# Настройка файервола (опционально)
Write-Host "🔥 Шаг 3: Настройка файервола" -ForegroundColor Blue
try {{
    # Разрешаем VNC порт в файерволе
    New-NetFirewallRule -DisplayName "VNC Server" -Direction Inbound -Port 5900 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "VNC HTTP" -Direction Inbound -Port 5800 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
    Write-Host "✓ Файервол настроен" -ForegroundColor Green
}} catch {{
    Write-Host "⚠ Не удалось настроить файервол автоматически" -ForegroundColor Yellow
}}

# Завершение
Write-Host ""
Write-Host "🎉 УСТАНОВКА ЗАВЕРШЕНА!" -ForegroundColor Green
Write-Host "========================" -ForegroundColor Green
Write-Host "VNC Сервер: АКТИВЕН" -ForegroundColor Cyan
Write-Host "Порт: 5900" -ForegroundColor Cyan  
Write-Host "Пароль: $VNC_PASSWORD" -ForegroundColor Cyan
Write-Host "Ключ установки: $INSTALLATION_KEY" -ForegroundColor Cyan
Write-Host ""
Write-Host "Теперь вы можете подключиться через веб-интерфейс:" -ForegroundColor Yellow
Write-Host "https://$SERVER_URL" -ForegroundColor Blue
Write-Host ""

# Скрыть иконку в трее (опционально)
$TrayRegPath = "HKLM:\\SOFTWARE\\TightVNC\\Server"
try {{
    Set-ItemProperty -Path $TrayRegPath -Name "ShowTrayIcon" -Value 0 -ErrorAction SilentlyContinue
}} catch {{
    # Игнорируем ошибки
}}

Write-Host "Установка завершена. Окно закроется через 10 секунд..." -ForegroundColor Yellow
Start-Sleep -Seconds 10'''
    
    return script_content

async def log_activity(connection_id: str, action: str, details: str, ip_address: str = None):
    """Логирование действий"""
    log_entry = ActivityLog(
        connection_id=connection_id,
        action=action,
        details=details,
        ip_address=ip_address
    )
    await db.activity_logs.insert_one(log_entry.dict())

async def check_vnc_connection(ip_address: str, port: int = 5900, timeout: float = 3.0):
    """Проверить доступность VNC соединения"""
    if not ip_address:
        return False
    
    # В демо режиме симулируем активные соединения для половины машин
    if DEMO_MODE:
        import random
        random.seed(ip_address)  # Стабильный результат для одного IP
        return random.choice([True, True, False])  # 66% шанс быть активным
    
    try:
        # Создаем сокет соединение для проверки порта
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip_address, port),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False

async def update_connection_status_check():
    """Периодическая проверка статусов VNC соединений"""
    while True:
        try:
            # Получить все соединения с IP адресами
            connections = await db.vnc_connections.find({"ip_address": {"$ne": None}}).to_list(1000)
            
            for connection in connections:
                if connection["ip_address"]:
                    is_accessible = await check_vnc_connection(connection["ip_address"], connection["vnc_port"])
                    new_status = "active" if is_accessible else "inactive"
                    
                    # Обновить статус если изменился
                    if connection["status"] != new_status:
                        await db.vnc_connections.update_one(
                            {"id": connection["id"]},
                            {"$set": {"status": new_status, "last_seen": datetime.utcnow()}}
                        )
                        await log_activity(
                            connection["id"], 
                            "status_auto_update", 
                            f"Статус автоматически изменен на {new_status}"
                        )
                        logger.info(f"Connection {connection['id']} status changed to {new_status}")
            
            # Проверять каждые 30 секунд
            await asyncio.sleep(30) 
            
        except Exception as e:
            logger.error(f"Error in status check: {e}")
            await asyncio.sleep(60)  # Если ошибка, ждем дольше

# ================== API ROUTES ==================

# Basic routes
@api_router.get("/")
async def root():
    return {"message": "VNC Management System API", "version": "1.0.0"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

# VNC Connections Management
@api_router.post("/connections", response_model=VNCConnection)
async def create_connection(connection_data: VNCConnectionCreate):
    """Создать новое VNC соединение"""
    installation_key = generate_installation_key()
    
    connection = VNCConnection(
        **connection_data.dict(),
        installation_key=installation_key
    )
    
    # Сохранить соединение
    await db.vnc_connections.insert_one(connection.dict())
    
    # Создать ключ установки
    install_key = InstallationKey(
        key=installation_key,
        machine_name=connection_data.name,
        connection_id=connection.id
    )
    await db.installation_keys.insert_one(install_key.dict())
    
    return connection

@api_router.get("/connections", response_model=List[VNCConnection])
async def get_connections():
    """Получить все VNC соединения"""
    connections = await db.vnc_connections.find().to_list(1000)
    return [VNCConnection(**conn) for conn in connections]

@api_router.get("/connections/{connection_id}", response_model=VNCConnection)
async def get_connection(connection_id: str):
    """Получить конкретное соединение"""
    connection = await db.vnc_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    return VNCConnection(**connection)

@api_router.put("/connections/{connection_id}/status")
async def update_connection_status(connection_id: str, status: str):
    """Обновить статус соединения"""
    valid_statuses = ["active", "inactive", "installing", "error"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    update_data = {
        "status": status,
        "last_seen": datetime.utcnow()
    }
    
    result = await db.vnc_connections.update_one(
        {"id": connection_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    await log_activity(connection_id, "status_update", f"Status changed to {status}")
    
    return {"message": "Status updated successfully"}

@api_router.post("/connections/{connection_id}/simulate-active")
async def simulate_active_connection(connection_id: str):
    """Симулировать активное соединение для демонстрации"""
    connection = await db.vnc_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Установить случайный IP адрес если его нет
    if not connection.get("ip_address"):
        import random
        ip_address = f"192.168.1.{random.randint(100, 200)}"
        await db.vnc_connections.update_one(
            {"id": connection_id},
            {"$set": {"ip_address": ip_address}}
        )
    else:
        ip_address = connection["ip_address"]
    
    # Активировать соединение
    update_data = {
        "status": "active",
        "last_seen": datetime.utcnow()
    }
    
    result = await db.vnc_connections.update_one(
        {"id": connection_id},
        {"$set": update_data}
    )
    
    await log_activity(connection_id, "demo_activation", f"Соединение активировано для демонстрации (IP: {ip_address})")
    
    return {"message": "Connection activated for demo", "ip_address": ip_address}

# Installation Scripts
@api_router.get("/generate-installer/{connection_id}")
async def generate_installer(connection_id: str):
    """Генерировать PowerShell установщик для соединения"""
    connection = await db.vnc_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    script_content = generate_powershell_script(connection["installation_key"])
    
    # Создать файл скрипта
    filename = f"vnc_installer_{connection['id'][:8]}.ps1"
    
    await log_activity(connection_id, "installer_generated", f"PowerShell installer generated: {filename}")
    
    return StreamingResponse(
        io.StringIO(script_content),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )

@api_router.post("/register-machine")
async def register_machine(registration_data: dict):
    """Регистрация машины после установки VNC"""
    installation_key = registration_data.get("installation_key")
    machine_name = registration_data.get("machine_name")
    ip_address = registration_data.get("ip_address")
    status = registration_data.get("status", "active")
    
    if not installation_key:
        raise HTTPException(status_code=400, detail="Installation key required")
    
    # Найти ключ установки
    install_key = await db.installation_keys.find_one({"key": installation_key})
    if not install_key:
        raise HTTPException(status_code=404, detail="Invalid installation key")
    
    if install_key["used"]:
        raise HTTPException(status_code=400, detail="Installation key already used")
    
    # Обновить соединение
    connection_id = install_key["connection_id"]
    update_data = {
        "ip_address": ip_address,
        "status": status,
        "last_seen": datetime.utcnow()
    }
    
    await db.vnc_connections.update_one(
        {"id": connection_id},
        {"$set": update_data}
    )
    
    # Отметить ключ как использованный
    await db.installation_keys.update_one(
        {"key": installation_key},
        {"$set": {"used": True, "used_at": datetime.utcnow()}}
    )
    
    await log_activity(connection_id, "machine_registered", f"Machine {machine_name} registered with IP {ip_address}")
    
    return {"message": "Machine registered successfully", "connection_id": connection_id}

# VNC Control
@api_router.post("/connect/{connection_id}")
async def start_vnc_session(connection_id: str):
    """Начать VNC сессию"""
    connection = await db.vnc_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if connection["status"] != "active":
        raise HTTPException(status_code=400, detail="Connection is not active")
    
    await log_activity(connection_id, "vnc_connect", f"VNC session started to {connection['ip_address']}")
    
    # Возвращаем данные для подключения к VNC
    return {
        "connection_id": connection_id,
        "ip_address": connection["ip_address"],
        "port": connection["vnc_port"],
        "password": connection["vnc_password"],
        "websocket_url": f"ws://localhost:6080/websockify?token={connection_id}"
    }

# Activity Logs
@api_router.get("/logs", response_model=List[ActivityLog])
async def get_activity_logs(limit: int = 100):
    """Получить логи активности"""
    logs = await db.activity_logs.find().sort("timestamp", -1).limit(limit).to_list(limit)
    return [ActivityLog(**log) for log in logs]

@api_router.get("/logs/{connection_id}", response_model=List[ActivityLog])
async def get_connection_logs(connection_id: str, limit: int = 50):
    """Получить логи для конкретного соединения"""
    logs = await db.activity_logs.find({"connection_id": connection_id}).sort("timestamp", -1).limit(limit).to_list(limit)
    return [ActivityLog(**log) for log in logs]

# Statistics
@api_router.get("/stats")
async def get_statistics():
    """Получить статистику системы"""
    total_connections = await db.vnc_connections.count_documents({})
    active_connections = await db.vnc_connections.count_documents({"status": "active"})
    inactive_connections = await db.vnc_connections.count_documents({"status": "inactive"})
    
    # Активность за последние 24 часа
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_activity = await db.activity_logs.count_documents({"timestamp": {"$gte": yesterday}})
    
    return {
        "total_connections": total_connections,
        "active_connections": active_connections,
        "inactive_connections": inactive_connections,
        "recent_activity_24h": recent_activity,
        "timestamp": datetime.utcnow()
    }

# File Management Operations
@api_router.get("/files/{connection_id}")
async def list_files(connection_id: str, path: str = "/"):
    """Получить список файлов на удаленной машине"""
    connection = await db.vnc_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if connection["status"] != "active":
        raise HTTPException(status_code=400, detail="Connection is not active")
    
    # Симуляция файловой системы (в реальной системе это будет RPC к удаленной машине)
    mock_files = [
        {
            "name": "Documents",
            "type": "directory",
            "size": 0,
            "modified": "2025-06-20T10:30:00Z",
            "path": "/Documents"
        },
        {
            "name": "Desktop",
            "type": "directory", 
            "size": 0,
            "modified": "2025-06-20T09:15:00Z",
            "path": "/Desktop"
        },
        {
            "name": "report.pdf",
            "type": "file",
            "size": 2048576,
            "modified": "2025-06-21T08:45:00Z",
            "path": "/report.pdf"
        },
        {
            "name": "data.xlsx",
            "type": "file", 
            "size": 1024000,
            "modified": "2025-06-20T16:20:00Z",
            "path": "/data.xlsx"
        },
        {
            "name": "backup.zip",
            "type": "file",
            "size": 10485760,
            "modified": "2025-06-19T14:10:00Z", 
            "path": "/backup.zip"
        }
    ]
    
    await log_activity(connection_id, "file_list", f"Listed files in {path}")
    
    return {
        "connection_id": connection_id,
        "current_path": path,
        "files": mock_files
    }

@api_router.post("/files/{connection_id}/upload")
async def upload_file(connection_id: str, file: UploadFile = File(...), remote_path: str = "/"):
    """Загрузить файл на удаленную машину"""
    connection = await db.vnc_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if connection["status"] != "active":
        raise HTTPException(status_code=400, detail="Connection is not active")
    
    # Создать директорию для загруженных файлов
    upload_dir = Path("/tmp/vnc_uploads") / connection_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Сохранить файл
    file_path = upload_dir / file.filename
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Вычислить контрольную сумму
    checksum = hashlib.md5(content).hexdigest()
    
    # Создать запись о передаче файла
    file_transfer = FileTransfer(
        connection_id=connection_id,
        filename=file.filename,
        file_size=len(content),
        file_path=str(file_path),
        transfer_type="upload",
        checksum=checksum
    )
    
    await db.file_transfers.insert_one(file_transfer.dict())
    await log_activity(connection_id, "file_upload", f"Uploaded {file.filename} ({len(content)} bytes)")
    
    return {
        "message": "File uploaded successfully",
        "filename": file.filename,
        "size": len(content),
        "checksum": checksum,
        "remote_path": f"{remote_path.rstrip('/')}/{file.filename}"
    }

@api_router.get("/files/{connection_id}/download")
async def download_file(connection_id: str, file_path: str):
    """Скачать файл с удаленной машины"""
    connection = await db.vnc_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if connection["status"] != "active":
        raise HTTPException(status_code=400, detail="Connection is not active")
    
    # Симуляция скачивания файла (создаем тестовый файл)
    filename = os.path.basename(file_path)
    content = f"Mock file content for {filename} from {connection['name']}\nGenerated at: {datetime.utcnow()}\nFile path: {file_path}".encode()
    
    # Создать запись о передаче файла
    file_transfer = FileTransfer(
        connection_id=connection_id,
        filename=filename,
        file_size=len(content),
        file_path=file_path,
        transfer_type="download",
        checksum=hashlib.md5(content).hexdigest()
    )
    
    await db.file_transfers.insert_one(file_transfer.dict())
    await log_activity(connection_id, "file_download", f"Downloaded {filename} ({len(content)} bytes)")
    
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )

@api_router.get("/files/{connection_id}/transfers", response_model=List[FileTransfer])
async def get_file_transfers(connection_id: str, limit: int = 50):
    """Получить историю передач файлов"""
    transfers = await db.file_transfers.find({"connection_id": connection_id}).sort("timestamp", -1).limit(limit).to_list(limit)
    return [FileTransfer(**transfer) for transfer in transfers]

# WebSocket для VNC прокси
websocket_connections = {}
vnc_proxies = {}

@app.websocket("/websockify")
async def websockify_vnc_proxy(websocket: WebSocket, token: str):
    """WebSocket прокси для VNC соединения через websockify протокол"""
    await websocket.accept()
    
    connection = await db.vnc_connections.find_one({"id": token})
    if not connection:
        await websocket.close(code=1008, reason="Connection not found")
        return
    
    if connection["status"] != "active" or not connection.get("ip_address"):
        await websocket.close(code=1008, reason="Connection not active or no IP")
        return
    
    vnc_host = connection["ip_address"]
    vnc_port = connection.get("vnc_port", 5900)
    
    # Добавить соединение в активные
    websocket_connections[token] = websocket
    
    try:
        await log_activity(token, "vnc_websocket_connect", f"WebSocket VNC session started to {vnc_host}:{vnc_port}")
        
        # Создать TCP соединение к VNC серверу
        try:
            vnc_reader, vnc_writer = await asyncio.open_connection(vnc_host, vnc_port)
            vnc_proxies[token] = (vnc_reader, vnc_writer)
            
            # Запустить прокси между WebSocket и VNC TCP
            await asyncio.gather(
                proxy_websocket_to_vnc(websocket, vnc_writer),
                proxy_vnc_to_websocket(vnc_reader, websocket),
                return_exceptions=True
            )
            
        except (ConnectionRefusedError, OSError) as e:
            logger.error(f"Failed to connect to VNC server {vnc_host}:{vnc_port}: {e}")
            await websocket.close(code=1011, reason=f"VNC server unavailable: {e}")
            
    except Exception as e:
        logger.error(f"WebSocket VNC proxy error: {e}")
    finally:
        # Очистка соединений
        websocket_connections.pop(token, None)
        if token in vnc_proxies:
            _, vnc_writer = vnc_proxies.pop(token)
            vnc_writer.close()
            await vnc_writer.wait_closed()
        await log_activity(token, "vnc_websocket_disconnect", "WebSocket VNC session ended")

async def proxy_websocket_to_vnc(websocket: WebSocket, vnc_writer):
    """Прокси данных от WebSocket к VNC серверу"""
    try:
        while True:
            data = await websocket.receive_bytes()
            vnc_writer.write(data)
            await vnc_writer.drain()
    except Exception as e:
        logger.debug(f"WebSocket to VNC proxy ended: {e}")

async def proxy_vnc_to_websocket(vnc_reader, websocket: WebSocket):
    """Прокси данных от VNC сервера к WebSocket"""
    try:
        while True:
            data = await vnc_reader.read(8192)
            if not data:
                break
            await websocket.send_bytes(data)
    except Exception as e:
        logger.debug(f"VNC to WebSocket proxy ended: {e}")

# VNC Screen capture (симуляция)
@api_router.get("/vnc/{connection_id}/screenshot")
async def get_vnc_screenshot(connection_id: str):
    """Получить скриншот VNC экрана"""
    connection = await db.vnc_connections.find_one({"id": connection_id})
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    if connection["status"] != "active":
        raise HTTPException(status_code=400, detail="Connection is not active")
    
    # Создаем простой тестовый "скриншот" SVG
    svg_content = f'''<svg width="800" height="600" xmlns="http://www.w3.org/2000/svg">
    <rect width="100%" height="100%" fill="#1e40af"/>
    <text x="400" y="250" text-anchor="middle" fill="white" font-size="24" font-family="Arial">
        VNC Screen: {connection['name']}
    </text>
    <text x="400" y="300" text-anchor="middle" fill="white" font-size="16" font-family="Arial">
        IP: {connection['ip_address']}
    </text>
    <text x="400" y="330" text-anchor="middle" fill="white" font-size="14" font-family="Arial">
        Screenshot at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}
    </text>
    <rect x="100" y="400" width="600" height="100" fill="white" stroke="black" stroke-width="2"/>
    <text x="400" y="440" text-anchor="middle" fill="black" font-size="16" font-family="Arial">
        Simulated Desktop Environment
    </text>
    <text x="400" y="460" text-anchor="middle" fill="black" font-size="12" font-family="Arial">
        This is a mock VNC screen for demonstration
    </text>
</svg>'''
    
    await log_activity(connection_id, "vnc_screenshot", "Screenshot captured")
    
    return StreamingResponse(
        io.StringIO(svg_content),
        media_type="image/svg+xml"
    )

# WebSocket для файлового менеджера
@app.websocket("/ws/files/{connection_id}")
async def file_manager_websocket(websocket: WebSocket, connection_id: str):
    """WebSocket for real-time file operations"""
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command")
            
            if command == "refresh":
                # Отправить обновленный список файлов
                files_response = await list_files(connection_id, data.get("path", "/"))
                await websocket.send_json({
                    "type": "file_list",
                    "data": files_response
                })
            elif command == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"File manager WebSocket error: {e}")

# System utilities
@api_router.get("/system/info")
async def get_system_info():
    """Получить информацию о системе"""
    return {
        "vnc_management_version": "1.0.0",
        "total_websocket_connections": len(websocket_connections),
        "active_websockets": list(websocket_connections.keys()),
        "system_time": datetime.utcnow(),
        "features": {
            "vnc_viewer": True,
            "file_manager": True,
            "websocket_proxy": True,
            "screenshot_capture": True
        }
    }

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    """Запуск фоновых задач при старте приложения"""
    # Запуск фоновой задачи проверки статусов
    asyncio.create_task(update_connection_status_check())
    logger.info("VNC Management System started with background status checking")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)