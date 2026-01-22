import sqlite3
import os

# Create data directory
os.makedirs('data', exist_ok=True)

# Connect to database
conn = sqlite3.connect('data/tfg_soa.db')
cursor = conn.cursor()

# Create usuarios table
cursor.execute('''
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    nombre TEXT,
    apellidos TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Create appointments table
cursor.execute('''
CREATE TABLE IF NOT EXISTS citas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tutor_id INTEGER NOT NULL,
    estudiante_id INTEGER,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    estado TEXT DEFAULT 'disponible',
    motivo TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Create files table
cursor.execute('''
CREATE TABLE IF NOT EXISTS archivos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    ruta TEXT NOT NULL,
    usuario_id INTEGER NOT NULL,
    tipo TEXT,
    size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Create notifications table
cursor.execute('''
CREATE TABLE IF NOT EXISTS notificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    mensaje TEXT NOT NULL,
    leida INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Insert default users (password: tutor123 and estudiante123)
# Using simple hash for demo - in production use proper bcrypt
from hashlib import sha256
tutor_hash = sha256("tutor123".encode()).hexdigest()
student_hash = sha256("estudiante123".encode()).hexdigest()

try:
    cursor.execute('''
        INSERT INTO usuarios (username, email, password_hash, role, nombre, apellidos)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', ('tutor1', 'tutor1@example.com', tutor_hash, 'tutor', 'Juan', 'García'))
except sqlite3.IntegrityError:
    pass

try:
    cursor.execute('''
        INSERT INTO usuarios (username, email, password_hash, role, nombre, apellidos)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', ('estudiante1', 'estudiante1@example.com', student_hash, 'estudiante', 'María', 'López'))
except sqlite3.IntegrityError:
    pass

conn.commit()
conn.close()

print("✅ Database initialized successfully!")
print("📍 Database location: data/tfg_soa.db")