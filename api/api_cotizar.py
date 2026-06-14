from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

router = APIRouter(prefix="/api/cotizar", tags=["cotizaciones"])

class CotizacionRequest(BaseModel):
    nombre_negocio: str = Field(..., min_length=2, max_length=100)
    tipo_negocio: str = Field(..., min_length=2)
    pack: str = Field(..., pattern="^(presencia|whatsapp_pro|automatizacion|completo)$")
    telefono: str = Field(..., pattern="^\+?[0-9\s\-]{8,20}$")
    email: Optional[str] = None
    notas: Optional[str] = None
    ciudad: str = "tetouan"

class CotizacionResponse(BaseModel):
    id: int
    nombre_negocio: str
    tipo_negocio: str
    pack: str
    pack_nombre: str
    precio_entrada: int
    precio_mantenimiento: int
    moneda: str = "MAD"
    telefono: str
    email: Optional[str]
    notas: Optional[str]
    ciudad: str
    fecha: datetime
    estado: str = "pendiente"
    descuento_aplicado: int = 0
    precio_final: int

PRECIOS = {
    "presencia": {"entrada": 250, "mantenimiento": 150, "nombre": "Presencia Digital"},
    "whatsapp_pro": {"entrada": 400, "mantenimiento": 200, "nombre": "WhatsApp Pro"},
    "automatizacion": {"entrada": 800, "mantenimiento": 350, "nombre": "Automatización"},
    "completo": {"entrada": 1200, "mantenimiento": 500, "nombre": "Pack Completo"},
}

PACKS_DETALLE = {
    "presencia": {
        "nombre": "Presencia Digital",
        "descripcion": "Landing page + Redes sociales básicas",
        "incluye": ["Landing page responsive", "Perfil Google Business", "Facebook/Instagram básico", "1 post semanal"],
        "tiempo_entrega": "7 días",
        "garantia": "30 días"
    },
    "whatsapp_pro": {
        "nombre": "WhatsApp Pro",
        "descripcion": "Bot de pedidos + catálogo digital",
        "incluye": ["Bot de pedidos WhatsApp", "Catálogo digital", "Panel de administración", "Notificaciones automáticas", "Soporte 24/7"],
        "tiempo_entrega": "14 días",
        "garantia": "60 días"
    },
    "automatizacion": {
        "nombre": "Automatización",
        "descripcion": "Flujos automáticos + integraciones",
        "incluye": ["Todo WhatsApp Pro", "Reservas automáticas", "Recordatorios SMS/WhatsApp", "Reportes mensuales", "API propia"],
        "tiempo_entrega": "21 días",
        "garantia": "90 días"
    },
    "completo": {
        "nombre": "Pack Completo",
        "descripcion": "Solución integral digital",
        "incluye": ["Todo Automatización", "App web PWA", "Analytics avanzado", "Marketing automatizado", "Manager dedicado"],
        "tiempo_entrega": "30 días",
        "garantia": "1 año"
    }
}

@router.post("/", response_model=CotizacionResponse)
async def crear_cotizacion(data: CotizacionRequest, request: Request):
    db = request.app.state.db
    pack_info = PRECIOS.get(data.pack.lower(), PRECIOS["presencia"])
    pack_detalle = PACKS_DETALLE.get(data.pack.lower(), PACKS_DETALLE["presencia"])

    # Calcular descuento por volumen o promoción
    descuento = 0
    precio_final = pack_info["entrada"] - descuento

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cotizaciones 
               (nombre_negocio, tipo_negocio, pack, pack_nombre, telefono, email, notas, ciudad,
                precio_entrada, precio_mantenimiento, moneda, descuento_aplicado, precio_final, estado)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
               RETURNING id, fecha, estado""",
            data.nombre_negocio, data.tipo_negocio, data.pack, pack_detalle["nombre"],
            data.telefono, data.email, data.notas, data.ciudad,
            pack_info["entrada"], pack_info["mantenimiento"], "MAD",
            descuento, precio_final, "pendiente"
        )

    return CotizacionResponse(
        id=row["id"],
        nombre_negocio=data.nombre_negocio,
        tipo_negocio=data.tipo_negocio,
        pack=data.pack,
        pack_nombre=pack_detalle["nombre"],
        precio_entrada=pack_info["entrada"],
        precio_mantenimiento=pack_info["mantenimiento"],
        moneda="MAD",
        telefono=data.telefono,
        email=data.email,
        notas=data.notas,
        ciudad=data.ciudad,
        fecha=row["fecha"],
        estado=row["estado"],
        descuento_aplicado=descuento,
        precio_final=precio_final
    )

@router.get("/packs")
async def listar_packs():
    """Devuelve todos los packs con precios y detalles."""
    return {
        "packs": [
            {
                "code": k,
                "nombre": v["nombre"],
                "precio_entrada": PRECIOS[k]["entrada"],
                "precio_mantenimiento": PRECIOS[k]["mantenimiento"],
                "moneda": "MAD",
                **PACKS_DETALLE[k]
            }
            for k, v in PRECIOS.items()
        ]
    }

@router.get("/historial")
async def historial_cotizaciones(request: Request, limit: int = 50, offset: int = 0):
    db = request.app.state.db
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM cotizaciones ORDER BY fecha DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM cotizaciones")
    return {"cotizaciones": [dict(r) for r in rows], "total": total}

@router.patch("/{cotizacion_id}")
async def actualizar_cotizacion(cotizacion_id: int, updates: dict, request: Request):
    db = request.app.state.db
    allowed = {"estado", "descuento_aplicado", "precio_final", "notas"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        raise HTTPException(status_code=400, detail="No hay campos válidos para actualizar")

    set_clause = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(fields.keys())])

    async with db.acquire() as conn:
        await conn.execute(
            f"UPDATE cotizaciones SET {set_clause} WHERE id = $1",
            cotizacion_id, *fields.values()
        )
        row = await conn.fetchrow("SELECT * FROM cotizaciones WHERE id = $1", cotizacion_id)
    if not row:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return dict(row)
