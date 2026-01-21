"""
Servicio de Notificaciones - SOA TFG
Este microservicio gestiona los avisos y notificaciones del sistema.
Puerto: 5005
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

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Tipos de notificación
class TipoNotificacion(str, Enum):
    ARCHIVO_NUEVO = "archivo_nuevo"
    FEEDBACK_NUEVO = "feedback_nuevo"
    CITA_NUEVA = "cita_nueva"
    CITA_CONFIRMADA = "cita_confirmada"
    CITA_RECHAZADA = "cita_rechazada"
    CITA_CANCELADA = "cita_cancelada"
    SISTEMA = "sistema"

# Tabla de notificaciones
notificaciones_table = Table(
    "notificaciones",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tipo", String),
    Column("usuario_destino_id", Integer),
    Column("usuario_origen_id", Integer, nullable=True),
    Column("mensaje", String),
    Column("referencia_tipo", String, nullable=True),  # archivo, cita
    Column("referencia_id", Integer, nullable=True),
    Column("fecha_creacion", String),
    Column("leida", Integer, default=0),  # 0 = no leída, 1 = leída
    Column("fecha_lectura", String, nullable=True),
)

# Crear tablas
engine = create_engine(DATABASE_URL.replace("../../../", "./"))

app = FastAPI(
    title="Servicio de Notificaciones",
    description="Microservicio SOA para gestión de notificaciones y avisos del sistema TFG",
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
class NotificacionCreate(BaseModel):
    tipo: str
    usuario_destino_id: int
    usuario_origen_id: Optional[int] = None
    mensaje: str
    referencia_tipo: Optional[str] = None
    referencia_id: Optional[int] = None

class NotificacionResponse(BaseModel):
    id: int
    tipo: str
    mensaje: str
    fecha_creacion: str
    leida: bool
    usuario_origen_id: Optional[int]
    referencia_tipo: Optional[str]
    referencia_id: Optional[int]

# ========== FUNCIONES AUXILIARES ==========
def obtener_icono_notificacion(tipo: str) -> str:
    """Obtener icono según tipo de notificación"""
    iconos = {
        TipoNotificacion.ARCHIVO_NUEVO.value: "📄",
        TipoNotificacion.FEEDBACK_NUEVO.value: "💬",
        TipoNotificacion.CITA_NUEVA.value: "📅",
        TipoNotificacion.CITA_CONFIRMADA.value: "✅",
        TipoNotificacion.CITA_RECHAZADA.value: "❌",
        TipoNotificacion.CITA_CANCELADA.value: "🚫",
        TipoNotificacion.SISTEMA.value: "🔔",
    }
    return iconos.get(tipo, "🔔")

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()
    # Crear tabla si no existe
    try:
        metadata.create_all(engine)
    except:
        pass

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ========== ENDPOINTS ==========

@app.get("/health")
async def health_check():
    """Verificar estado del servicio"""
    return {
        "servicio": "notificaciones",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/")
async def crear_notificacion(notificacion: NotificacionCreate):
    """
    Crear una nueva notificación.
    Llamado por otros servicios cuando ocurre un evento relevante.
    """
    # Validar tipo
    tipos_validos = [t.value for t in TipoNotificacion]
    if notificacion.tipo not in tipos_validos:
        notificacion.tipo = TipoNotificacion.SISTEMA.value
    
    # Insertar notificación
    query = notificaciones_table.insert().values(
        tipo=notificacion.tipo,
        usuario_destino_id=notificacion.usuario_destino_id,
        usuario_origen_id=notificacion.usuario_origen_id,
        mensaje=notificacion.mensaje,
        referencia_tipo=notificacion.referencia_tipo,
        referencia_id=notificacion.referencia_id,
        fecha_creacion=datetime.now().isoformat(),
        leida=0
    )
    
    notif_id = await database.execute(query)
    
    return {
        "mensaje": "Notificación creada",
        "notificacion_id": notif_id,
        "tipo": notificacion.tipo
    }

@app.get("/usuario/{usuario_id}")
async def obtener_notificaciones_usuario(
    usuario_id: int, 
    solo_no_leidas: bool = False,
    limite: int = 50
):
    """
    Obtener notificaciones de un usuario.
    Opcionalmente filtrar solo las no leídas.
    """
    query = """SELECT n.*, 
               COALESCE(u.nombre, 'Sistema') as origen_nombre
               FROM notificaciones n
               LEFT JOIN usuarios u ON n.usuario_origen_id = u.id
               WHERE n.usuario_destino_id = :usuario_id"""
    
    params = {"usuario_id": usuario_id}
    
    if solo_no_leidas:
        query += " AND n.leida = 0"
    
    query += f" ORDER BY n.fecha_creacion DESC LIMIT {limite}"
    
    notificaciones = await database.fetch_all(query, params)
    
    # Contar no leídas
    no_leidas = await database.fetch_one(
        "SELECT COUNT(*) as count FROM notificaciones WHERE usuario_destino_id = :id AND leida = 0",
        {"id": usuario_id}
    )
    
    resultado = []
    for n in notificaciones:
        notif = dict(n)
        notif["icono"] = obtener_icono_notificacion(n["tipo"])
        notif["leida"] = bool(n["leida"])
        resultado.append(notif)
    
    return {
        "usuario_id": usuario_id,
        "notificaciones": resultado,
        "total": len(resultado),
        "no_leidas": no_leidas["count"]
    }

@app.put("/{notificacion_id}/leer")
async def marcar_como_leida(notificacion_id: int, usuario_id: int):
    """Marcar una notificación como leída"""
    notif = await database.fetch_one(
        "SELECT * FROM notificaciones WHERE id = :id AND usuario_destino_id = :usuario_id",
        {"id": notificacion_id, "usuario_id": usuario_id}
    )
    
    if not notif:
        raise HTTPException(
            status_code=404,
            detail="Notificación no encontrada"
        )
    
    await database.execute(
        "UPDATE notificaciones SET leida = 1, fecha_lectura = :fecha WHERE id = :id",
        {"fecha": datetime.now().isoformat(), "id": notificacion_id}
    )
    
    return {"mensaje": "Notificación marcada como leída", "notificacion_id": notificacion_id}

@app.put("/usuario/{usuario_id}/leer-todas")
async def marcar_todas_como_leidas(usuario_id: int):
    """Marcar todas las notificaciones de un usuario como leídas"""
    await database.execute(
        "UPDATE notificaciones SET leida = 1, fecha_lectura = :fecha WHERE usuario_destino_id = :id AND leida = 0",
        {"fecha": datetime.now().isoformat(), "id": usuario_id}
    )
    
    return {"mensaje": "Todas las notificaciones marcadas como leídas", "usuario_id": usuario_id}

@app.delete("/{notificacion_id}")
async def eliminar_notificacion(notificacion_id: int, usuario_id: int):
    """Eliminar una notificación"""
    notif = await database.fetch_one(
        "SELECT * FROM notificaciones WHERE id = :id AND usuario_destino_id = :usuario_id",
        {"id": notificacion_id, "usuario_id": usuario_id}
    )
    
    if not notif:
        raise HTTPException(
            status_code=404,
            detail="Notificación no encontrada"
        )
    
    await database.execute("DELETE FROM notificaciones WHERE id = :id", {"id": notificacion_id})
    
    return {"mensaje": "Notificación eliminada", "notificacion_id": notificacion_id}

@app.delete("/usuario/{usuario_id}/limpiar")
async def limpiar_notificaciones(usuario_id: int, solo_leidas: bool = True):
    """
    Eliminar notificaciones de un usuario.
    Por defecto solo elimina las ya leídas.
    """
    query = "DELETE FROM notificaciones WHERE usuario_destino_id = :id"
    if solo_leidas:
        query += " AND leida = 1"
    
    await database.execute(query, {"id": usuario_id})
    
    return {
        "mensaje": "Notificaciones eliminadas",
        "usuario_id": usuario_id,
        "solo_leidas": solo_leidas
    }

@app.get("/contador/{usuario_id}")
async def obtener_contador(usuario_id: int):
    """Obtener contador de notificaciones no leídas (para badge)"""
    count = await database.fetch_one(
        "SELECT COUNT(*) as count FROM notificaciones WHERE usuario_destino_id = :id AND leida = 0",
        {"id": usuario_id}
    )
    
    return {
        "usuario_id": usuario_id,
        "no_leidas": count["count"]
    }

@app.get("/resumen/{usuario_id}")
async def obtener_resumen(usuario_id: int):
    """Obtener resumen de notificaciones por tipo"""
    resumen = await database.fetch_all(
        """SELECT tipo, COUNT(*) as count, SUM(CASE WHEN leida = 0 THEN 1 ELSE 0 END) as no_leidas
           FROM notificaciones 
           WHERE usuario_destino_id = :id
           GROUP BY tipo""",
        {"id": usuario_id}
    )
    
    resultado = {}
    total = 0
    total_no_leidas = 0
    
    for r in resumen:
        resultado[r["tipo"]] = {
            "total": r["count"],
            "no_leidas": r["no_leidas"],
            "icono": obtener_icono_notificacion(r["tipo"])
        }
        total += r["count"]
        total_no_leidas += r["no_leidas"]
    
    return {
        "usuario_id": usuario_id,
        "por_tipo": resultado,
        "total": total,
        "total_no_leidas": total_no_leidas
    }

@app.post("/broadcast")
async def enviar_broadcast(mensaje: str, tipo: str = "sistema"):
    """
    Enviar notificación a todos los usuarios (solo admin).
    Útil para avisos del sistema.
    """
    # Obtener todos los usuarios
    usuarios = await database.fetch_all("SELECT id FROM usuarios")
    
    for usuario in usuarios:
        await database.execute(
            notificaciones_table.insert().values(
                tipo=tipo,
                usuario_destino_id=usuario["id"],
                usuario_origen_id=None,
                mensaje=mensaje,
                fecha_creacion=datetime.now().isoformat(),
                leida=0
            )
        )
    
    return {
        "mensaje": "Broadcast enviado",
        "usuarios_notificados": len(usuarios)
    }

@app.get("/info")
async def service_info():
    """Información del servicio"""
    return {
        "nombre": "Servicio de Notificaciones",
        "descripcion": "Gestiona los avisos y notificaciones del sistema",
        "tipos_notificacion": [t.value for t in TipoNotificacion],
        "endpoints": [
            {"ruta": "/", "metodo": "POST", "descripcion": "Crear notificación"},
            {"ruta": "/usuario/{id}", "metodo": "GET", "descripcion": "Obtener notificaciones"},
            {"ruta": "/{id}/leer", "metodo": "PUT", "descripcion": "Marcar como leída"},
            {"ruta": "/usuario/{id}/leer-todas", "metodo": "PUT", "descripcion": "Leer todas"},
            {"ruta": "/contador/{id}", "metodo": "GET", "descripcion": "Contador no leídas"},
            {"ruta": "/resumen/{id}", "metodo": "GET", "descripcion": "Resumen por tipo"},
            {"ruta": "/broadcast", "metodo": "POST", "descripcion": "Enviar a todos"},
            {"ruta": "/health", "metodo": "GET", "descripcion": "Estado del servicio"}
        ],
        "puerto": 5005
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5005)
