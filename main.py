"""
Orchestrator ISA OS v13.4.2 — FIX DEFINITIVO
FastAPI + asyncpg + Neon PostgreSQL + Jinja2
DB Migration completa + Cache invalidation
"""

import os
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncpg

# ─── CONFIG ─────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
PORT = int(os.getenv("PORT", "8000"))

COOKIE_NAME = "isa_session"
SESSION_MAX_AGE = 86400 * 7

# ============================================================
# IMPORTAR ROUTER DE LEADS (DESPUÉS DE LAS CONFIGS)
# ============================================================
from leads_router_v3 import router as leads_router

# ─── PYDANTIC MODELS ────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    nombre: str
    telefono: str
    tipo_negocio: str = "restaurante"
    ciudad: str = "Tetuan"
    notas: str = ""
    fuente: str = "manual"

class LeadUpdate(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    tipo_negocio: Optional[str] = None
    ciudad: Optional[str] = None
    notas: Optional[str] = None
    estado: Optional[str] = None
    score: Optional[int] = None
    pack_recomendado: Optional[str] = None
    caso: Optional[str] = None
    web: Optional[str] = None
    rrss: Optional[str] = None
    whatsapp_business: Optional[bool] = None
    rating: Optional[float] = None
    resenas: Optional[int] = None

class CotizacionCreate(BaseModel):
    lead_id: int
    pack: str
    precio_entrada: int
    precio_mantenimiento: int = 0
    notas: str = ""
    tipo: str = "nueva"

class UsuarioCreate(BaseModel):
    username: str
    password: str
    nombre_display: str
    rol: str = "vendedor"

class LoginForm(BaseModel):
    username: str
    password: str

class ProgresoVenta(BaseModel):
    momento: str
    completado: bool = True
    notas: str = ""

class ClasificacionLead(BaseModel):
    caso: str
    score: int = Field(..., ge=0, le=10)
    respuestas_auditoria: dict = {}

# ─── CASOS A-G + PACKS + SPEECHES ───────────────────────────────────────

CASOS = {
    "A": {"nombre": "El Fantasma", "criterio": "Sin web, sin RRSS, sin WA Business", "prioridad": 1, "color": "#EF4444", "emoji": "🔴", "pack_recomendado": "base", "pack_nombre": "Pack Base", "pack_precio": 900, "pitch": "Su competencia ya está en internet y usted no aparece ni en Google Maps. Está perdiendo clientes todos los días."},
    "B": {"nombre": "El Influencer Cojo", "criterio": "Solo RRSS, sin web propia", "prioridad": 2, "color": "#F97316", "emoji": "🟠", "pack_recomendado": "base", "pack_nombre": "Pack Base", "pack_precio": 900, "pitch": "Si Facebook le cierra la cuenta mañana, pierde todo. Necesita su propio espacio en internet con dominio propio."},
    "C": {"nombre": "El Desactualizado", "criterio": "Web vieja, no responsive, mal hecha", "prioridad": 4, "color": "#EAB308", "emoji": "🟡", "pack_recomendado": "completo", "pack_nombre": "Pack Completo", "pack_precio": 1200, "pitch": "Su web carga en 8 segundos y no se ve en móvil. Google lo penaliza y los clientes se van."},
    "D": {"nombre": "El WhatsApp Caótico", "criterio": "WA personal, sin catálogo, sin respuestas automáticas", "prioridad": 3, "color": "#F97316", "emoji": "🟠", "pack_recomendado": "whatsapp_pro", "pack_nombre": "WhatsApp Pro", "pack_precio": 400, "pitch": "Está perdiendo 3 de cada 10 mensajes porque no tiene catálogo ni respuestas automáticas. Los clientes se cansan de esperar."},
    "E": {"nombre": "La Mina de Oro", "criterio": "+40 reseñas, sin web, alto tráfico en Maps", "prioridad": 1, "color": "#EF4444", "emoji": "🔴", "pack_recomendado": "conversion", "pack_nombre": "Pack Conversión", "pack_precio": 2500, "pitch": "Tiene 40+ reseñas y clientes buscándolo, pero no tiene web para capturarlos. Es una mina de oro sin herramientas."},
    "F": {"nombre": "El Semi-Digital", "criterio": "Todo básico, quiere escalar y automatizar", "prioridad": 5, "color": "#00FF88", "emoji": "🟢", "pack_recomendado": "automatizacion", "pack_nombre": "Automatización", "pack_precio": 800, "pitch": "Tiene buena base. Ahora necesita automatización para no perder tiempo respondiendo lo mismo y escalar sin contratar más gente."},
    "G": {"nombre": "El Competidor Digital", "criterio": "Ya tiene todo profesionalmente configurado", "prioridad": 7, "color": "#94A3B8", "emoji": "⚪", "pack_recomendado": None, "pack_nombre": None, "pack_precio": 0, "pitch": "Ya tiene todo bien configurado. ¿Le gustaría una auditoría gratuita para ver si hay oportunidades de mejora?"},
}

PACKS = {
    "presencia": {"nombre": "Pack Presencia", "precio": 250, "mantenimiento": 150, "color": "#94A3B8"},
    "whatsapp_pro": {"nombre": "WhatsApp Pro", "precio": 400, "mantenimiento": 200, "color": "#F97316"},
    "automatizacion": {"nombre": "Automatización", "precio": 800, "mantenimiento": 350, "color": "#00FF88"},
    "completo": {"nombre": "Pack Completo", "precio": 1200, "mantenimiento": 500, "color": "#00E5FF"},
    "base": {"nombre": "Pack Base", "precio": 900, "mantenimiento": 150, "color": "#EAB308"},
    "conversion": {"nombre": "Pack Conversión", "precio": 2500, "mantenimiento": 200, "color": "#EF4444"},
    "escala": {"nombre": "Pack Escala", "precio": 8000, "mantenimiento": 500, "color": "#A855F7"},
}

ESTADOS = ["nuevo", "auditoria", "objecion", "propuesta_enviada", "cerrado", "onboarding", "ejecucion", "entregado", "mantenimiento", "seguimiento", "rechazado"]

SPEECHES = {
    "M0": {"titulo": "Preparación", "icono": "📋", "objetivo": "Validar que el lead es potencial antes de contactar", "checklist": ["Verificar nombre del negocio y teléfono", "Confirmar tipo de negocio y ciudad", "Revisar si ya existe en el CRM", "Asignar vendedor responsable"], "speech": "Lead registrado: {nombre}. Negocio: {tipo_negocio} en {ciudad}. Listo para iniciar contacto."},
    "M1": {"titulo": "Apertura", "icono": "👋", "objetivo": "Presentarse y ofrecer auditoría gratuita de 5 min", "speech_template": "¡Hola! Soy {vendedor} de IA Boost Prufer. Me dedico a ayudar a negocios como {nombre} a vender más desde el móvil.\n\nNoté que {observacion}. ¿Le gustaría que le haga una auditoría gratuita de 5 minutos para ver qué está perdiendo?", "observaciones": {"A": "no aparece en Google Maps cuando busco {tipo_negocio} en esta zona", "B": "solo tiene redes sociales pero no tiene página web propia", "C": "su web no se ve bien en móvil y carga muy lento", "D": "su WhatsApp no tiene catálogo de productos ni respuestas automáticas", "E": "tiene muchas reseñas en Google pero no tiene web para capturar esos clientes", "F": "ya tiene presencia digital básica pero podría automatizar mucho más", "G": "ya tiene todo bien configurado, pero quizás hay oportunidades de mejora"}},
    "M2": {"titulo": "Objeción de Precio", "icono": "💰", "objetivo": "Desviar la pregunta de precio hacia la auditoría", "speech_desviacion": "Depende de lo que necesite. Por eso le propongo la auditoría gratuita: en 5 minutos le digo exactamente qué tiene bien, qué le está haciendo perder clientes, y cuánto cuesta solucionarlo. No hay compromiso.", "speech_precio": "Desde {precio_minimo} MAD puede empezar. Pero prefiero que vea primero qué necesita, para no cobrarle de más ni de menos."},
    "M3": {"titulo": "Auditoría Express", "icono": "🔍", "objetivo": "Hacer 5 preguntas clave y clasificar el caso A-G", "preguntas": [{"id": "usa_whatsapp", "texto": "¿Usa WhatsApp para atender clientes?", "peso": 2}, {"id": "google_maps", "texto": "¿Aparece su negocio en Google Maps completo?", "peso": 2}, {"id": "consultas_diarias", "texto": "¿Recibe más de 10 consultas al día?", "peso": 2}, {"id": "competidores", "texto": "¿Sus competidores tienen presencia digital?", "peso": 2}, {"id": "smartphone", "texto": "¿Usa smartphone activamente para el negocio?", "peso": 2}], "speech_cierre": "Gracias por su tiempo. Según lo que me cuenta, su negocio califica como {caso_nombre}. Le explico por qué:"},
    "M4": {"titulo": "Diagnóstico", "icono": "📊", "objetivo": "Presentar pérdidas estimadas y comparar con competencia", "speech": "Le cuento: usted está perdiendo aproximadamente {perdida_estimada} clientes al mes porque {razon}.\n\nSus competidores sí están capturando esos clientes con {solucion_competencia}. Yo le puedo solucionar eso en 48 horas.", "perdidas": {"A": {"clientes": 15, "razon": "no aparece en Google Maps ni tiene web", "solucion": "Google Business + landing page"}, "B": {"clientes": 10, "razon": "depende 100% de redes sociales que puede perder", "solucion": "web propia con dominio"}, "C": {"clientes": 8, "razon": "su web no funciona en móvil y Google lo penaliza", "solucion": "web responsive optimizada"}, "D": {"clientes": 12, "razon": "no tiene catálogo ni respuestas automáticas", "solucion": "WhatsApp Business con catálogo"}, "E": {"clientes": 20, "razon": "tiene tráfico pero no lo convierte", "solucion": "landing persuasiva + funnel"}, "F": {"clientes": 5, "razon": "pierde tiempo en tareas repetitivas", "solucion": "automatización con IA"}, "G": {"clientes": 0, "razon": "ya está bien posicionado", "solucion": "auditoría gratuita"}}},
    "M5": {"titulo": "Mostrar Opciones", "icono": "📦", "objetivo": "Presentar packs recomendados según caso", "speech": "Aquí tiene. Estos son los packs que tengo. El que más le conviene según la auditoría es el {pack_nombre} por {pack_precio} MAD."},
    "M6": {"titulo": "Manejo de Dudas", "icono": "❓", "objetivo": "Reafirmar valor con ejemplos y comparaciones", "speech": "Mire, esto es lo que hacen en Estados Unidos con presupuestos de 10,000 dólares. Yo le traigo la versión para su negocio y su presupuesto.\n\nNo necesita invertir miles. Empezamos en {precio_minimo} MAD y escalamos según resultados.", "ejemplos": [{"nombre": "Clínica Dental", "url": "grandstreetdental.com", "sector": "salud"}, {"nombre": "Café Premium", "url": "onyxcoffeelab.com", "sector": "restaurante"}, {"nombre": "Salón Belleza", "url": "sirensalonsf.com", "sector": "belleza"}, {"nombre": "Consultorio Médico", "url": "onemedical.com", "sector": "salud"}, {"nombre": "Gimnasio", "url": "equinox.com", "sector": "fitness"}]},
    "M7": {"titulo": "Cierre", "icono": "✅", "objetivo": "Enviar propuesta y solicitar 50% anticipado", "speech": "Le envío por WhatsApp la propuesta con el precio exacto y lo que incluye.\n\nSi le parece, empezamos mañana. Solo necesito 50% adelantado ({anticipo} MAD) para comenzar y el resto al entregar.\n\n¿Le parece bien?"},
}

# ─── HELPERS ──────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256((password + SECRET_KEY).encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def generate_session_token() -> str:
    return secrets.token_urlsafe(32)

def get_db_url() -> str:
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "?" in url:
        url = url.split("?")[0]
    if "sslmode" not in url:
        url += "?sslmode=require"
    return url

# ─── DB LIFESPAN CON MIGRACIÓN COMPLETA ─────────────────────────────────

pool: Optional[asyncpg.Pool] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(get_db_url(), min_size=2, max_size=10)
    async with pool.acquire() as conn:
        # 1. Crear tabla leads si no existe (v13.3 compatible)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(255) NOT NULL,
                telefono VARCHAR(50) NOT NULL,
                tipo_negocio VARCHAR(100) DEFAULT 'restaurante',
                ciudad VARCHAR(100) DEFAULT 'Tetuan',
                estado VARCHAR(50) DEFAULT 'nuevo',
                score INTEGER DEFAULT 0,
                pack_recomendado VARCHAR(50) DEFAULT '',
                caso VARCHAR(10) DEFAULT '',
                fuente VARCHAR(50) DEFAULT 'manual',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 2. MIGRACIÓN leads: Agregar columnas nuevas si no existen
        leads_cols = [
            ("notas", "TEXT DEFAULT ''"),
            ("web", "VARCHAR(255) DEFAULT ''"),
            ("rrss", "VARCHAR(255) DEFAULT ''"),
            ("whatsapp_business", "BOOLEAN DEFAULT FALSE"),
            ("rating", "REAL DEFAULT 0"),
            ("resenas", "INTEGER DEFAULT 0"),
            ("vendedor_id", "INTEGER DEFAULT NULL"),
            ("momento_actual", "VARCHAR(10) DEFAULT 'M0'"),
            ("fecha_inicio_mantenimiento", "TIMESTAMP DEFAULT NULL"),
            ("pack_contratado", "VARCHAR(50) DEFAULT ''"),
            ("precio_mantenimiento_mensual", "INTEGER DEFAULT 0"),
            ("proxima_renovacion", "TIMESTAMP DEFAULT NULL"),
        ]
        for col_name, col_type in leads_cols:
            try:
                await conn.execute(f'ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col_name} {col_type}')
            except Exception as e:
                print(f"[MIGRACIÓN leads] {col_name}: {e}")

        # 3. Tabla lead_historial
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_historial (
                id SERIAL PRIMARY KEY,
                lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                campo VARCHAR(100) NOT NULL,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                vendedor_id INTEGER,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 3.1 MIGRACIÓN lead_historial: Agregar notas si no existe
        try:
            await conn.execute("ALTER TABLE lead_historial ADD COLUMN IF NOT EXISTS notas TEXT DEFAULT ''")
        except Exception as e:
            print(f"[MIGRACIÓN lead_historial] notas: {e}")

        # 4. Tabla cotizaciones
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id SERIAL PRIMARY KEY,
                lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                pack VARCHAR(50) NOT NULL,
                precio_entrada INTEGER NOT NULL,
                precio_mantenimiento INTEGER DEFAULT 0,
                estado VARCHAR(50) DEFAULT 'pendiente',
                notas TEXT DEFAULT '',
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 4.1 MIGRACIÓN cotizaciones: Agregar tipo si no existe
        try:
            await conn.execute("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'nueva'")
        except Exception as e:
            print(f"[MIGRACIÓN cotizaciones] tipo: {e}")

        # 5. Tabla usuarios
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                nombre_display VARCHAR(255) NOT NULL,
                rol VARCHAR(20) DEFAULT 'vendedor',
                activo BOOLEAN DEFAULT TRUE,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 6. Tabla sesiones
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sesiones (
                token VARCHAR(255) PRIMARY KEY,
                usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
                expira TIMESTAMP NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 7. Tabla servicios
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS servicios (
                id SERIAL PRIMARY KEY,
                codigo VARCHAR(100) UNIQUE NOT NULL,
                nombre VARCHAR(255) NOT NULL,
                categoria VARCHAR(100),
                precio_base INTEGER DEFAULT 0,
                activo BOOLEAN DEFAULT TRUE
            )
        """)
        # 8. Tabla referidos
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referidos (
                id SERIAL PRIMARY KEY,
                codigo VARCHAR(50) UNIQUE NOT NULL,
                nombre_referidor VARCHAR(255),
                telefono_referidor VARCHAR(50),
                lead_id INTEGER REFERENCES leads(id),
                comision_pagada BOOLEAN DEFAULT FALSE,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 9. Insertar/actualizar admin
        admin_hash = hash_password("admin123")
        await conn.execute("""
            INSERT INTO usuarios (username, password_hash, nombre_display, rol)
            VALUES ('admin', $1, 'Administrador', 'admin')
            ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash
        """, admin_hash)
        # 10. Insertar packs como servicios
        for codigo, pack in PACKS.items():
            await conn.execute("""
                INSERT INTO servicios (codigo, nombre, categoria, precio_base)
                VALUES ($1, $2, 'pack', $3)
                ON CONFLICT (codigo) DO NOTHING
            """, codigo, pack["nombre"], pack["precio"])

        # 11. Crear tabla leads_scrap (para leads de Outscraper)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS leads_scrap (
                id SERIAL PRIMARY KEY,
                nombre_negocio VARCHAR(255) NOT NULL,
                telefono VARCHAR(50),
                whatsapp BOOLEAN DEFAULT FALSE,
                email VARCHAR(255),
                tiene_web BOOLEAN DEFAULT FALSE,
                website_url TEXT,
                tiene_facebook BOOLEAN DEFAULT FALSE,
                facebook_url TEXT,
                tiene_instagram BOOLEAN DEFAULT FALSE,
                instagram_url TEXT,
                direccion TEXT,
                ciudad VARCHAR(100) DEFAULT 'Tetouan',
                latitud DECIMAL(10, 7),
                longitud DECIMAL(10, 7),
                place_id VARCHAR(255) UNIQUE,
                google_id VARCHAR(255),
                google_maps_url TEXT,
                rating DECIMAL(3, 2),
                num_reviews INTEGER DEFAULT 0,
                categoria VARCHAR(100),
                subtipos TEXT,
                estado_negocio VARCHAR(50) DEFAULT 'OPERATIONAL',
                caso_negocio VARCHAR(1),
                notas_scraping TEXT,
                estrategia_venta VARCHAR(50),
                pack_recomendado VARCHAR(50),
                precio_recomendado INTEGER,
                score INTEGER DEFAULT 0,
                score_detalle JSONB DEFAULT '{}',
                estado VARCHAR(20) DEFAULT 'nuevo',
                fuente VARCHAR(50) DEFAULT 'outscraper',
                raw_data JSONB DEFAULT '{}',
                ultimo_contacto TIMESTAMP,
                mensaje_enviado TEXT,
                respuesta_recibida TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # 11. LIMPIAR CACHE DE STATEMENTS (fix InvalidCachedStatementError)
        try:
            await conn.execute("DISCARD ALL")
            print("[CACHE] Statements cache limpiado")
        except Exception as e:
            print(f"[CACHE] No se pudo limpiar: {e}")

    yield
    await pool.close()

# ─── FASTAPI APP ─────────────────────────────────────────────────────────

app = FastAPI(title="Orchestrator ISA v13.4.2", lifespan=lifespan)

# ============================================================
# REGISTRAR ROUTER DE LEADS (DESPUÉS DE CREAR app)
# ============================================================
app.include_router(leads_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── AUTH DEPENDENCIES ───────────────────────────────────────────────────

async def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME)
    if not token or not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.username, u.nombre_display, u.rol, u.activo
            FROM sesiones s
            JOIN usuarios u ON s.usuario_id = u.id
            WHERE s.token = $1 AND s.expira > NOW() AND u.activo = TRUE
            """,
            token
        )
        if row:
            return dict(row)
    return None

async def require_auth(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    return user

async def require_admin(request: Request):
    user = await get_current_user(request)
    if not user or user["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Requiere rol admin")
    return user

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/portal", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

@app.post("/auth/login")
async def auth_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash, activo FROM usuarios WHERE username = $1",
            username
        )
        if not row or not verify_password(password, row["password_hash"]) or not row["activo"]:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Usuario o contraseña incorrectos",
                "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
            }, status_code=401)
        token = generate_session_token()
        expira = datetime.utcnow() + timedelta(seconds=SESSION_MAX_AGE)
        await conn.execute(
            "INSERT INTO sesiones (token, usuario_id, expira) VALUES ($1, $2, $3)",
            token, row["id"], expira
        )
    response = RedirectResponse(url="/portal", status_code=302)
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return response

@app.post("/auth/logout")
async def auth_logout(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token and pool:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM sesiones WHERE token = $1", token)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response

# ─── API: USUARIOS ──────────────────────────────────────────────────────

@app.post("/api/usuarios")
async def crear_usuario(data: UsuarioCreate, user=Depends(require_admin)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    pw_hash = hash_password(data.password)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO usuarios (username, password_hash, nombre_display, rol)
                   VALUES ($1, $2, $3, $4) RETURNING id, username, nombre_display, rol, activo""",
                data.username, pw_hash, data.nombre_display, data.rol
            )
            return dict(row)
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, "Username ya existe")

@app.get("/api/usuarios")
async def listar_usuarios(user=Depends(require_admin)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, username, nombre_display, rol, activo FROM usuarios ORDER BY id")
        return [dict(r) for r in rows]

# ─── API: LEADS (tabla original) ──────────────────────────────────────────

@app.post("/api/leads")
async def crear_lead(data: LeadCreate):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO leads (nombre, telefono, tipo_negocio, ciudad, notas, fuente)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING *""",
            data.nombre, data.telefono, data.tipo_negocio, data.ciudad,
            data.notas, data.fuente
        )
        await conn.execute(
            """INSERT INTO lead_historial (lead_id, campo, valor_anterior, valor_nuevo, notas)
               VALUES ($1, 'estado', NULL, 'nuevo', 'Lead creado')""",
            row["id"]
        )
        return dict(row)

@app.get("/api/leads")
async def listar_leads(
    estado: Optional[str] = Query(None),
    fuente: Optional[str] = Query(None),
    caso: Optional[str] = Query(None),
    vendedor_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        where = ["1=1"]
        params = []
        if estado:
            where.append(f"estado = ${len(params)+1}")
            params.append(estado)
        if fuente:
            where.append(f"fuente = ${len(params)+1}")
            params.append(fuente)
        if caso:
            where.append(f"caso = ${len(params)+1}")
            params.append(caso)
        if vendedor_id:
            where.append(f"vendedor_id = ${len(params)+1}")
            params.append(vendedor_id)
        where_sql = " AND ".join(where)
        rows = await conn.fetch(
            f"SELECT * FROM leads WHERE {where_sql} ORDER BY fecha_creacion DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset
        )
        return [dict(r) for r in rows]

@app.get("/api/leads/{lead_id}")
async def obtener_lead(lead_id: int):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        lead = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        if not lead:
            raise HTTPException(404, "Lead no encontrado")
        historial = await conn.fetch(
            "SELECT * FROM lead_historial WHERE lead_id = $1 ORDER BY fecha DESC", lead_id
        )
        cotizaciones = await conn.fetch(
            "SELECT * FROM cotizaciones WHERE lead_id = $1 ORDER BY fecha DESC", lead_id
        )
        return {"lead": dict(lead), "historial": [dict(h) for h in historial], "cotizaciones": [dict(c) for c in cotizaciones]}

@app.patch("/api/leads/{lead_id}")
async def actualizar_lead(lead_id: int, data: LeadUpdate, user=Depends(require_auth)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        lead = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        if not lead:
            raise HTTPException(404, "Lead no encontrado")
        updates = []
        params = []
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                updates.append(f"{field} = ${len(params)+1}")
                params.append(value)
        if not updates:
            return dict(lead)
        params.append(lead_id)
        await conn.execute(
            f"UPDATE leads SET {', '.join(updates)}, fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = ${len(params)}",
            *params
        )
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None and field in lead and str(lead[field]) != str(value):
                await conn.execute(
                    """INSERT INTO lead_historial (lead_id, campo, valor_anterior, valor_nuevo, vendedor_id, notas)
                       VALUES ($1, $2, $3, $4, $5, $6)""",
                    lead_id, field, str(lead[field]), str(value), user["id"], "Actualizado desde panel vendedor"
                )
        updated = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        return dict(updated)

@app.delete("/api/leads/{lead_id}")
async def eliminar_lead(lead_id: int, user=Depends(require_admin)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM leads WHERE id = $1", lead_id)
    return {"ok": True}

# ─── API: CLASIFICACIÓN Y PROGRESO ───────────────────────────────────────

@app.post("/api/leads/{lead_id}/clasificar")
async def clasificar_lead(lead_id: int, data: ClasificacionLead, user=Depends(require_auth)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    if data.caso not in CASOS:
        raise HTTPException(400, f"Caso {data.caso} no válido. Use: {', '.join(CASOS.keys())}")
    async with pool.acquire() as conn:
        lead = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        if not lead:
            raise HTTPException(404, "Lead no encontrado")
        caso_info = CASOS[data.caso]
        await conn.execute(
            """UPDATE leads SET caso = $1, score = $2, pack_recomendado = $3, estado = 'auditoria',
               fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = $4""",
            data.caso, data.score, caso_info["pack_recomendado"] or "", lead_id
        )
        await conn.execute(
            """INSERT INTO lead_historial (lead_id, campo, valor_anterior, valor_nuevo, vendedor_id, notas)
               VALUES ($1, 'caso', $2, $3, $4, $5)""",
            lead_id, lead.get("caso", ""), data.caso, user["id"],
            f"Auditoría completada. Score: {data.score}/10. Caso: {caso_info['nombre']}. Respuestas: {data.respuestas_auditoria}"
        )
        updated = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        return {"lead": dict(updated), "caso": caso_info, "pack": PACKS.get(caso_info["pack_recomendado"]) if caso_info["pack_recomendado"] else None}

@app.post("/api/leads/{lead_id}/progreso")
async def guardar_progreso(lead_id: int, data: ProgresoVenta, user=Depends(require_auth)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    if data.momento not in SPEECHES:
        raise HTTPException(400, f"Momento {data.momento} no válido")
    async with pool.acquire() as conn:
        lead = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        if not lead:
            raise HTTPException(404, "Lead no encontrado")
        await conn.execute(
            "UPDATE leads SET momento_actual = $1, fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = $2",
            data.momento, lead_id
        )
        await conn.execute(
            """INSERT INTO lead_historial (lead_id, campo, valor_anterior, valor_nuevo, vendedor_id, notas)
               VALUES ($1, 'momento', $2, $3, $4, $5)""",
            lead_id, lead.get("momento_actual", "M0"), data.momento, user["id"], data.notas
        )
        return {"ok": True, "momento": data.momento, "completado": data.completado}

# ─── API: COTIZACIONES ───────────────────────────────────────────────────

@app.post("/api/cotizar")
async def crear_cotizacion(data: CotizacionCreate, user=Depends(require_auth)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    if data.pack not in PACKS:
        raise HTTPException(400, f"Pack {data.pack} no válido")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cotizaciones (lead_id, pack, precio_entrada, precio_mantenimiento, notas, tipo)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            data.lead_id, data.pack, data.precio_entrada, data.precio_mantenimiento, data.notas, data.tipo
        )
        if data.tipo == "renovacion":
            await conn.execute(
                """UPDATE leads SET proxima_renovacion = proxima_renovacion + INTERVAL '30 days',
                   fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = $1""",
                data.lead_id
            )
        return dict(row)

@app.get("/api/cotizar/packs")
async def listar_packs():
    return PACKS

# ─── API: RENOVACIONES ──────────────────────────────────────────────────

@app.get("/api/renovaciones/pendientes")
async def renovaciones_pendientes(user=Depends(require_auth), dias: int = Query(7, ge=1, le=30)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT l.*, c.pack as pack_actual, c.precio_mantenimiento as mantenimiento_actual
               FROM leads l
               LEFT JOIN cotizaciones c ON l.id = c.lead_id AND c.tipo = 'nueva'
               WHERE l.estado = 'mantenimiento'
               AND l.proxima_renovacion <= CURRENT_TIMESTAMP + INTERVAL '%s days'
               AND l.proxima_renovacion > CURRENT_TIMESTAMP
               ORDER BY l.proxima_renovacion ASC""",
            dias
        )
        return [dict(r) for r in rows]

@app.post("/api/leads/{lead_id}/renovacion")
async def generar_renovacion(lead_id: int, user=Depends(require_auth)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        lead = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        if not lead:
            raise HTTPException(404, "Lead no encontrado")
        if lead["estado"] != "mantenimiento":
            raise HTTPException(400, "El lead no está en mantenimiento")
        pack = lead.get("pack_contratado", "")
        if not pack or pack not in PACKS:
            raise HTTPException(400, "Pack contratado no válido")
        pack_info = PACKS[pack]
        row = await conn.fetchrow(
            """INSERT INTO cotizaciones (lead_id, pack, precio_entrada, precio_mantenimiento, notas, tipo)
               VALUES ($1, $2, 0, $3, $4, 'renovacion') RETURNING *""",
            lead_id, pack, pack_info["mantenimiento"],
            f"Renovación automática generada. Próxima renovación: {lead['proxima_renovacion']}"
        )
        await conn.execute(
            """INSERT INTO lead_historial (lead_id, campo, valor_anterior, valor_nuevo, vendedor_id, notas)
               VALUES ($1, 'renovacion', NULL, 'generada', $2, $3)""",
            lead_id, user["id"], f"Cotización de renovación generada: {pack_info['nombre']} - {pack_info['mantenimiento']} MAD/mes"
        )
        return {"cotizacion": dict(row), "pack": pack_info, "lead": dict(lead)}

# ─── API: DASHBOARD ──────────────────────────────────────────────────────

@app.get("/api/dashboard")
async def dashboard(user=Depends(require_auth)):
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        total_leads = await conn.fetchval("SELECT COUNT(*) FROM leads")
        leads_nuevos = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'nuevo'")
        leads_auditoria = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'auditoria'")
        leads_cerrados = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'cerrado'")
        leads_mantenimiento = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'mantenimiento'")
        renovaciones_7d = await conn.fetchval(
            """SELECT COUNT(*) FROM leads WHERE estado = 'mantenimiento'
               AND proxima_renovacion <= CURRENT_TIMESTAMP + INTERVAL '7 days'"""
        )
        ingresos_potenciales = await conn.fetchval(
            "SELECT COALESCE(SUM(precio_entrada), 0) FROM cotizaciones WHERE estado = 'pendiente'"
        )
        ingresos_cerrados = await conn.fetchval(
            "SELECT COALESCE(SUM(precio_entrada), 0) FROM cotizaciones WHERE estado = 'aceptada'"
        )
        mantenimiento_mensual = await conn.fetchval(
            "SELECT COALESCE(SUM(precio_mantenimiento), 0) FROM cotizaciones WHERE estado = 'aceptada'"
        )
        return {
            "total_leads": total_leads, "leads_nuevos": leads_nuevos,
            "leads_auditoria": leads_auditoria, "leads_cerrados": leads_cerrados,
            "leads_mantenimiento": leads_mantenimiento, "renovaciones_7d": renovaciones_7d,
            "ingresos_potenciales": ingresos_potenciales, "ingresos_cerrados": ingresos_cerrados,
            "mantenimiento_mensual": mantenimiento_mensual,
        }

@app.get("/api/servicios")
async def listar_servicios():
    if not pool:
        raise HTTPException(500, "DB no disponible")
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM servicios WHERE activo = TRUE ORDER BY categoria, nombre")
        return [dict(r) for r in rows]

# ─── HEALTH ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    db_status = "disconnected"
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                db_status = "connected"
        except Exception:
            db_status = "error"
    return {"status": "healthy", "db": db_status, "version": "13.4.2"}

# ─── PORTAL ROUTES (PROTEGIDAS) ──────────────────────────────────────────

@app.get("/portal", response_class=HTMLResponse)
async def portal_inicio(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal.html", {
        "request": request, "user": user,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

@app.get("/portal/leads", response_class=HTMLResponse)
async def portal_leads(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal_leads.html", {
        "request": request, "user": user,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

@app.get("/portal/dashboard", response_class=HTMLResponse)
async def portal_dashboard(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal_dashboard.html", {
        "request": request, "user": user,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

@app.get("/portal/cotizador", response_class=HTMLResponse)
async def portal_cotizador(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal_cotizador.html", {
        "request": request, "user": user,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

@app.get("/portal/seguimiento", response_class=HTMLResponse)
async def portal_seguimiento(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal_seguimiento.html", {
        "request": request, "user": user,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

@app.get("/portal/catalogos", response_class=HTMLResponse)
async def portal_catalogos(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal_catalogos.html", {
        "request": request, "user": user, "packs": PACKS,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

@app.get("/portal/speeches", response_class=HTMLResponse)
async def portal_speeches(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal_speeches.html", {
        "request": request, "user": user, "speeches": SPEECHES, "casos": CASOS,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

# ─── VENDEDOR VENTA (PÁGINA PRINCIPAL) ──────────────────────────────────

@app.get("/vendedor/venta", response_class=HTMLResponse)
async def vendedor_venta(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal_vendedor.html", {
        "request": request, "user": user, "casos": CASOS, "packs": PACKS, "speeches": SPEECHES, "estados": ESTADOS,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88", "texto": "#FFFFFF", "texto_secundario": "#94A3B8", "alerta": "#EF4444"}
    })

# ─── VALIDADOR (MÓVIL, RÁPIDO) ──────────────────────────────────────────

@app.get("/portal/validador", response_class=HTMLResponse)
async def portal_validador(request: Request, user=Depends(require_auth)):
    return templates.TemplateResponse("portal_validador.html", {
        "request": request, "user": user, "packs": PACKS,
        "colores": {"fondo": "#0B1120", "card": "#151E32", "cyan": "#00E5FF", "verde": "#00FF88"}
    })

# ─── LANDINGS (PÚBLICAS) ───────────────────────────────────────────────

@app.get("/l/p", response_class=HTMLResponse)
async def landing_prufer(request: Request):
    return templates.TemplateResponse("landings/prufer.html", {"request": request})

@app.get("/l/w", response_class=HTMLResponse)
async def landing_webexpress(request: Request):
    return templates.TemplateResponse("landings/webexpress.html", {"request": request})

# ─── MAIN ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
