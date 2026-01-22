"""
ESB Gateway - Enterprise Service Bus
Punto central de entrada para la arquitectura SOA.
Enruta las peticiones a los microservicios correspondientes.
Puerto: 5000
"""

import os
import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Configuración de servicios
SERVICES = {
    "auth": os.getenv("AUTH_SERVICE", "http://localhost:5001"),
    "users": os.getenv("USERS_SERVICE", "http://localhost:5002"),
    "files": os.getenv("FILES_SERVICE", "http://localhost:5003"),
    "appointments": os.getenv("APPOINTMENTS_SERVICE", "http://localhost:5004"),
    "notifications": os.getenv("NOTIFICATIONS_SERVICE", "http://localhost:5005"),
}

# Frontend directory
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")

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
    allow_credentials=True,
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

class CitaRespuesta(BaseModel):
    tutor_id: int
    motivo_rechazo: Optional[str] = None

class FeedbackRequest(BaseModel):
    feedback: str
    tutor_id: int
    estado: Optional[str] = "revisado"

# ========== FUNCIONES AUXILIARES ==========
async def proxy_request(service: str, path: str, method: str = "GET", data: dict = None, params: dict = None):
    """Proxy request to microservice"""
    url = f"{SERVICES[service]}{path}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, json=data)
            elif method == "PUT":
                response = await client.put(url, json=data)
            elif method == "DELETE":
                response = await client.delete(url)
            else:
                raise HTTPException(status_code=405, detail="Method not allowed")
            
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response.json().get("detail", "Error"))
            
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Servicio {service} no disponible: {str(e)}")

async def check_service_health(service: str) -> dict:
    """Check if a service is healthy"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{SERVICES[service]}/health")
            if response.status_code == 200:
                return {"servicio": service, "estado": "activo", "detalles": response.json()}
            return {"servicio": service, "estado": "error", "detalles": None}
    except:
        return {"servicio": service, "estado": "inactivo", "detalles": None}

# ========== FRONTEND ==========

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main frontend page"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Replace API_URL for direct file access
            content = content.replace("const API_URL = '/api'", "const API_URL = 'http://localhost:5000/api'")
            return HTMLResponse(content=content)
    return HTMLResponse("<h1>Sistema TFG SOA - ESB Gateway</h1><p>Frontend no disponible. Acceda a <a href='/docs'>/docs</a> para la API.</p>")

@app.get("/registro", response_class=HTMLResponse)
async def serve_registro():
    """Serve registration page"""
    return HTMLResponse(content="""
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
            .warning { background: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; margin-bottom: 15px; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎓 Registro de Usuario</h1>
            <div class="warning">⚠️ <strong>Importante:</strong> Los estudiantes DEBEN seleccionar un tutor (requisito obligatorio)</div>
            <div id="message"></div>
            <form id="form">
                <div class="form-group"><label>Nombre completo *</label><input type="text" id="nombre" required></div>
                <div class="form-group"><label>Email *</label><input type="email" id="email" required></div>
                <div class="form-group"><label>Usuario *</label><input type="text" id="username" required></div>
                <div class="form-group"><label>Contraseña *</label><input type="password" id="password" required minlength="6"></div>
                <div class="form-group"><label>Rol *</label><select id="rol" onchange="toggleTutor()"><option value="estudiante">Estudiante</option><option value="tutor">Tutor</option></select></div>
                <div class="form-group" id="tutorGroup"><label>Tutor asignado * (obligatorio para estudiantes)</label><select id="tutor_id" required><option value="">-- Selecciona tu tutor --</option></select></div>
                <button type="submit">Registrarse</button>
            </form>
            <div class="link"><a href="/">← Volver al login</a></div>
        </div>
        <script>
            const API_URL = 'http://localhost:5000/api';
            
            async function toggleTutor() {
                const rol = document.getElementById('rol').value;
                const tutorGroup = document.getElementById('tutorGroup');
                const tutorSelect = document.getElementById('tutor_id');
                
                if (rol === 'estudiante') {
                    tutorGroup.style.display = 'block';
                    tutorSelect.required = true;
                    const res = await fetch(API_URL + '/tutores');
                    const tutores = await res.json();
                    tutorSelect.innerHTML = '<option value="">-- Selecciona tu tutor --</option>' + 
                        tutores.map(t => `<option value="${t.id}">${t.nombre} (${t.email})</option>`).join('');
                } else {
                    tutorGroup.style.display = 'none';
                    tutorSelect.required = false;
                }
            }
            
            document.getElementById('form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const rol = document.getElementById('rol').value;
                const tutor_id = document.getElementById('tutor_id').value;
                
                if (rol === 'estudiante' && !tutor_id) {
                    document.getElementById('message').innerHTML = '<p class="error">❌ Los estudiantes DEBEN tener un tutor asignado</p>';
                    return;
                }
                
                const data = {
                    nombre: document.getElementById('nombre').value,
                    email: document.getElementById('email').value,
                    username: document.getElementById('username').value,
                    password: document.getElementById('password').value,
                    rol: rol,
                    tutor_id: rol === 'estudiante' ? parseInt(tutor_id) : null
                };
                
                try {
                    const res = await fetch(API_URL + '/registro', { 
                        method: 'POST', 
                        headers: {'Content-Type': 'application/json'}, 
                        body: JSON.stringify(data) 
                    });
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
    """)

# ========== HEALTH & STATUS ==========

@app.get("/api/health")
async def health_check():
    """Check system health"""
    services_status = []
    for service in SERVICES:
        status = await check_service_health(service)
        services_status.append(status)
    
    active = sum(1 for s in services_status if s["estado"] == "activo")
    
    return {
        "sistema": "Sistema TFG SOA",
        "estado": "operativo" if active == len(SERVICES) else "degradado",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "servicios": services_status,
        "servicios_activos": active,
        "total_servicios": len(SERVICES)
    }

@app.get("/api/services")
async def list_services():
    """List all available services"""
    return {
        "servicios": [
            {"nombre": "auth", "puerto": 5001, "descripcion": "Autenticación y tokens"},
            {"nombre": "users", "puerto": 5002, "descripcion": "Gestión de usuarios"},
            {"nombre": "files", "puerto": 5003, "descripcion": "Gestión de archivos"},
            {"nombre": "appointments", "puerto": 5004, "descripcion": "Gestión de citas"},
            {"nombre": "notifications", "puerto": 5005, "descripcion": "Notificaciones"},
        ]
    }

# ========== AUTENTICACIÓN ==========

@app.post("/api/login")
async def login(request: LoginRequest):
    """Login user"""
    return await proxy_request("auth", "/login", "POST", request.dict())

@app.post("/api/logout")
async def logout():
    """Logout user"""
    return {"mensaje": "Sesión cerrada correctamente"}

@app.post("/api/validate-token")
async def validate_token(token: str):
    """Validate token"""
    return await proxy_request("auth", "/validate", "POST", {"token": token})

# ========== USUARIOS ==========

@app.post("/api/registro")
async def registrar_usuario(usuario: UsuarioRegistro):
    """Register new user"""
    return await proxy_request("users", "/", "POST", usuario.dict())

@app.get("/api/usuarios")
async def listar_usuarios(rol: Optional[str] = None):
    """List users"""
    params = {"rol": rol} if rol else None
    return await proxy_request("users", "/", "GET", params=params)

@app.get("/api/usuarios/{usuario_id}")
async def obtener_usuario(usuario_id: int):
    """Get user by ID"""
    return await proxy_request("users", f"/{usuario_id}", "GET")

@app.get("/api/tutores")
async def listar_tutores():
    """List available tutors"""
    return await proxy_request("users", "/tutores/lista", "GET")

@app.get("/api/tutores/{tutor_id}/estudiantes")
async def estudiantes_tutor(tutor_id: int):
    """Get students of a tutor"""
    return await proxy_request("users", f"/tutores/{tutor_id}/estudiantes", "GET")

# ========== ARCHIVOS ==========

@app.post("/api/archivos/subir")
async def subir_archivo(estudiante_id: int = Form(...), file: UploadFile = File(...)):
    """Upload file"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Read file content
            content = await file.read()
            
            # Prepare multipart form data
            files = {"file": (file.filename, content, file.content_type or "application/octet-stream")}
            data = {"estudiante_id": str(estudiante_id)}
            
            response = await client.post(
                f"{SERVICES['files']}/subir", 
                files=files, 
                data=data
            )
            
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail", "Error subiendo archivo")
                except:
                    detail = response.text or "Error subiendo archivo"
                raise HTTPException(status_code=response.status_code, detail=detail)
            
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Servicio files no disponible: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/archivos/estudiante/{estudiante_id}")
async def archivos_estudiante(estudiante_id: int):
    """Get student files"""
    return await proxy_request("files", f"/estudiante/{estudiante_id}", "GET")

@app.get("/api/archivos/tutor/{tutor_id}")
async def archivos_tutor(tutor_id: int, estado: Optional[str] = None):
    """Get tutor files"""
    params = {"estado": estado} if estado else None
    return await proxy_request("files", f"/tutor/{tutor_id}", "GET", params=params)

@app.post("/api/archivos/{archivo_id}/feedback")
async def feedback_archivo(archivo_id: int, feedback: str = Form(...), tutor_id: int = Form(...), estado: str = Form("revisado")):
    """Add feedback to a file"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{SERVICES['files']}/{archivo_id}/feedback",
                data={
                    "feedback": feedback,
                    "tutor_id": str(tutor_id),
                    "estado": estado
                }
            )
            
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail", "Error enviando feedback")
                except:
                    detail = response.text or "Error enviando feedback"
                raise HTTPException(status_code=response.status_code, detail=detail)
            
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Servicio files no disponible: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/archivos/{archivo_id}/descargar")
async def descargar_archivo(archivo_id: int):
    """Download file"""
    return await proxy_request("files", f"/{archivo_id}/descargar", "GET")

# ========== CITAS ==========

@app.post("/api/citas/solicitar")
async def solicitar_cita(cita: CitaSolicitud):
    """Request appointment"""
    return await proxy_request("appointments", "/solicitar", "POST", cita.dict())

@app.get("/api/citas/usuario/{usuario_id}")
async def citas_usuario(usuario_id: int):
    """Get user appointments"""
    return await proxy_request("appointments", f"/usuario/{usuario_id}", "GET")

@app.get("/api/citas/tutor/{tutor_id}")
async def citas_tutor(tutor_id: int, estado: Optional[str] = None):
    """Get tutor appointments"""
    params = {"estado": estado} if estado else None
    return await proxy_request("appointments", f"/tutor/{tutor_id}", "GET", params=params)

@app.put("/api/citas/{cita_id}/confirmar")
async def confirmar_cita(cita_id: int, request: CitaRespuesta):
    """Confirm appointment"""
    return await proxy_request("appointments", f"/{cita_id}/confirmar", "PUT", request.dict())

@app.put("/api/citas/{cita_id}/rechazar")
async def rechazar_cita(cita_id: int, request: CitaRespuesta):
    """Reject appointment"""
    return await proxy_request("appointments", f"/{cita_id}/rechazar", "PUT", request.dict())

@app.put("/api/citas/{cita_id}/cancelar")
async def cancelar_cita(cita_id: int, usuario_id: int):
    """Cancel appointment"""
    return await proxy_request("appointments", f"/{cita_id}/cancelar", "PUT", {"usuario_id": usuario_id})

# ========== NOTIFICACIONES ==========

@app.get("/api/notificaciones/{usuario_id}")
async def obtener_notificaciones(usuario_id: int):
    """Get user notifications"""
    return await proxy_request("notifications", f"/usuario/{usuario_id}", "GET")

@app.put("/api/notificaciones/{notificacion_id}/leer")
async def marcar_leida(notificacion_id: int, usuario_id: int):
    """Mark notification as read"""
    return await proxy_request("notifications", f"/{notificacion_id}/leer", "PUT", {"usuario_id": usuario_id})

@app.put("/api/notificaciones/leer-todas/{usuario_id}")
async def marcar_todas_leidas(usuario_id: int):
    """Mark all notifications as read"""
    return await proxy_request("notifications", f"/leer-todas/{usuario_id}", "PUT")

# ========== MAIN ==========

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 ESB Gateway - Sistema TFG SOA")
    print("=" * 60)
    print(f"📍 Gateway:       http://localhost:5000")
    print(f"📍 API Docs:      http://localhost:5000/docs")
    print(f"📍 Frontend:      http://localhost:5000/")
    print("=" * 60)
    print("Servicios requeridos:")
    for name, url in SERVICES.items():
        print(f"   • {name}: {url}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=5000)