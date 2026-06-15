#!/usr/bin/env python3
"""
leads_router_v3.py - Endpoints FastAPI con Estrategia Francotirador

Cambios V3:
- Clasificación automática Casos A-G al cargar leads
- Columnas: caso_negocio, notas_scraping, estrategia_venta, pack_recomendado, precio_recomendado
- Mensajes personalizados por caso (A-G) con frases de scrap.txt
- Endpoint /por-caso para filtrar por clasificación
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import json
import tempfile
from datetime import datetime, timedelta

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])

NEON_URL = os.getenv("DATABASE_URL")

# ── MODELOS ────────────────────────────────────────────────────

class LeadResponse(BaseModel):
    id: int
    nombre_negocio: str
    telefono: Optional[str]
    email: Optional[str]
    tiene_web: bool
    website_url: Optional[str]
    rating: Optional[float]
    num_reviews: int
    score: int = Field(..., ge=0, le=100)
    score_detalle: dict
    caso_negocio: Optional[str]
    notas_scraping: Optional[str]
    estrategia_venta: Optional[str]
    pack_recomendado: Optional[str]
    precio_recomendado: Optional[int]
    estado: str
    categoria: Optional[str]
    direccion: Optional[str]
    ciudad: str
    google_maps_url: Optional[str]
    mensaje_presentacion: Optional[str] = None

class LeadMensajeRequest(BaseModel):
    lead_id: int
    idioma: str = Field(default="es", pattern="^(es|fr|ar)$")
    tipo_mensaje: str = Field(default="presentacion", pattern="^(presentacion|problema|solucion|precios|garantia|cierre)$")

class LeadMensajeResponse(BaseModel):
    lead_id: int
    nombre_negocio: str
    score: int = Field(..., ge=0, le=100)
    temperatura: str
    caso_negocio: Optional[str]
    estrategia_venta: Optional[str]
    pack_recomendado: Optional[str]
    precio_recomendado: Optional[int]
    idioma: str
    mensaje: str
    recomendacion: str
    telefono_valido: bool

class CargarResponse(BaseModel):
    total: int
    hot: int
    warm: int
    cold: int
    ice: int
    sin_web: int
    con_telefono: int
    por_caso: dict
    mensaje: str

class SeguimientoResponse(BaseModel):
    d2_enviados: int
    d5_enviados: int
    d10_enviados: int
    total_enviados: int
    detalle: List[dict]

# ── DB HELPERS ─────────────────────────────────────────────────

def get_db():
    if not NEON_URL:
        raise HTTPException(500, "DATABASE_URL no configurada")
    return psycopg2.connect(NEON_URL, cursor_factory=RealDictCursor)


# ── CLASIFICACIÓN FRANCOTIRADOR (Casos A-G) ──────────────────

def clasificar_caso(
    tiene_web: bool,
    rating: Optional[float],
    num_reviews: int,
    telefono: Optional[str],
    notas: str = ""
) -> dict:
    """
    Clasifica un lead en Casos A-G según la estrategia francotirador.
    Retorna: {caso, estrategia, pack, precio, notas}
    """
    notas_lower = notas.lower() if notas else ""

    # Caso E: La Mina de Oro (tiene web, buen rating, muchas reviews)
    if tiene_web and rating and rating >= 4.0 and num_reviews >= 500:
        return {
            "caso": "E",
            "estrategia": "Automatizacion",
            "pack": "Automatizacion",
            "precio": 800,
            "notas": "Mina de Oro: Alto volumen. Vender automatización, no visibilidad."
        }

    # Caso D: El WhatsApp Caótico (tiene web pero canal roto)
    elif tiene_web and ("no sirve" in notas_lower or "whatsapp roto" in notas_lower or "link roto" in notas_lower):
        return {
            "caso": "D",
            "estrategia": "WhatsApp Pro",
            "pack": "WhatsApp Pro",
            "precio": 400,
            "notas": "Canal roto: Web existe pero WhatsApp falla. Perdiendo ventas diarias."
        }

    # Caso C: El Desactualizado (tiene web pero rating bajo)
    elif tiene_web and rating and rating < 4.0:
        return {
            "caso": "C",
            "estrategia": "Completo",
            "pack": "Completo",
            "precio": 1200,
            "notas": "Reputación dañada: Web existe pero no genera confianza."
        }

    # Caso F: El Semi-Digital (tiene web, rating medio, pocas reviews)
    elif tiene_web and rating and rating >= 3.5 and num_reviews < 100:
        return {
            "caso": "F",
            "estrategia": "Presencia",
            "pack": "Presencia Plus",
            "precio": 400,
            "notas": "Semi-digital: Tiene web pero poco tráfico. Necesita visibilidad."
        }

    # Caso A: El Fantasma (sin web, buen rating)
    elif not tiene_web and rating and rating >= 4.0:
        return {
            "caso": "A",
            "estrategia": "Presencia",
            "pack": "Presencia",
            "precio": 250,
            "notas": "Fantasma con potencial: Buen producto, invisible digitalmente."
        }

    # Caso B: El Influencer Cojo (sin web, rating bajo, pocas reviews)
    elif not tiene_web and rating and rating < 4.0 and num_reviews < 50:
        return {
            "caso": "B",
            "estrategia": "Completo",
            "pack": "Completo",
            "precio": 1200,
            "notas": "Influencer Cojo: Sin presencia y reputación dañada. Necesita todo."
        }

    # Caso G: El Inalcanzable (sin teléfono)
    elif not telefono:
        return {
            "caso": "G",
            "estrategia": "Ninguno",
            "pack": "Ninguno",
            "precio": 0,
            "notas": "Inalcanzable: Sin teléfono. No contactable por WhatsApp."
        }

    # Default: Caso A genérico
    else:
        return {
            "caso": "A",
            "estrategia": "Presencia",
            "pack": "Presencia",
            "precio": 250,
            "notas": "Sin web. Necesita presencia digital básica."
        }


# ── SCORING (0-100) ──────────────────────────────────────────

def calcular_score(row: dict) -> tuple[int, dict]:
    score = 0
    detalle = {}

    website = str(row.get("website", "")).strip()
    tiene_web = bool(website and website.lower() not in ["nan", "none", ""])
    if not tiene_web:
        score += 40
        detalle["sin_web"] = 40
    else:
        detalle["sin_web"] = 0

    whatsapp = str(row.get("whatsapp", "")).strip()
    tiene_wa = bool(whatsapp and whatsapp.lower() not in ["nan", "none", ""])
    if not tiene_wa:
        score += 15
        detalle["sin_whatsapp_business"] = 15
    else:
        detalle["sin_whatsapp_business"] = 0

    try:
        rating = float(row.get("rating", 0))
        if rating > 0 and rating < 4.0:
            score += 10
            detalle["rating_bajo"] = 10
        elif rating >= 4.5:
            score += 5
            detalle["rating_alto"] = 5
        else:
            detalle["rating_neutro"] = 0
    except:
        detalle["rating_neutro"] = 0

    try:
        reviews = int(row.get("reviews", 0))
        if reviews >= 500:
            score += 15
            detalle["muchas_reviews"] = 15
        elif reviews >= 100:
            score += 10
            detalle["reviews_moderadas"] = 10
        elif reviews >= 20:
            score += 5
            detalle["pocas_reviews"] = 5
        else:
            detalle["reviews_muy_pocas"] = 0
    except:
        detalle["reviews_error"] = 0

    phone = str(row.get("phone", "")).strip()
    if phone and phone.lower() not in ["nan", "none", ""]:
        score += 10
        detalle["tiene_telefono"] = 10
    else:
        detalle["tiene_telefono"] = 0

    email = str(row.get("email", "")).strip()
    if not email or email.lower() in ["nan", "none", ""]:
        score += 5
        detalle["sin_email"] = 5
    else:
        detalle["tiene_email"] = 0

    categoria = str(row.get("category", "")).lower()
    subtipos = str(row.get("subtypes", "")).lower()
    alta_demanda = ["restaurant", "cafe", "hotel", "bakery", "pastry"]
    if any(cat in categoria or cat in subtipos for cat in alta_demanda):
        score += 5
        detalle["categoria_alta_demanda"] = 5
    else:
        detalle["categoria_estandar"] = 0

    score = min(score, 100)
    detalle["score_total"] = score

    return score, detalle


def limpiar_telefono(phone: str) -> str | None:
    if not phone or str(phone).lower() in ["nan", "none", ""]:
        return None
    p = str(phone).strip()
    p = p.replace(" ", "").replace("-", "").replace(".", "")
    if p.startswith("+212"):
        return p
    if p.startswith("0"):
        return "+212" + p[1:]
    if p.startswith("212"):
        return "+" + p
    if len(p) >= 9:
        return "+212" + p
    return p


def validar_telefono_marroqui(phone: str) -> bool:
    if not phone:
        return False
    if not phone.startswith("+212"):
        return False
    digits = phone.replace("+", "").replace(" ", "")
    return len(digits) == 12 and digits[3:].isdigit()


def get_temperatura(score: int) -> str:
    if score >= 80:
        return "🔥 HOT"
    elif score >= 60:
        return "🌡️ WARM"
    elif score >= 40:
        return "❄️ COLD"
    else:
        return "🧊 ICE"


def get_recomendacion(score: int, tiene_web: bool, rating: Optional[float], caso: Optional[str]) -> str:
    recs = []
    if score >= 80:
        recs.append("🎯 PRIORIDAD MÁXIMA: Contactar HOY")
    elif score >= 60:
        recs.append("📞 Contactar esta semana")
    else:
        recs.append("📋 Seguimiento programado")

    if caso:
        recs.append(f"🎲 Caso {caso}")
    if not tiene_web:
        recs.append("💰 Sin web = oportunidad máxima")
    if rating and rating < 4.0:
        recs.append("⭐ Rating bajo = necesita reputación")

    return " | ".join(recs)


# ── MENSAJES POR CASO (de scrap.txt) ─────────────────────────

MENSAJES_CASO = {
    "es": {
        "A": {  # El Fantasma
            "presentacion": "Soy Isa. Veo que {nombre} tiene buenas reseñas pero no aparece en Google cuando alguien busca. El 40% de las ventas locales se pierden por no aparecer en Google Maps. Para un restaurante, no tener web hoy es como no tener carta. Creamos su presencia digital en 24 horas desde solo 250 MAD.",
            "problema": "El 40% de las ventas locales se pierden por no aparecer en Google Maps. {nombre} tiene buen producto pero es invisible digitalmente. Cada día que pasa sin web son clientes que van a la competencia.",
            "solucion": "En 24 horas creamos su ficha de Google Maps optimizada y su presencia digital básica. Incluye dirección, horarios, fotos y teléfono visible. Desde solo 250 MAD.",
            "precios": "Pack Presencia: 250 MAD. Incluye Google Maps optimizado, ficha básica y dirección web. Sin mantenimiento mensual.",
        },
        "B": {  # El Influencer Cojo
            "presentacion": "Soy Isa. Veo que {nombre} necesita trabajo completo: sin web y con reputación por mejorar. Mi pack completo rehace su contenido, automatiza respuestas y le devuelvo su dinero si no ve resultados. Desde 1,200 MAD.",
            "problema": "Sin presencia digital y con reputación dañada, {nombre} está perdiendo clientes por dos frentes. La gente no los encuentra Y cuando los encuentra no confía.",
            "solucion": "Pack Completo: web profesional, Google Maps optimizado, WhatsApp Business con catálogo, y gestión de reputación. Garantía de 30 días o devolución. 1,200 MAD.",
            "precios": "Pack Completo: 1,200 MAD. Todo incluido: web, Google Maps, WhatsApp Pro, gestión de reputación. Mantenimiento mensual incluido.",
        },
        "C": {  # El Desactualizado
            "presentacion": "Soy Isa. Veo que {nombre} tiene web pero las reseñas muestran que la experiencia digital no refleja la realidad. Ofrezco un pack completo para rehacer su contenido, automatizar respuestas y mejorar su imagen. Garantía por escrito: si en 30 días no nota más confianza y ventas, le devuelvo el dinero. 1,200 MAD.",
            "problema": "{nombre} tiene web, pero su rating de {rating} muestra que no genera confianza. Las reseñas negativas están ahuyentando clientes. Su web no está trabajando para usted, está trabajando en contra.",
            "solucion": "Rehacemos su contenido digital, optimizamos Google Maps, conectamos WhatsApp Business con respuestas automáticas, y gestionamos su reputación. Garantía de 30 días. 1,200 MAD.",
            "precios": "Pack Completo: 1,200 MAD. Rehace su imagen digital completa. Incluye garantía de 30 días.",
        },
        "D": {  # El WhatsApp Caótico
            "presentacion": "Soy Isa. Noté que tienen una web muy bonita, pero el link de WhatsApp no funciona. El 67% de los clientes abandonan si no reciben respuesta en 5 minutos. Tener la web con el WhatsApp roto es como tener la puerta del local cerrada. En 48 horas les conecto el Pack WhatsApp Pro (400 MAD) para que no pierdan ni un pedido.",
            "problema": "El 67% de los clientes abandonan si no reciben respuesta en 5 minutos. {nombre} tiene la web pero su canal principal de comunicación está roto. Está perdiendo dinero ahora mismo.",
            "solucion": "En 48 horas solucionamos su WhatsApp Business: catálogo de productos, respuestas automáticas, y conexión correcta con su web. Pack WhatsApp Pro: 400 MAD.",
            "precios": "Pack WhatsApp Pro: 400 MAD. Catálogo, respuestas automáticas, conexión web. Mantenimiento mensual incluido.",
        },
        "E": {  # La Mina de Oro
            "presentacion": "Soy Isa de Orchestrator ISA. Veo que {nombre} es muy popular en Google Maps (¡{reviews} reseñas!). Mi sistema no es para que los encuentren (ya los encuentran), es para automatizar las reservas y pedidos que ya reciben y que su WhatsApp no colapse. Puedo ayudarles a gestionar ese volumen desde 800 MAD. ¿Tienen 5 minutos para una demo?",
            "problema": "{nombre} ya tiene clientes ({reviews} reseñas), pero está perdiendo eficiencia. Las reservas se pierden, el WhatsApp colapsa, y no pueden atender todo el volumen que ya tienen.",
            "solucion": "Automatizamos sus reservas, pedidos y respuestas. WhatsApp Business con IA, catálogo dinámico, y sistema de gestión. Usted se enfoca en cocinar, nosotros en digitalizar. 800 MAD.",
            "precios": "Pack Automatización: 800 MAD. Sistema completo de gestión. Ideal para alto volumen.",
        },
        "F": {  # El Semi-Digital
            "presentacion": "Soy Isa. Veo que {nombre} tiene web pero poco tráfico. Tienen la estructura pero les falta visibilidad. Mi Pack Presencia Plus les da el empujón que necesitan: SEO local, Google Maps optimizado y campaña básica. 400 MAD.",
            "problema": "{nombre} tiene web pero poca gente la encuentra. Tienen la estructura pero no la visibilidad. Es como tener un local en una calle sin señalización.",
            "solucion": "Pack Presencia Plus: optimización SEO local, Google Maps premium, y estrategia de visibilidad básica. 400 MAD.",
            "precios": "Pack Presencia Plus: 400 MAD. SEO local + Google Maps premium + visibilidad.",
        },
        "G": {  # El Inalcanzable
            "presentacion": "Lamentablemente no podemos contactar a {nombre} porque no tienen teléfono registrado. Recomendamos buscar su contacto por otros medios o visitar el local directamente.",
            "problema": "Sin teléfono no podemos ayudarles por WhatsApp. Necesitamos un canal de contacto.",
            "solucion": "Buscar teléfono alternativo o contactar presencialmente.",
            "precios": "N/A",
        },
    },
    "fr": {
        "A": {
            "presentacion": "Je suis Isa. Je vois que {nombre} a de bonnes critiques mais n\'apparaît pas sur Google. 40% des ventes locales sont perdues sans présence digitale. Créons votre présence en 24h depuis 250 MAD.",
        },
        "D": {
            "presentacion": "Je suis Isa. J\'ai remarqué que votre site web est beau, mais le lien WhatsApp ne fonctionne pas. 67% des clients abandonnent sans réponse en 5 minutes. Pack WhatsApp Pro: 400 MAD en 48h.",
        },
        "E": {
            "presentacion": "Je suis Isa. {nombre} est très populaire ({reviews} avis). Mon système automatise les réservations que vous recevez déjà. Depuis 800 MAD.",
        },
    },
    "ar": {
        "A": {
            "presentacion": "Ana Isa. {nombre} 3ndou reviews mzyana walakin ma kayan f Google. 40% dyal l'mabi3at katmchi. N9edrou n9adou presence dyalkom f 24 sa3a b 250 MAD.",
        },
        "D": {
            "presentacion": "Ana Isa. Website dyalkom zwina walakin WhatsApp ma khedamch. 67% dyal l'clyanet kay-sam7ou. Pack WhatsApp Pro: 400 MAD f 48 sa3a.",
        },
        "E": {
            "presentacion": "Ana Isa. {nombre} m3rouf bzzaf ({reviews} reviews). System dyali kay-automatise l'reservations li 9belou. Men 800 MAD.",
        },
    }
}


# Mensajes genéricos para tipos no definidos en Caso
MENSAJES_GENERICOS = {
    "es": {
        "problema": "¿Sabía que el 67% de los clientes abandonan si no reciben respuesta en 5 minutos? Además, el 40% de las ventas locales se pierden por no aparecer en Google Maps.",
        "solucion": "Mi sistema le entrega en 48 horas su ficha de Google Maps optimizada, WhatsApp Business con catálogo y respuestas automáticas. Incluye capacitación de 15 minutos y garantía de 30 días.",
        "precios": "Tenemos opciones para cada nivel: Presencia (250 MAD), WhatsApp Pro (400 MAD), Automatización con IA (800 MAD) o Pack Completo (1,200 MAD).",
        "garantia": "Le doy mi garantía por escrito: si en 30 días no ve el sistema funcionando, le devuelvo el 100% de su dinero.",
        "cierre": "Perfecto. Para comenzar hoy solo necesito el 50% de anticipo y el resto al entregar en 48 horas. ¿Le parece bien?",
        "seguimiento_d2": "Hola {nombre}, solo le escribo para saber si tuvo chance de revisar la propuesta. Quedo atento por si tiene alguna duda. ¡Saludos!",
        "seguimiento_d5": "Hola {nombre}, le escribo de nuevo porque sé que está ocupado. La oferta sigue vigente. ¿Podemos agendar 5 minutos?",
        "seguimiento_d10": "Hola {nombre}, último mensaje. No quiero ser pesado, pero sé que esta propuesta puede ayudarle mucho. Si cambia de opinión, aquí estoy. ¡Éxito!",
    },
    "fr": {
        "problema": "Saviez-vous que 67% des clients abandonnent sans réponse en 5 minutes? 40% des ventes sont perdues sans Google Maps.",
        "solucion": "Mon système vous livre en 48h: Google Maps, WhatsApp Business avec catalogue. Formation 15 min et garantie 30 jours.",
        "precios": "Packs: Présence (250 MAD), WhatsApp Pro (400 MAD), Automatisation (800 MAD), Complet (1,200 MAD).",
        "garantia": "Garantie par écrit: si en 30 jours vous ne voyez pas de résultats, je vous rembourse 100%.",
        "cierre": "Parfait. Pour commencer aujourd\'hui, 50% d\'acompte. Je vous envoie la proposition détaillée.",
    },
    "ar": {
        "problema": "Wach 3arf bli 67% dyal l'clyanet kay-sam7ou ila majawbtihomch f 5 d9ay9? W 40% dyal l'mabi3at kat-mchi 7it makat-banouch f Google Maps.",
        "solucion": "System dyali kay-وجد f 48 sa3a: Google Maps, WhatsApp Business fih l'catálogo. 15 d9ay3 dyal t3lim w garantie 30 youm.",
        "precios": "Packs: Presencia (250 MAD), WhatsApp Pro (400 MAD), Automatisation (800 MAD), Completo (1,200 MAD).",
        "garantia": "Garantie maktuba: ila f 30 youm machftouch l'natija, kan-rj3 likom flouskom 100%.",
    }
}


def generar_mensaje_personalizado(lead: dict, idioma: str, tipo: str) -> str:
    """Genera mensaje personalizado según Caso A-G."""
    nombre = lead["nombre_negocio"]
    caso = lead.get("caso_negocio", "A")
    rating = lead.get("rating")
    reviews = lead.get("num_reviews", 0)

    # Intentar obtener mensaje específico del caso
    mensajes_idioma = MENSAJES_CASO.get(idioma, MENSAJES_CASO["es"])
    mensajes_caso = mensajes_idioma.get(caso, mensajes_idioma.get("A", {}))

    base = mensajes_caso.get(tipo)

    # Si no hay mensaje específico para este tipo, usar genérico
    if not base:
        genericos = MENSAJES_GENERICOS.get(idioma, MENSAJES_GENERICOS["es"])
        base = genericos.get(tipo, genericos["problema"])

    # Saludo personalizado
    if idioma == "es":
        saludo = f"Hola {nombre}! 👋\n\n"
    elif idioma == "fr":
        saludo = f"Bonjour {nombre}! 👋\n\n"
    else:
        saludo = f"Salam {nombre}! 👋\n\n"

    # Formatear variables
    mensaje = saludo + base.format(
        nombre=nombre,
        rating=rating or "N/A",
        reviews=reviews
    )

    # Personalización adicional según perfil
    if tipo == "presentacion":
        if not lead.get("tiene_web") and caso not in ["C", "D", "E", "F"]:
            if idioma == "es":
                mensaje += "\n\n💡 Vi que aún no tienen página web. Cada día sin presencia digital son clientes que van a la competencia."

        if rating and rating < 4.0 and caso not in ["C"]:
            if idioma == "es":
                mensaje += f"\n\n⭐ Su rating actual es {rating}. Con mi sistema podemos mejorar su reputación online."

    return mensaje


# ── PROCESAMIENTO EXCEL ──────────────────────────────────────

def procesar_excel(filepath: str) -> list[dict]:
    df = pd.read_excel(filepath)
    df = df[df["place_id"].notna()]
    df = df[df["place_id"] != "__NO_PLACE_FOUND__"]
    df = df.drop_duplicates(subset=["place_id"], keep="first")

    leads = []
    for _, row in df.iterrows():
        score, score_detalle = calcular_score(row)

        website = str(row.get("website", "")).strip()
        tiene_web = bool(website and website.lower() not in ["nan", "none", ""])

        phone_raw = str(row.get("phone", "")).strip()
        phone = limpiar_telefono(phone_raw) if phone_raw.lower() not in ["nan", "none", ""] else None

        email = str(row.get("email", "")).strip()
        email = email if email.lower() not in ["nan", "none", ""] else None

        fb = str(row.get("company_facebook", "")).strip()
        ig = str(row.get("company_instagram", "")).strip()

        # Notas del scrap (columna "nota" o similar en Outscraper)
        notas_raw = str(row.get("nota", "")).strip()
        notas = notas_raw if notas_raw.lower() not in ["nan", "none", ""] else ""

        # Clasificación automática
        rating_val = float(row.get("rating")) if pd.notna(row.get("rating")) else None
        reviews_val = int(row.get("reviews", 0)) if pd.notna(row.get("reviews")) else 0

        clasificacion = clasificar_caso(
            tiene_web=tiene_web,
            rating=rating_val,
            num_reviews=reviews_val,
            telefono=phone,
            notas=notas
        )

        lead = {
            "nombre_negocio": str(row.get("name", "")).strip()[:255],
            "telefono": phone,
            "whatsapp": bool(str(row.get("whatsapp", "")).strip() and 
                           str(row.get("whatsapp", "")).strip().lower() not in ["nan", "none", ""]),
            "email": email[:255] if email else None,
            "tiene_web": tiene_web,
            "website_url": website if tiene_web else None,
            "tiene_facebook": bool(fb and fb.lower() not in ["nan", "none", ""]),
            "facebook_url": fb if fb and fb.lower() not in ["nan", "none", ""] else None,
            "tiene_instagram": bool(ig and ig.lower() not in ["nan", "none", ""]),
            "instagram_url": ig if ig and ig.lower() not in ["nan", "none", ""] else None,
            "direccion": str(row.get("address", "")).strip() if pd.notna(row.get("address")) else None,
            "ciudad": str(row.get("city", "Tetouan")).strip()[:100],
            "latitud": float(row.get("latitude")) if pd.notna(row.get("latitude")) else None,
            "longitud": float(row.get("longitude")) if pd.notna(row.get("longitude")) else None,
            "place_id": str(row.get("place_id", "")).strip()[:255],
            "google_id": str(row.get("google_id", "")).strip()[:255] if pd.notna(row.get("google_id")) else None,
            "google_maps_url": str(row.get("location_link", "")).strip() if pd.notna(row.get("location_link")) else None,
            "rating": rating_val,
            "num_reviews": reviews_val,
            "categoria": str(row.get("category", "")).strip()[:100] if pd.notna(row.get("category")) else None,
            "subtipos": str(row.get("subtypes", "")).strip() if pd.notna(row.get("subtypes")) else None,
            "estado_negocio": str(row.get("business_status", "OPERATIONAL")).strip()[:50],
            # Estrategia Francotirador
            "caso_negocio": clasificacion["caso"],
            "notas_scraping": clasificacion["notas"],
            "estrategia_venta": clasificacion["estrategia"],
            "pack_recomendado": clasificacion["pack"],
            "precio_recomendado": clasificacion["precio"],
            # Scoring
            "score": score,
            "score_detalle": json.dumps(score_detalle),
            "estado": "nuevo",
            "fuente": "outscraper",
            "raw_data": json.dumps({
                "working_hours": str(row.get("working_hours", "")) if pd.notna(row.get("working_hours")) else None,
                "about": str(row.get("about", "")) if pd.notna(row.get("about")) else None,
                "description": str(row.get("description", "")) if pd.notna(row.get("description")) else None,
                "phone_raw": phone_raw,
                "nota_raw": notas,
            }),
        }
        leads.append(lead)

    return leads


def insertar_en_neon(leads: list[dict]) -> list:
    conn = psycopg2.connect(NEON_URL)
    cur = conn.cursor()

    query = """
    INSERT INTO public.leads_scrap (
        nombre_negocio, telefono, whatsapp, email,
        tiene_web, website_url, tiene_facebook, facebook_url,
        tiene_instagram, instagram_url, direccion, ciudad,
        latitud, longitud, place_id, google_id, google_maps_url,
        rating, num_reviews, categoria, subtipos, estado_negocio,
        caso_negocio, notas_scraping, estrategia_venta, pack_recomendado, precio_recomendado,
        score, score_detalle, estado, fuente, raw_data
    ) VALUES %s
    ON CONFLICT (place_id) DO UPDATE SET
        nombre_negocio = EXCLUDED.nombre_negocio,
        telefono = EXCLUDED.telefono,
        whatsapp = EXCLUDED.whatsapp,
        email = EXCLUDED.email,
        tiene_web = EXCLUDED.tiene_web,
        website_url = EXCLUDED.website_url,
        tiene_facebook = EXCLUDED.tiene_facebook,
        facebook_url = EXCLUDED.facebook_url,
        tiene_instagram = EXCLUDED.tiene_instagram,
        instagram_url = EXCLUDED.instagram_url,
        direccion = EXCLUDED.direccion,
        latitud = EXCLUDED.latitud,
        longitud = EXCLUDED.longitud,
        google_id = EXCLUDED.google_id,
        google_maps_url = EXCLUDED.google_maps_url,
        rating = EXCLUDED.rating,
        num_reviews = EXCLUDED.num_reviews,
        categoria = EXCLUDED.categoria,
        subtipos = EXCLUDED.subtipos,
        estado_negocio = EXCLUDED.estado_negocio,
        caso_negocio = EXCLUDED.caso_negocio,
        notas_scraping = EXCLUDED.notas_scraping,
        estrategia_venta = EXCLUDED.estrategia_venta,
        pack_recomendado = EXCLUDED.pack_recomendado,
        precio_recomendado = EXCLUDED.precio_recomendado,
        score = EXCLUDED.score,
        score_detalle = EXCLUDED.score_detalle,
        raw_data = EXCLUDED.raw_data,
        updated_at = NOW()
    RETURNING id, nombre_negocio, score, caso_negocio, estado
    """

    values = [(
        l["nombre_negocio"], l["telefono"], l["whatsapp"], l["email"],
        l["tiene_web"], l["website_url"], l["tiene_facebook"], l["facebook_url"],
        l["tiene_instagram"], l["instagram_url"], l["direccion"], l["ciudad"],
        l["latitud"], l["longitud"], l["place_id"], l["google_id"], l["google_maps_url"],
        l["rating"], l["num_reviews"], l["categoria"], l["subtipos"], l["estado_negocio"],
        l["caso_negocio"], l["notas_scraping"], l["estrategia_venta"], l["pack_recomendado"], l["precio_recomendado"],
        l["score"], l["score_detalle"], l["estado"], l["fuente"], l["raw_data"]
    ) for l in leads]

    execute_values(cur, query, values, page_size=100)
    resultados = cur.fetchall()

    conn.commit()
    cur.close()
    conn.close()

    return resultados


# ── ENDPOINTS ──────────────────────────────────────────────────

@router.post("/cargar", response_model=CargarResponse)
async def cargar_leads(file: UploadFile = File(...)):
    """Carga leads desde Excel de Outscraper con clasificación automática."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Solo archivos Excel (.xlsx, .xls)")

    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        leads = procesar_excel(tmp_path)
        resultados = insertar_en_neon(leads)

        scores = [r[2] for r in resultados]
        casos = {}
        for r in resultados:
            c = r[3] or "A"
            casos[c] = casos.get(c, 0) + 1

        return CargarResponse(
            total=len(resultados),
            hot=sum(1 for s in scores if s >= 80),
            warm=sum(1 for s in scores if 60 <= s < 80),
            cold=sum(1 for s in scores if 40 <= s < 60),
            ice=sum(1 for s in scores if s < 40),
            sin_web=sum(1 for l in leads if not l["tiene_web"]),
            con_telefono=sum(1 for l in leads if l["telefono"]),
            por_caso=casos,
            mensaje=f"✅ {len(resultados)} leads cargados. Casos: {casos}"
        )
    finally:
        os.unlink(tmp_path)


@router.get("/", response_model=List[LeadResponse])
def listar_leads(
    estado: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    caso: Optional[str] = Query(None, pattern="^[A-G]$"),
    estrategia: Optional[str] = Query(None),
    sin_web: Optional[bool] = Query(None),
    ciudad: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lista leads con filtros incluyendo caso y estrategia."""
    conn = get_db()
    cur = conn.cursor()

    conditions = ["1=1"]
    params = []

    if estado:
        conditions.append("estado = %s")
        params.append(estado)
    if min_score is not None:
        conditions.append("score >= %s")
        params.append(min_score)
    if max_score is not None:
        conditions.append("score <= %s")
        params.append(max_score)
    if caso:
        conditions.append("caso_negocio = %s")
        params.append(caso)
    if estrategia:
        conditions.append("estrategia_venta ILIKE %s")
        params.append(f"%{estrategia}%")
    if sin_web is not None:
        conditions.append("tiene_web = %s")
        params.append(sin_web)
    if ciudad:
        conditions.append("ciudad ILIKE %s")
        params.append(f"%{ciudad}%")
    if categoria:
        conditions.append("categoria ILIKE %s")
        params.append(f"%{categoria}%")

    where_clause = " AND ".join(conditions)

    query = f"""
    SELECT id, nombre_negocio, telefono, email,
        tiene_web, website_url, rating, num_reviews,
        score, score_detalle, caso_negocio, notas_scraping,
        estrategia_venta, pack_recomendado, precio_recomendado,
        estado, categoria, direccion, ciudad, google_maps_url
    FROM public.leads_scrap
    WHERE {where_clause}
    ORDER BY score DESC, num_reviews DESC
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    for row in rows:
        data = dict(row)
        data["score_detalle"] = json.loads(data.get("score_detalle", "{}"))
        results.append(LeadResponse(**data))

    return results


@router.get("/por-caso")
def leads_por_caso():
    """Retorna distribución de leads por Caso A-G."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT 
        caso_negocio,
        COUNT(*) as cantidad,
        ROUND(AVG(score), 1) as score_promedio,
        ROUND(AVG(precio_recomendado), 0) as precio_promedio,
        STRING_AGG(nombre_negocio, ', ' ORDER BY score DESC) as top_negocios
    FROM public.leads_scrap
    WHERE caso_negocio IS NOT NULL
    GROUP BY caso_negocio
    ORDER BY cantidad DESC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(r) for r in rows]


@router.get("/prioritarios", response_model=List[LeadResponse])
def leads_prioritarios(
    limit: int = Query(20, ge=1, le=100),
    min_score: int = Query(60, ge=0, le=100),
):
    """Retorna leads con score >= min_score."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, nombre_negocio, telefono, email,
        tiene_web, website_url, rating, num_reviews,
        score, score_detalle, caso_negocio, notas_scraping,
        estrategia_venta, pack_recomendado, precio_recomendado,
        estado, categoria, direccion, ciudad, google_maps_url
    FROM public.leads_scrap
    WHERE score >= %s 
    AND estado NOT IN ('cerrado', 'descartado')
    ORDER BY score DESC, num_reviews DESC
    LIMIT %s
    """, (min_score, limit))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    for row in rows:
        data = dict(row)
        data["score_detalle"] = json.loads(data.get("score_detalle", "{}"))
        results.append(LeadResponse(**data))

    return results


@router.get("/next", response_model=LeadResponse)
def siguiente_lead(
    idioma: str = Query("es", pattern="^(es|fr|ar)$"),
    tipo_mensaje: str = Query("presentacion", pattern="^(presentacion|problema|solucion|precios|garantia|cierre)$"),
):
    """Obtiene siguiente lead prioritario con mensaje personalizado por Caso."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, nombre_negocio, telefono, email,
        tiene_web, website_url, rating, num_reviews,
        score, score_detalle, caso_negocio, notas_scraping,
        estrategia_venta, pack_recomendado, precio_recomendado,
        estado, categoria, direccion, ciudad, google_maps_url
    FROM public.leads_scrap
    WHERE estado = 'nuevo'
    ORDER BY score DESC, num_reviews DESC
    LIMIT 1
    """)

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(404, "No hay leads nuevos disponibles")

    data = dict(row)
    data["score_detalle"] = json.loads(data.get("score_detalle", "{}"))
    data["mensaje_presentacion"] = generar_mensaje_personalizado(data, idioma, tipo_mensaje)

    return LeadResponse(**data)


@router.post("/{lead_id}/mensaje", response_model=LeadMensajeResponse)
def generar_mensaje(lead_id: int, req: LeadMensajeRequest):
    """Genera mensaje específico para un lead según su Caso A-G."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, nombre_negocio, telefono, email,
        tiene_web, website_url, rating, num_reviews,
        score, score_detalle, caso_negocio, notas_scraping,
        estrategia_venta, pack_recomendado, precio_recomendado,
        estado, categoria, direccion, ciudad, google_maps_url
    FROM public.leads_scrap
    WHERE id = %s
    """, (lead_id,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(404, f"Lead {lead_id} no encontrado")

    data = dict(row)
    score = data["score"]
    nombre = data["nombre_negocio"]
    telefono = data.get("telefono")
    caso = data.get("caso_negocio")

    telefono_valido = validar_telefono_marroqui(telefono) if telefono else False

    mensaje = generar_mensaje_personalizado(data, req.idioma, req.tipo_mensaje)

    temperatura = get_temperatura(score)
    recomendacion = get_recomendacion(score, data["tiene_web"], data.get("rating"), caso)

    if not telefono_valido:
        recomendacion += " ⚠️ Teléfono inválido - NO ENVIAR"

    return LeadMensajeResponse(
        lead_id=lead_id,
        nombre_negocio=nombre,
        score=score,
        temperatura=temperatura,
        caso_negocio=caso,
        estrategia_venta=data.get("estrategia_venta"),
        pack_recomendado=data.get("pack_recomendado"),
        precio_recomendado=data.get("precio_recomendado"),
        idioma=req.idioma,
        mensaje=mensaje,
        recomendacion=recomendacion,
        telefono_valido=telefono_valido,
    )


@router.post("/{lead_id}/contactar")
def marcar_contactado(lead_id: int, mensaje_enviado: Optional[str] = None):
    """Marca un lead como contactado."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    UPDATE public.leads_scrap
    SET estado = 'contactado',
        ultimo_contacto = NOW(),
        mensaje_enviado = COALESCE(%s, mensaje_enviado),
        updated_at = NOW()
    WHERE id = %s
    RETURNING id, nombre_negocio, estado, score, caso_negocio
    """, (mensaje_enviado, lead_id))

    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(404, f"Lead {lead_id} no encontrado")

    return dict(row)


@router.post("/{lead_id}/respuesta")
def registrar_respuesta(
    lead_id: int,
    respuesta: str,
    nuevo_estado: Optional[str] = Query(None, pattern="^(respondio|interesado|propuesta_enviada|cerrado|descartado)$"),
):
    """Registra respuesta del lead."""
    conn = get_db()
    cur = conn.cursor()

    estado_update = nuevo_estado or "respondio"

    cur.execute("""
    UPDATE public.leads_scrap
    SET respuesta_recibida = %s,
        estado = %s,
        ultimo_contacto = NOW(),
        updated_at = NOW()
    WHERE id = %s
    RETURNING id, nombre_negocio, estado, score, caso_negocio
    """, (respuesta, estado_update, lead_id))

    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(404, f"Lead {lead_id} no encontrado")

    return dict(row)


@router.post("/seguimiento-automatico", response_model=SeguimientoResponse)
def seguimiento_automatico(background_tasks: BackgroundTasks):
    """Envía seguimientos automáticos D2, D5, D10."""
    conn = get_db()
    cur = conn.cursor()
    hoy = datetime.now()

    detalle = []
    d2_enviados = d5_enviados = d10_enviados = 0

    # D2
    cur.execute("""
    SELECT id, nombre_negocio, telefono, estado, ultimo_contacto, caso_negocio
    FROM public.leads_scrap
    WHERE estado = 'contactado'
    AND ultimo_contacto < %s
    AND ultimo_contacto > %s
    AND respuesta_recibida IS NULL
    """, (hoy - timedelta(days=2), hoy - timedelta(days=3)))

    for lead in cur.fetchall():
        if validar_telefono_marroqui(lead["telefono"]):
            d2_enviados += 1
            detalle.append({
                "lead_id": lead["id"],
                "nombre": lead["nombre_negocio"],
                "tipo": "D2",
                "telefono": lead["telefono"],
                "caso": lead["caso_negocio"]
            })
            cur.execute("""
            UPDATE public.leads_scrap SET estado='seguimiento_d2', updated_at=NOW() WHERE id=%s
            """, (lead["id"],))

    # D5
    cur.execute("""
    SELECT id, nombre_negocio, telefono, estado, ultimo_contacto, caso_negocio
    FROM public.leads_scrap
    WHERE estado IN ('contactado', 'seguimiento_d2')
    AND ultimo_contacto < %s
    AND ultimo_contacto > %s
    AND respuesta_recibida IS NULL
    """, (hoy - timedelta(days=5), hoy - timedelta(days=6)))

    for lead in cur.fetchall():
        if validar_telefono_marroqui(lead["telefono"]):
            d5_enviados += 1
            detalle.append({
                "lead_id": lead["id"],
                "nombre": lead["nombre_negocio"],
                "tipo": "D5",
                "telefono": lead["telefono"],
                "caso": lead["caso_negocio"]
            })
            cur.execute("""
            UPDATE public.leads_scrap SET estado='seguimiento_d5', updated_at=NOW() WHERE id=%s
            """, (lead["id"],))

    # D10
    cur.execute("""
    SELECT id, nombre_negocio, telefono, estado, ultimo_contacto, caso_negocio
    FROM public.leads_scrap
    WHERE estado IN ('seguimiento_d2', 'seguimiento_d5')
    AND ultimo_contacto < %s
    AND ultimo_contacto > %s
    AND respuesta_recibida IS NULL
    """, (hoy - timedelta(days=10), hoy - timedelta(days=11)))

    for lead in cur.fetchall():
        if validar_telefono_marroqui(lead["telefono"]):
            d10_enviados += 1
            detalle.append({
                "lead_id": lead["id"],
                "nombre": lead["nombre_negocio"],
                "tipo": "D10",
                "telefono": lead["telefono"],
                "caso": lead["caso_negocio"]
            })
            cur.execute("""
            UPDATE public.leads_scrap SET estado='descartado', updated_at=NOW() WHERE id=%s
            """, (lead["id"],))

    conn.commit()
    cur.close()
    conn.close()

    return SeguimientoResponse(
        d2_enviados=d2_enviados,
        d5_enviados=d5_enviados,
        d10_enviados=d10_enviados,
        total_enviados=d2_enviados + d5_enviados + d10_enviados,
        detalle=detalle
    )


@router.get("/stats/resumen")
def resumen_leads():
    """Dashboard rápido con distribución por Caso."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE estado = 'nuevo') as nuevos,
        COUNT(*) FILTER (WHERE estado = 'contactado') as contactados,
        COUNT(*) FILTER (WHERE estado = 'respondio') as respondieron,
        COUNT(*) FILTER (WHERE estado = 'interesado') as interesados,
        COUNT(*) FILTER (WHERE estado = 'cerrado') as cerrados,
        COUNT(*) FILTER (WHERE estado = 'descartado') as descartados,
        COUNT(*) FILTER (WHERE score >= 80) as hot,
        COUNT(*) FILTER (WHERE score >= 60 AND score < 80) as warm,
        COUNT(*) FILTER (WHERE score >= 40 AND score < 60) as cold,
        COUNT(*) FILTER (WHERE score < 40) as ice,
        COUNT(*) FILTER (WHERE tiene_web = FALSE) as sin_web,
        COUNT(*) FILTER (WHERE telefono IS NOT NULL) as con_telefono,
        ROUND(AVG(score), 1) as score_promedio,
        -- Por caso
        COUNT(*) FILTER (WHERE caso_negocio = 'A') as caso_a,
        COUNT(*) FILTER (WHERE caso_negocio = 'B') as caso_b,
        COUNT(*) FILTER (WHERE caso_negocio = 'C') as caso_c,
        COUNT(*) FILTER (WHERE caso_negocio = 'D') as caso_d,
        COUNT(*) FILTER (WHERE caso_negocio = 'E') as caso_e,
        COUNT(*) FILTER (WHERE caso_negocio = 'F') as caso_f,
        COUNT(*) FILTER (WHERE caso_negocio = 'G') as caso_g
    FROM public.leads_scrap
    """)

    row = cur.fetchone()
    cur.close()
    conn.close()

    return dict(row)
