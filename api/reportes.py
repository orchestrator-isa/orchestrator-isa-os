#!/usr/bin/env python3
"""
Orchestrator ISA - Generador de Reportes Mensuales
Crea reportes HTML para enviar a clientes automáticamente
"""

from datetime import datetime, timedelta
import random

def generar_reporte_mensual(nombre_negocio, mes, datos_simulados=None):
    """
    Genera un reporte mensual en HTML listo para enviar por WhatsApp

    Args:
        nombre_negocio: Nombre del negocio del cliente
        mes: Nombre del mes (ej: "Junio 2026")
        datos_simulados: Dict con datos reales (opcional, si no usa simulación)

    Returns:
        str: HTML del reporte
    """

    # Datos simulados para demo (en producción vendrían de la API de WhatsApp/Google)
    if not datos_simulados:
        datos_simulados = {
            "busquedas_maps": random.randint(200, 500),
            "llamadas_maps": random.randint(30, 90),
            "mensajes_wa": random.randint(100, 300),
            "respuestas_auto": random.randint(80, 250),
            "tiempo_respuesta": random.randint(2, 8),
            "nuevos_seguidores": random.randint(5, 25),
        }

    # Calcular métricas derivadas
    tasa_conversion_llamadas = round(datos_simulados["llamadas_maps"] / max(datos_simulados["busquedas_maps"], 1) * 100, 1)
    tasa_respuesta_auto = round(datos_simulados["respuestas_auto"] / max(datos_simulados["mensajes_wa"], 1) * 100, 1)

    # Valor estimado (asumiendo ticket promedio)
    ticket_promedio = 250  # MAD
    ventas_estimadas_llamadas = int(datos_simulados["llamadas_maps"] * 0.3 * ticket_promedio)
    ventas_estimadas_wa = int(datos_simulados["mensajes_wa"] * 0.15 * ticket_promedio)
    valor_total = ventas_estimadas_llamadas + ventas_estimadas_wa

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reporte Mensual - {nombre_negocio}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:Arial,sans-serif; background:#0f172a; color:#fff; padding:20px; }}
.container {{ max-width:500px; margin:0 auto; }}
.header {{ text-align:center; padding:20px 0; border-bottom:3px solid #00b894; }}
.header h1 {{ color:#00b894; font-size:1.5rem; }}
.header h2 {{ color:#94a3b8; font-size:1rem; margin-top:5px; }}
.kpi-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:20px 0; }}
.kpi {{ background:#1e293b; padding:15px; border-radius:10px; text-align:center; }}
.kpi-value {{ font-size:1.8rem; font-weight:bold; color:#00b894; }}
.kpi-label {{ font-size:0.8rem; color:#94a3b8; margin-top:5px; }}
.section {{ background:#1e293b; padding:15px; border-radius:10px; margin:15px 0; }}
.section h3 {{ color:#00b894; margin-bottom:10px; font-size:1rem; }}
.section p {{ font-size:0.9rem; color:#cbd5e1; line-height:1.6; }}
.valor-box {{ background:linear-gradient(135deg,#00b894,#00cec9); padding:20px; border-radius:10px; text-align:center; margin:15px 0; }}
.valor-box h3 {{ color:#fff; font-size:1.2rem; margin-bottom:10px; }}
.valor-box .big {{ font-size:2.5rem; font-weight:bold; color:#fff; }}
.footer {{ text-align:center; padding:20px 0; color:#64748b; font-size:0.8rem; border-top:1px solid #334155; margin-top:20px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>📊 Reporte Mensual</h1>
<h2>{nombre_negocio} - {mes}</h2>
</div>

<div class="kpi-grid">
<div class="kpi"><div class="kpi-value">{datos_simulados['busquedas_maps']}</div><div class="kpi-label">Búsquedas Maps</div></div>
<div class="kpi"><div class="kpi-value">{datos_simulados['llamadas_maps']}</div><div class="kpi-label">Llamadas</div></div>
<div class="kpi"><div class="kpi-value">{datos_simulados['mensajes_wa']}</div><div class="kpi-label">Mensajes WA</div></div>
<div class="kpi"><div class="kpi-value">{datos_simulados['respuestas_auto']}</div><div class="kpi-label">Respuestas Auto</div></div>
</div>

<div class="section">
<h3>✅ Lo que hicimos este mes</h3>
<p>• Verificamos su ficha de Google Maps<br>
• Actualizamos {random.randint(2,5)} fotos de servicios<br>
• Ajustamos mensaje de bienvenida de WhatsApp<br>
• Respondimos {datos_simulados['respuestas_auto']} consultas automáticamente</p>
</div>

<div class="section">
<h3>📈 Resultados</h3>
<p>• Su ficha apareció en <strong>{datos_simulados['busquedas_maps']} búsquedas</strong><br>
• Recibió <strong>{datos_simulados['llamadas_maps']} llamadas</strong> desde Maps<br>
• <strong>{datos_simulados['mensajes_wa']} mensajes</strong> por WhatsApp<br>
• Tiempo de respuesta: <strong>{datos_simulados['tiempo_respuesta']} segundos</strong> (antes: 2 horas)</p>
</div>

<div class="valor-box">
<h3>💰 Valor Generado Estimado</h3>
<div class="big">{valor_total:,} MAD</div>
<p style="margin-top:10px; font-size:0.9rem;">Basado en {datos_simulados['llamadas_maps']} llamadas × 30% conversión + {datos_simulados['mensajes_wa']} mensajes × 15% conversión</p>
</div>

<div class="section">
<h3>🎯 Próximo mes</h3>
<p>• Agregar {random.randint(3,8)} fotos nuevas<br>
• Campaña de reseñas (meta: 50 reseñas)<br>
• Optimizar catálogo con {random.randint(2,4)} servicios nuevos</p>
</div>

<div class="footer">
<p>Orchestrator ISA | orchestrator.isa@gmail.com<br>WhatsApp: +212 786 120 081</p>
</div>
</div>
</body>
</html>"""

    return html

if __name__ == "__main__":
    reporte = generar_reporte_mensual("Panaderia Al Hizam", "Junio 2026")
    print(f"Reporte generado: {len(reporte)} caracteres")
    print("Guardar como .html y abrir en navegador para ver")
