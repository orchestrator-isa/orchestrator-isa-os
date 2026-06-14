from fastapi import APIRouter, HTTPException, Request
from typing import Optional, List
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/reportes", tags=["reportes"])

@router.get("/leads")
async def reporte_leads(
    request: Request,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    agrupar: Optional[str] = "estado"  # estado, ciudad, tipo_negocio, pack, semana
):
    db = request.app.state.db

    # Parsear fechas
    fecha_desde = datetime.strptime(desde, "%Y-%m-%d") if desde else datetime.now() - timedelta(days=30)
    fecha_hasta = datetime.strptime(hasta, "%Y-%m-%d") if hasta else datetime.now()

    async with db.acquire() as conn:
        # Leads en rango de fechas
        leads = await conn.fetch(
            """SELECT * FROM leads 
               WHERE fecha_creacion BETWEEN $1 AND $2
               ORDER BY fecha_creacion DESC""",
            fecha_desde, fecha_hasta
        )

        # Agrupaciones
        if agrupar == "estado":
            agrupado = await conn.fetch(
                """SELECT estado, COUNT(*) as cantidad, AVG(score) as score_promedio
                   FROM leads WHERE fecha_creacion BETWEEN $1 AND $2
                   GROUP BY estado ORDER BY cantidad DESC""",
                fecha_desde, fecha_hasta
            )
        elif agrupar == "ciudad":
            agrupado = await conn.fetch(
                """SELECT ciudad, COUNT(*) as cantidad, AVG(score) as score_promedio
                   FROM leads WHERE fecha_creacion BETWEEN $1 AND $2
                   GROUP BY ciudad ORDER BY cantidad DESC""",
                fecha_desde, fecha_hasta
            )
        elif agrupar == "tipo_negocio":
            agrupado = await conn.fetch(
                """SELECT tipo_negocio, COUNT(*) as cantidad, AVG(score) as score_promedio
                   FROM leads WHERE fecha_creacion BETWEEN $1 AND $2
                   GROUP BY tipo_negocio ORDER BY cantidad DESC""",
                fecha_desde, fecha_hasta
            )
        elif agrupar == "pack":
            agrupado = await conn.fetch(
                """SELECT pack_recomendado, COUNT(*) as cantidad
                   FROM leads WHERE fecha_creacion BETWEEN $1 AND $2 AND pack_recomendado IS NOT NULL
                   GROUP BY pack_recomendado ORDER BY cantidad DESC""",
                fecha_desde, fecha_hasta
            )
        elif agrupar == "semana":
            agrupado = await conn.fetch(
                """SELECT DATE_TRUNC('week', fecha_creacion) as semana, COUNT(*) as cantidad
                   FROM leads WHERE fecha_creacion BETWEEN $1 AND $2
                   GROUP BY semana ORDER BY semana""",
                fecha_desde, fecha_hasta
            )
        else:
            agrupado = []

        # Evolución temporal (últimos 12 meses)
        evolucion = await conn.fetch(
            """SELECT DATE_TRUNC('month', fecha_creacion) as mes, 
                      COUNT(*) as nuevos,
                      COUNT(*) FILTER (WHERE estado = 'cerrado') as cerrados
               FROM leads WHERE fecha_creacion >= NOW() - INTERVAL '12 months'
               GROUP BY mes ORDER BY mes"""
        )

    return {
        "periodo": {"desde": fecha_desde.isoformat(), "hasta": fecha_hasta.isoformat()},
        "total_leads": len(leads),
        "leads": [dict(r) for r in leads],
        "agrupado_por": agrupar,
        "agrupacion": [dict(r) for r in agrupado],
        "evolucion_mensual": [dict(r) for r in evolucion]
    }

@router.get("/cotizaciones")
async def reporte_cotizaciones(
    request: Request,
    desde: Optional[str] = None,
    hasta: Optional[str] = None
):
    db = request.app.state.db
    fecha_desde = datetime.strptime(desde, "%Y-%m-%d") if desde else datetime.now() - timedelta(days=30)
    fecha_hasta = datetime.strptime(hasta, "%Y-%m-%d") if hasta else datetime.now()

    async with db.acquire() as conn:
        # Resumen por pack
        por_pack = await conn.fetch(
            """SELECT pack, COUNT(*) as cantidad, 
                      SUM(precio_entrada) as total_entrada,
                      SUM(precio_mantenimiento) as total_mantenimiento
               FROM cotizaciones WHERE fecha BETWEEN $1 AND $2
               GROUP BY pack ORDER BY cantidad DESC""",
            fecha_desde, fecha_hasta
        )

        # Estado de cotizaciones
        por_estado = await conn.fetch(
            """SELECT estado, COUNT(*) as cantidad, SUM(precio_final) as valor_total
               FROM cotizaciones WHERE fecha BETWEEN $1 AND $2
               GROUP BY estado ORDER BY cantidad DESC""",
            fecha_desde, fecha_hasta
        )

        # Ingresos proyectados (mantenimiento mensual de activos)
        ingresos_mensuales = await conn.fetchval(
            """SELECT COALESCE(SUM(precio_mantenimiento), 0) 
               FROM cotizaciones WHERE estado = 'aceptada'"""
        )

        # Top clientes potenciales por valor
        top_clientes = await conn.fetch(
            """SELECT nombre_negocio, tipo_negocio, pack, precio_final, estado
               FROM cotizaciones WHERE fecha BETWEEN $1 AND $2
               ORDER BY precio_final DESC LIMIT 20""",
            fecha_desde, fecha_hasta
        )

    return {
        "periodo": {"desde": fecha_desde.isoformat(), "hasta": fecha_hasta.isoformat()},
        "por_pack": [dict(r) for r in por_pack],
        "por_estado": [dict(r) for r in por_estado],
        "ingresos_mensuales_proyectados": ingresos_mensuales,
        "top_clientes_potenciales": [dict(r) for r in top_clientes]
    }

@router.get("/financiero")
async def reporte_financiero(request: Request, mes: Optional[int] = None, anio: Optional[int] = None):
    db = request.app.state.db

    # Si no se especifica, usar mes actual
    if not mes or not anio:
        hoy = datetime.now()
        mes = mes or hoy.month
        anio = anio or hoy.year

    async with db.acquire() as conn:
        # Cotizaciones aceptadas en el mes
        cotizaciones_mes = await conn.fetch(
            """SELECT * FROM cotizaciones 
               WHERE EXTRACT(MONTH FROM fecha) = $1 AND EXTRACT(YEAR FROM fecha) = $2
               AND estado = 'aceptada'""",
            mes, anio
        )

        # Ingresos por tipo
        ingresos_entrada = sum(c["precio_entrada"] for c in cotizaciones_mes)
        ingresos_mantenimiento = await conn.fetchval(
            """SELECT COALESCE(SUM(precio_mantenimiento), 0) 
               FROM cotizaciones WHERE estado = 'aceptada'"""
        )

        # Comparación con mes anterior
        mes_anterior = mes - 1 if mes > 1 else 12
        anio_anterior = anio if mes > 1 else anio - 1

        cotizaciones_mes_ant = await conn.fetch(
            """SELECT * FROM cotizaciones 
               WHERE EXTRACT(MONTH FROM fecha) = $1 AND EXTRACT(YEAR FROM fecha) = $2
               AND estado = 'aceptada'""",
            mes_anterior, anio_anterior
        )

        ingresos_ant = sum(c["precio_entrada"] for c in cotizaciones_mes_ant)
        variacion = ((ingresos_entrada - ingresos_ant) / ingresos_ant * 100) if ingresos_ant > 0 else 0

    return {
        "periodo": {"mes": mes, "anio": anio},
        "ingresos_entrada": ingresos_entrada,
        "ingresos_mantenimiento_mensual": ingresos_mantenimiento,
        "total_mensual_estimado": ingresos_entrada + ingresos_mantenimiento,
        "cotizaciones_aceptadas": len(cotizaciones_mes),
        "variacion_mes_anterior_porcentaje": round(variacion, 2),
        "tendencia": "up" if variacion > 0 else "down" if variacion < 0 else "stable"
    }

@router.get("/scraping")
async def reporte_scraping(request: Request, dias: int = 30):
    db = request.app.state.db
    import os
    data_dir = os.getenv("DATA_DIR", ".")

    async with db.acquire() as conn:
        # Leads provenientes de scraping vs manuales
        leads_scraping = await conn.fetchval(
            "SELECT COUNT(*) FROM leads WHERE fuente = 'google_maps'"
        )
        leads_manuales = await conn.fetchval(
            "SELECT COUNT(*) FROM leads WHERE fuente IS NULL OR fuente != 'google_maps'"
        )

        # Leads scrapeados convertidos
        leads_scraping_convertidos = await conn.fetchval(
            """SELECT COUNT(*) FROM leads 
               WHERE fuente = 'google_maps' AND estado IN ('cerrado', 'mantenimiento')"""
        )

    # Archivos CSV recientes
    try:
        files = sorted(
            [f for f in os.listdir(data_dir) if f.startswith("leads_") and f.endswith(".csv")],
            key=lambda x: os.path.getmtime(os.path.join(data_dir, x)),
            reverse=True
        )
        archivos_recientes = files[:10]
    except:
        archivos_recientes = []

    return {
        "leads_desde_scraping": leads_scraping or 0,
        "leads_manuales": leads_manuales or 0,
        "leads_scraping_convertidos": leads_scraping_convertidos or 0,
        "tasa_conversion_scraping": round(leads_scraping_convertidos / leads_scraping, 3) if leads_scraping else 0,
        "archivos_scraping_recientes": archivos_recientes,
        "total_archivos_scraping": len(archivos_recientes)
    }
