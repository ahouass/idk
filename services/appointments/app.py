"""
Servicio de Citas/Tutorías - SOA TFG
Este microservicio gestiona las citas entre estudiantes y tutores.
Puerto: 5004
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum
import databases
import sqlalchemy
from sqlalchemy import Table, Column, Integer, String, create_engine
import os

# Configuración
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///../../../data/tfg_soa.db")
NOTIFICATIONS_SERVICE = os.getenv("NOTIFICATIONS_SERVICE", "http://localhost:5005")

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Estados de cita
class EstadoCita(str, Enum):
    PENDIENTE = "pendiente"
    CONFIRMADA = "confirmada"
    RECHAZADA = "rechazada"
    CANCELADA = "cancelada"
    COMPLETADA = "completada"

# Tabla de citas
citas_table = Table(
    "citas",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("estudiante_id", Integer),
    Column("tutor_id", Integer),
    Column("fecha", String),
    Column("hora", String),
    Column("motivo", String),
    Column("estado", String, default="pendiente"),
    Column("lugar", String, nullable=True),
    Column("notas", String, nullable=True),
    Column("fecha_solicitud", String),
    Column("fecha_respuesta", String, nullable=True),
    Column("motivo_rechazo", String, nullable=True),
)

app = FastAPI(
    title="Servicio de Citas/Tutorías",
    description="Microservicio SOA para gestión de citas entre estudiantes y tutores",
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
class CitaSolicitud(BaseModel):
    estudiante_id: int
    tutor_id: int
    fecha: str  # Formato: YYYY-MM-DD
    hora: str   # Formato: HH:MM
    motivo: str
    lugar: Optional[str] = "Por determinar"

class CitaRespuesta(BaseModel):
    tutor_id: int
    aceptar: bool
    motivo_rechazo: Optional[str] = None
    lugar: Optional[str] = None
    notas: Optional[str] = None

class CitaActualizacion(BaseModel):
    fecha: Optional[str] = None
    hora: Optional[str] = None
    motivo: Optional[str] = None
    lugar: Optional[str] = None

# ========== FUNCIONES AUXILIARES ==========
async def notificar_cita(tipo: str, estudiante_id: int, tutor_id: int, mensaje: str, cita_id: int):
    """Enviar notificación relacionada con citas"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # Determinar destinatario según tipo
            if tipo in ["cita_nueva", "cita_cancelada_estudiante"]:
                destinatario = tutor_id
                origen = estudiante_id
            else:
                destinatario = estudiante_id
                origen = tutor_id
            
            await client.post(
                f"{NOTIFICATIONS_SERVICE}/",
                json={
                    "tipo": tipo,
                    "usuario_destino_id": destinatario,
                    "usuario_origen_id": origen,
                    "mensaje": mensaje,
                    "referencia_tipo": "cita",
                    "referencia_id": cita_id
                }
            )
    except Exception as e:
        print(f"Error enviando notificación: {e}")

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
    """Verificar estado del servicio"""
    return {
        "servicio": "citas",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/solicitar")
async def solicitar_cita(cita: CitaSolicitud):
    """
    Solicitar una nueva cita de tutoría.
    El estudiante propone fecha, hora y motivo.
    """
    # Verificar que no haya conflicto de horario
    cita_existente = await database.fetch_one(
        """SELECT id FROM citas 
           WHERE tutor_id = :tutor_id AND fecha = :fecha AND hora = :hora 
           AND estado IN ('pendiente', 'confirmada')""",
        {"tutor_id": cita.tutor_id, "fecha": cita.fecha, "hora": cita.hora}
    )
    
    if cita_existente:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una cita en ese horario"
        )
    
    # Crear cita
    query = citas_table.insert().values(
        estudiante_id=cita.estudiante_id,
        tutor_id=cita.tutor_id,
        fecha=cita.fecha,
        hora=cita.hora,
        motivo=cita.motivo,
        estado=EstadoCita.PENDIENTE.value,
        lugar=cita.lugar,
        fecha_solicitud=datetime.now().isoformat()
    )
    
    cita_id = await database.execute(query)
    
    # Notificar al tutor
    await notificar_cita(
        "cita_nueva",
        cita.estudiante_id,
        cita.tutor_id,
        f"Nueva solicitud de tutoría para {cita.fecha} a las {cita.hora}",
        cita_id
    )
    
    return {
        "mensaje": "Cita solicitada exitosamente",
        "cita_id": cita_id,
        "estado": EstadoCita.PENDIENTE.value,
        "fecha": cita.fecha,
        "hora": cita.hora
    }

@app.put("/{cita_id}/responder")
async def responder_cita(cita_id: int, respuesta: CitaRespuesta):
    """
    Confirmar o rechazar una cita (solo tutores).
    """
    # Verificar que la cita existe y pertenece al tutor
    cita = await database.fetch_one(
        "SELECT * FROM citas WHERE id = :id AND tutor_id = :tutor_id",
        {"id": cita_id, "tutor_id": respuesta.tutor_id}
    )
    
    if not cita:
        raise HTTPException(
            status_code=404,
            detail="Cita no encontrada o no autorizada"
        )
    
    if cita["estado"] != EstadoCita.PENDIENTE.value:
        raise HTTPException(
            status_code=400,
            detail=f"La cita ya fue procesada (estado: {cita['estado']})"
        )
    
    # Actualizar estado
    nuevo_estado = EstadoCita.CONFIRMADA.value if respuesta.aceptar else EstadoCita.RECHAZADA.value
    
    updates = {
        "estado": nuevo_estado,
        "fecha_respuesta": datetime.now().isoformat(),
        "id": cita_id
    }
    
    query = "UPDATE citas SET estado = :estado, fecha_respuesta = :fecha_respuesta"
    
    if respuesta.lugar:
        query += ", lugar = :lugar"
        updates["lugar"] = respuesta.lugar
    
    if respuesta.notas:
        query += ", notas = :notas"
        updates["notas"] = respuesta.notas
    
    if not respuesta.aceptar and respuesta.motivo_rechazo:
        query += ", motivo_rechazo = :motivo_rechazo"
        updates["motivo_rechazo"] = respuesta.motivo_rechazo
    
    query += " WHERE id = :id"
    
    await database.execute(query, updates)
    
    # Notificar al estudiante
    mensaje = f"Tu cita del {cita['fecha']} ha sido {'confirmada' if respuesta.aceptar else 'rechazada'}"
    await notificar_cita(
        "cita_confirmada" if respuesta.aceptar else "cita_rechazada",
        cita["estudiante_id"],
        respuesta.tutor_id,
        mensaje,
        cita_id
    )
    
    return {
        "mensaje": f"Cita {'confirmada' if respuesta.aceptar else 'rechazada'}",
        "cita_id": cita_id,
        "estado": nuevo_estado
    }

@app.put("/{cita_id}/cancelar")
async def cancelar_cita(cita_id: int, usuario_id: int):
    """Cancelar una cita (puede ser estudiante o tutor)"""
    cita = await database.fetch_one(
        "SELECT * FROM citas WHERE id = :id AND (estudiante_id = :usuario_id OR tutor_id = :usuario_id)",
        {"id": cita_id, "usuario_id": usuario_id}
    )
    
    if not cita:
        raise HTTPException(
            status_code=404,
            detail="Cita no encontrada o no autorizada"
        )
    
    if cita["estado"] in [EstadoCita.COMPLETADA.value, EstadoCita.CANCELADA.value]:
        raise HTTPException(
            status_code=400,
            detail="No se puede cancelar esta cita"
        )
    
    await database.execute(
        "UPDATE citas SET estado = :estado, fecha_respuesta = :fecha WHERE id = :id",
        {"estado": EstadoCita.CANCELADA.value, "fecha": datetime.now().isoformat(), "id": cita_id}
    )
    
    # Notificar
    es_estudiante = cita["estudiante_id"] == usuario_id
    await notificar_cita(
        "cita_cancelada_estudiante" if es_estudiante else "cita_cancelada_tutor",
        cita["estudiante_id"],
        cita["tutor_id"],
        f"La cita del {cita['fecha']} ha sido cancelada",
        cita_id
    )
    
    return {"mensaje": "Cita cancelada", "cita_id": cita_id}

@app.get("/usuario/{usuario_id}")
async def obtener_citas_usuario(usuario_id: int, estado: Optional[str] = None):
    """Obtener todas las citas de un usuario (estudiante o tutor)"""
    query = """SELECT c.*, 
               e.nombre as estudiante_nombre, e.email as estudiante_email,
               t.nombre as tutor_nombre, t.email as tutor_email
               FROM citas c
               JOIN usuarios e ON c.estudiante_id = e.id
               JOIN usuarios t ON c.tutor_id = t.id
               WHERE c.estudiante_id = :usuario_id OR c.tutor_id = :usuario_id"""
    
    params = {"usuario_id": usuario_id}
    
    if estado:
        query += " AND c.estado = :estado"
        params["estado"] = estado
    
    query += " ORDER BY c.fecha DESC, c.hora DESC"
    
    citas = await database.fetch_all(query, params)
    
    return {
        "usuario_id": usuario_id,
        "citas": [dict(c) for c in citas],
        "total": len(citas)
    }

@app.get("/tutor/{tutor_id}/pendientes")
async def obtener_citas_pendientes_tutor(tutor_id: int):
    """Obtener citas pendientes de respuesta para un tutor"""
    citas = await database.fetch_all(
        """SELECT c.*, u.nombre as estudiante_nombre, u.email as estudiante_email
           FROM citas c
           JOIN usuarios u ON c.estudiante_id = u.id
           WHERE c.tutor_id = :tutor_id AND c.estado = 'pendiente'
           ORDER BY c.fecha_solicitud ASC""",
        {"tutor_id": tutor_id}
    )
    
    return {
        "tutor_id": tutor_id,
        "citas_pendientes": [dict(c) for c in citas],
        "total": len(citas)
    }

@app.get("/agenda/{usuario_id}")
async def obtener_agenda(usuario_id: int, proximas: bool = True):
    """
    Obtener agenda de citas confirmadas.
    Por defecto muestra solo las próximas (fecha >= hoy).
    """
    hoy = datetime.now().strftime("%Y-%m-%d")
    
    query = """SELECT c.*, 
               e.nombre as estudiante_nombre,
               t.nombre as tutor_nombre
               FROM citas c
               JOIN usuarios e ON c.estudiante_id = e.id
               JOIN usuarios t ON c.tutor_id = t.id
               WHERE (c.estudiante_id = :usuario_id OR c.tutor_id = :usuario_id)
               AND c.estado = 'confirmada'"""
    
    params = {"usuario_id": usuario_id}
    
    if proximas:
        query += " AND c.fecha >= :hoy"
        params["hoy"] = hoy
    
    query += " ORDER BY c.fecha ASC, c.hora ASC"
    
    citas = await database.fetch_all(query, params)
    
    return {
        "usuario_id": usuario_id,
        "agenda": [dict(c) for c in citas],
        "total": len(citas),
        "proximas_solo": proximas
    }

@app.get("/{cita_id}")
async def obtener_cita(cita_id: int):
    """Obtener detalles de una cita específica"""
    cita = await database.fetch_one(
        """SELECT c.*, 
           e.nombre as estudiante_nombre, e.email as estudiante_email,
           t.nombre as tutor_nombre, t.email as tutor_email
           FROM citas c
           JOIN usuarios e ON c.estudiante_id = e.id
           JOIN usuarios t ON c.tutor_id = t.id
           WHERE c.id = :id""",
        {"id": cita_id}
    )
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    return dict(cita)

@app.put("/{cita_id}/completar")
async def completar_cita(cita_id: int, tutor_id: int, notas: Optional[str] = None):
    """Marcar una cita como completada (después de realizarse)"""
    cita = await database.fetch_one(
        "SELECT * FROM citas WHERE id = :id AND tutor_id = :tutor_id AND estado = 'confirmada'",
        {"id": cita_id, "tutor_id": tutor_id}
    )
    
    if not cita:
        raise HTTPException(
            status_code=404,
            detail="Cita no encontrada o no puede ser completada"
        )
    
    updates = {
        "estado": EstadoCita.COMPLETADA.value,
        "id": cita_id
    }
    
    query = "UPDATE citas SET estado = :estado"
    
    if notas:
        query += ", notas = :notas"
        updates["notas"] = notas
    
    query += " WHERE id = :id"
    
    await database.execute(query, updates)
    
    return {"mensaje": "Cita marcada como completada", "cita_id": cita_id}

@app.get("/estadisticas/{usuario_id}")
async def obtener_estadisticas(usuario_id: int):
    """Obtener estadísticas de citas de un usuario"""
    stats = await database.fetch_all(
        """SELECT estado, COUNT(*) as count 
           FROM citas 
           WHERE estudiante_id = :id OR tutor_id = :id
           GROUP BY estado""",
        {"id": usuario_id}
    )
    
    total = await database.fetch_one(
        """SELECT COUNT(*) as total FROM citas 
           WHERE estudiante_id = :id OR tutor_id = :id""",
        {"id": usuario_id}
    )
    
    return {
        "usuario_id": usuario_id,
        "total_citas": total["total"],
        "por_estado": {s["estado"]: s["count"] for s in stats}
    }

@app.get("/info")
async def service_info():
    """Información del servicio"""
    return {
        "nombre": "Servicio de Citas/Tutorías",
        "descripcion": "Gestiona las citas entre estudiantes y tutores",
        "estados_cita": [e.value for e in EstadoCita],
        "endpoints": [
            {"ruta": "/solicitar", "metodo": "POST", "descripcion": "Solicitar cita"},
            {"ruta": "/{id}/responder", "metodo": "PUT", "descripcion": "Confirmar/Rechazar cita"},
            {"ruta": "/{id}/cancelar", "metodo": "PUT", "descripcion": "Cancelar cita"},
            {"ruta": "/usuario/{id}", "metodo": "GET", "descripcion": "Citas del usuario"},
            {"ruta": "/agenda/{id}", "metodo": "GET", "descripcion": "Agenda de citas"},
            {"ruta": "/tutor/{id}/pendientes", "metodo": "GET", "descripcion": "Citas pendientes"},
            {"ruta": "/{id}/completar", "metodo": "PUT", "descripcion": "Marcar completada"},
            {"ruta": "/health", "metodo": "GET", "descripcion": "Estado del servicio"}
        ],
        "puerto": 5004
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5004)
