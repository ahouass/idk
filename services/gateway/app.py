"""
ESB Gateway - Enterprise Service Bus
Punto central de entrada para la arquitectura SOA.
Enruta las peticiones a los microservicios correspondientes.
Puerto: 5000
"""
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import httpx
import os
from datetime import datetime

# Configuración de servicios
SERVICES = {
    "auth": os.getenv("AUTH_SERVICE", "http://localhost:5001"),
    "users": os.getenv("USERS_SERVICE", "http://localhost:5002"),
    "files": os.getenv("FILES_SERVICE", "http://localhost:5003"),
    "appointments": os.getenv("APPOINTMENTS_SERVICE", "http://localhost:5004"),
    "notifications": os.getenv("NOTIFICATIONS_SERVICE", "http://localhost:5005"),
}

app = FastAPI(
    title="ESB Gateway - Sistema TFG SOA",
    description="""
    **Enterprise Service Bus (ESB)** - Punto central de la arquitectura SOA.
    
    Este gateway actúa como intermediario entre el cliente y los microservicios,
    proporcionando:
    - Enrutamiento de peticiones
    - Agregación de respuestas
    - Gestión centralizada de errores
    - Documentación unificada de la API
    
    ## Servicios disponibles:
    - **Auth** (puerto 5001): Autenticación y tokens
    - **Users** (puerto 5002): Gestión de usuarios
    - **Files** (puerto 5003): Gestión de archivos
    - **Appointments** (puerto 5004): Gestión de citas
    - **Notifications** (puerto 5005): Notificaciones
    """,
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
    lugar: Optional[str] = "Por determinar"

class CitaRespuesta(BaseModel):
    tutor_id: int
    aceptar: bool
    motivo_rechazo: Optional[str] = None
    lugar: Optional[str] = None
    notas: Optional[str] = None

class FeedbackRequest(BaseModel):
    feedback: str
    tutor_id: int
    estado: Optional[str] = "revisado"

# ========== FUNCIONES AUXILIARES ==========
async def proxy_request(service: str, path: str, method: str = "GET", data: dict = None, params: dict = None):
    """Realizar petición a un microservicio"""
    if service not in SERVICES:
        raise HTTPException(status_code=400, detail=f"Servicio desconocido: {service}")
    
    url = f"{SERVICES[service]}{path}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, json=data, params=params)
            elif method == "PUT":
                response = await client.put(url, json=data, params=params)
            elif method == "DELETE":
                response = await client.delete(url, params=params)
            else:
                raise HTTPException(status_code=400, detail=f"Método no soportado: {method}")
            
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Servicio '{service}' no disponible"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error comunicándose con servicio '{service}': {str(e)}"
            )

async def check_service_health(service: str) -> dict:
    """Verificar estado de un servicio"""
    try:
        result = await proxy_request(service, "/health")
        return {"servicio": service, "estado": "activo", "detalles": result}
    except:
        return {"servicio": service, "estado": "inactivo", "detalles": None}

# ========== ENDPOINTS PRINCIPALES ==========

@app.get("/")
async def serve_frontend():
    """Servir página principal"""
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return HTMLResponse("<h1>Sistema TFG SOA - ESB Gateway</h1><p>Frontend no disponible. Acceda a /docs para la API.</p>")

@app.get("/api/health")
async def health_check():
    """Estado general del sistema y todos los servicios"""
    servicios_estado = []
    
    for service in SERVICES.keys():
        estado = await check_service_health(service)
        servicios_estado.append(estado)
    
    servicios_activos = sum(1 for s in servicios_estado if s["estado"] == "activo")
    
    return {
        "sistema": "Sistema TFG SOA",
        "estado": "operativo" if servicios_activos > 0 else "degradado",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "servicios": servicios_estado,
        "servicios_activos": servicios_activos,
        "total_servicios": len(SERVICES)
    }

@app.get("/api/services")
async def listar_servicios():
    """Listar todos los servicios disponibles"""
    return {
        "servicios": list(SERVICES.keys()),
        "urls": SERVICES,
        "descripcion": {
            "auth": "Autenticación y gestión de tokens",
            "users": "Gestión de usuarios (estudiantes y tutores)",
            "files": "Gestión de archivos y entregas",
            "appointments": "Gestión de citas y tutorías",
            "notifications": "Sistema de notificaciones"
        }
    }

# ========== AUTENTICACIÓN (auth service) ==========

@app.post("/api/login")
async def login(request: LoginRequest):
    """Iniciar sesión"""
    return await proxy_request("auth", "/login", "POST", request.dict())

@app.post("/api/logout")
async def logout(token: str):
    """Cerrar sesión"""
    return await proxy_request("auth", "/logout", "POST", {"token": token})

@app.post("/api/validate-token")
async def validate_token(token: str):
    """Validar token"""
    return await proxy_request("auth", "/validate", "POST", {"token": token})

# ========== USUARIOS (users service) ==========

@app.post("/api/registro")
async def registrar_usuario(usuario: UsuarioRegistro):
    """Registrar nuevo usuario"""
    return await proxy_request("users", "/", "POST", usuario.dict())

@app.get("/api/usuarios")
async def listar_usuarios(rol: Optional[str] = None):
    """Listar usuarios, opcionalmente por rol"""
    params = {"rol": rol} if rol else None
    return await proxy_request("users", "/", params=params)

@app.get("/api/usuarios/{usuario_id}")
async def obtener_usuario(usuario_id: int):
    """Obtener información de un usuario"""
    return await proxy_request("users", f"/{usuario_id}")

@app.get("/api/tutores")
async def listar_tutores():
    """Listar todos los tutores"""
    return await proxy_request("users", "/tutores/lista")

@app.get("/api/tutores/{tutor_id}/estudiantes")
async def estudiantes_del_tutor(tutor_id: int):
    """Obtener estudiantes de un tutor"""
    return await proxy_request("users", f"/tutores/{tutor_id}/estudiantes")

# ========== ARCHIVOS (files service) ==========

@app.post("/api/archivos/subir")
async def subir_archivo(
    estudiante_id: int = Form(...),
    file: UploadFile = File(...)
):
    """Subir archivo (PDF o ZIP)"""
    # Obtener tutor_id del estudiante
    try:
        usuario = await proxy_request("users", f"/{estudiante_id}")
        tutor_id = usuario.get("tutor_id", 1)
    except:
        tutor_id = 1
    
    # Enviar archivo al servicio de archivos
    url = f"{SERVICES['files']}/subir"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            files = {"file": (file.filename, await file.read(), file.content_type)}
            data = {"estudiante_id": str(estudiante_id), "tutor_id": str(tutor_id)}
            response = await client.post(url, files=files, data=data)
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Servicio de archivos no disponible")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error subiendo archivo: {str(e)}")

@app.get("/api/archivos/estudiante/{estudiante_id}")
async def archivos_estudiante(estudiante_id: int):
    """Obtener archivos de un estudiante"""
    return await proxy_request("files", f"/estudiante/{estudiante_id}")

@app.get("/api/archivos/tutor/{tutor_id}")
async def archivos_tutor(tutor_id: int, estado: Optional[str] = None):
    """Obtener archivos asignados a un tutor"""
    params = {"estado": estado} if estado else None
    return await proxy_request("files", f"/tutor/{tutor_id}", params=params)

@app.post("/api/archivos/{archivo_id}/feedback")
async def agregar_feedback(archivo_id: int, request: FeedbackRequest):
    """Agregar feedback a un archivo"""
    return await proxy_request("files", f"/{archivo_id}/feedback", "POST", request.dict())

@app.get("/api/archivos/{archivo_id}/descargar")
async def descargar_archivo(archivo_id: int):
    """Descargar archivo"""
    url = f"{SERVICES['files']}/{archivo_id}/descargar"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                # Obtener nombre del archivo de los headers
                content_disposition = response.headers.get("content-disposition", "")
                filename = "archivo"
                if "filename=" in content_disposition:
                    filename = content_disposition.split("filename=")[-1].strip('"')
                
                return FileResponse(
                    path=response.content,
                    filename=filename,
                    media_type="application/octet-stream"
                )
            raise HTTPException(status_code=response.status_code, detail="Error descargando archivo")
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Servicio de archivos no disponible")

# ========== CITAS (appointments service) ==========

@app.post("/api/citas/solicitar")
async def solicitar_cita(request: CitaSolicitud):
    """Solicitar nueva cita"""
    return await proxy_request("appointments", "/solicitar", "POST", request.dict())

@app.put("/api/citas/{cita_id}/confirmar")
async def confirmar_cita(cita_id: int, tutor_id: int):
    """Confirmar una cita (tutor)"""
    return await proxy_request(
        "appointments", 
        f"/{cita_id}/responder", 
        "PUT", 
        {"tutor_id": tutor_id, "aceptar": True}
    )

@app.put("/api/citas/{cita_id}/rechazar")
async def rechazar_cita(cita_id: int, tutor_id: int, motivo: Optional[str] = None):
    """Rechazar una cita (tutor)"""
    return await proxy_request(
        "appointments",
        f"/{cita_id}/responder",
        "PUT",
        {"tutor_id": tutor_id, "aceptar": False, "motivo_rechazo": motivo}
    )

@app.put("/api/citas/{cita_id}/cancelar")
async def cancelar_cita(cita_id: int, usuario_id: int):
    """Cancelar una cita"""
    return await proxy_request("appointments", f"/{cita_id}/cancelar", "PUT", params={"usuario_id": usuario_id})

@app.get("/api/citas/usuario/{usuario_id}")
async def citas_usuario(usuario_id: int, estado: Optional[str] = None):
    """Obtener citas de un usuario"""
    params = {"estado": estado} if estado else None
    return await proxy_request("appointments", f"/usuario/{usuario_id}", params=params)

@app.get("/api/citas/agenda/{usuario_id}")
async def agenda_usuario(usuario_id: int):
    """Obtener agenda de citas confirmadas"""
    return await proxy_request("appointments", f"/agenda/{usuario_id}")

# ========== NOTIFICACIONES (notifications service) ==========

@app.get("/api/notificaciones/{usuario_id}")
async def obtener_notificaciones(usuario_id: int, solo_no_leidas: bool = False):
    """Obtener notificaciones de un usuario"""
    params = {"solo_no_leidas": solo_no_leidas}
    return await proxy_request("notifications", f"/usuario/{usuario_id}", params=params)

@app.put("/api/notificaciones/{notificacion_id}/leer")
async def marcar_notificacion_leida(notificacion_id: int, usuario_id: int):
    """Marcar notificación como leída"""
    return await proxy_request("notifications", f"/{notificacion_id}/leer", "PUT", params={"usuario_id": usuario_id})

@app.put("/api/notificaciones/leer-todas/{usuario_id}")
async def marcar_todas_leidas(usuario_id: int):
    """Marcar todas las notificaciones como leídas"""
    return await proxy_request("notifications", f"/usuario/{usuario_id}/leer-todas", "PUT")

@app.get("/api/notificaciones/contador/{usuario_id}")
async def contador_notificaciones(usuario_id: int):
    """Obtener contador de notificaciones no leídas"""
    return await proxy_request("notifications", f"/contador/{usuario_id}")

# ========== ENDPOINT REGISTRO (HTML) ==========

@app.get("/registro", response_class=HTMLResponse)
async def pagina_registro():
    """Página de registro"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Registro - Sistema TFG SOA</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                padding: 40px;
                max-width: 500px;
                width: 100%;
            }
            h1 { color: #2c3e50; margin-bottom: 30px; text-align: center; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 8px; color: #555; font-weight: 500; }
            input, select { 
                width: 100%; 
                padding: 12px 15px; 
                border: 2px solid #e0e0e0; 
                border-radius: 10px; 
                font-size: 16px;
                transition: border-color 0.3s;
            }
            input:focus, select:focus { 
                outline: none; 
                border-color: #667eea; 
            }
            button { 
                width: 100%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; 
                border: none; 
                padding: 15px; 
                border-radius: 10px; 
                font-size: 18px;
                cursor: pointer; 
                margin-top: 20px;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            button:hover { 
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
            }
            .error { color: #e74c3c; background: #ffeaea; padding: 10px; border-radius: 5px; margin-bottom: 15px; }
            .success { color: #27ae60; background: #eafff0; padding: 10px; border-radius: 5px; margin-bottom: 15px; }
            .login-link { text-align: center; margin-top: 20px; }
            .login-link a { color: #667eea; text-decoration: none; }
            .login-link a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎓 Registro en Sistema TFG</h1>
            <div id="message"></div>
            <form id="registroForm">
                <div class="form-group">
                    <label>Nombre completo:</label>
                    <input type="text" id="nombre" required placeholder="Ej: Juan Pérez García">
                </div>
                <div class="form-group">
                    <label>Email:</label>
                    <input type="email" id="email" required placeholder="Ej: usuario@usal.es">
                </div>
                <div class="form-group">
                    <label>Nombre de usuario:</label>
                    <input type="text" id="username" required placeholder="Ej: jperez">
                </div>
                <div class="form-group">
                    <label>Contraseña:</label>
                    <input type="password" id="password" required placeholder="Mínimo 6 caracteres">
                </div>
                <div class="form-group">
                    <label>Rol:</label>
                    <select id="rol" onchange="toggleTutorField()">
                        <option value="estudiante">Estudiante</option>
                        <option value="tutor">Tutor</option>
                    </select>
                </div>
                <div class="form-group" id="tutorGroup">
                    <label>Tutor asignado:</label>
                    <select id="tutor_id">
                        <option value="">-- Selecciona tu tutor --</option>
                    </select>
                </div>
                <button type="submit">Crear Cuenta</button>
            </form>
            <div class="login-link">
                <p>¿Ya tienes cuenta? <a href="/">Inicia sesión aquí</a></p>
            </div>
        </div>
        
        <script>
            function toggleTutorField() {
                const rol = document.getElementById('rol').value;
                const tutorGroup = document.getElementById('tutorGroup');
                tutorGroup.style.display = rol === 'estudiante' ? 'block' : 'none';
                
                if (rol === 'estudiante') {
                    cargarTutores();
                }
            }
            
            async function cargarTutores() {
                try {
                    const response = await fetch('/api/tutores');
                    const tutores = await response.json();
                    
                    const select = document.getElementById('tutor_id');
                    select.innerHTML = '<option value="">-- Selecciona tu tutor --</option>';
                    
                    tutores.forEach(tutor => {
                        const option = document.createElement('option');
                        option.value = tutor.id;
                        option.textContent = `${tutor.nombre} (${tutor.email})`;
                        select.appendChild(option);
                    });
                } catch (error) {
                    console.error('Error cargando tutores:', error);
                }
            }
            
            document.getElementById('registroForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const rol = document.getElementById('rol').value;
                const tutor_id = document.getElementById('tutor_id').value;
                
                if (rol === 'estudiante' && !tutor_id) {
                    document.getElementById('message').innerHTML = 
                        '<p class="error">Por favor selecciona un tutor</p>';
                    return;
                }
                
                const usuario = {
                    nombre: document.getElementById('nombre').value,
                    email: document.getElementById('email').value,
                    username: document.getElementById('username').value,
                    password: document.getElementById('password').value,
                    rol: rol,
                    tutor_id: rol === 'estudiante' ? parseInt(tutor_id) : null
                };
                
                try {
                    const response = await fetch('/api/registro', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(usuario)
                    });
                    
                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Error en registro');
                    }
                    
                    document.getElementById('message').innerHTML = 
                        '<p class="success">✅ ' + data.mensaje + '. Redirigiendo...</p>';
                    
                    setTimeout(() => {
                        window.location.href = '/';
                    }, 2000);
                    
                } catch (error) {
                    document.getElementById('message').innerHTML = 
                        '<p class="error">❌ Error: ' + error.message + '</p>';
                }
            });
            
            // Inicializar
            toggleTutorField();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
