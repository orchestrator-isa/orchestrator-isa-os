#!/usr/bin/env python3
"""
Orchestrator ISA - Módulo de Scraping (FASE 0)
Radar de Leads: Extrae negocios de Google Maps y los clasifica
"""

import csv
import json
import re
from typing import List, Dict
from enum import Enum

class CasoNegocio(str, Enum):
    FANTASMA = "A"           # Sin web, sin RRSS, sin WhatsApp
    INFLUENCER_COJO = "B"    # Solo RRSS, sin web
    DESACTUALIZADO = "C"     # Web vieja/mala
    WHATSAPP_CAOTICO = "D"   # WA sin catálogo, sin estructura
    MINA_ORO = "E"           # +40 reseñas, sin web
    DIGITALIZADO = "F"       # Ya tiene todo (upsell)
    CLIENTE_ISA = "G"        # Ya es cliente

class LeadScraper:
    """Clasifica negocios según su presencia digital"""

    @staticmethod
    def clasificar(nombre: str, tiene_web: bool, tiene_rrss: bool, 
                   tiene_whatsapp: bool, tiene_catalogo: bool,
                   reseñas: int, web_vieja: bool = False) -> Dict:
        """
        Clasifica un negocio en casos A-G

        Returns:
            dict con caso, prioridad, speech_recomendado, pack_sugerido
        """

        # Lógica de clasificación
        if reseñas >= 40 and not tiene_web:
            caso = CasoNegocio.MINA_ORO
            prioridad = "🔴 URGENTE"
            speech = f"{nombre} tiene {reseñas} reseñas en Google. Eso significa que la gente YA lo busca y lo encuentra. Pero cuando quieren más información... no hay web. Está perdiendo clientes que ya lo eligieron."
            pack = "completo"

        elif not tiene_web and not tiene_rrss and not tiene_whatsapp:
            caso = CasoNegocio.FANTASMA
            prioridad = "🔴 URGENTE"
            speech = f"{nombre} no existe en internet. Su competencia se lo está comiendo. Empecemos con lo básico: Google Maps + WhatsApp Business."
            pack = "presencia"

        elif tiene_rrss and not tiene_web:
            caso = CasoNegocio.INFLUENCER_COJO
            prioridad = "🔴 URGENTE"
            speech = f"{nombre} tiene comunidad en redes, pero depende 100% de Mark Zuckerberg. Si le cierran la cuenta, pierde todo. Necesita su 'local propio' en internet."
            pack = "whatsapp_pro"

        elif tiene_web and web_vieja:
            caso = CasoNegocio.DESACTUALIZADO
            prioridad = "🟠 MEDIO"
            speech = f"{nombre} tiene web pero parece de 2015. No es responsive, no tiene HTTPS. Eso espanta clientes. Rediseño completo hacia el Pack Orgánico."
            pack = "completo"

        elif tiene_whatsapp and not tiene_catalogo:
            caso = CasoNegocio.WHATSAPP_CAOTICO
            prioridad = "🟠 MEDIO"
            speech = f"{nombre} usa WhatsApp pero responde los mismos mensajes todos los días. Pierde 2-3 horas diarias. Automatice el 80% con catálogo y respuestas rápidas."
            pack = "whatsapp_pro"

        elif tiene_web and tiene_rrss and tiene_whatsapp and tiene_catalogo:
            caso = CasoNegocio.DIGITALIZADO
            prioridad = "🟢 UPSELL"
            speech = f"{nombre} ya está digitalizado. Ahora escalemos: automatización con IA, SEO local, contenido mensual."
            pack = "automatizacion"

        else:
            caso = CasoNegocio.FANTASMA
            prioridad = "🔴 URGENTE"
            speech = f"{nombre} necesita presencia digital urgente."
            pack = "presencia"

        return {
            "caso": caso.value,
            "nombre": caso.name.replace("_", " ").title(),
            "prioridad": prioridad,
            "speech": speech,
            "pack_sugerido": pack,
            "score_potencial": 10 if caso in [CasoNegocio.MINA_ORO, CasoNegocio.FANTASMA] else 
                              7 if caso in [CasoNegocio.INFLUENCER_COJO, CasoNegocio.WHATSAPP_CAOTICO] else
                              5 if caso == CasoNegocio.DESACTUALIZADO else 3
        }

    @staticmethod
    def procesar_csv(filepath: str) -> List[Dict]:
        """Procesa CSV de Google Maps y clasifica cada negocio"""
        resultados = []

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Detectar campos del CSV
                nombre = row.get('title', row.get('name', 'Desconocido'))
                telefono = row.get('phone', '')
                web = row.get('website', '')
                reseñas = int(row.get('reviews', '0').replace(',', '')) if row.get('reviews') else 0

                # Inferir presencia digital
                tiene_web = bool(web and web != '')
                tiene_rrss = bool(row.get('facebook', '') or row.get('instagram', ''))
                tiene_whatsapp = telefono.startswith('+212 6') or telefono.startswith('+212 7')
                tiene_catalogo = False  # Requiere verificación manual

                clasificacion = LeadScraper.clasificar(
                    nombre, tiene_web, tiene_rrss, tiene_whatsapp, 
                    tiene_catalogo, reseñas
                )

                resultados.append({
                    "nombre": nombre,
                    "telefono": telefono,
                    "direccion": row.get('address', ''),
                    "clasificacion": clasificacion,
                    "raw_data": row
                })

        # Ordenar por prioridad
        prioridad_order = {"🔴 URGENTE": 0, "🟠 MEDIO": 1, "🟢 UPSELL": 2}
        resultados.sort(key=lambda x: prioridad_order.get(x["clasificacion"]["prioridad"], 3))

        return resultados

# ─── EJEMPLO DE USO ────────────────────────────────────────
if __name__ == "__main__":
    # Ejemplo manual
    resultado = LeadScraper.clasificar(
        nombre="Panadería Al Hizam",
        tiene_web=False,
        tiene_rrss=True,
        tiene_whatsapp=True,
        tiene_catalogo=False,
        reseñas=52
    )
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
