"""
Servicio de Archivos - SOA TFG
Este microservicio gestiona la subida de archivos y el feedback de tutores.
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
from sqlalchemy import Table, Column, Integer, String, ForeignKey, create_engine
import os
import shutil
import uuid

# Configuración
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///../../../data/tfg_soa.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "../../../uploads")
NOTIFICATIONS_SERVICE = os.getenv("NOTIFICATIONS_SERVICE", "http://localhost:5005")

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Tabla de archivos
archivos_table = Table(
    "archivos",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre_original", String),
    Column("nombre_guardado", String),
    Column("ruta", String),
    Column("tipo", String),  # pdf o zip
    Column("tamanio", Integer),
    Column("estudiante_id", Integer),
    Column("tutor_id", Integer),
    Column("fecha_subida", String),
    Column("feedback", String, default=""),
    Column("fecha_feedback", String, nullable=True),
    Column("estado", String, default="pendiente"),  # pendiente, revisado, necesita_cambios
)

app = FastAPI(
    title="Servicio de Archivos",
    description="Microservicio SOA para gestión de entregas de archivos del sistema TFG",
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
class FeedbackRequest(BaseModel):
    feedback: str
    tutor_id: int
    estado: Optional[str] = "revisado"  # revisado, necesita_cambios

class ArchivoResponse(BaseModel):
    id: int
    nombre_original: str
    tipo: str
    estudiante_id: int
    tutor_id: int
    fecha_subida: str
    feedback: Optional[str]
    fecha_feedback: Optional[str]
    estado: str

# ========== FUNCIONES AUXILIARES ==========
def crear_directorio_uploads():
    """Crear directorio de uploads si no existe"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)

def es_extension_permitida(filename: str) -> bool:
    """Verificar si la extensión del archivo es permitida"""
    return filename.lower().endswith(('.pdf', '.zip'))

def obtener_tipo_archivo(filename: str) -> str:
    """Obtener tipo de archivo basado en extensión"""
    if filename.lower().endswith('.pdf'):
        return 'pdf'
    elif filename.lower().endswith('.zip'):
        return 'zip'
    return 'desconocido'

async def notificar_nuevo_archivo(estudiante_id: int, tutor_id: int, nombre_archivo: str):
    """Enviar notificación cuando se sube un nuevo archivo"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{NOTIFICATIONS_SERVICE}/",
                json={
                    "tipo": "archivo_nuevo",
                    "usuario_destino_id": tutor_id,
                    "usuario_origen_id": estudiante_id,
                    "mensaje": f"Nuevo archivo subido: {nombre_archivo}",
                    "referencia_tipo": "archivo",
                    "referencia_id": 0
                }
            )
    except Exception as e:
        print(f"Error enviando notificación: {e}")

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()
    crear_directorio_uploads()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ========== ENDPOINTS ==========

@app.get("/health")
async def health_check():
    """Verificar estado del servicio"""
    return {
        "servicio": "archivos",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "upload_dir": UPLOAD_DIR
    }

@app.post("/subir")
async def subir_archivo(
    estudiante_id: int = Form(...),
    tutor_id: int = Form(...),
    file: UploadFile = File(...)
):
    """
    Subir un nuevo archivo (PDF o ZIP).
    El estudiante debe especificar su ID y el ID de su tutor.
    """
    # Verificar extensión
    if not es_extension_permitida(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Solo se permiten archivos PDF o ZIP"
        )
    
    # Generar nombre único para el archivo
    extension = file.filename.split('.')[-1].lower()
    nombre_guardado = f"{estudiante_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{extension}"
    ruta_archivo = os.path.join(UPLOAD_DIR, nombre_guardado)
    
    # Guardar archivo
    try:
        crear_directorio_uploads()
        with open(ruta_archivo, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            tamanio = len(content)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error guardando archivo: {str(e)}"
        )
    
    # Insertar registro en base de datos
    query = archivos_table.insert().values(
        nombre_original=file.filename,
        nombre_guardado=nombre_guardado,
        ruta=ruta_archivo,
        tipo=obtener_tipo_archivo(file.filename),
        tamanio=tamanio,
        estudiante_id=estudiante_id,
        tutor_id=tutor_id,
        fecha_subida=datetime.now().isoformat(),
        feedback="",
        fecha_feedback=None,
        estado="pendiente"
    )
    
    archivo_id = await database.execute(query)
    
    # Notificar al tutor
    await notificar_nuevo_archivo(estudiante_id, tutor_id, file.filename)
    
    return {
        "mensaje": "Archivo subido exitosamente",
        "archivo_id": archivo_id,
        "nombre_original": file.filename,
        "nombre_guardado": nombre_guardado,
        "tipo": obtener_tipo_archivo(file.filename),
        "tamanio_bytes": tamanio
    }

@app.get("/estudiante/{estudiante_id}")
async def obtener_archivos_estudiante(estudiante_id: int):
    """Obtener todos los archivos subidos por un estudiante"""
    archivos = await database.fetch_all(
        """SELECT id, nombre_original, tipo, estudiante_id, tutor_id, 
           fecha_subida, feedback, fecha_feedback, estado, tamanio
           FROM archivos WHERE estudiante_id = :estudiante_id 
           ORDER BY fecha_subida DESC""",
        {"estudiante_id": estudiante_id}
    )
    
    return {
        "estudiante_id": estudiante_id,
        "archivos": [dict(a) for a in archivos],
        "total": len(archivos)
    }

@app.get("/tutor/{tutor_id}")
async def obtener_archivos_tutor(tutor_id: int, estado: Optional[str] = None):
    """
    Obtener todos los archivos asignados a un tutor.
    Opcionalmente filtrar por estado (pendiente, revisado, necesita_cambios).
    """
    query = """SELECT a.*, u.nombre as estudiante_nombre, u.username as estudiante_username
               FROM archivos a 
               JOIN usuarios u ON a.estudiante_id = u.id
               WHERE a.tutor_id = :tutor_id"""
    
    params = {"tutor_id": tutor_id}
    
    if estado:
        query += " AND a.estado = :estado"
        params["estado"] = estado
    
    query += " ORDER BY a.fecha_subida DESC"
    
    archivos = await database.fetch_all(query, params)
    
    # Contar por estado
    estados = await database.fetch_all(
        """SELECT estado, COUNT(*) as count FROM archivos 
           WHERE tutor_id = :tutor_id GROUP BY estado""",
        {"tutor_id": tutor_id}
    )
    
    return {
        "tutor_id": tutor_id,
        "archivos": [dict(a) for a in archivos],
        "total": len(archivos),
        "por_estado": {e["estado"]: e["count"] for e in estados}
    }

@app.get("/{archivo_id}")
async def obtener_archivo(archivo_id: int):
    """Obtener información de un archivo específico"""
    archivo = await database.fetch_one(
        "SELECT * FROM archivos WHERE id = :id",
        {"id": archivo_id}
    )
    
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    return dict(archivo)

@app.get("/{archivo_id}/descargar")
async def descargar_archivo(archivo_id: int):
    """Descargar un archivo"""
    archivo = await database.fetch_one(
        "SELECT * FROM archivos WHERE id = :id",
        {"id": archivo_id}
    )
    
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    ruta = archivo["ruta"]
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Archivo físico no encontrado")
    
    return FileResponse(
        path=ruta,
        filename=archivo["nombre_original"],
        media_type="application/octet-stream"
    )

@app.post("/{archivo_id}/feedback")
async def agregar_feedback(archivo_id: int, request: FeedbackRequest):
    """
    Agregar feedback a un archivo (solo tutores).
    El tutor puede marcar como "revisado" o "necesita_cambios".
    """
    # Verificar que el archivo existe y pertenece al tutor
    archivo = await database.fetch_one(
        "SELECT * FROM archivos WHERE id = :id AND tutor_id = :tutor_id",
        {"id": archivo_id, "tutor_id": request.tutor_id}
    )
    
    if not archivo:
        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado o no autorizado"
        )
    
    # Validar estado
    if request.estado not in ["revisado", "necesita_cambios"]:
        request.estado = "revisado"
    
    # Actualizar feedback
    await database.execute(
        """UPDATE archivos 
           SET feedback = :feedback, fecha_feedback = :fecha, estado = :estado 
           WHERE id = :id""",
        {
            "feedback": request.feedback,
            "fecha": datetime.now().isoformat(),
            "estado": request.estado,
            "id": archivo_id
        }
    )
    
    # Notificar al estudiante
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{NOTIFICATIONS_SERVICE}/",
                json={
                    "tipo": "feedback_nuevo",
                    "usuario_destino_id": archivo["estudiante_id"],
                    "usuario_origen_id": request.tutor_id,
                    "mensaje": f"Tu archivo '{archivo['nombre_original']}' ha sido revisado: {request.estado}",
                    "referencia_tipo": "archivo",
                    "referencia_id": archivo_id
                }
            )
    except Exception as e:
        print(f"Error enviando notificación: {e}")
    
    return {
        "mensaje": "Feedback agregado",
        "archivo_id": archivo_id,
        "estado": request.estado
    }

@app.delete("/{archivo_id}")
async def eliminar_archivo(archivo_id: int, estudiante_id: int):
    """Eliminar un archivo (solo el estudiante propietario)"""
    archivo = await database.fetch_one(
        "SELECT * FROM archivos WHERE id = :id AND estudiante_id = :estudiante_id",
        {"id": archivo_id, "estudiante_id": estudiante_id}
    )
    
    if not archivo:
        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado o no autorizado"
        )
    
    # Eliminar archivo físico
    if os.path.exists(archivo["ruta"]):
        os.remove(archivo["ruta"])
    
    # Eliminar registro
    await database.execute("DELETE FROM archivos WHERE id = :id", {"id": archivo_id})
    
    return {"mensaje": "Archivo eliminado", "archivo_id": archivo_id}

@app.get("/historial/{estudiante_id}")
async def historial_archivos(estudiante_id: int):
    """
    Obtener historial completo de archivos con fechas y estados.
    Útil para ver el progreso del estudiante.
    """
    archivos = await database.fetch_all(
        """SELECT id, nombre_original, tipo, fecha_subida, feedback, 
           fecha_feedback, estado, tamanio
           FROM archivos WHERE estudiante_id = :estudiante_id 
           ORDER BY fecha_subida ASC""",
        {"estudiante_id": estudiante_id}
    )
    
    return {
        "estudiante_id": estudiante_id,
        "historial": [dict(a) for a in archivos],
        "total_entregas": len(archivos),
        "ultima_entrega": archivos[-1]["fecha_subida"] if archivos else None
    }

@app.get("/info")
async def service_info():
    """Información del servicio"""
    return {
        "nombre": "Servicio de Archivos",
        "descripcion": "Gestiona la subida de archivos y feedback de tutores",
        "formatos_permitidos": ["PDF", "ZIP"],
        "endpoints": [
            {"ruta": "/subir", "metodo": "POST", "descripcion": "Subir archivo"},
            {"ruta": "/estudiante/{id}", "metodo": "GET", "descripcion": "Archivos del estudiante"},
            {"ruta": "/tutor/{id}", "metodo": "GET", "descripcion": "Archivos del tutor"},
            {"ruta": "/{id}", "metodo": "GET", "descripcion": "Info de archivo"},
            {"ruta": "/{id}/descargar", "metodo": "GET", "descripcion": "Descargar archivo"},
            {"ruta": "/{id}/feedback", "metodo": "POST", "descripcion": "Agregar feedback"},
            {"ruta": "/historial/{id}", "metodo": "GET", "descripcion": "Historial de entregas"},
            {"ruta": "/health", "metodo": "GET", "descripcion": "Estado del servicio"}
        ],
        "puerto": 5003
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5003)
