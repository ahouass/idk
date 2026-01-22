"""
Servicio de Citas - SOA TFG
Este microservicio gestiona las citas de tutorías.
Puerto: 5004
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import databases
import sqlalchemy
import os
import httpx

# Configuración - Fixed paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'tfg_soa.db')}"
NOTIFICATIONS_SERVICE = os.getenv("NOTIFICATIONS_SERVICE", "http://localhost:5005")

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Tabla de citas
citas_table = sqlalchemy.Table(
    "citas",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("estudiante_id", sqlalchemy.Integer),
    sqlalchemy.Column("tutor_id", sqlalchemy.Integer),
    sqlalchemy.Column("fecha", sqlalchemy.String),
    sqlalchemy.Column("hora", sqlalchemy.String),
    sqlalchemy.Column("motivo", sqlalchemy.String),
    sqlalchemy.Column("estado", sqlalchemy.String, default="pendiente"),
    sqlalchemy.Column("motivo_rechazo", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("fecha_solicitud", sqlalchemy.String),
    sqlalchemy.Column("fecha_respuesta", sqlalchemy.String, nullable=True),
)

# Crear tablas
engine = sqlalchemy.create_engine(DATABASE_URL.replace("sqlite:///", "sqlite:///"))
metadata.create_all(engine)

app = FastAPI(
    title="Servicio de Citas",
    description="Microservicio SOA para gestión de citas de tutorías",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== MODELOS ==========
class CitaSolicitud(BaseModel):
    estudiante_id: int
    tutor_id: int
    fecha: str
    hora: str
    motivo: str

class CitaRespuesta(BaseModel):
    tutor_id: int
    motivo_rechazo: Optional[str] = None

# ========== FUNCIONES ==========
async def notificar(usuario_id: int, tipo: str, mensaje: str, datos: dict = None):
    """Enviar notificación"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{NOTIFICATIONS_SERVICE}/", json={
                "usuario_id": usuario_id,
                "tipo": tipo,
                "mensaje": mensaje,
                "datos": datos or {}
            })
    except Exception as e:
        print(f"Error notificando: {e}")

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()
    print(f"✅ Appointments Service conectado a: {DATABASE_URL}")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ========== ENDPOINTS ==========
@app.get("/health")
async def health():
    """Health check"""
    return {
        "servicio": "citas",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/solicitar")
async def solicitar_cita(cita: CitaSolicitud):
    """Solicitar una nueva cita"""
    
    # Verificar que no haya cita duplicada
    query_check = """
        SELECT * FROM citas 
        WHERE estudiante_id = :estudiante_id 
        AND tutor_id = :tutor_id 
        AND fecha = :fecha 
        AND hora = :hora 
        AND estado = 'pendiente'
    """
    existente = await database.fetch_one(query_check, {
        "estudiante_id": cita.estudiante_id,
        "tutor_id": cita.tutor_id,
        "fecha": cita.fecha,
        "hora": cita.hora
    })
    
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe una cita pendiente para esa fecha y hora")
    
    # Crear cita
    query = citas_table.insert().values(
        estudiante_id=cita.estudiante_id,
        tutor_id=cita.tutor_id,
        fecha=cita.fecha,
        hora=cita.hora,
        motivo=cita.motivo,
        estado="pendiente",
        fecha_solicitud=datetime.now().isoformat()
    )
    cita_id = await database.execute(query)
    
    # Notificar al tutor
    await notificar(
        cita.tutor_id,
        "cita",
        f"Nueva solicitud de cita para {cita.fecha} a las {cita.hora}",
        {"cita_id": cita_id, "fecha": cita.fecha, "hora": cita.hora}
    )
    
    return {
        "mensaje": "Cita solicitada correctamente",
        "cita": {
            "id": cita_id,
            "fecha": cita.fecha,
            "hora": cita.hora,
            "estado": "pendiente"
        }
    }

@app.get("/usuario/{usuario_id}")
async def citas_usuario(usuario_id: int):
    """Obtener citas de un usuario (como estudiante o tutor)"""
    query = """
        SELECT * FROM citas 
        WHERE estudiante_id = :usuario_id OR tutor_id = :usuario_id 
        ORDER BY fecha DESC, hora DESC
    """
    citas = await database.fetch_all(query, {"usuario_id": usuario_id})
    return [dict(c) for c in citas]

@app.get("/tutor/{tutor_id}")
async def citas_tutor(tutor_id: int, estado: Optional[str] = None):
    """Obtener citas de un tutor"""
    if estado:
        query = "SELECT * FROM citas WHERE tutor_id = :tutor_id AND estado = :estado ORDER BY fecha DESC, hora DESC"
        citas = await database.fetch_all(query, {"tutor_id": tutor_id, "estado": estado})
    else:
        query = "SELECT * FROM citas WHERE tutor_id = :tutor_id ORDER BY fecha DESC, hora DESC"
        citas = await database.fetch_all(query, {"tutor_id": tutor_id})
    
    return [dict(c) for c in citas]

@app.get("/estudiante/{estudiante_id}")
async def citas_estudiante(estudiante_id: int):
    """Obtener citas de un estudiante"""
    query = "SELECT * FROM citas WHERE estudiante_id = :estudiante_id ORDER BY fecha DESC, hora DESC"
    citas = await database.fetch_all(query, {"estudiante_id": estudiante_id})
    return [dict(c) for c in citas]

@app.get("/{cita_id}")
async def obtener_cita(cita_id: int):
    """Obtener una cita por ID"""
    query = "SELECT * FROM citas WHERE id = :id"
    cita = await database.fetch_one(query, {"id": cita_id})
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    return dict(cita)

@app.put("/{cita_id}/confirmar")
async def confirmar_cita(cita_id: int, request: CitaRespuesta):
    """Confirmar una cita"""
    # Verificar cita
    query = "SELECT * FROM citas WHERE id = :id"
    cita = await database.fetch_one(query, {"id": cita_id})
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    if cita["estado"] != "pendiente":
        raise HTTPException(status_code=400, detail="La cita ya fue procesada")
    
    # Actualizar
    update_query = """
        UPDATE citas 
        SET estado = 'confirmada', fecha_respuesta = :fecha 
        WHERE id = :id
    """
    await database.execute(update_query, {"fecha": datetime.now().isoformat(), "id": cita_id})
    
    # Notificar al estudiante
    await notificar(
        cita["estudiante_id"],
        "cita",
        f"Tu cita para {cita['fecha']} a las {cita['hora']} ha sido confirmada",
        {"cita_id": cita_id, "estado": "confirmada"}
    )
    
    return {"mensaje": "Cita confirmada", "estado": "confirmada"}

@app.put("/{cita_id}/rechazar")
async def rechazar_cita(cita_id: int, request: CitaRespuesta):
    """Rechazar una cita"""
    # Verificar cita
    query = "SELECT * FROM citas WHERE id = :id"
    cita = await database.fetch_one(query, {"id": cita_id})
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    if cita["estado"] != "pendiente":
        raise HTTPException(status_code=400, detail="La cita ya fue procesada")
    
    # Actualizar
    update_query = """
        UPDATE citas 
        SET estado = 'rechazada', motivo_rechazo = :motivo, fecha_respuesta = :fecha 
        WHERE id = :id
    """
    await database.execute(update_query, {
        "motivo": request.motivo_rechazo or "Sin motivo especificado",
        "fecha": datetime.now().isoformat(),
        "id": cita_id
    })
    
    # Notificar al estudiante
    await notificar(
        cita["estudiante_id"],
        "cita",
        f"Tu cita para {cita['fecha']} a las {cita['hora']} ha sido rechazada",
        {"cita_id": cita_id, "estado": "rechazada", "motivo": request.motivo_rechazo}
    )
    
    return {"mensaje": "Cita rechazada", "estado": "rechazada"}

@app.put("/{cita_id}/cancelar")
async def cancelar_cita(cita_id: int, usuario_id: int):
    """Cancelar una cita"""
    # Verificar cita
    query = "SELECT * FROM citas WHERE id = :id"
    cita = await database.fetch_one(query, {"id": cita_id})
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    if cita["estado"] not in ["pendiente", "confirmada"]:
        raise HTTPException(status_code=400, detail="No se puede cancelar esta cita")
    
    # Actualizar
    update_query = "UPDATE citas SET estado = 'cancelada', fecha_respuesta = :fecha WHERE id = :id"
    await database.execute(update_query, {"fecha": datetime.now().isoformat(), "id": cita_id})
    
    # Notificar a la otra parte
    notificar_a = cita["tutor_id"] if usuario_id == cita["estudiante_id"] else cita["estudiante_id"]
    await notificar(
        notificar_a,
        "cita",
        f"La cita para {cita['fecha']} a las {cita['hora']} ha sido cancelada",
        {"cita_id": cita_id, "estado": "cancelada"}
    )
    
    return {"mensaje": "Cita cancelada", "estado": "cancelada"}

@app.get("/agenda/{tutor_id}")
async def agenda_tutor(tutor_id: int):
    """Obtener agenda de citas confirmadas de un tutor"""
    query = """
        SELECT * FROM citas 
        WHERE tutor_id = :tutor_id AND estado = 'confirmada' 
        ORDER BY fecha ASC, hora ASC
    """
    citas = await database.fetch_all(query, {"tutor_id": tutor_id})
    return [dict(c) for c in citas]

if __name__ == "__main__":
    import uvicorn
    print("📅 Iniciando Servicio de Citas...")
    uvicorn.run(app, host="0.0.0.0", port=5004)