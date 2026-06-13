from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json

router = APIRouter()

# === MODELOS ===

class MicroservicioItem(BaseModel):
    id: str
    name: str
    price: int

class CotizacionRequest(BaseModel):
    # Datos del cliente
    negocio: str
    tipo: str
    dueno: Optional[str] = ""
    telefono: str
    email: Optional[str] = ""
    ciudad: Optional[str] = "Marruecos"

    # Selección del catálogo
    pack: Optional[str] = None  # presencia / whatsapp / automatizacion / completo
    micros: List[MicroservicioItem] = []

    # Extra
    notas: Optional[str] = ""
    descuento: Optional[int] = 0  # en MAD

class CotizacionResponse(BaseModel):
    success: bool
    cotizacion_id: str
    html: str
    pdf_url: Optional[str] = None
    resumen: dict
    whatsapp_url: str
    fecha: str


# === CONFIGURACIÓN DE PACKS ===

PACKS = {
    "presencia": {
        "name": "Pack Presencia",
        "price": 250,
        "mant": 150,
        "desc": "Google Maps + WA básico + verificación mensual",
        "features": [
            "Google Maps optimizado",
            "WhatsApp Business básico",
            "Verificación mensual",
            "Capacitación 15 minutos"
        ]
    },
    "whatsapp": {
        "name": "Pack WhatsApp Pro",
        "price": 400,
        "mant": 200,
        "desc": "Catálogo + respuestas automáticas + ajustes mensuales",
        "features": [
            "Catálogo de productos completo",
            "Respuestas automáticas 24/7",
            "10 respuestas rápidas",
            "Ajustes mensuales"
        ]
    },
    "automatizacion": {
        "name": "Pack Automatización",
        "price": 800,
        "mant": 350,
        "desc": "Chatbot IA + flujos + optimización continua",
        "features": [
            "Chatbot con IA integrada",
            "Flujos automáticos personalizados",
            "Optimización continua",
            "Reporte mensual de métricas"
        ]
    },
    "completo": {
        "name": "Pack Completo",
        "price": 1200,
        "mant": 500,
        "desc": "Todo + contenido mensual + SEO local + reportes",
        "features": [
            "Todo lo de los packs anteriores",
            "Contenido mensual para RRSS",
            "SEO local avanzado",
            "Reportes de métricas detallados"
        ]
    }
}


# === GENERADOR DE HTML ===

def generar_html_cotizacion(data: CotizacionRequest, cotizacion_id: str) -> str:
    """Genera el HTML profesional de la cotización"""

    fecha = datetime.now().strftime("%d de %B de %Y")

    # Calcular totales
    pack_price = 0
    pack_mant = 0
    pack_name = ""
    pack_desc = ""
    pack_features = []

    if data.pack and data.pack in PACKS:
        p = PACKS[data.pack]
        pack_price = p["price"]
        pack_mant = p["mant"]
        pack_name = p["name"]
        pack_desc = p["desc"]
        pack_features = p["features"]

    micros_total = sum(m.price for m in data.micros)
    total_entrada = pack_price + micros_total - data.descuento

    # HTML de la cotización
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Propuesta Comercial - {data.negocio}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 700px; margin: 0 auto; background: white; box-shadow: 0 0 50px rgba(0,0,0,0.1); }}

        .header {{ 
            background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%); 
            color: white; 
            padding: 3rem 2rem; 
            text-align: center;
            position: relative;
            overflow: hidden;
        }}
        .header::before {{
            content: '';
            position: absolute;
            top: -50%; left: -50%;
            width: 200%; height: 200%;
            background: radial-gradient(circle, rgba(0,229,255,0.1) 0%, transparent 70%);
        }}
        .header h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; position: relative; }}
        .header p {{ opacity: 0.8; font-size: 0.95rem; position: relative; }}
        .badge {{ 
            display: inline-block; 
            background: linear-gradient(135deg, #00E5FF 0%, #00FF88 100%); 
            color: #0a0a0f; 
            padding: 0.4rem 1rem; 
            border-radius: 100px; 
            font-size: 0.8rem; 
            font-weight: 700; 
            margin-top: 1rem;
            position: relative;
        }}

        .content {{ padding: 2rem; }}

        .cliente-info {{ 
            background: #f8f9fa; 
            padding: 1.5rem; 
            border-radius: 12px; 
            margin-bottom: 2rem;
            border-left: 4px solid #00E5FF;
        }}
        .cliente-info h3 {{ color: #0a0a0f; margin-bottom: 1rem; font-size: 1.1rem; }}
        .info-row {{ display: flex; margin-bottom: 0.5rem; font-size: 0.9rem; }}
        .info-row strong {{ width: 120px; color: #666; font-weight: 600; }}

        .pack-box {{ 
            background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%); 
            color: white; 
            padding: 2rem; 
            border-radius: 16px; 
            margin: 1.5rem 0;
            position: relative;
            overflow: hidden;
        }}
        .pack-box::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 4px;
            background: linear-gradient(90deg, #00E5FF, #00FF88);
        }}
        .pack-box h3 {{ margin: 0 0 0.5rem 0; font-size: 1.4rem; }}
        .pack-box p {{ margin: 0 0 1rem 0; opacity: 0.8; font-size: 0.9rem; }}
        .pack-box .price {{ 
            font-size: 2.5rem; 
            font-weight: 800; 
            background: linear-gradient(135deg, #00E5FF 0%, #00FF88 100%); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent; 
            display: inline-block;
        }}
        .pack-box ul {{ margin-top: 1rem; list-style: none; }}
        .pack-box ul li {{ padding: 0.3rem 0; font-size: 0.9rem; }}
        .pack-box ul li::before {{ content: '✓ '; color: #00FF88; font-weight: 700; }}

        .micros-table {{ 
            width: 100%; 
            border-collapse: collapse; 
            margin: 1rem 0;
        }}
        .micros-table th {{ 
            text-align: left; 
            padding: 0.75rem; 
            background: #f8f9fa; 
            font-size: 0.85rem; 
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .micros-table td {{ 
            padding: 0.75rem; 
            border-bottom: 1px solid #eee; 
            font-size: 0.9rem; 
        }}
        .micros-table td:last-child {{ text-align: right; font-weight: 700; }}

        .total-box {{ 
            background: #0a0a0f; 
            color: white; 
            padding: 2rem; 
            border-radius: 16px; 
            text-align: center; 
            margin: 2rem 0;
            position: relative;
            overflow: hidden;
        }}
        .total-box::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 4px;
            background: linear-gradient(90deg, #00E5FF, #00FF88);
        }}
        .total-box .label {{ font-size: 0.9rem; opacity: 0.7; text-transform: uppercase; letter-spacing: 1px; }}
        .total-box .amount {{ 
            font-size: 3rem; 
            font-weight: 800; 
            background: linear-gradient(135deg, #00E5FF 0%, #00FF88 100%); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent; 
            margin: 0.5rem 0; 
        }}
        .total-box .mant {{ color: #00FF88; font-size: 1.1rem; font-weight: 600; }}
        .total-box .ahorro {{ color: #ffc107; font-size: 0.9rem; margin-top: 0.5rem; }}

        .notas {{ 
            background: #fff3cd; 
            border-left: 4px solid #ffc107; 
            padding: 1rem; 
            border-radius: 0 8px 8px 0; 
            margin: 1.5rem 0; 
            font-size: 0.9rem; 
        }}

        .cta-section {{ text-align: center; margin: 2.5rem 0; }}
        .cta-section h3 {{ margin-bottom: 0.75rem; font-size: 1.3rem; }}
        .cta-section p {{ color: #666; margin-bottom: 1.5rem; font-size: 0.95rem; }}
        .cta-btn {{ 
            display: inline-block; 
            background: linear-gradient(135deg, #00E5FF 0%, #00FF88 100%); 
            color: #0a0a0f; 
            padding: 1rem 2.5rem; 
            border-radius: 100px; 
            text-decoration: none; 
            font-weight: 700; 
            font-size: 1rem;
            box-shadow: 0 8px 25px rgba(0,229,255,0.3);
        }}

        .garantia {{ 
            text-align: center; 
            padding: 1.5rem; 
            font-size: 0.85rem; 
            color: #666; 
            border-top: 1px solid #eee; 
            background: #fafafa;
        }}

        .footer {{ 
            background: #0a0a0f; 
            color: white; 
            padding: 2.5rem 2rem; 
            text-align: center; 
        }}
        .footer .brand {{ font-size: 1.3rem; font-weight: 700; margin-bottom: 0.5rem; }}
        .footer .tagline {{ opacity: 0.7; font-size: 0.9rem; margin-bottom: 1rem; }}
        .footer a {{ color: #00E5FF; text-decoration: none; }}
        .footer .contact {{ margin-top: 1rem; font-size: 0.9rem; }}

        .cotiz-id {{ 
            text-align: center; 
            font-size: 0.75rem; 
            color: #999; 
            padding: 0.5rem;
            background: #fafafa;
        }}

        @media print {{ 
            .container {{ max-width: 100%; box-shadow: none; }}
            body {{ background: white; }}
            .cta-btn {{ box-shadow: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 ORCHESTRATOR ISA</h1>
            <p>Propuesta Comercial de Digitalización</p>
            <div class="badge">Válida por 7 días · ID: {cotizacion_id}</div>
        </div>

        <div class="content">
            <div class="cliente-info">
                <h3>📋 Datos del Proyecto</h3>
                <div class="info-row"><strong>Negocio:</strong> {data.negocio}</div>
                <div class="info-row"><strong>Tipo:</strong> {data.tipo}</div>
                <div class="info-row"><strong>Cliente:</strong> {data.dueno or 'Estimado'}</div>
                <div class="info-row"><strong>Ciudad:</strong> {data.ciudad}</div>
                <div class="info-row"><strong>Fecha:</strong> {fecha}</div>
                <div class="info-row"><strong>Teléfono:</strong> {data.telefono}</div>
                {f'<div class="info-row"><strong>Email:</strong> {data.email}</div>' if data.email else ''}
            </div>
"""

    # Pack seleccionado
    if data.pack:
        features_html = "".join([f"<li>{f}</li>" for f in pack_features])
        html += f"""
            <div class="pack-box">
                <h3>{pack_name}</h3>
                <p>{pack_desc}</p>
                <div class="price">{pack_price} MAD</div>
                <ul>{features_html}</ul>
            </div>
"""

    # Microservicios
    if data.micros:
        micros_rows = "".join([
            f"<tr><td>{m.name}</td><td>{m.price} MAD</td></tr>"
            for m in data.micros
        ])
        html += f"""
            <h3 style="margin-top: 2rem; font-size: 1.1rem;">🔧 Microservicios Adicionales</h3>
            <table class="micros-table">
                <tr><th>Servicio</th><th>Precio</th></tr>
                {micros_rows}
            </table>
"""

    # Descuento
    descuento_html = ""
    if data.descuento > 0:
        descuento_html = f'<div class="ahorro">💰 Ahorro: {data.descuento} MAD (referido)</div>'

    html += f"""
            <div class="total-box">
                <div class="label">Inversión Total de Entrada</div>
                <div class="amount">{total_entrada} MAD</div>
                <div class="mant">+ {pack_mant} MAD/mes de mantenimiento</div>
                {descuento_html}
            </div>
"""

    # Notas
    if data.notas:
        html += f"""
            <div class="notas">
                <strong>📝 Notas:</strong> {data.notas}
            </div>
"""

    # CTA
    wa_number = data.telefono.replace(" ", "").replace("-", "").replace("+", "")
    html += f"""
            <div class="cta-section">
                <h3>¿Listo para empezar?</h3>
                <p>Entrega en 24-72 horas. Capacitación incluida. Garantía de funcionamiento.</p>
                <a href="https://wa.me/{wa_number}?text=Hola%2C%20vi%20la%20propuesta%20{y cotizacion_id}%20y%20quiero%20empezar" class="cta-btn">
                    💬 Confirmar por WhatsApp
                </a>
            </div>
        </div>

        <div class="garantia">
            🛡️ <strong>Garantía:</strong> Si no ves el sistema funcionando y probado, no se considera entregado.<br>
            🎓 Capacitación incluida: te enseño a usarlo en 15 minutos.
        </div>

        <div class="footer">
            <div class="brand">ORCHESTRATOR ISA</div>
            <div class="tagline">Digitalización Inteligente para Negocios Locales</div>
            <div class="contact">
                📱 <a href="https://wa.me/212786120081">+212 786 120 081</a> | 
                📧 <a href="mailto:orchestrator.isa@gmail.com">orchestrator.isa@gmail.com</a>
            </div>
        </div>

        <div class="cotiz-id">
            Cotización #{cotizacion_id} · Generada el {fecha} · orchestrator-isa-os v3.0
        </div>
    </div>
</body>
</html>"""

    return html


# === ENDPOINT ===

@router.post("/cotizar", response_model=CotizacionResponse)
async def cotizar(request: CotizacionRequest):
    """
    Genera una cotización HTML profesional lista para compartir.

    Recibe datos del cliente + selección de pack/microservicios del catálogo
    y devuelve HTML completo + URL de WhatsApp + resumen de precios.
    """
    try:
        # Generar ID único
        cotizacion_id = f"COT-{datetime.now().strftime('%Y%m%d')}-{hash(request.negocio + request.telefono) % 10000:04d}"

        # Validar pack si se envió
        if request.pack and request.pack not in PACKS:
            raise HTTPException(status_code=400, detail=f"Pack '{request.pack}' no válido. Opciones: {list(PACKS.keys())}")

        # Calcular totales
        pack_price = PACKS[request.pack]["price"] if request.pack else 0
        pack_mant = PACKS[request.pack]["mant"] if request.pack else 0
        micros_total = sum(m.price for m in request.micros)
        total_entrada = pack_price + micros_total - request.descuento

        # Generar HTML
        html = generar_html_cotizacion(request, cotizacion_id)

        # Guardar en archivo (para servir estático)
        filename = f"cotizacion_{cotizacion_id}.html"
        filepath = f"static/cotizaciones/{filename}"

        # Asegurar que existe la carpeta
        import os
        os.makedirs("static/cotizaciones", exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        # URL de WhatsApp pre-armada
        wa_msg = (
            f"Hola {request.dueno or 'estimado'}! 👋\n\n"
            f"Soy Isa de Orchestrator ISA. Te preparé la propuesta para *{request.negocio}*:\n\n"
            f"📦 {PACKS[request.pack]['name'] if request.pack else 'Servicios personalizados'}\n"
            f"💰 Inversión: {total_entrada} MAD\n"
            f"🔧 Mantenimiento: {pack_mant} MAD/mes\n\n"
            f"✅ Entrega en 24-72 horas\n"
            f"✅ Capacitación incluida (15 min)\n"
            f"✅ Garantía: si no funciona, no se considera entregado\n\n"
            f"¿Te parece bien? Podemos empezar hoy con el 50% de anticipo. 💪"
        )

        wa_number = request.telefono.replace(" ", "").replace("-", "").replace("+", "")
        whatsapp_url = f"https://wa.me/{wa_number}?text={wa_msg.replace(chr(10), '%0A').replace(' ', '%20')}"

        # Guardar en base de datos (si existe conexión)
        try:
            # Aquí iría la lógica de guardar en SQLite/PostgreSQL
            # Por ahora solo guardamos el archivo
            pass
        except:
            pass

        return CotizacionResponse(
            success=True,
            cotizacion_id=cotizacion_id,
            html=html,
            pdf_url=None,  # TODO: Generar PDF con weasyprint o similar
            resumen={
                "pack": request.pack,
                "pack_nombre": PACKS[request.pack]["name"] if request.pack else None,
                "pack_precio": pack_price,
                "micros_cantidad": len(request.micros),
                "micros_total": micros_total,
                "descuento": request.descuento,
                "total_entrada": total_entrada,
                "mantenimiento_mensual": pack_mant,
                "roi_estimado": f"{total_entrada * 3} MAD"  # Estimación simple
            },
            whatsapp_url=whatsapp_url,
            fecha=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando cotización: {str(e)}")


# === ENDPOINT ADICIONAL: Obtener cotización guardada ===

@router.get("/cotizar/{cotizacion_id}")
async def get_cotizacion(cotizacion_id: str):
    """Devuelve una cotización guardada por ID"""
    filepath = f"static/cotizaciones/cotizacion_{cotizacion_id}.html"

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)

