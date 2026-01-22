"""
Servicio de Notificaciones - SOA TFG
Este microservicio gestiona las notificaciones del sistema.
Puerto: 5005
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import databases
import sqlalchemy
import os

# Configuración - Fixed paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'tfg_soa.db')}"

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Tabla de notificaciones
notificaciones_table = sqlalchemy.Table(
    "notificaciones",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("usuario_id", sqlalchemy.Integer),
    sqlalchemy.Column("tipo", sqlalchemy.String),
    sqlalchemy.Column("mensaje", sqlalchemy.String),
    sqlalchemy.Column("datos", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("leida", sqlalchemy.Boolean, default=False),
    sqlalchemy.Column("fecha", sqlalchemy.String),
)

# Crear tablas
engine = sqlalchemy.create_engine(DATABASE_URL.replace("sqlite:///", "sqlite:///"))
metadata.create_all(engine)

app = FastAPI(
    title="Servicio de Notificaciones",
    description="Microservicio SOA para gestión de notificaciones",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== MODELOS ==========
class NotificacionCreate(BaseModel):
    usuario_id: int
    tipo: str
    mensaje: str
    datos: Optional[dict] = None

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()
    print(f"✅ Notifications Service conectado a: {DATABASE_URL}")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ========== ENDPOINTS ==========
@app.get("/health")
async def health():
    """Health check"""
    return {
        "servicio": "notificaciones",
        "estado": "activo",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/")
async def crear_notificacion(notificacion: NotificacionCreate):
    """Crear una nueva notificación"""
    import json
    
    query = notificaciones_table.insert().values(
        usuario_id=notificacion.usuario_id,
        tipo=notificacion.tipo,
        mensaje=notificacion.mensaje,
        datos=json.dumps(notificacion.datos) if notificacion.datos else None,
        leida=False,
        fecha=datetime.now().isoformat()
    )
    notificacion_id = await database.execute(query)
    
    return {
        "mensaje": "Notificación creada",
        "id": notificacion_id
    }

@app.get("/usuario/{usuario_id}")
async def obtener_notificaciones(usuario_id: int):
    """Obtener notificaciones de un usuario"""
    import json
    
    query = "SELECT * FROM notificaciones WHERE usuario_id = :usuario_id ORDER BY fecha DESC"
    notificaciones = await database.fetch_all(query, {"usuario_id": usuario_id})
    
    result = []
    for n in notificaciones:
        item = dict(n)
        if item.get("datos"):
            try:
                item["datos"] = json.loads(item["datos"])
            except:
                pass
        result.append(item)
    
    return result

@app.get("/usuario/{usuario_id}/no-leidas")
async def obtener_no_leidas(usuario_id: int):
    """Obtener notificaciones no leídas"""
    query = "SELECT COUNT(*) as count FROM notificaciones WHERE usuario_id = :usuario_id AND leida = 0"
    result = await database.fetch_one(query, {"usuario_id": usuario_id})
    return {"no_leidas": result["count"] if result else 0}

@app.put("/{notificacion_id}/leer")
async def marcar_leida(notificacion_id: int):
    """Marcar notificación como leída"""
    query = "UPDATE notificaciones SET leida = 1 WHERE id = :id"
    await database.execute(query, {"id": notificacion_id})
    return {"mensaje": "Notificación marcada como leída"}

@app.put("/leer-todas/{usuario_id}")
async def marcar_todas_leidas(usuario_id: int):
    """Marcar todas las notificaciones como leídas"""
    query = "UPDATE notificaciones SET leida = 1 WHERE usuario_id = :usuario_id"
    await database.execute(query, {"usuario_id": usuario_id})
    return {"mensaje": "Todas las notificaciones marcadas como leídas"}

@app.delete("/{notificacion_id}")
async def eliminar_notificacion(notificacion_id: int):
    """Eliminar una notificación"""
    query = "DELETE FROM notificaciones WHERE id = :id"
    await database.execute(query, {"id": notificacion_id})
    return {"mensaje": "Notificación eliminada"}

if __name__ == "__main__":
    import uvicorn
    print("🔔 Iniciando Servicio de Notificaciones...")
    uvicorn.run(app, host="0.0.0.0", port=5005)