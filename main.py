#!/usr/bin/env python3
"""
Orchestrator ISA OS - Portal Centralizado
FastAPI + SQLite + PWA
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
from enum import Enum
import sqlite3
import json
import os
import uuid

# ─── CONFIGURACIÓN ─────────────────────────────────────────
DB_PATH = "orchestrator_isa.db"
STATIC_DIR = "static"
TEMPLATES_DIR = "templates"

# Login simple (cambiar en producción)
ADMIN_USER = os.getenv("ADMIN_USER", "isa")
ADMIN_PASS = os.getenv("ADMIN_PASS", "orchestrator2024")

def verify_password(username: str, password: str) -> bool:
    return username == ADMIN_USER and password == ADMIN_PASS

app = FastAPI(
    title="Orchestrator ISA OS",
    description="Sistema Operativo de Ventas y Digitalización",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ─── MODELOS DE DATOS ──────────────────────────────────────

class EstadoLead(str, Enum):
    PROSPECCION = "prospeccion"
    AUDITORIA = "auditoria"
    OBJECION = "objecion"
    PROPUESTA_ENVIADA = "propuesta_enviada"
    SEGUIMIENTO_D2 = "seguimiento_d2"
    SEGUIMIENTO_D5 = "seguimiento_d5"
    SEGUIMIENTO_D10 = "seguimiento_d10"
    CERRADO = "cerrado"
    ONBOARDING = "onboarding"
    EJECUCION = "ejecucion"
    ENTREGADO = "entregado"
    MANTENIMIENTO = "mantenimiento"
    RENOVACION = "renovacion"
    ARCHIVADO = "archivado"
    REACTIVACION = "reactivacion"

class TipoNegocio(str, Enum):
    CLINICA_DENTAL = "clinica_dental"
    SALON_BELLEZA = "salon_belleza"
    RESTAURANTE = "restaurante"
    CAFE = "cafe"
    CONSULTORIO_MEDICO = "consultorio_medico"
    TALLER_MECANICO = "taller_mecanico"
    FARMACIA = "farmacia"
    GIMNASIO = "gimnasio"
    ACADEMIA_IDIOMAS = "academia_idiomas"
    PANADERIA = "panaderia"
    INMOBILIARIA = "inmobiliaria"
    OTRO = "otro"

class PackRecomendado(str, Enum):
    PRESENCIA = "presencia"
    WHATSAPP_PRO = "whatsapp_pro"
    AUTOMATIZACION = "automatizacion"
    COMPLETO = "completo"
    NO_CLIENTE = "no_cliente"

class ValidacionInput(BaseModel):
    nombre_negocio: str = Field(..., min_length=2, max_length=100)
    tipo_negocio: TipoNegocio
    nombre_dueno: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    usa_whatsapp: int = Field(..., ge=0, le=2)
    en_google_maps: int = Field(..., ge=0, le=2)
    consultas_diarias: int = Field(..., ge=0, le=1)
    competidores_digitalizados: int = Field(..., ge=0, le=1)
    dueno_smartphone: int = Field(..., ge=0, le=2)
    notas: Optional[str] = None

class CotizacionInput(BaseModel):
    lead_id: str
    pack: PackRecomendado
    precio_personalizado: Optional[int] = None
    notas: Optional[str] = None

class SeguimientoInput(BaseModel):
    lead_id: str
    tipo: str
    mensaje: str
    canal: str = "whatsapp"

# ─── PRECIOS BASE ──────────────────────────────────────────

PRECIOS = {
    "presencia": {"entrada": 250, "mantenimiento": 150, "nombre": "Pack Presencia"},
    "whatsapp_pro": {"entrada": 400, "mantenimiento": 200, "nombre": "WhatsApp Pro"},
    "automatizacion": {"entrada": 800, "mantenimiento": 350, "nombre": "Automatización"},
    "completo": {"entrada": 1200, "mantenimiento": 500, "nombre": "Pack Completo"},
}

SPEECHES = {
    "clinica_dental": "El 60% de pacientes nuevos buscan 'dentista cerca de mí' en Google. Si no aparece en Maps con fotos reales de su consultorio, esos pacientes van a su competencia.",
    "salon_belleza": "Sus clientas le escriben a las 11pm preguntando precios. A las 8am ya encontraron otra peluquería que respondió. Automatice las respuestas 24/7.",
    "restaurante": "El 70% de los pedidos empiezan por WhatsApp. Si tarda más de 5 minutos en responder, el cliente ya pidió en otro lado. Catálogo digital + respuestas automáticas.",
    "cafe": "Los clientes buscan cafeterías en Google Maps a toda hora. Sin ficha optimizada con fotos y horarios, aparece su competencia primero.",
    "consultorio_medico": "Un paciente con dolor busca 'médico urgente Tetuán' a las 2am. Si no aparece en Google o su WhatsApp está apagado, pierde esa consulta.",
    "taller_mecanico": "Los talleres con web y WhatsApp profesional cobran 20% más porque generan confianza desde el primer mensaje. Tarjeta digital + catálogo de servicios.",
    "farmacia": "La gente busca medicamentos por WhatsApp a toda hora. Sin respuesta automática, van a la farmacia de la esquina. Catálogo de productos más consultados.",
    "gimnasio": "Enero es su mes dorado: todo el mundo quiere inscribirse. Pero si su WhatsApp se satura o no responde en 5 minutos, pierde 3 de cada 10 inscripciones.",
    "academia_idiomas": "Las inscripciones son estacionales: septiembre y enero. Sin presencia digital constante, pierde alumnos a academias que sí aparecen en Google.",
    "panaderia": "El pan artesanal se vende por Instagram: foto del croissant dorado, pedido por DM, entrega en 30 min. Sin sistema, pierde pedidos en los mensajes.",
    "inmobiliaria": "Un lead de inmobiliaria se enfría en 15 minutos si no responde. Formulario de captación que le avisa al WhatsApp instantáneamente.",
    "otro": "Cada día que pasa sin presencia digital, su competencia le roba clientes. Empecemos hoy.",
}

# ─── INICIALIZACIÓN DB ─────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            nombre_negocio TEXT NOT NULL,
            tipo_negocio TEXT NOT NULL,
            nombre_dueno TEXT,
            telefono TEXT,
            direccion TEXT,
            score INTEGER,
            pack_recomendado TEXT,
            estado TEXT DEFAULT 'prospeccion',
            speech TEXT,
            precio_entrada INTEGER,
            precio_mantenimiento INTEGER,
            notas TEXT,
            created_at TEXT,
            updated_at TEXT,
            fecha_cierre TEXT,
            fecha_entrega TEXT,
            fecha_renovacion TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            pack TEXT,
            precio_entrada INTEGER,
            precio_mantenimiento INTEGER,
            estado TEXT DEFAULT 'pendiente',
            created_at TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads (id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS seguimientos (
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            tipo TEXT,
            mensaje TEXT,
            canal TEXT,
            enviado INTEGER DEFAULT 0,
            fecha_envio TEXT,
            created_at TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads (id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS actividades (
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            tipo TEXT,
            descripcion TEXT,
            created_at TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads (id)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ─── FUNCIONES CORE ────────────────────────────────────────

def calcular_score(data: ValidacionInput) -> dict:
    score = 0
    detalles = {}

    if data.usa_whatsapp == 2:
        score += 2; detalles["wa"] = "Activo +2"
    elif data.usa_whatsapp == 1:
        score += 1; detalles["wa"] = "Parcial +1"
    else:
        detalles["wa"] = "No +0"

    if data.en_google_maps == 0:
        score += 2; detalles["gm"] = "No aparece +2"
    elif data.en_google_maps == 1:
        score += 1; detalles["gm"] = "Parcial +1"
    else:
        detalles["gm"] = "Completo +0"

    if data.consultas_diarias == 1:
        score += 2; detalles["q"] = "10+ consultas +2"
    else:
        detalles["q"] = "<10 consultas +0"

    if data.competidores_digitalizados == 1:
        score += 2; detalles["comp"] = "Competidores SI +2"
    else:
        score += 1; detalles["comp"] = "Sin competencia +1"

    if data.dueno_smartphone == 2:
        score += 2; detalles["phone"] = "Activo +2"
    elif data.dueno_smartphone == 1:
        score += 1; detalles["phone"] = "Básico +1"
    else:
        detalles["phone"] = "No +0"

    if score >= 8:
        pack = PackRecomendado.COMPLETO
        pack_key = "completo"
        accion = "CLIENTE IDEAL - Contactar HOY"
    elif score >= 5:
        pack = PackRecomendado.WHATSAPP_PRO
        pack_key = "whatsapp_pro"
        accion = "BUEN CLIENTE - Contactar esta semana"
    elif score >= 3:
        pack = PackRecomendado.PRESENCIA
        pack_key = "presencia"
        accion = "CLIENTE BÁSICO - Contactar si hay tiempo"
    else:
        pack = PackRecomendado.NO_CLIENTE
        pack_key = None
        accion = "RECHAZAR - No invertir tiempo"

    speech = SPEECHES.get(data.tipo_negocio.value, SPEECHES["otro"])

    return {
        "score": score,
        "max_score": 10,
        "pack": pack.value,
        "pack_nombre": PRECIOS[pack_key]["nombre"] if pack_key else "No aplica",
        "precio_entrada": PRECIOS[pack_key]["entrada"] if pack_key else 0,
        "precio_mantenimiento": PRECIOS[pack_key]["mantenimiento"] if pack_key else 0,
        "accion": accion,
        "speech": speech,
        "detalles": detalles,
    }

def generar_cotizacion_html(lead_id: str, pack: str, precio_entrada: int, precio_mantenimiento: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = c.fetchone()
    conn.close()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")

    nombre_negocio = lead[1]
    nombre_dueno = lead[3] or "Cliente"
    telefono = lead[4] or "+212 786 120 081"
    pack_nombre = PRECIOS[pack]["nombre"]

    features = {
        "presencia": [
            "Google Maps optimizado con fotos y horarios",
            "WhatsApp Business básico configurado",
            "Verificación mensual de funcionamiento",
            "Capacitación de 15 minutos incluida",
        ],
        "whatsapp_pro": [
            "Catálogo de productos/servicios con fotos",
            "Respuestas automáticas 24/7",
            "10 respuestas rápidas personalizadas",
            "Ajustes mensuales según temporada",
        ],
        "automatizacion": [
            "Chatbot con IA que entiende a tus clientes",
            "Flujos automáticos: pedido → confirmación → entrega",
            "Optimización continua según conversaciones",
            "Reporte mensual de conversaciones y conversiones",
        ],
        "completo": [
            "Todo lo anterior incluido",
            "Contenido mensual para redes sociales",
            "SEO local para aparecer primero en tu zona",
            "Reporte mensual con métricas de crecimiento",
        ],
    }

    fecha = datetime.now().strftime("%d/%m/%Y")

    features_html = "".join(f'<li>{f}</li>' for f in features.get(pack, []))

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Propuesta - {nombre_negocio}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a; color: white; min-height: 100vh; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; }}
        .header {{ text-align: center; padding: 30px 0; border-bottom: 3px solid #00b894; }}
        .header h1 {{ color: #00b894; font-size: 2.2rem; margin-bottom: 10px; }}
        .header h2 {{ font-size: 1.2rem; color: #94a3b8; }}
        .info {{ padding: 20px 0; border-bottom: 1px solid #1e293b; }}
        .info-row {{ display: flex; justify-content: space-between; padding: 8px 0; }}
        .info-label {{ color: #94a3b8; }}
        .info-value {{ color: white; font-weight: 600; }}
        .pack-section {{ padding: 30px 0; text-align: center; }}
        .pack-name {{ color: #00b894; font-size: 1.8rem; font-weight: bold; margin-bottom: 10px; }}
        .price {{ font-size: 3rem; color: #00b894; font-weight: bold; margin: 20px 0; }}
        .price-mes {{ font-size: 1.2rem; color: #94a3b8; }}
        .features {{ list-style: none; padding: 20px 0; }}
        .features li {{ padding: 12px 0; padding-left: 35px; position: relative; border-bottom: 1px solid #1e293b; }}
        .features li::before {{ content: "✓"; position: absolute; left: 0; color: #00b894; font-weight: bold; font-size: 1.2rem; }}
        .cta {{ background: #00b894; color: white; padding: 18px 40px; border-radius: 50px; text-align: center; font-size: 1.3rem; font-weight: bold; margin: 30px 0; text-decoration: none; display: block; }}
        .footer {{ text-align: center; padding: 20px 0; color: #64748b; font-size: 0.9rem; border-top: 1px solid #1e293b; }}
        .guarantee {{ background: #1e293b; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center; }}
        .guarantee p {{ color: #00b894; font-size: 1.1rem; }}
        @media print {{ body {{ background: white; color: #0f172a; }} .header h1 {{ color: #00b894; }} .cta {{ background: #00b894; color: white; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 ORCHESTRATOR ISA</h1>
            <h2>Propuesta Personalizada</h2>
        </div>
        <div class="info">
            <div class="info-row"><span class="info-label">Cliente:</span><span class="info-value">{nombre_dueno}</span></div>
            <div class="info-row"><span class="info-label">Negocio:</span><span class="info-value">{nombre_negocio}</span></div>
            <div class="info-row"><span class="info-label">Fecha:</span><span class="info-value">{fecha}</span></div>
        </div>
        <div class="pack-section">
            <div class="pack-name">{pack_nombre}</div>
            <div class="price">{precio_entrada} MAD</div>
            <div class="price-mes">+ {precio_mantenimiento} MAD/mes mantenimiento</div>
        </div>
        <ul class="features">
            {features_html}
        </ul>
        <div class="guarantee">
            <p>✅ Garantía: Si en 30 días no ve resultados, le devolvemos el 100%</p>
            <p style="margin-top:10px; color:#94a3b8; font-size:0.9rem;">Entrega: 24-72 horas | Capacitación: 15 min incluida</p>
        </div>
        <a href="https://wa.me/212786120081" class="cta">📱 Aceptar Propuesta: +212 786 120 081</a>
        <div class="footer">
            <p>orchestrator.isa@gmail.com | github.com/AssistantIsa</p>
            <p style="margin-top:10px;">Auditoría gratuita de 5 minutos</p>
        </div>
    </div>
</body>
</html>"""
    return html

# ─── API ENDPOINTS ─────────────────────────────────────────

@app.post("/api/validar")
async def validar_negocio(data: ValidacionInput):
    resultado = calcular_score(data)
    lead_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO leads (id, nombre_negocio, tipo_negocio, nombre_dueno, telefono,
                          direccion, score, pack_recomendado, estado, speech,
                          precio_entrada, precio_mantenimiento, notas, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (lead_id, data.nombre_negocio, data.tipo_negocio.value, data.nombre_dueno,
          data.telefono, data.direccion, resultado["score"], resultado["pack"],
          "prospeccion", resultado["speech"], resultado["precio_entrada"],
          resultado["precio_mantenimiento"], data.notas, now, now))
    conn.commit()
    conn.close()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO actividades (id, lead_id, tipo, descripcion, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (str(uuid.uuid4())[:8], lead_id, "validacion", f"Score: {resultado['score']}/10", now))
    conn.commit()
    conn.close()

    return {
        "lead_id": lead_id,
        "negocio": data.nombre_negocio,
        **resultado,
        "siguiente_paso": "Agendar auditoría express de 5 minutos" if resultado["score"] >= 3 else "Archivar y reactivar en 30 días",
    }

@app.post("/api/cotizar")
async def generar_cotizacion(data: CotizacionInput):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id = ?", (data.lead_id,))
    lead = c.fetchone()
    conn.close()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")

    pack = data.pack.value
    precio_entrada = data.precio_personalizado or PRECIOS[pack]["entrada"]
    precio_mantenimiento = PRECIOS[pack]["mantenimiento"]

    html = generar_cotizacion_html(data.lead_id, pack, precio_entrada, precio_mantenimiento)

    filename = f"cotizacion_{data.lead_id}_{datetime.now().strftime('%Y%m%d')}.html"
    filepath = os.path.join(STATIC_DIR, "cotizaciones", filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    cotizacion_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO cotizaciones (id, lead_id, pack, precio_entrada, precio_mantenimiento, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cotizacion_id, data.lead_id, pack, precio_entrada, precio_mantenimiento, now))
    c.execute("""
        UPDATE leads SET estado = ?, updated_at = ? WHERE id = ?
    """, ("propuesta_enviada", now, data.lead_id))
    conn.commit()
    conn.close()

    return {
        "cotizacion_id": cotizacion_id,
        "lead_id": data.lead_id,
        "pack": pack,
        "precio_entrada": precio_entrada,
        "precio_mantenimiento": precio_mantenimiento,
        "url_html": f"/static/cotizaciones/{filename}",
        "mensaje": "Cotización generada. Comparta el link con el cliente o abra en el navegador para imprimir/PDF."
    }

@app.get("/api/leads")
async def listar_leads(estado: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if estado:
        c.execute("SELECT * FROM leads WHERE estado = ? ORDER BY created_at DESC", (estado,))
    else:
        c.execute("SELECT * FROM leads ORDER BY created_at DESC")
    leads = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"total": len(leads), "leads": leads}

@app.get("/api/leads/{lead_id}")
async def obtener_lead(lead_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = c.fetchone()
    if not lead:
        conn.close()
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    c.execute("SELECT * FROM actividades WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,))
    actividades = [dict(row) for row in c.fetchall()]
    c.execute("SELECT * FROM cotizaciones WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,))
    cotizaciones = [dict(row) for row in c.fetchall()]
    c.execute("SELECT * FROM seguimientos WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,))
    seguimientos = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"lead": dict(lead), "actividades": actividades, "cotizaciones": cotizaciones, "seguimientos": seguimientos}

@app.post("/api/leads/{lead_id}/estado")
async def cambiar_estado(lead_id: str, nuevo_estado: str):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = c.fetchone()
    if not lead:
        conn.close()
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    c.execute("UPDATE leads SET estado = ?, updated_at = ? WHERE id = ?", (nuevo_estado, now, lead_id))
    c.execute("""
        INSERT INTO actividades (id, lead_id, tipo, descripcion, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (str(uuid.uuid4())[:8], lead_id, "cambio_estado", f"{lead[8]} -> {nuevo_estado}", now))
    conn.commit()
    conn.close()
    return {"lead_id": lead_id, "estado_anterior": lead[8], "estado_nuevo": nuevo_estado}

@app.post("/api/seguimiento")
async def registrar_seguimiento(data: SeguimientoInput):
    seg_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO seguimientos (id, lead_id, tipo, mensaje, canal, enviado, fecha_envio, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (seg_id, data.lead_id, data.tipo, data.mensaje, data.canal, 0, None, now))
    conn.commit()
    conn.close()
    return {"seguimiento_id": seg_id, "lead_id": data.lead_id, "tipo": data.tipo, "estado": "programado"}

@app.get("/api/dashboard")
async def dashboard():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT estado, COUNT(*) FROM leads GROUP BY estado")
    estados = {row[0]: row[1] for row in c.fetchall()}
    c.execute("SELECT COUNT(*) FROM leads")
    total_leads = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE estado = 'cerrado'")
    cerrados = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM leads WHERE estado = 'mantenimiento'")
    activos = c.fetchone()[0] or 0
    c.execute("SELECT SUM(precio_entrada) FROM leads WHERE estado IN ('cerrado', 'ejecucion', 'entregado', 'mantenimiento')")
    ingresos_entrada = c.fetchone()[0] or 0
    c.execute("SELECT SUM(precio_mantenimiento) FROM leads WHERE estado = 'mantenimiento'")
    ingresos_mes = c.fetchone()[0] or 0
    mes_actual = datetime.now().strftime("%Y-%m")
    c.execute("SELECT COUNT(*) FROM leads WHERE strftime('%Y-%m', created_at) = ?", (mes_actual,))
    leads_mes = c.fetchone()[0] or 0
    conn.close()
    tasa_cierre = (cerrados / total_leads * 100) if total_leads > 0 else 0
    return {
        "kpi": {
            "total_leads": total_leads,
            "leads_este_mes": leads_mes,
            "clientes_cerrados": cerrados,
            "clientes_activos": activos,
            "tasa_cierre_porciento": round(tasa_cierre, 1),
            "ingresos_entrada_total": ingresos_entrada,
            "ingresos_recurrentes_mes": ingresos_mes,
            "ingresos_anual_proyectado": ingresos_mes * 12,
        },
        "por_estado": estados,
        "meta_mes_6": {
            "clientes_objetivo": 40,
            "ingresos_recurrentes_objetivo": 10000,
            "progreso_clientes": round(activos / 40 * 100, 1),
            "progreso_ingresos": round(ingresos_mes / 10000 * 100, 1),
        }
    }

@app.get("/api/seguimientos/pendientes")
async def seguimientos_pendientes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT s.*, l.nombre_negocio, l.nombre_dueno, l.telefono
        FROM seguimientos s
        JOIN leads l ON s.lead_id = l.id
        WHERE s.enviado = 0
        ORDER BY s.created_at DESC
    """)
    pendientes = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"total": len(pendientes), "pendientes": pendientes}

# ─── PORTAL WEB CON LOGIN ──────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def portal_login(request: Request):
    """Página de login del portal"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if verify_password(username, password):
        return RedirectResponse(url="/portal", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Credenciales incorrectas"})

@app.get("/portal", response_class=HTMLResponse)
async def portal_main(request: Request):
    """Portal principal con diagrama interactivo"""
    return templates.TemplateResponse("portal.html", {"request": request})

@app.get("/portal/{section}", response_class=HTMLResponse)
async def portal_section(request: Request, section: str):
    """Secciones del portal"""
    valid_sections = ["catalogos", "scripts", "seguimiento", "landing", "idioma", "speeches", "diagrama", "validador", "leads", "dashboard"]
    if section not in valid_sections:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    return templates.TemplateResponse(f"portal_{section}.html", {"request": request})

# ─── MONTAR ESTÁTICOS ────────────────────────────────────

os.makedirs(os.path.join(STATIC_DIR, "cotizaciones"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
