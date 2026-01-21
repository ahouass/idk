"""
Servicio de Autenticación - SOA TFG
Este microservicio gestiona el inicio de sesión y la generación de tokens.
Puerto: 5001
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import bcrypt
import uuid
import databases
import sqlalchemy
from sqlalchemy import Table, Column, Integer, String, create_engine
import os
import jwt

# Configuración
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///../../../data/tfg_soa.db")
SECRET_KEY = os.getenv("SECRET_KEY", "tfg-soa-secret-key-2026")
TOKEN_EXPIRATION_HOURS = 24

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Tabla de usuarios (solo para lectura en auth)
usuarios_table = Table(
    "usuarios",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String, unique=True, index=True),
    Column("nombre", String),
    Column("email", String, unique=True),
    Column("password_hash", String),
    Column("rol", String),
    Column("tutor_id", Integer, nullable=True),
    Column("fecha_registro", String),
)

# Tabla de tokens activos
tokens_table = Table(
    "tokens",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("usuario_id", Integer),
    Column("token", String, unique=True),
    Column("fecha_creacion", String),
    Column("fecha_expiracion", String),
    Column("activo", Integer, default=1),
)

app = FastAPI(
    title="Servicio de Autenticación",
    description="Microservicio SOA para autenticación de usuarios del sistema TFG",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== MODELOS ==========
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    token: str
    tipo: str = "Bearer"
    expira_en: str
    usuario: dict

class ValidateTokenRequest(BaseModel):
    token: str

# ========== FUNCIONES AUXILIARES ==========
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar contraseña usando bcrypt"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except:
        return False

def create_token(usuario_id: int, username: str, rol: str) -> str:
    """Crear JWT token"""
    expiration = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRATION_HOURS)
    payload = {
        "sub": str(usuario_id),
        "username": username,
        "rol": rol,
        "exp": expiration,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token: str) -> Optional[dict]:
    """Decodificar y validar JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ========== ENDPOINTS ==========

@app.get("/health")
async def health_check():
    """Verificar estado del servicio de autenticación"""
    return {
        "servicio": "auth",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Iniciar sesión con credenciales de usuario.
    Retorna un token JWT para autenticación posterior.
    """
    # Buscar usuario
    query = "SELECT * FROM usuarios WHERE username = :username"
    usuario = await database.fetch_one(query, {"username": request.username})
    
    if not usuario:
        raise HTTPException(
            status_code=401,
            detail="Credenciales inválidas"
        )
    
    # Verificar contraseña
    if not verify_password(request.password, usuario["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Credenciales inválidas"
        )
    
    # Generar token
    token = create_token(usuario["id"], usuario["username"], usuario["rol"])
    expiracion = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRATION_HOURS)
    
    # Preparar respuesta del usuario (sin password)
    usuario_response = {
        "id": usuario["id"],
        "username": usuario["username"],
        "nombre": usuario["nombre"],
        "email": usuario["email"],
        "rol": usuario["rol"],
        "tutor_id": usuario["tutor_id"]
    }
    
    return TokenResponse(
        token=token,
        tipo="Bearer",
        expira_en=expiracion.isoformat(),
        usuario=usuario_response
    )

@app.post("/validate")
async def validate_token(request: ValidateTokenRequest):
    """
    Validar un token JWT.
    Usado por otros servicios para verificar autenticación.
    """
    payload = decode_token(request.token)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Token inválido o expirado"
        )
    
    return {
        "valido": True,
        "usuario_id": payload["sub"],
        "username": payload["username"],
        "rol": payload["rol"],
        "expira": payload["exp"]
    }

@app.post("/logout")
async def logout(request: ValidateTokenRequest):
    """
    Cerrar sesión (invalidar token).
    En una implementación completa, agregaría el token a una lista negra.
    """
    # Validar que el token existe
    payload = decode_token(request.token)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Token inválido"
        )
    
    return {
        "mensaje": "Sesión cerrada exitosamente",
        "usuario": payload["username"]
    }

@app.get("/info")
async def service_info():
    """Información del servicio"""
    return {
        "nombre": "Servicio de Autenticación",
        "descripcion": "Gestiona la autenticación mediante tokens JWT",
        "endpoints": [
            {"ruta": "/login", "metodo": "POST", "descripcion": "Iniciar sesión"},
            {"ruta": "/validate", "metodo": "POST", "descripcion": "Validar token"},
            {"ruta": "/logout", "metodo": "POST", "descripcion": "Cerrar sesión"},
            {"ruta": "/health", "metodo": "GET", "descripcion": "Estado del servicio"}
        ],
        "puerto": 5001
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
