"""
Servicio de Archivos - SOA TFG
Este microservicio gestiona los archivos (entregas) de los estudiantes.
Puerto: 5003
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import databases
import sqlalchemy
import os
import shutil
import httpx

# Configuración - Fixed paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

# Create directories
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'tfg_soa.db')}"
NOTIFICATIONS_SERVICE = os.getenv("NOTIFICATIONS_SERVICE", "http://localhost:5005")

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Tabla de archivos
archivos_table = sqlalchemy.Table(
    "archivos",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("estudiante_id", sqlalchemy.Integer),
    sqlalchemy.Column("nombre_original", sqlalchemy.String),
    sqlalchemy.Column("nombre_guardado", sqlalchemy.String),
    sqlalchemy.Column("ruta", sqlalchemy.String),
    sqlalchemy.Column("tipo", sqlalchemy.String),
    sqlalchemy.Column("tamano", sqlalchemy.Integer),
    sqlalchemy.Column("fecha_subida", sqlalchemy.String),
    sqlalchemy.Column("estado", sqlalchemy.String, default="pendiente"),
    sqlalchemy.Column("feedback", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("tutor_id", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("fecha_feedback", sqlalchemy.String, nullable=True),
)

# Crear tablas
engine = sqlalchemy.create_engine(DATABASE_URL.replace("sqlite:///", "sqlite:///"))
metadata.create_all(engine)

app = FastAPI(
    title="Servicio de Archivos",
    description="Microservicio SOA para gestión de archivos y entregas",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Extensiones permitidas
ALLOWED_EXTENSIONS = {".pdf", ".zip"}

def allowed_file(filename: str) -> bool:
    """Verificar si el archivo tiene extensión permitida"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

async def get_user_role(user_id: int) -> Optional[str]:
    """Obtener el rol de un usuario"""
    try:
        query = "SELECT rol FROM usuarios WHERE id = :id"
        user = await database.fetch_one(query, {"id": user_id})
        if user:
            return user["rol"]
        return None
    except Exception as e:
        print(f"Error obteniendo rol: {e}")
        return None

async def is_tutor_of_student(tutor_id: int, estudiante_id: int) -> bool:
    """Verificar si un tutor tiene asignado a un estudiante"""
    try:
        query = "SELECT tutor_id FROM usuarios WHERE id = :estudiante_id"
        student = await database.fetch_one(query, {"estudiante_id": estudiante_id})
        if student and student["tutor_id"] == tutor_id:
            return True
        return False
    except Exception as e:
        print(f"Error verificando relación tutor-estudiante: {e}")
        return False

async def notify_tutor(estudiante_id: int, archivo_nombre: str):
    """Notificar al tutor sobre nuevo archivo"""
    try:
        # Obtener tutor_id del estudiante
        query = "SELECT tutor_id, nombre FROM usuarios WHERE id = :id"
        estudiante = await database.fetch_one(query, {"id": estudiante_id})
        
        if estudiante and estudiante["tutor_id"]:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{NOTIFICATIONS_SERVICE}/", json={
                    "usuario_id": estudiante["tutor_id"],
                    "tipo": "archivo",
                    "mensaje": f"Nuevo archivo subido por {estudiante['nombre']}: {archivo_nombre}",
                    "datos": {"estudiante_id": estudiante_id, "archivo": archivo_nombre}
                })
    except Exception as e:
        print(f"Error notificando: {e}")

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()
    print(f"✅ Files Service conectado a: {DATABASE_URL}")
    print(f"📁 Directorio de uploads: {UPLOAD_DIR}")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ========== ENDPOINTS ==========
@app.get("/health")
async def health():
    """Health check"""
    return {
        "servicio": "archivos",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "upload_dir": UPLOAD_DIR
    }

@app.post("/subir")
async def subir_archivo(estudiante_id: int = Form(...), file: UploadFile = File(...)):
    """Subir un archivo (PDF o ZIP) - SOLO ESTUDIANTES"""
    
    # Verificar que el que sube es un estudiante
    rol = await get_user_role(estudiante_id)
    if rol != "estudiante":
        raise HTTPException(
            status_code=403, 
            detail="Solo los estudiantes pueden subir archivos"
        )
    
    # Validar extensión
    if not allowed_file(file.filename):
        raise HTTPException(
            status_code=400, 
            detail=f"Tipo de archivo no permitido. Solo se permiten: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Crear nombre único
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = os.path.splitext(file.filename)[1].lower()
    nombre_guardado = f"{estudiante_id}_{timestamp}{ext}"
    ruta_archivo = os.path.join(UPLOAD_DIR, nombre_guardado)
    
    try:
        # Guardar archivo
        with open(ruta_archivo, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Obtener tamaño
        tamano = os.path.getsize(ruta_archivo)
        
        # Guardar en base de datos
        query = archivos_table.insert().values(
            estudiante_id=estudiante_id,
            nombre_original=file.filename,
            nombre_guardado=nombre_guardado,
            ruta=ruta_archivo,
            tipo=ext.replace(".", ""),
            tamano=tamano,
            fecha_subida=datetime.now().isoformat(),
            estado="pendiente"
        )
        archivo_id = await database.execute(query)
        
        # Notificar al tutor
        await notify_tutor(estudiante_id, file.filename)
        
        return {
            "mensaje": "Archivo subido correctamente",
            "archivo": {
                "id": archivo_id,
                "nombre": file.filename,
                "tamano": tamano,
                "tipo": ext.replace(".", ""),
                "estado": "pendiente"
            }
        }
        
    except Exception as e:
        # Limpiar archivo si hubo error
        if os.path.exists(ruta_archivo):
            os.remove(ruta_archivo)
        raise HTTPException(status_code=500, detail=f"Error subiendo archivo: {str(e)}")

@app.get("/estudiante/{estudiante_id}")
async def archivos_estudiante(estudiante_id: int):
    """Obtener archivos de un estudiante"""
    query = "SELECT * FROM archivos WHERE estudiante_id = :estudiante_id ORDER BY fecha_subida DESC"
    archivos = await database.fetch_all(query, {"estudiante_id": estudiante_id})
    
    return [dict(a) for a in archivos]

@app.get("/tutor/{tutor_id}")
async def archivos_tutor(tutor_id: int, estado: Optional[str] = None):
    """Obtener archivos de estudiantes de un tutor"""
    # Verificar que es un tutor
    rol = await get_user_role(tutor_id)
    if rol != "tutor":
        raise HTTPException(
            status_code=403, 
            detail="Solo los tutores pueden acceder a esta información"
        )
    
    # Primero obtener estudiantes del tutor
    query_estudiantes = "SELECT id FROM usuarios WHERE tutor_id = :tutor_id"
    estudiantes = await database.fetch_all(query_estudiantes, {"tutor_id": tutor_id})
    
    if not estudiantes:
        return []
    
    estudiante_ids = [e["id"] for e in estudiantes]
    
    # Obtener archivos
    if estado:
        query = f"SELECT * FROM archivos WHERE estudiante_id IN ({','.join(map(str, estudiante_ids))}) AND estado = :estado ORDER BY fecha_subida DESC"
        archivos = await database.fetch_all(query, {"estado": estado})
    else:
        query = f"SELECT * FROM archivos WHERE estudiante_id IN ({','.join(map(str, estudiante_ids))}) ORDER BY fecha_subida DESC"
        archivos = await database.fetch_all(query)
    
    return [dict(a) for a in archivos]

@app.get("/{archivo_id}")
async def obtener_archivo(archivo_id: int):
    """Obtener información de un archivo"""
    query = "SELECT * FROM archivos WHERE id = :id"
    archivo = await database.fetch_one(query, {"id": archivo_id})
    
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    return dict(archivo)

@app.get("/{archivo_id}/descargar")
async def descargar_archivo(archivo_id: int, usuario_id: int):
    """Descargar un archivo - SOLO el estudiante dueño o su tutor"""
    query = "SELECT * FROM archivos WHERE id = :id"
    archivo = await database.fetch_one(query, {"id": archivo_id})
    
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    # Verificar permisos
    rol = await get_user_role(usuario_id)
    
    if rol == "estudiante":
        # El estudiante solo puede descargar sus propios archivos
        if archivo["estudiante_id"] != usuario_id:
            raise HTTPException(
                status_code=403, 
                detail="No tienes permiso para descargar este archivo"
            )
    elif rol == "tutor":
        # El tutor solo puede descargar archivos de sus estudiantes
        is_his_student = await is_tutor_of_student(usuario_id, archivo["estudiante_id"])
        if not is_his_student:
            raise HTTPException(
                status_code=403, 
                detail="Solo puedes descargar archivos de tus estudiantes"
            )
    else:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permiso para descargar archivos"
        )
    
    if not os.path.exists(archivo["ruta"]):
        raise HTTPException(status_code=404, detail="Archivo físico no encontrado")
    
    return FileResponse(
        path=archivo["ruta"],
        filename=archivo["nombre_original"],
        media_type="application/octet-stream"
    )

@app.post("/{archivo_id}/feedback")
async def agregar_feedback(archivo_id: int, feedback: str = Form(...), tutor_id: int = Form(...), estado: str = Form("revisado")):
    """Agregar feedback a un archivo - SOLO TUTORES"""
    
    # Verificar que es un tutor
    rol = await get_user_role(tutor_id)
    if rol != "tutor":
        raise HTTPException(
            status_code=403, 
            detail="Solo los tutores pueden dar feedback"
        )
    
    # Verificar que el archivo existe
    query = "SELECT * FROM archivos WHERE id = :id"
    archivo = await database.fetch_one(query, {"id": archivo_id})
    
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    # Verificar que el tutor tiene asignado a este estudiante
    is_his_student = await is_tutor_of_student(tutor_id, archivo["estudiante_id"])
    if not is_his_student:
        raise HTTPException(
            status_code=403, 
            detail="Solo puedes dar feedback a archivos de tus estudiantes"
        )
    
    # Actualizar archivo
    update_query = """
        UPDATE archivos 
        SET feedback = :feedback, tutor_id = :tutor_id, estado = :estado, fecha_feedback = :fecha
        WHERE id = :id
    """
    await database.execute(update_query, {
        "feedback": feedback,
        "tutor_id": tutor_id,
        "estado": estado,
        "fecha": datetime.now().isoformat(),
        "id": archivo_id
    })
    
    # Notificar al estudiante
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{NOTIFICATIONS_SERVICE}/", json={
                "usuario_id": archivo["estudiante_id"],
                "tipo": "feedback",
                "mensaje": f"Tu archivo '{archivo['nombre_original']}' ha sido revisado: {feedback[:50]}...",
                "datos": {"archivo_id": archivo_id, "estado": estado}
            })
    except Exception as e:
        print(f"Error notificando: {e}")
    
    return {"mensaje": "Feedback agregado correctamente", "estado": estado}

@app.delete("/{archivo_id}")
async def eliminar_archivo(archivo_id: int, usuario_id: int):
    """Eliminar un archivo - SOLO el estudiante dueño"""
    query = "SELECT * FROM archivos WHERE id = :id"
    archivo = await database.fetch_one(query, {"id": archivo_id})
    
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    # Verificar que el que elimina es el dueño del archivo
    if archivo["estudiante_id"] != usuario_id:
        raise HTTPException(
            status_code=403, 
            detail="Solo puedes eliminar tus propios archivos"
        )
    
    # Eliminar archivo físico
    if os.path.exists(archivo["ruta"]):
        os.remove(archivo["ruta"])
    
    # Eliminar de base de datos
    delete_query = "DELETE FROM archivos WHERE id = :id"
    await database.execute(delete_query, {"id": archivo_id})
    
    return {"mensaje": "Archivo eliminado correctamente"}

@app.get("/info")
async def info():
    """Información del servicio"""
    return {
        "servicio": "Archivos",
        "puerto": 5003,
        "extensiones_permitidas": list(ALLOWED_EXTENSIONS),
        "directorio_uploads": UPLOAD_DIR,
        "endpoints": ["/health", "/subir", "/estudiante/{id}", "/tutor/{id}", "/{id}/feedback", "/{id}/descargar"]
    }

if __name__ == "__main__":
    import uvicorn
    print("📁 Iniciando Servicio de Archivos...")
    uvicorn.run(app, host="0.0.0.0", port=5003)