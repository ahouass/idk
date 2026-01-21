"""
Servicio de Usuarios - SOA TFG
Este microservicio gestiona los usuarios (estudiantes y tutores).
Puerto: 5002
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import bcrypt
import databases
import sqlalchemy
from sqlalchemy import Table, Column, Integer, String, ForeignKey, create_engine
import os

# Configuración - Fixed path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(DATA_DIR, 'tfg_soa.db')}")

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Tabla de usuarios
usuarios_table = Table(
    "usuarios",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String, unique=True, index=True),
    Column("nombre", String),
    Column("email", String, unique=True),
    Column("password_hash", String),
    Column("rol", String),  # "estudiante" o "tutor"
    Column("tutor_id", Integer, ForeignKey("usuarios.id"), nullable=True),
    Column("fecha_registro", String),
)

app = FastAPI(
    title="Servicio de Usuarios",
    description="Microservicio SOA para gestión de usuarios del sistema TFG",
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
class UsuarioBase(BaseModel):
    nombre: str
    email: str
    username: str
    rol: str
    tutor_id: Optional[int] = None

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioResponse(BaseModel):
    id: int
    username: str
    nombre: str
    email: str
    rol: str
    tutor_id: Optional[int]
    fecha_registro: str

class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None
    tutor_id: Optional[int] = None

class AsignacionTutor(BaseModel):
    estudiante_id: int
    tutor_id: int

# ========== FUNCIONES AUXILIARES ==========
def hash_password(password: str) -> str:
    """Hash de contraseña usando bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()
    
    # Verificar si hay usuarios, si no crear los por defecto
    count = await database.fetch_one("SELECT COUNT(*) as count FROM usuarios")
    if count["count"] == 0:
        await crear_usuarios_iniciales()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

async def crear_usuarios_iniciales():
    """Crear usuarios de demostración"""
    # Tutor por defecto
    tutor_hash = hash_password("tutor123")
    query = usuarios_table.insert().values(
        username="tutor1",
        nombre="Dr. Antonio López",
        email="tutor@usal.es",
        password_hash=tutor_hash,
        rol="tutor",
        fecha_registro=datetime.now().isoformat()
    )
    await database.execute(query)
    
    # Segundo tutor
    tutor2_hash = hash_password("tutor123")
    query = usuarios_table.insert().values(
        username="tutor2",
        nombre="Dra. María Fernández",
        email="tutor2@usal.es",
        password_hash=tutor2_hash,
        rol="tutor",
        fecha_registro=datetime.now().isoformat()
    )
    await database.execute(query)
    
    # Obtener ID del primer tutor
    tutor = await database.fetch_one("SELECT id FROM usuarios WHERE username = 'tutor1'")
    tutor_id = tutor["id"]
    
    # Estudiantes vinculados al tutor 1
    estudiantes = [
        ("estudiante1", "Juan Pérez", "juan@usal.es", "estudiante123"),
        ("estudiante2", "María García", "maria@usal.es", "estudiante123"),
        ("estudiante3", "Carlos López", "carlos@usal.es", "estudiante123"),
    ]
    
    for username, nombre, email, password in estudiantes:
        password_hash = hash_password(password)
        query = usuarios_table.insert().values(
            username=username,
            nombre=nombre,
            email=email,
            password_hash=password_hash,
            rol="estudiante",
            tutor_id=tutor_id,
            fecha_registro=datetime.now().isoformat()
        )
        await database.execute(query)

# ========== ENDPOINTS ==========

@app.get("/health")
async def health_check():
    """Verificar estado del servicio"""
    return {
        "servicio": "usuarios",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/", response_model=dict)
async def crear_usuario(usuario: UsuarioCreate):
    """
    Registrar un nuevo usuario en el sistema.
    Los estudiantes deben estar vinculados a un tutor.
    """
    # Verificar que el username/email no exista
    existing = await database.fetch_one(
        "SELECT id FROM usuarios WHERE username = :username OR email = :email",
        {"username": usuario.username, "email": usuario.email}
    )
    
    if existing:
        raise HTTPException(status_code=400, detail="Username o email ya registrado")
    
    # Validar rol
    if usuario.rol not in ["estudiante", "tutor"]:
        raise HTTPException(status_code=400, detail="Rol debe ser 'estudiante' o 'tutor'")
    
    # Si es estudiante, verificar que tiene tutor asignado
    if usuario.rol == "estudiante":
        if not usuario.tutor_id:
            raise HTTPException(
                status_code=400, 
                detail="Los estudiantes deben tener un tutor asignado"
            )
        
        # Verificar que el tutor existe
        tutor = await database.fetch_one(
            "SELECT id FROM usuarios WHERE id = :id AND rol = 'tutor'",
            {"id": usuario.tutor_id}
        )
        if not tutor:
            raise HTTPException(status_code=404, detail="Tutor no encontrado")
    
    # Hash de contraseña
    password_hash = hash_password(usuario.password)
    
    # Insertar usuario
    query = usuarios_table.insert().values(
        username=usuario.username,
        nombre=usuario.nombre,
        email=usuario.email,
        password_hash=password_hash,
        rol=usuario.rol,
        tutor_id=usuario.tutor_id if usuario.rol == "estudiante" else None,
        fecha_registro=datetime.now().isoformat()
    )
    
    usuario_id = await database.execute(query)
    
    return {
        "mensaje": "Usuario registrado exitosamente",
        "usuario_id": usuario_id,
        "username": usuario.username,
        "rol": usuario.rol
    }

@app.get("/", response_model=List[dict])
async def listar_usuarios(rol: Optional[str] = None):
    """
    Listar todos los usuarios o filtrar por rol.
    """
    query = "SELECT id, username, nombre, email, rol, tutor_id, fecha_registro FROM usuarios"
    if rol:
        query += f" WHERE rol = '{rol}'"
    query += " ORDER BY nombre"
    
    usuarios = await database.fetch_all(query)
    return [dict(u) for u in usuarios]

@app.get("/{usuario_id}")
async def obtener_usuario(usuario_id: int):
    """Obtener información de un usuario específico"""
    usuario = await database.fetch_one(
        "SELECT id, username, nombre, email, rol, tutor_id, fecha_registro FROM usuarios WHERE id = :id",
        {"id": usuario_id}
    )
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    resultado = dict(usuario)
    
    # Si es estudiante, obtener info del tutor
    if usuario["rol"] == "estudiante" and usuario["tutor_id"]:
        tutor = await database.fetch_one(
            "SELECT id, nombre, email FROM usuarios WHERE id = :id",
            {"id": usuario["tutor_id"]}
        )
        if tutor:
            resultado["tutor"] = dict(tutor)
    
    # Si es tutor, obtener sus estudiantes
    if usuario["rol"] == "tutor":
        estudiantes = await database.fetch_all(
            "SELECT id, username, nombre, email FROM usuarios WHERE tutor_id = :tutor_id",
            {"tutor_id": usuario_id}
        )
        resultado["estudiantes"] = [dict(e) for e in estudiantes]
    
    return resultado

@app.put("/{usuario_id}")
async def actualizar_usuario(usuario_id: int, datos: UsuarioUpdate):
    """Actualizar información de un usuario"""
    # Verificar que existe
    usuario = await database.fetch_one(
        "SELECT * FROM usuarios WHERE id = :id",
        {"id": usuario_id}
    )
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Construir query de actualización
    updates = []
    params = {"id": usuario_id}
    
    if datos.nombre:
        updates.append("nombre = :nombre")
        params["nombre"] = datos.nombre
    
    if datos.email:
        # Verificar que el email no esté en uso
        existing = await database.fetch_one(
            "SELECT id FROM usuarios WHERE email = :email AND id != :id",
            {"email": datos.email, "id": usuario_id}
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email ya está en uso")
        updates.append("email = :email")
        params["email"] = datos.email
    
    if datos.tutor_id is not None and usuario["rol"] == "estudiante":
        # Verificar que el tutor existe
        tutor = await database.fetch_one(
            "SELECT id FROM usuarios WHERE id = :tutor_id AND rol = 'tutor'",
            {"tutor_id": datos.tutor_id}
        )
        if not tutor:
            raise HTTPException(status_code=404, detail="Tutor no encontrado")
        updates.append("tutor_id = :tutor_id")
        params["tutor_id"] = datos.tutor_id
    
    if updates:
        query = f"UPDATE usuarios SET {', '.join(updates)} WHERE id = :id"
        await database.execute(query, params)
    
    return {"mensaje": "Usuario actualizado", "usuario_id": usuario_id}

@app.delete("/{usuario_id}")
async def eliminar_usuario(usuario_id: int):
    """Eliminar un usuario del sistema"""
    usuario = await database.fetch_one(
        "SELECT * FROM usuarios WHERE id = :id",
        {"id": usuario_id}
    )
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Si es tutor, verificar que no tenga estudiantes asignados
    if usuario["rol"] == "tutor":
        estudiantes = await database.fetch_one(
            "SELECT COUNT(*) as count FROM usuarios WHERE tutor_id = :id",
            {"id": usuario_id}
        )
        if estudiantes["count"] > 0:
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar un tutor con estudiantes asignados"
            )
    
    await database.execute("DELETE FROM usuarios WHERE id = :id", {"id": usuario_id})
    
    return {"mensaje": "Usuario eliminado", "usuario_id": usuario_id}

# ========== ENDPOINTS DE TUTORES ==========

@app.get("/tutores/lista")
async def listar_tutores():
    """Obtener lista de todos los tutores disponibles"""
    tutores = await database.fetch_all(
        "SELECT id, nombre, email FROM usuarios WHERE rol = 'tutor' ORDER BY nombre"
    )
    return [dict(t) for t in tutores]

@app.get("/tutores/{tutor_id}/estudiantes")
async def obtener_estudiantes_tutor(tutor_id: int):
    """Obtener todos los estudiantes asignados a un tutor"""
    # Verificar que el tutor existe
    tutor = await database.fetch_one(
        "SELECT id, nombre, email FROM usuarios WHERE id = :id AND rol = 'tutor'",
        {"id": tutor_id}
    )
    
    if not tutor:
        raise HTTPException(status_code=404, detail="Tutor no encontrado")
    
    estudiantes = await database.fetch_all(
        "SELECT id, username, nombre, email, fecha_registro FROM usuarios WHERE tutor_id = :tutor_id",
        {"tutor_id": tutor_id}
    )
    
    return {
        "tutor": dict(tutor),
        "estudiantes": [dict(e) for e in estudiantes],
        "total": len(estudiantes)
    }

@app.post("/tutores/asignar")
async def asignar_tutor(asignacion: AsignacionTutor):
    """Asignar un tutor a un estudiante"""
    # Verificar estudiante
    estudiante = await database.fetch_one(
        "SELECT * FROM usuarios WHERE id = :id AND rol = 'estudiante'",
        {"id": asignacion.estudiante_id}
    )
    
    if not estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    
    # Verificar tutor
    tutor = await database.fetch_one(
        "SELECT * FROM usuarios WHERE id = :id AND rol = 'tutor'",
        {"id": asignacion.tutor_id}
    )
    
    if not tutor:
        raise HTTPException(status_code=404, detail="Tutor no encontrado")
    
    # Actualizar asignación
    await database.execute(
        "UPDATE usuarios SET tutor_id = :tutor_id WHERE id = :estudiante_id",
        {"tutor_id": asignacion.tutor_id, "estudiante_id": asignacion.estudiante_id}
    )
    
    return {
        "mensaje": "Tutor asignado correctamente",
        "estudiante_id": asignacion.estudiante_id,
        "tutor_id": asignacion.tutor_id
    }

@app.get("/info")
async def service_info():
    """Información del servicio"""
    return {
        "nombre": "Servicio de Usuarios",
        "descripcion": "Gestiona usuarios (estudiantes y tutores) del sistema",
        "endpoints": [
            {"ruta": "/", "metodo": "GET", "descripcion": "Listar usuarios"},
            {"ruta": "/", "metodo": "POST", "descripcion": "Crear usuario"},
            {"ruta": "/{id}", "metodo": "GET", "descripcion": "Obtener usuario"},
            {"ruta": "/{id}", "metodo": "PUT", "descripcion": "Actualizar usuario"},
            {"ruta": "/{id}", "metodo": "DELETE", "descripcion": "Eliminar usuario"},
            {"ruta": "/tutores/lista", "metodo": "GET", "descripcion": "Listar tutores"},
            {"ruta": "/tutores/{id}/estudiantes", "metodo": "GET", "descripcion": "Estudiantes de un tutor"},
            {"ruta": "/tutores/asignar", "metodo": "POST", "descripcion": "Asignar tutor"},
            {"ruta": "/health", "metodo": "GET", "descripcion": "Estado del servicio"}
        ],
        "puerto": 5002
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)
