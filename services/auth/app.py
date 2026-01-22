"""
Servicio de Autenticación - SOA TFG
Este microservicio gestiona la autenticación y tokens JWT.
Puerto: 5001
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
import databases
import sqlalchemy
import os

# Configuración - Fixed path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'tfg_soa.db')}"

# JWT Config
SECRET_KEY = os.getenv("SECRET_KEY", "tfg-soa-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Tabla de usuarios (solo para consulta, la creación está en users service)
usuarios_table = sqlalchemy.Table(
    "usuarios",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("username", sqlalchemy.String, unique=True),
    sqlalchemy.Column("nombre", sqlalchemy.String),
    sqlalchemy.Column("email", sqlalchemy.String, unique=True),
    sqlalchemy.Column("password_hash", sqlalchemy.String),
    sqlalchemy.Column("rol", sqlalchemy.String),
    sqlalchemy.Column("tutor_id", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("fecha_registro", sqlalchemy.String),
)

# Crear tablas
engine = sqlalchemy.create_engine(DATABASE_URL.replace("sqlite:///", "sqlite:///"))
metadata.create_all(engine)

app = FastAPI(
    title="Servicio de Autenticación",
    description="Microservicio SOA para autenticación y gestión de tokens JWT",
    version="1.0.0"
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
    access_token: str
    token_type: str
    usuario: dict

class ValidateRequest(BaseModel):
    token: str

# ========== FUNCIONES ==========
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar contraseña"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Crear token JWT"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """Decodificar token JWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()
    print(f"✅ Auth Service conectado a: {DATABASE_URL}")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ========== ENDPOINTS ==========
@app.get("/health")
async def health():
    """Health check"""
    return {
        "servicio": "auth",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/login")
async def login(request: LoginRequest):
    """Login y obtener token"""
    query = "SELECT * FROM usuarios WHERE username = :username"
    usuario = await database.fetch_one(query, {"username": request.username})
    
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    
    if not verify_password(request.password, usuario["password_hash"]):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    
    # Crear token
    token_data = {
        "sub": str(usuario["id"]),
        "username": usuario["username"],
        "rol": usuario["rol"]
    }
    access_token = create_access_token(token_data)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "usuario": {
            "id": usuario["id"],
            "username": usuario["username"],
            "nombre": usuario["nombre"],
            "email": usuario["email"],
            "rol": usuario["rol"],
            "tutor_id": usuario["tutor_id"]
        }
    }

@app.post("/validate")
async def validate_token(request: ValidateRequest):
    """Validar token JWT"""
    payload = decode_token(request.token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    
    return {
        "valid": True,
        "user_id": payload.get("sub"),
        "username": payload.get("username"),
        "rol": payload.get("rol")
    }

@app.get("/info")
async def info():
    """Información del servicio"""
    return {
        "servicio": "Autenticación",
        "puerto": 5001,
        "endpoints": ["/health", "/login", "/validate", "/info"]
    }

if __name__ == "__main__":
    import uvicorn
    print("🔐 Iniciando Servicio de Autenticación...")
    uvicorn.run(app, host="0.0.0.0", port=5001)