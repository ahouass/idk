"""
Sistema TFG SOA - Aplicación Principal (Monolito)
=================================================

Este archivo implementa una versión monolítica del sistema que puede ser usada
alternativamente a la arquitectura de microservicios.

Para la arquitectura SOA completa, usar los servicios en la carpeta /services/

Ejecutar con: python app.py
O con: uvicorn app:app --reload --port 8000
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import databases
import sqlalchemy
from sqlalchemy import Table, Column, Integer, String, ForeignKey, create_engine
import bcrypt
import uuid
import os

# ========== CONFIGURACIÓN ==========
DATABASE_URL = "sqlite:///./data/tfg_soa.db"
UPLOAD_DIR = "./uploads"

# Crear directorios
os.makedirs("./data", exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# ========== TABLAS ==========
usuarios_table = Table(
    "usuarios",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String, unique=True, index=True),
    Column("nombre", String),
    Column("email", String, unique=True),
    Column("password_hash", String),
    Column("rol", String),
    Column("tutor_id", Integer, ForeignKey("usuarios.id"), nullable=True),
    Column("fecha_registro", String),
)

archivos_table = Table(
    "archivos",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre_original", String),
    Column("nombre_guardado", String),
    Column("ruta", String),
    Column("tipo", String),
    Column("tamanio", Integer),
    Column("estudiante_id", Integer, ForeignKey("usuarios.id")),
    Column("tutor_id", Integer, ForeignKey("usuarios.id")),
    Column("fecha_subida", String),
    Column("feedback", String, default=""),
    Column("fecha_feedback", String, nullable=True),
    Column("estado", String, default="pendiente"),
)

citas_table = Table(
    "citas",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("estudiante_id", Integer, ForeignKey("usuarios.id")),
    Column("tutor_id", Integer, ForeignKey("usuarios.id")),
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

notificaciones_table = Table(
    "notificaciones",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tipo", String),
    Column("usuario_destino_id", Integer),
    Column("usuario_origen_id", Integer, nullable=True),
    Column("mensaje", String),
    Column("referencia_tipo", String, nullable=True),
    Column("referencia_id", Integer, nullable=True),
    Column("fecha_creacion", String),
    Column("leida", Integer, default=0),
    Column("fecha_lectura", String, nullable=True),
)

# Crear tablas
engine = create_engine(DATABASE_URL)
metadata.create_all(engine)

# ========== APLICACIÓN ==========
app = FastAPI(
    title="Sistema TFG SOA - Gestión de Tutorías",
    description="""
    ## Sistema de Gestión de Tutorías y Entregas
    
    Desarrollado siguiendo principios de **Arquitectura Orientada a Servicios (SOA)**.
    
    ### Funcionalidades:
    - **Gestión de Usuarios**: Estudiantes y Tutores con roles diferenciados
    - **Gestión de Archivos**: Subida de PDF/ZIP con feedback de tutores
    - **Agenda de Citas**: Solicitud y confirmación de tutorías
    - **Notificaciones**: Sistema de avisos en tiempo real
    
    ### Arquitectura:
    Este sistema puede ejecutarse como:
    1. **Monolito** (este archivo): Puerto 8000
    2. **Microservicios** (carpeta /services): ESB en puerto 5000
    
    ---
    Universidad de Salamanca • Segunda Convocatoria SOA 2026
    """,
    version="2.0.0",
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

class UsuarioRegistro(BaseModel):
    nombre: str
    email: str
    username: str
    password: str
    rol: str
    tutor_id: Optional[int] = None

class CitaSolicitud(BaseModel):
    estudiante_id: int
    tutor_id: int
    fecha: str
    hora: str
    motivo: str

class FeedbackRequest(BaseModel):
    feedback: str
    tutor_id: int
    estado: Optional[str] = "revisado"

# ========== FUNCIONES AUXILIARES ==========
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

async def crear_notificacion(tipo: str, destino_id: int, origen_id: int, mensaje: str, ref_tipo: str = None, ref_id: int = None):
    """Crear una notificación en la base de datos"""
    query = notificaciones_table.insert().values(
        tipo=tipo,
        usuario_destino_id=destino_id,
        usuario_origen_id=origen_id,
        mensaje=mensaje,
        referencia_tipo=ref_tipo,
        referencia_id=ref_id,
        fecha_creacion=datetime.now().isoformat(),
        leida=0
    )
    await database.execute(query)

# ========== EVENTOS ==========
@app.on_event("startup")
async def startup():
    await database.connect()
    
    # Crear usuarios por defecto
    count = await database.fetch_one("SELECT COUNT(*) as count FROM usuarios")
    if count["count"] == 0:
        # Tutores
        for i, (username, nombre, email) in enumerate([
            ("tutor1", "Dr. Antonio López", "tutor@usal.es"),
            ("tutor2", "Dra. María Fernández", "tutor2@usal.es"),
        ], 1):
            query = usuarios_table.insert().values(
                username=username,
                nombre=nombre,
                email=email,
                password_hash=hash_password("tutor123"),
                rol="tutor",
                fecha_registro=datetime.now().isoformat()
            )
            await database.execute(query)
        
        # Estudiantes
        tutor = await database.fetch_one("SELECT id FROM usuarios WHERE username = 'tutor1'")
        for username, nombre, email in [
            ("estudiante1", "Juan Pérez", "juan@usal.es"),
            ("estudiante2", "María García", "maria@usal.es"),
            ("estudiante3", "Carlos López", "carlos@usal.es"),
        ]:
            query = usuarios_table.insert().values(
                username=username,
                nombre=nombre,
                email=email,
                password_hash=hash_password("estudiante123"),
                rol="estudiante",
                tutor_id=tutor["id"],
                fecha_registro=datetime.now().isoformat()
            )
            await database.execute(query)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# ========== ENDPOINTS PRINCIPALES ==========

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Servir página principal"""
    if os.path.exists("frontend/index.html"):
        with open("frontend/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    elif os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Sistema TFG SOA</h1><p>Acceda a <a href='/docs'>/docs</a> para la API.</p>")

@app.get("/api/health")
async def health_check():
    """Estado del sistema"""
    count = await database.fetch_one("SELECT COUNT(*) as count FROM usuarios")
    return {
        "estado": "operativo",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "base_datos": "conectada",
        "usuarios_registrados": count["count"]
    }

# ========== AUTENTICACIÓN ==========

@app.post("/api/login")
async def login(request: LoginRequest):
    """Iniciar sesión"""
    usuario = await database.fetch_one(
        "SELECT * FROM usuarios WHERE username = :username",
        {"username": request.username}
    )
    
    if not usuario or not verify_password(request.password, usuario["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    return {
        "token": str(uuid.uuid4()),
        "usuario": {
            "id": usuario["id"],
            "username": usuario["username"],
            "nombre": usuario["nombre"],
            "email": usuario["email"],
            "rol": usuario["rol"],
            "tutor_id": usuario["tutor_id"]
        },
        "mensaje": "Login exitoso"
    }

@app.post("/api/registro")
async def registrar_usuario(usuario: UsuarioRegistro):
    """Registrar nuevo usuario"""
    existing = await database.fetch_one(
        "SELECT id FROM usuarios WHERE username = :username OR email = :email",
        {"username": usuario.username, "email": usuario.email}
    )
    
    if existing:
        raise HTTPException(status_code=400, detail="Username o email ya registrado")
    
    if usuario.rol not in ["estudiante", "tutor"]:
        raise HTTPException(status_code=400, detail="Rol inválido")
    
    if usuario.rol == "estudiante" and not usuario.tutor_id:
        raise HTTPException(status_code=400, detail="Los estudiantes deben tener un tutor asignado")
    
    query = usuarios_table.insert().values(
        username=usuario.username,
        nombre=usuario.nombre,
        email=usuario.email,
        password_hash=hash_password(usuario.password),
        rol=usuario.rol,
        tutor_id=usuario.tutor_id if usuario.rol == "estudiante" else None,
        fecha_registro=datetime.now().isoformat()
    )
    
    usuario_id = await database.execute(query)
    return {"mensaje": "Usuario registrado exitosamente", "usuario_id": usuario_id}

# ========== USUARIOS ==========

@app.get("/api/usuarios")
async def listar_usuarios(rol: Optional[str] = None):
    """Listar usuarios"""
    query = "SELECT id, username, nombre, email, rol, tutor_id FROM usuarios"
    if rol:
        query += f" WHERE rol = '{rol}'"
    return await database.fetch_all(query)

@app.get("/api/tutores")
async def listar_tutores():
    """Listar tutores disponibles"""
    return await database.fetch_all(
        "SELECT id, nombre, email FROM usuarios WHERE rol = 'tutor'"
    )

@app.get("/api/tutores/{tutor_id}/estudiantes")
async def estudiantes_del_tutor(tutor_id: int):
    """Obtener estudiantes de un tutor"""
    tutor = await database.fetch_one(
        "SELECT id, nombre FROM usuarios WHERE id = :id AND rol = 'tutor'",
        {"id": tutor_id}
    )
    if not tutor:
        raise HTTPException(status_code=404, detail="Tutor no encontrado")
    
    estudiantes = await database.fetch_all(
        "SELECT id, username, nombre, email FROM usuarios WHERE tutor_id = :id",
        {"id": tutor_id}
    )
    return {"tutor": dict(tutor), "estudiantes": [dict(e) for e in estudiantes], "total": len(estudiantes)}

# ========== ARCHIVOS ==========

@app.post("/api/archivos/subir")
async def subir_archivo(estudiante_id: int = Form(...), file: UploadFile = File(...)):
    """Subir archivo (PDF o ZIP)"""
    if not file.filename.lower().endswith(('.pdf', '.zip')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF o ZIP")
    
    estudiante = await database.fetch_one(
        "SELECT id, tutor_id FROM usuarios WHERE id = :id AND rol = 'estudiante'",
        {"id": estudiante_id}
    )
    if not estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    
    # Guardar archivo
    extension = file.filename.split('.')[-1].lower()
    nombre_guardado = f"{estudiante_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{extension}"
    ruta = os.path.join(UPLOAD_DIR, nombre_guardado)
    
    content = await file.read()
    with open(ruta, "wb") as f:
        f.write(content)
    
    # Registrar en BD
    query = archivos_table.insert().values(
        nombre_original=file.filename,
        nombre_guardado=nombre_guardado,
        ruta=ruta,
        tipo=extension,
        tamanio=len(content),
        estudiante_id=estudiante_id,
        tutor_id=estudiante["tutor_id"],
        fecha_subida=datetime.now().isoformat(),
        estado="pendiente"
    )
    archivo_id = await database.execute(query)
    
    # Notificar al tutor
    await crear_notificacion(
        "archivo_nuevo",
        estudiante["tutor_id"],
        estudiante_id,
        f"Nuevo archivo subido: {file.filename}",
        "archivo",
        archivo_id
    )
    
    return {"mensaje": "Archivo subido", "archivo_id": archivo_id, "nombre_original": file.filename}

@app.get("/api/archivos/estudiante/{estudiante_id}")
async def archivos_estudiante(estudiante_id: int):
    """Obtener archivos de un estudiante"""
    archivos = await database.fetch_all(
        "SELECT * FROM archivos WHERE estudiante_id = :id ORDER BY fecha_subida DESC",
        {"id": estudiante_id}
    )
    return {"estudiante_id": estudiante_id, "archivos": [dict(a) for a in archivos], "total": len(archivos)}

@app.get("/api/archivos/tutor/{tutor_id}")
async def archivos_tutor(tutor_id: int, estado: Optional[str] = None):
    """Obtener archivos asignados a un tutor"""
    query = """SELECT a.*, u.nombre as estudiante_nombre 
               FROM archivos a 
               JOIN usuarios u ON a.estudiante_id = u.id 
               WHERE a.tutor_id = :tutor_id"""
    params = {"tutor_id": tutor_id}
    
    if estado:
        query += " AND a.estado = :estado"
        params["estado"] = estado
    
    query += " ORDER BY a.fecha_subida DESC"
    archivos = await database.fetch_all(query, params)
    return {"tutor_id": tutor_id, "archivos": [dict(a) for a in archivos], "total": len(archivos)}

@app.post("/api/archivos/{archivo_id}/feedback")
async def agregar_feedback(archivo_id: int, request: FeedbackRequest):
    """Agregar feedback a un archivo"""
    archivo = await database.fetch_one(
        "SELECT * FROM archivos WHERE id = :id AND tutor_id = :tutor_id",
        {"id": archivo_id, "tutor_id": request.tutor_id}
    )
    
    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    await database.execute(
        "UPDATE archivos SET feedback = :feedback, fecha_feedback = :fecha, estado = :estado WHERE id = :id",
        {"feedback": request.feedback, "fecha": datetime.now().isoformat(), "estado": request.estado, "id": archivo_id}
    )
    
    # Notificar al estudiante
    await crear_notificacion(
        "feedback_nuevo",
        archivo["estudiante_id"],
        request.tutor_id,
        f"Tu archivo '{archivo['nombre_original']}' ha sido revisado",
        "archivo",
        archivo_id
    )
    
    return {"mensaje": "Feedback agregado", "archivo_id": archivo_id}

# ========== CITAS ==========

@app.post("/api/citas/solicitar")
async def solicitar_cita(cita: CitaSolicitud):
    """Solicitar nueva cita"""
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
    await crear_notificacion(
        "cita_nueva",
        cita.tutor_id,
        cita.estudiante_id,
        f"Nueva solicitud de tutoría para {cita.fecha}",
        "cita",
        cita_id
    )
    
    return {"mensaje": "Cita solicitada", "cita_id": cita_id}

@app.get("/api/citas/usuario/{usuario_id}")
async def citas_usuario(usuario_id: int):
    """Obtener citas de un usuario"""
    citas = await database.fetch_all(
        """SELECT c.*, e.nombre as estudiante_nombre, t.nombre as tutor_nombre
           FROM citas c
           JOIN usuarios e ON c.estudiante_id = e.id
           JOIN usuarios t ON c.tutor_id = t.id
           WHERE c.estudiante_id = :id OR c.tutor_id = :id
           ORDER BY c.fecha DESC""",
        {"id": usuario_id}
    )
    return {"usuario_id": usuario_id, "citas": [dict(c) for c in citas], "total": len(citas)}

@app.put("/api/citas/{cita_id}/confirmar")
async def confirmar_cita(cita_id: int, tutor_id: int):
    """Confirmar una cita"""
    cita = await database.fetch_one(
        "SELECT * FROM citas WHERE id = :id AND tutor_id = :tutor_id",
        {"id": cita_id, "tutor_id": tutor_id}
    )
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    await database.execute(
        "UPDATE citas SET estado = 'confirmada', fecha_respuesta = :fecha WHERE id = :id",
        {"fecha": datetime.now().isoformat(), "id": cita_id}
    )
    
    await crear_notificacion(
        "cita_confirmada",
        cita["estudiante_id"],
        tutor_id,
        f"Tu cita del {cita['fecha']} ha sido confirmada",
        "cita",
        cita_id
    )
    
    return {"mensaje": "Cita confirmada", "cita_id": cita_id}

@app.put("/api/citas/{cita_id}/rechazar")
async def rechazar_cita(cita_id: int, tutor_id: int):
    """Rechazar una cita"""
    cita = await database.fetch_one(
        "SELECT * FROM citas WHERE id = :id AND tutor_id = :tutor_id",
        {"id": cita_id, "tutor_id": tutor_id}
    )
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    await database.execute(
        "UPDATE citas SET estado = 'rechazada', fecha_respuesta = :fecha WHERE id = :id",
        {"fecha": datetime.now().isoformat(), "id": cita_id}
    )
    
    await crear_notificacion(
        "cita_rechazada",
        cita["estudiante_id"],
        tutor_id,
        f"Tu cita del {cita['fecha']} ha sido rechazada",
        "cita",
        cita_id
    )
    
    return {"mensaje": "Cita rechazada", "cita_id": cita_id}

# ========== NOTIFICACIONES ==========

@app.get("/api/notificaciones/{usuario_id}")
async def obtener_notificaciones(usuario_id: int):
    """Obtener notificaciones de un usuario"""
    notificaciones = await database.fetch_all(
        """SELECT * FROM notificaciones 
           WHERE usuario_destino_id = :id 
           ORDER BY fecha_creacion DESC LIMIT 50""",
        {"id": usuario_id}
    )
    
    no_leidas = await database.fetch_one(
        "SELECT COUNT(*) as count FROM notificaciones WHERE usuario_destino_id = :id AND leida = 0",
        {"id": usuario_id}
    )
    
    # Agregar iconos
    iconos = {
        "archivo_nuevo": "📄",
        "feedback_nuevo": "💬",
        "cita_nueva": "📅",
        "cita_confirmada": "✅",
        "cita_rechazada": "❌"
    }
    
    resultado = []
    for n in notificaciones:
        notif = dict(n)
        notif["icono"] = iconos.get(n["tipo"], "🔔")
        notif["leida"] = bool(n["leida"])
        resultado.append(notif)
    
    return {"usuario_id": usuario_id, "notificaciones": resultado, "no_leidas": no_leidas["count"]}

@app.put("/api/notificaciones/{notificacion_id}/leer")
async def marcar_leida(notificacion_id: int, usuario_id: int):
    """Marcar notificación como leída"""
    await database.execute(
        "UPDATE notificaciones SET leida = 1, fecha_lectura = :fecha WHERE id = :id AND usuario_destino_id = :usuario_id",
        {"fecha": datetime.now().isoformat(), "id": notificacion_id, "usuario_id": usuario_id}
    )
    return {"mensaje": "Notificación marcada como leída"}

@app.put("/api/notificaciones/leer-todas/{usuario_id}")
async def marcar_todas_leidas(usuario_id: int):
    """Marcar todas las notificaciones como leídas"""
    await database.execute(
        "UPDATE notificaciones SET leida = 1, fecha_lectura = :fecha WHERE usuario_destino_id = :id AND leida = 0",
        {"fecha": datetime.now().isoformat(), "id": usuario_id}
    )
    return {"mensaje": "Todas las notificaciones marcadas como leídas"}

# ========== PÁGINA DE REGISTRO ==========

@app.get("/registro", response_class=HTMLResponse)
async def pagina_registro():
    """Página de registro de usuarios"""
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Registro - Sistema TFG SOA</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container { background: white; border-radius: 20px; padding: 40px; max-width: 500px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
            h1 { color: #2c3e50; margin-bottom: 30px; text-align: center; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 8px; color: #555; font-weight: 500; }
            input, select { width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 16px; }
            input:focus, select:focus { outline: none; border-color: #667eea; }
            button { width: 100%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 15px; border-radius: 10px; font-size: 18px; cursor: pointer; margin-top: 20px; }
            button:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4); }
            .error { color: #e74c3c; background: #ffeaea; padding: 10px; border-radius: 5px; margin-bottom: 15px; }
            .success { color: #27ae60; background: #eafff0; padding: 10px; border-radius: 5px; margin-bottom: 15px; }
            .link { text-align: center; margin-top: 20px; }
            .link a { color: #667eea; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎓 Registro</h1>
            <div id="message"></div>
            <form id="form">
                <div class="form-group"><label>Nombre completo</label><input type="text" id="nombre" required></div>
                <div class="form-group"><label>Email</label><input type="email" id="email" required></div>
                <div class="form-group"><label>Usuario</label><input type="text" id="username" required></div>
                <div class="form-group"><label>Contraseña</label><input type="password" id="password" required></div>
                <div class="form-group"><label>Rol</label><select id="rol" onchange="toggleTutor()"><option value="estudiante">Estudiante</option><option value="tutor">Tutor</option></select></div>
                <div class="form-group" id="tutorGroup"><label>Tutor asignado</label><select id="tutor_id"><option value="">-- Selecciona --</option></select></div>
                <button type="submit">Registrarse</button>
            </form>
            <div class="link"><a href="/">← Volver al login</a></div>
        </div>
        <script>
            async function toggleTutor() {
                const rol = document.getElementById('rol').value;
                document.getElementById('tutorGroup').style.display = rol === 'estudiante' ? 'block' : 'none';
                if (rol === 'estudiante') {
                    const res = await fetch('/api/tutores');
                    const tutores = await res.json();
                    const select = document.getElementById('tutor_id');
                    select.innerHTML = '<option value="">-- Selecciona --</option>' + 
                        tutores.map(t => `<option value="${t.id}">${t.nombre}</option>`).join('');
                }
            }
            document.getElementById('form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const rol = document.getElementById('rol').value;
                const data = {
                    nombre: document.getElementById('nombre').value,
                    email: document.getElementById('email').value,
                    username: document.getElementById('username').value,
                    password: document.getElementById('password').value,
                    rol: rol,
                    tutor_id: rol === 'estudiante' ? parseInt(document.getElementById('tutor_id').value) : null
                };
                try {
                    const res = await fetch('/api/registro', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) });
                    const result = await res.json();
                    if (!res.ok) throw new Error(result.detail);
                    document.getElementById('message').innerHTML = '<p class="success">✅ Registro exitoso. Redirigiendo...</p>';
                    setTimeout(() => window.location.href = '/', 2000);
                } catch (err) {
                    document.getElementById('message').innerHTML = '<p class="error">❌ ' + err.message + '</p>';
                }
            });
            toggleTutor();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
