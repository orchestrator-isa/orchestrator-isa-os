from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import asyncpg

# ─── Importar routers de la API ───
from api.api_cotizar import router as cotizar_router
from api.referidos import router as referidos_router
from api.reportes import router as reportes_router
from api.scraping import router as scraping_router

# ─── Configuración ───
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/orchestrator")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

# ─── Lifespan: conexión a DB + creación de tablas ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

    async with app.state.db.acquire() as conn:
        # Tabla leads
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                tipo_negocio TEXT NOT NULL,
                telefono TEXT,
                email TEXT,
                score INTEGER DEFAULT 0,
                pack_recomendado TEXT,
                estado TEXT DEFAULT 'prospeccion',
                ciudad TEXT DEFAULT 'tetouan',
                fuente TEXT DEFAULT 'manual',
                fecha_creacion TIMESTAMP DEFAULT NOW(),
                fecha_actualizacion TIMESTAMP DEFAULT NOW()
            )
        """)

        # Tabla cotizaciones
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id SERIAL PRIMARY KEY,
                nombre_negocio TEXT NOT NULL,
                tipo_negocio TEXT NOT NULL,
                pack TEXT NOT NULL,
                pack_nombre TEXT,
                telefono TEXT NOT NULL,
                email TEXT,
                notas TEXT,
                ciudad TEXT DEFAULT 'tetouan',
                precio_entrada INTEGER,
                precio_mantenimiento INTEGER,
                moneda TEXT DEFAULT 'MAD',
                descuento_aplicado INTEGER DEFAULT 0,
                precio_final INTEGER,
                estado TEXT DEFAULT 'pendiente',
                fecha TIMESTAMP DEFAULT NOW()
            )
        """)

        # Tabla referidos
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referidos (
                id SERIAL PRIMARY KEY,
                codigo TEXT UNIQUE NOT NULL,
                nombre_referidor TEXT NOT NULL,
                telefono_referidor TEXT NOT NULL,
                email_referidor TEXT,
                nombre_referido TEXT NOT NULL,
                telefono_referido TEXT NOT NULL,
                tipo_negocio_referido TEXT NOT NULL,
                pack_contratado TEXT,
                notas TEXT,
                estado TEXT DEFAULT 'pendiente',
                comision_pagada INTEGER DEFAULT 0,
                fecha_creacion TIMESTAMP DEFAULT NOW(),
                fecha_actualizacion TIMESTAMP DEFAULT NOW(),
                fecha_cierre TIMESTAMP
            )
        """)

    yield
    await app.state.db.close()

app = FastAPI(
    title="Orchestrator ISA API",
    version="13.2.0",
    description="Sistema de gestión de leads, cotizaciones y referidos para negocios en Marruecos",
    lifespan=lifespan
)

# ─── CORS ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers de la API ───
app.include_router(cotizar_router)
app.include_router(referidos_router)
app.include_router(reportes_router)
app.include_router(scraping_router)

# ─── Static & Templates ───
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Rutas del Portal ───
PORTAL_ROUTES = [
    ("/", "portal.html"),
    ("/portal", "portal.html"),
    ("/portal/validador", "portal_validador.html"),
    ("/portal/leads", "portal_leads.html"),
    ("/portal/dashboard", "portal_dashboard.html"),
    ("/portal/catalogos", "portal_catalogos.html"),
    ("/portal/cotizador", "portal_cotizador.html"),
    ("/portal/diagrama", "portal_diagrama.html"),
    ("/portal/idioma", "portal_idioma.html"),
    ("/portal/landing", "portal_landing.html"),
    ("/portal/scripts", "portal_scripts.html"),
    ("/portal/seguimiento", "portal_seguimiento.html"),
    ("/portal/speeches", "portal_speeches.html"),
]

for route, template in PORTAL_ROUTES:
    @app.get(route, response_class=HTMLResponse)
    async def portal_page(request: Request, template=template):
        return templates.TemplateResponse(template, {"request": request})

# ─── API Legacy: Leads (mantenido para compatibilidad con templates existentes) ───
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class LeadCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    tipo_negocio: str = Field(..., min_length=2)
    telefono: Optional[str] = None
    email: Optional[str] = None
    score: int = Field(0, ge=0, le=10)
    pack_recomendado: Optional[str] = None
    estado: str = Field("prospeccion", pattern="^(prospeccion|auditoria|propuesta|cerrado|mantenimiento)$")
    ciudad: Optional[str] = "tetouan"
    fuente: Optional[str] = "manual"

class LeadOut(BaseModel):
    id: int
    nombre: str
    tipo_negocio: str
    telefono: Optional[str]
    email: Optional[str]
    score: int
    pack_recomendado: Optional[str]
    estado: str
    ciudad: Optional[str]
    fuente: Optional[str]
    fecha_creacion: datetime

@app.post("/api/leads", response_model=LeadOut)
async def crear_lead(lead: LeadCreate, request: Request):
    db = request.app.state.db
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO leads (nombre, tipo_negocio, telefono, email, score, pack_recomendado, estado, ciudad, fuente)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               RETURNING id, nombre, tipo_negocio, telefono, email, score, pack_recomendado, estado, ciudad, fuente, fecha_creacion""",
            lead.nombre, lead.tipo_negocio, lead.telefono, lead.email,
            lead.score, lead.pack_recomendado, lead.estado, lead.ciudad, lead.fuente
        )
    return dict(row)

@app.get("/api/leads")
async def obtener_leads(request: Request, estado: Optional[str] = None, limit: int = 100, offset: int = 0):
    db = request.app.state.db
    async with db.acquire() as conn:
        if estado and estado != "todos":
            rows = await conn.fetch(
                "SELECT * FROM leads WHERE estado = $1 ORDER BY fecha_creacion DESC LIMIT $2 OFFSET $3",
                estado, limit, offset
            )
            total = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = $1", estado)
        else:
            rows = await conn.fetch(
                "SELECT * FROM leads ORDER BY fecha_creacion DESC LIMIT $1 OFFSET $2",
                limit, offset
            )
            total = await conn.fetchval("SELECT COUNT(*) FROM leads")
    return {"leads": [dict(r) for r in rows], "total": total}

@app.get("/api/leads/{lead_id}")
async def obtener_lead(lead_id: int, request: Request):
    db = request.app.state.db
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    return dict(row)

@app.patch("/api/leads/{lead_id}")
async def actualizar_lead(lead_id: int, updates: dict, request: Request):
    db = request.app.state.db
    allowed = {"nombre", "tipo_negocio", "telefono", "email", "score", "pack_recomendado", "estado", "ciudad", "fuente"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        raise HTTPException(status_code=400, detail="No hay campos válidos para actualizar")

    set_clause = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(fields.keys())])

    async with db.acquire() as conn:
        await conn.execute(
            f"UPDATE leads SET {set_clause}, fecha_actualizacion = NOW() WHERE id = $1",
            lead_id, *fields.values()
        )
        row = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    return dict(row)

@app.delete("/api/leads/{lead_id}")
async def eliminar_lead(lead_id: int, request: Request):
    db = request.app.state.db
    async with db.acquire() as conn:
        result = await conn.execute("DELETE FROM leads WHERE id = $1", lead_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    return {"status": "deleted", "id": lead_id}

# ─── API Legacy: Dashboard ───
@app.get("/api/dashboard")
async def dashboard_data(request: Request):
    db = request.app.state.db
    async with db.acquire() as conn:
        leads_totales = await conn.fetchval("SELECT COUNT(*) FROM leads")
        clientes_cerrados = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'cerrado'")
        en_mantenimiento = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'mantenimiento'")
        en_prospeccion = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'prospeccion'")
        en_auditoria = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'auditoria'")
        en_propuesta = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE estado = 'propuesta'")

        ingresos_mes = en_mantenimiento * 250
        total_cerrados_mantenimiento = clientes_cerrados + en_mantenimiento
        tasa_conversion = (total_cerrados_mantenimiento / leads_totales) if leads_totales > 0 else 0

        por_ciudad = await conn.fetch("SELECT ciudad, COUNT(*) as count FROM leads GROUP BY ciudad")
        por_pack = await conn.fetch("SELECT pack_recomendado, COUNT(*) as count FROM leads WHERE pack_recomendado IS NOT NULL GROUP BY pack_recomendado")
        ultimos_7 = await conn.fetchval("SELECT COUNT(*) FROM leads WHERE fecha_creacion >= NOW() - INTERVAL '7 days'")

        # Cotizaciones
        cotizaciones_pendientes = await conn.fetchval("SELECT COUNT(*) FROM cotizaciones WHERE estado = 'pendiente'")
        cotizaciones_aceptadas = await conn.fetchval("SELECT COUNT(*) FROM cotizaciones WHERE estado = 'aceptada'")
        ingresos_cotizaciones = await conn.fetchval("SELECT COALESCE(SUM(precio_final), 0) FROM cotizaciones WHERE estado = 'aceptada'")

        # Referidos
        total_referidos = await conn.fetchval("SELECT COUNT(*) FROM referidos")
        referidos_pagados = await conn.fetchval("SELECT COUNT(*) FROM referidos WHERE estado = 'pagado'")

    return {
        "leads_totales": leads_totales,
        "clientes_cerrados": clientes_cerrados,
        "en_mantenimiento": en_mantenimiento,
        "en_prospeccion": en_prospeccion,
        "en_auditoria": en_auditoria,
        "en_propuesta": en_propuesta,
        "ingresos_mes": ingresos_mes,
        "tasa_conversion": round(tasa_conversion, 3),
        "nuevos_ultimos_7_dias": ultimos_7,
        "por_ciudad": {r["ciudad"]: r["count"] for r in por_ciudad},
        "por_pack": {r["pack_recomendado"]: r["count"] for r in por_pack},
        "cotizaciones": {
            "pendientes": cotizaciones_pendientes,
            "aceptadas": cotizaciones_aceptadas,
            "ingresos_totales": ingresos_cotizaciones
        },
        "referidos": {
            "total": total_referidos,
            "pagados": referidos_pagados
        }
    }

# ─── Health Check ───
@app.get("/health")
async def health_check(request: Request):
    try:
        db = request.app.state.db
        async with db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "db": "connected", "version": "13.2.0"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
