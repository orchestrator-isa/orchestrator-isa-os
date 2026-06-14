from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import hashlib

router = APIRouter(prefix="/api/referidos", tags=["referidos"])

class ReferidoCreate(BaseModel):
    nombre_referidor: str = Field(..., min_length=2)
    telefono_referidor: str = Field(..., pattern="^\+?[0-9\s\-]{8,20}$")
    nombre_referido: str = Field(..., min_length=2)
    telefono_referido: str = Field(..., pattern="^\+?[0-9\s\-]{8,20}$")
    tipo_negocio_referido: str
    email_referidor: Optional[str] = None
    notas: Optional[str] = None

class ReferidoUpdate(BaseModel):
    estado: Optional[str] = Field(None, pattern="^(pendiente|contactado|propuesta_enviada|cerrado|pagado|rechazado)$")
    comision_pagada: Optional[int] = None
    notas: Optional[str] = None

COMISIONES = {
    "presencia": 50,
    "whatsapp_pro": 100,
    "automatizacion": 200,
    "completo": 300,
    "base": 75,
    "conversion": 150,
    "escala": 400
}

def generar_codigo_referido(telefono: str) -> str:
    hash_base = hashlib.sha256(telefono.encode()).hexdigest()[:8]
    return f"ISA-{hash_base.upper()}"

@router.post("/")
async def crear_referido(data: ReferidoCreate, request: Request):
    db = request.app.state.db
    codigo = generar_codigo_referido(data.telefono_referidor)

    async with db.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM referidos WHERE telefono_referido = $1",
            data.telefono_referido
        )
        if existing:
            raise HTTPException(status_code=400, detail="Este negocio ya fue referido anteriormente")

        row = await conn.fetchrow(
            """INSERT INTO referidos 
               (codigo, nombre_referidor, telefono_referidor, email_referidor,
                nombre_referido, telefono_referido, tipo_negocio_referido, notas, estado)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               RETURNING id, codigo, fecha_creacion""",
            codigo, data.nombre_referidor, data.telefono_referidor, data.email_referidor,
            data.nombre_referido, data.telefono_referido, data.tipo_negocio_referido,
            data.notas, "pendiente"
        )

    return {
        "status": "success",
        "referido_id": row["id"],
        "codigo": row["codigo"],
        "fecha_creacion": row["fecha_creacion"].isoformat(),
        "mensaje": f"Referido registrado. Código: {row['codigo']}"
    }

@router.get("/")
async def listar_referidos(request: Request, estado: Optional[str] = None, limit: int = 100, offset: int = 0):
    db = request.app.state.db
    async with db.acquire() as conn:
        if estado:
            rows = await conn.fetch(
                "SELECT * FROM referidos WHERE estado = $1 ORDER BY fecha_creacion DESC LIMIT $2 OFFSET $3",
                estado, limit, offset
            )
            total = await conn.fetchval("SELECT COUNT(*) FROM referidos WHERE estado = $1", estado)
        else:
            rows = await conn.fetch(
                "SELECT * FROM referidos ORDER BY fecha_creacion DESC LIMIT $1 OFFSET $2",
                limit, offset
            )
            total = await conn.fetchval("SELECT COUNT(*) FROM referidos")

    return {
        "referidos": [dict(r) for r in rows],
        "total": total,
        "comisiones_disponibles": COMISIONES
    }

@router.get("/{referido_id}")
async def obtener_referido(referido_id: int, request: Request):
    db = request.app.state.db
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM referidos WHERE id = $1", referido_id)
    if not row:
        raise HTTPException(status_code=404, detail="Referido no encontrado")
    return dict(row)

@router.patch("/{referido_id}")
async def actualizar_referido(referido_id: int, data: ReferidoUpdate, request: Request):
    db = request.app.state.db
    fields = {k: v for k, v in data.dict(exclude_unset=True).items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    set_clause = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(fields.keys())])

    async with db.acquire() as conn:
        await conn.execute(
            f"UPDATE referidos SET {set_clause}, fecha_actualizacion = NOW() WHERE id = $1",
            referido_id, *fields.values()
        )
        row = await conn.fetchrow("SELECT * FROM referidos WHERE id = $1", referido_id)

    return dict(row)

@router.get("/estadisticas/resumen")
async def estadisticas_referidos(request: Request):
    db = request.app.state.db
    async with db.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM referidos")
        pendientes = await conn.fetchval("SELECT COUNT(*) FROM referidos WHERE estado = 'pendiente'")
        contactados = await conn.fetchval("SELECT COUNT(*) FROM referidos WHERE estado = 'contactado'")
        cerrados = await conn.fetchval("SELECT COUNT(*) FROM referidos WHERE estado = 'cerrado'")
        pagados = await conn.fetchval("SELECT COUNT(*) FROM referidos WHERE estado = 'pagado'")
        comision_total = await conn.fetchval("SELECT COALESCE(SUM(comision_pagada), 0) FROM referidos")

        top = await conn.fetch(
            """SELECT nombre_referidor, telefono_referidor, COUNT(*) as total, SUM(comision_pagada) as comision
               FROM referidos GROUP BY nombre_referidor, telefono_referidor ORDER BY total DESC LIMIT 10"""
        )

    return {
        "total_referidos": total,
        "pendientes": pendientes,
        "contactados": contactados,
        "cerrados": cerrados,
        "pagados": pagados,
        "comision_total_pagada": comision_total,
        "tasa_conversion": round(cerrados / total, 3) if total > 0 else 0,
        "top_referidores": [dict(r) for r in top]
    }

@router.get("/codigo/{codigo}")
async def verificar_codigo(codigo: str, request: Request):
    db = request.app.state.db
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM referidos WHERE codigo = $1", codigo)
    if not row:
        raise HTTPException(status_code=404, detail="Código no válido")
    return {
        "valido": True,
        "referidor": row["nombre_referidor"],
        "estado": row["estado"],
        "comision": COMISIONES.get(row.get("pack_contratado", ""), 0)
    }
