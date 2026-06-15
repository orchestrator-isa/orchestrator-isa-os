#!/usr/bin/env python3
"""
leads_bot_handler_v3.py - Bot con Estrategia Francotirador (Casos A-G)

Cambios V3:
- Muestra Caso A-G, estrategia, pack y precio recomendado
- Mensajes personalizados por caso (de scrap.txt)
- Comando /caso para filtrar por clasificación
- Comando /estrategia para ver resumen por caso
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

ADMIN_PHONE = os.getenv("ADMIN_PHONE", "+212XXXXXXXXX")
DATABASE_URL = os.getenv("DATABASE_URL")

# ── MENSAJES DEL BOT ─────────────────────────────────────────

MENSAJES_BOT = {
    "es": {
        "no_leads": "📭 No hay leads nuevos disponibles. ¡Buen trabajo! 🎉",
        "no_telefono": "❌ Este lead no tiene teléfono válido. No se puede enviar mensaje.",
        "telefono_invalido": "❌ Teléfono inválido: {telefono}",
        "enviado": "✅ Mensaje enviado a {nombre} ({telefono}).\n📊 Score: {score} | 🎲 Caso: {caso} | 💰 Pack: {pack} ({precio} MAD)",
        "envio_error": "❌ Error enviando a {nombre}: {error}",
        "cancelado": "❌ Cancelado. El lead sigue disponible.",
        "stats": """📊 *Resumen de Leads*
Total: {total}
🔥 Hot: {hot} | 🌡️ Warm: {warm} | ❄️ Cold: {cold} | 🧊 Ice: {ice}
📞 Nuevos: {nuevos} | Contactados: {contactados}
💰 Cerrados: {cerrados} | Descartados: {descartados}

🎲 *Por Caso:*
A-Fantasma: {caso_a} | B-Cojo: {caso_b} | C-Desactualizado: {caso_c}
D-WA Caótico: {caso_d} | E-Mina Oro: {caso_e} | F-Semi-Digital: {caso_f}
G-Inalcanzable: {caso_g}""",
        "seguimiento_resultado": """📬 *Seguimiento Automático*
D2: {d2} | D5: {d5} | D10: {d10}
Total: {total}

{detalle}""",
        "estrategia_resumen": """🎯 *Estrategia por Caso*

*Caso A - Fantasma* (sin web, buen rating)
→ Pack Presencia (250 MAD)
→ Ángulo: "No tener web = no tener carta"

*Caso B - Influencer Cojo* (sin web, rating bajo)
→ Pack Completo (1,200 MAD)
→ Ángulo: "Necesita todo: presencia + reputación"

*Caso C - Desactualizado* (web + rating bajo)
→ Pack Completo (1,200 MAD)
→ Ángulo: "Garantía de 30 días o devolución"

*Caso D - WhatsApp Caótico* (web + WA roto)
→ Pack WhatsApp Pro (400 MAD)
→ Ángulo: "Web bonita pero puerta cerrada"

*Caso E - Mina de Oro* (web + buen rating + muchas reviews)
→ Pack Automatización (800 MAD)
→ Ángulo: "Ya tienen clientes, falta sistema"

*Caso F - Semi-Digital* (web + poco tráfico)
→ Pack Presencia Plus (400 MAD)
→ Ángulo: "Tienen estructura, falta visibilidad"

*Caso G - Inalcanzable* (sin teléfono)
→ Ninguno (0 MAD)
→ Acción: Buscar contacto alternativo""",
        "help": """🤖 *Comandos de Leads ISA V3*

*lead* / *siguiente* - Ver siguiente lead prioritario
*si* - Confirmar envío al lead mostrado
*no* - Cancelar y pasar al siguiente
*lead stats* - Resumen del pipeline
*lead buscar <nombre>* - Buscar lead
*lead info <id>* - Info detallada (incluye caso)
*contactar <id>* - Marcar como contactado manual
*seguimiento* - Ejecutar seguimiento D2/D5/D10
*caso <A-G>* - Ver leads de un caso específico
*estrategia* - Ver resumen de estrategias
*help* - Ver este mensaje

💡 El bot detecta automáticamente el Caso A-G
del lead y genera el mensaje perfecto.""",
    }
}


# ── DB HELPERS ───────────────────────────────────────────────

def get_db_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def get_next_lead() -> Optional[Dict[str, Any]]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, nombre_negocio, telefono, email, tiene_web, website_url,
           rating, num_reviews, score, score_detalle, caso_negocio, notas_scraping,
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
    return dict(row) if row else None


def get_lead_by_id(lead_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM public.leads_scrap WHERE id = %s
    """, (lead_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_leads_by_caso(caso: str) -> List[Dict[str, Any]]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, nombre_negocio, telefono, score, estado, caso_negocio,
           estrategia_venta, pack_recomendado, precio_recomendado
    FROM public.leads_scrap
    WHERE caso_negocio = %s AND estado = 'nuevo'
    ORDER BY score DESC
    LIMIT 10
    """, (caso,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def marcar_contactado_db(lead_id: int, mensaje: str):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
    UPDATE public.leads_scrap
    SET estado = 'contactado',
        ultimo_contacto = NOW(),
        mensaje_enviado = %s,
        updated_at = NOW()
    WHERE id = %s
    """, (mensaje, lead_id))
    conn.commit()
    cur.close()
    conn.close()


def get_lead_stats() -> Dict[str, Any]:
    conn = get_db_conn()
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


# ── VALIDACIÓN ───────────────────────────────────────────────

def validar_telefono_marroqui(phone: str) -> bool:
    if not phone:
        return False
    if not phone.startswith("+212"):
        return False
    digits = phone.replace("+", "").replace(" ", "")
    return len(digits) == 12 and digits[3:].isdigit()


# ── MENSAJES POR CASO ────────────────────────────────────────

MENSAJES_CASO = {
    "es": {
        "A": {  # Fantasma
            "presentacion": "Soy Isa. Veo que {nombre} tiene buenas reseñas pero no aparece en Google cuando alguien busca. El 40% de las ventas locales se pierden por no aparecer en Google Maps. Para un restaurante, no tener web hoy es como no tener carta. Creamos su presencia digital en 24 horas desde solo 250 MAD.",
            "problema": "El 40% de las ventas locales se pierden por no aparecer en Google Maps. {nombre} tiene buen producto pero es invisible digitalmente. Cada día que pasa sin web son clientes que van a la competencia.",
            "solucion": "En 24 horas creamos su ficha de Google Maps optimizada y su presencia digital básica. Incluye dirección, horarios, fotos y teléfono visible. Desde solo 250 MAD.",
            "precios": "Pack Presencia: 250 MAD. Incluye Google Maps optimizado, ficha básica y dirección web. Sin mantenimiento mensual.",
        },
        "B": {  # Influencer Cojo
            "presentacion": "Soy Isa. Veo que {nombre} necesita trabajo completo: sin web y con reputación por mejorar. Mi pack completo rehace su contenido, automatiza respuestas y le devuelvo su dinero si no ve resultados. Desde 1,200 MAD.",
            "problema": "Sin presencia digital y con reputación dañada, {nombre} está perdiendo clientes por dos frentes. La gente no los encuentra Y cuando los encuentra no confía.",
            "solucion": "Pack Completo: web profesional, Google Maps optimizado, WhatsApp Business con catálogo, y gestión de reputación. Garantía de 30 días o devolución. 1,200 MAD.",
            "precios": "Pack Completo: 1,200 MAD. Todo incluido: web, Google Maps, WhatsApp Pro, gestión de reputación. Mantenimiento mensual incluido.",
        },
        "C": {  # Desactualizado
            "presentacion": "Soy Isa. Veo que {nombre} tiene web pero las reseñas muestran que la experiencia digital no refleja la realidad. Ofrezco un pack completo para rehacer su contenido, automatizar respuestas y mejorar su imagen. Garantía por escrito: si en 30 días no nota más confianza y ventas, le devuelvo el dinero. 1,200 MAD.",
            "problema": "{nombre} tiene web, pero su rating de {rating} muestra que no genera confianza. Las reseñas negativas están ahuyentando clientes. Su web no está trabajando para usted, está trabajando en contra.",
            "solucion": "Rehacemos su contenido digital, optimizamos Google Maps, conectamos WhatsApp Business con respuestas automáticas, y gestionamos su reputación. Garantía de 30 días. 1,200 MAD.",
            "precios": "Pack Completo: 1,200 MAD. Rehace su imagen digital completa. Incluye garantía de 30 días.",
        },
        "D": {  # WhatsApp Caótico
            "presentacion": "Soy Isa. Noté que tienen una web muy bonita, pero el link de WhatsApp no funciona. El 67% de los clientes abandonan si no reciben respuesta en 5 minutos. Tener la web con el WhatsApp roto es como tener la puerta del local cerrada. En 48 horas les conecto el Pack WhatsApp Pro (400 MAD) para que no pierdan ni un pedido.",
            "problema": "El 67% de los clientes abandonan si no reciben respuesta en 5 minutos. {nombre} tiene la web pero su canal principal de comunicación está roto. Está perdiendo dinero ahora mismo.",
            "solucion": "En 48 horas solucionamos su WhatsApp Business: catálogo de productos, respuestas automáticas, y conexión correcta con su web. Pack WhatsApp Pro: 400 MAD.",
            "precios": "Pack WhatsApp Pro: 400 MAD. Catálogo, respuestas automáticas, conexión web. Mantenimiento mensual incluido.",
        },
        "E": {  # Mina de Oro
            "presentacion": "Soy Isa de Orchestrator ISA. Veo que {nombre} es muy popular en Google Maps (¡{reviews} reseñas!). Mi sistema no es para que los encuentren (ya los encuentran), es para automatizar las reservas y pedidos que ya reciben y que su WhatsApp no colapse. Puedo ayudarles a gestionar ese volumen desde 800 MAD. ¿Tienen 5 minutos para una demo?",
            "problema": "{nombre} ya tiene clientes ({reviews} reseñas), pero está perdiendo eficiencia. Las reservas se pierden, el WhatsApp colapsa, y no pueden atender todo el volumen que ya tienen.",
            "solucion": "Automatizamos sus reservas, pedidos y respuestas. WhatsApp Business con IA, catálogo dinámico, y sistema de gestión. Usted se enfoca en cocinar, nosotros en digitalizar. 800 MAD.",
            "precios": "Pack Automatización: 800 MAD. Sistema completo de gestión. Ideal para alto volumen.",
        },
        "F": {  # Semi-Digital
            "presentacion": "Soy Isa. Veo que {nombre} tiene web pero poco tráfico. Tienen la estructura pero les falta visibilidad. Mi Pack Presencia Plus les da el empujón que necesitan: SEO local, Google Maps optimizado y campaña básica. 400 MAD.",
            "problema": "{nombre} tiene web pero poca gente la encuentra. Tienen la estructura pero no la visibilidad. Es como tener un local en una calle sin señalización.",
            "solucion": "Pack Presencia Plus: optimización SEO local, Google Maps premium, y estrategia de visibilidad básica. 400 MAD.",
            "precios": "Pack Presencia Plus: 400 MAD. SEO local + Google Maps premium + visibilidad.",
        },
        "G": {  # Inalcanzable
            "presentacion": "Lamentablemente no podemos contactar a {nombre} porque no tienen teléfono registrado. Recomendamos buscar su contacto por otros medios o visitar el local directamente.",
            "problema": "Sin teléfono no podemos ayudarles por WhatsApp. Necesitamos un canal de contacto.",
            "solucion": "Buscar teléfono alternativo o contactar presencialmente.",
            "precios": "N/A",
        },
    }
}

MENSAJES_GENERICOS = {
    "es": {
        "garantia": "Le doy mi garantía por escrito: si en 30 días no ve el sistema funcionando, le devuelvo el 100% de su dinero.",
        "cierre": "Perfecto. Para comenzar hoy solo necesito el 50% de anticipo y el resto al entregar en 48 horas. ¿Le parece bien?",
        "seguimiento_d2": "Hola {nombre}, solo le escribo para saber si tuvo chance de revisar la propuesta. Quedo atento por si tiene alguna duda. ¡Saludos!",
        "seguimiento_d5": "Hola {nombre}, le escribo de nuevo porque sé que está ocupado. La oferta sigue vigente. ¿Podemos agendar 5 minutos?",
        "seguimiento_d10": "Hola {nombre}, último mensaje. No quiero ser pesado, pero sé que esta propuesta puede ayudarle mucho. Si cambia de opinión, aquí estoy. ¡Éxito!",
    }
}


def generar_mensaje_caso(lead: dict, idioma: str, tipo: str) -> str:
    """Genera mensaje según Caso A-G."""
    nombre = lead["nombre_negocio"]
    caso = lead.get("caso_negocio", "A")
    rating = lead.get("rating")
    reviews = lead.get("num_reviews", 0)

    mensajes_idioma = MENSAJES_CASO.get(idioma, MENSAJES_CASO["es"])
    mensajes_caso = mensajes_idioma.get(caso, mensajes_idioma.get("A", {}))

    base = mensajes_caso.get(tipo)
    if not base:
        genericos = MENSAJES_GENERICOS.get(idioma, MENSAJES_GENERICOS["es"])
        base = genericos.get(tipo, "")

    if idioma == "es":
        saludo = f"Hola {nombre}! 👋\n\n"
    else:
        saludo = f"Hola {nombre}! 👋\n\n"

    mensaje = saludo + base.format(
        nombre=nombre,
        rating=rating or "N/A",
        reviews=reviews
    )

    return mensaje


def get_temperatura(score: int) -> str:
    if score >= 80:
        return "🔥 HOT"
    elif score >= 60:
        return "🌡️ WARM"
    elif score >= 40:
        return "❄️ COLD"
    else:
        return "🧊 ICE"


# ── WHATSAPP API ─────────────────────────────────────────────

class WhatsAppAPI:
    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.base_url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"

    def send_message(self, to_phone: str, message: str) -> dict:
        import requests
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"body": message}
        }
        response = requests.post(self.base_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


# ── LEAD BOT HANDLER ─────────────────────────────────────────

class LeadBotHandler:
    def __init__(self, wa_api: WhatsAppAPI, admin_phone: str):
        self.wa_api = wa_api
        self.admin_phone = admin_phone
        self.pending_lead: Dict[str, int] = {}
        self.pending_mensaje: Dict[str, str] = {}

    def handle_message(self, from_phone: str, message: str) -> Optional[str]:
        msg = message.strip().lower()

        if from_phone != self.admin_phone:
            return None

        if msg in ["help", "ayuda", "?"]:
            return MENSAJES_BOT["es"]["help"]

        if msg in ["lead", "siguiente", "next", "próximo", "proximo"]:
            return self.cmd_siguiente_lead(from_phone)

        if msg in ["lead stats", "leads stats", "estadisticas", "estadísticas"]:
            return self.cmd_stats()

        if msg.startswith("lead buscar ") or msg.startswith("buscar lead "):
            nombre = message.split("buscar ", 1)[1].strip()
            return self.cmd_buscar(nombre)

        if msg.startswith("lead info "):
            try:
                lead_id = int(msg.split("info ")[1].strip())
                return self.cmd_info(lead_id)
            except ValueError:
                return "❌ ID inválido. Usa: lead info 123"

        if msg.startswith("caso "):
            caso = msg.split("caso ")[1].strip().upper()
            if caso in ["A", "B", "C", "D", "E", "F", "G"]:
                return self.cmd_caso(caso)
            return "❌ Caso inválido. Usa: caso A, caso B, etc."

        if msg == "estrategia":
            return MENSAJES_BOT["es"]["estrategia_resumen"]

        if msg in ["si", "sí", "yes", "oui", "iyeh", "نعم"]:
            return self.cmd_confirmar(from_phone)

        if msg in ["no", "non", "la", "لا"]:
            return self.cmd_cancelar(from_phone)

        if msg.startswith("contactar "):
            try:
                lead_id = int(msg.split("contactar ")[1].strip())
                return self.cmd_contactar_manual(lead_id)
            except ValueError:
                return "❌ ID inválido. Usa: contactar 123"

        if msg in ["seguimiento", "followup", "seguimiento automatico"]:
            return self.cmd_seguimiento()

        return None

    def cmd_siguiente_lead(self, from_phone: str) -> str:
        lead = get_next_lead()

        if not lead:
            return MENSAJES_BOT["es"]["no_leads"]

        self.pending_lead[from_phone] = lead["id"]

        idioma = "es"
        mensaje = generar_mensaje_caso(lead, idioma, "presentacion")
        self.pending_mensaje[from_phone] = mensaje

        score = lead["score"]
        temperatura = get_temperatura(score)
        caso = lead.get("caso_negocio", "A")
        pack = lead.get("pack_recomendado", "N/A")
        precio = lead.get("precio_recomendado", 0)

        # Descripción del caso
        caso_desc = {
            "A": "🎭 Fantasma (sin web, buen rating)",
            "B": "👤 Influencer Cojo (sin web, rating bajo)",
            "C": "📉 Desactualizado (web + rating bajo)",
            "D": "💔 WhatsApp Caótico (web + WA roto)",
            "E": "⛏️ Mina de Oro (web + buen rating + reviews)",
            "F": "🔧 Semi-Digital (web + poco tráfico)",
            "G": "🚫 Inalcanzable (sin teléfono)",
        }.get(caso, f"Caso {caso}")

        recs = []
        if score >= 80:
            recs.append("🎯 Contactar HOY")
        elif score >= 60:
            recs.append("📞 Contactar esta semana")
        if not lead["tiene_web"]:
            recs.append("💰 Sin web = oportunidad")
        if lead["rating"] and lead["rating"] < 4.0:
            recs.append("⭐ Rating bajo")

        telefono = lead.get("telefono")
        telefono_valido = validar_telefono_marroqui(telefono) if telefono else False

        preview = f"""
📋 *{lead['nombre_negocio']}* | {temperatura} | Score: {score}/100
🎲 *{caso_desc}*
💰 Pack recomendado: *{pack}* ({precio} MAD)
📞 {telefono or 'N/A'} {"✅ Válido" if telefono_valido else "❌ Inválido"}
📍 {lead['direccion'] or 'N/A'}
⭐ Rating: {lead['rating'] or 'N/A'} | 📝 Reviews: {lead['num_reviews']}
🌐 Web: {"✅ Sí" if lead['tiene_web'] else "❌ No"}

💬 *Mensaje sugerido:*
{mensaje}

🎯 *Recomendación:* {" | ".join(recs)}

{"✅ Teléfono válido. ¿Enviar mensaje? Responde: SI o NO" if telefono_valido else "❌ Teléfono inválido. No se puede enviar. Escribe 'lead' para el siguiente."}
        """

        return preview.strip()

    def cmd_confirmar(self, from_phone: str) -> str:
        lead_id = self.pending_lead.get(from_phone)
        mensaje = self.pending_mensaje.get(from_phone)

        if not lead_id:
            return "❌ No hay lead pendiente. Escribe 'lead' para ver el siguiente."

        lead = get_lead_by_id(lead_id)
        if not lead:
            del self.pending_lead[from_phone]
            del self.pending_mensaje[from_phone]
            return "❌ Lead no encontrado."

        telefono = lead.get("telefono")
        if not telefono:
            return MENSAJES_BOT["es"]["no_telefono"]

        if not validar_telefono_marroqui(telefono):
            return MENSAJES_BOT["es"]["telefono_invalido"].format(telefono=telefono)

        try:
            self.wa_api.send_message(telefono, mensaje)
            marcar_contactado_db(lead_id, mensaje)

            del self.pending_lead[from_phone]
            del self.pending_mensaje[from_phone]

            return MENSAJES_BOT["es"]["enviado"].format(
                nombre=lead["nombre_negocio"],
                telefono=telefono,
                score=lead["score"],
                caso=lead.get("caso_negocio", "A"),
                pack=lead.get("pack_recomendado", "N/A"),
                precio=lead.get("precio_recomendado", 0)
            )
        except Exception as e:
            return MENSAJES_BOT["es"]["envio_error"].format(
                nombre=lead["nombre_negocio"],
                error=str(e)
            )

    def cmd_cancelar(self, from_phone: str) -> str:
        if from_phone in self.pending_lead:
            del self.pending_lead[from_phone]
        if from_phone in self.pending_mensaje:
            del self.pending_mensaje[from_phone]
        return MENSAJES_BOT["es"]["cancelado"]

    def cmd_stats(self) -> str:
        stats = get_lead_stats()
        return MENSAJES_BOT["es"]["stats"].format(**stats)

    def cmd_caso(self, caso: str) -> str:
        """Muestra leads de un caso específico."""
        leads = get_leads_by_caso(caso)
        if not leads:
            return f"🎲 No hay leads nuevos del Caso {caso}."

        caso_nombres = {
            "A": "Fantasma", "B": "Influencer Cojo", "C": "Desactualizado",
            "D": "WhatsApp Caótico", "E": "Mina de Oro", "F": "Semi-Digital", "G": "Inalcanzable"
        }

        result = f"🎲 *Leads Caso {caso} - {caso_nombres.get(caso, '')}*\n\n"
        for l in leads:
            result += f"ID:{l['id']} | {l['nombre_negocio'][:25]} | Score:{l['score']} | {l['pack_recomendado']} ({l['precio_recomendado']} MAD)\n"

        return result

    def cmd_buscar(self, nombre: str) -> str:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
        SELECT id, nombre_negocio, telefono, score, estado, caso_negocio, pack_recomendado
        FROM public.leads_scrap
        WHERE nombre_negocio ILIKE %s
        ORDER BY score DESC
        LIMIT 5
        """, (f"%{nombre}%",))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return f"🔍 No se encontraron leads con '{nombre}'"

        result = f"🔍 Resultados para '{nombre}':\n\n"
        for r in rows:
            result += f"ID:{r['id']} | {r['nombre_negocio'][:25]} | Score:{r['score']} | Caso:{r['caso_negocio']} | {r['pack_recomendado']}\n"

        return result

    def cmd_info(self, lead_id: int) -> str:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return f"❌ Lead {lead_id} no encontrado"

        score_detalle = json.loads(lead.get("score_detalle", "{}"))
        telefono = lead.get("telefono")
        telefono_valido = validar_telefono_marroqui(telefono) if telefono else False

        caso_nombres = {
            "A": "🎭 Fantasma", "B": "👤 Influencer Cojo", "C": "📉 Desactualizado",
            "D": "💔 WhatsApp Caótico", "E": "⛏️ Mina de Oro", "F": "🔧 Semi-Digital", "G": "🚫 Inalcanzable"
        }

        info = f"""
📋 *Lead #{lead['id']}: {lead['nombre_negocio']}*

🎲 *Caso: {caso_nombres.get(lead.get('caso_negocio'), 'N/A')}*
💰 *Pack: {lead.get('pack_recomendado', 'N/A')}* ({lead.get('precio_recomendado', 0)} MAD)
📈 *Estrategia: {lead.get('estrategia_venta', 'N/A')}*

📞 Tel: {telefono or 'N/A'} {"✅" if telefono_valido else "❌"}
📧 Email: {lead['email'] or 'N/A'}
📍 {lead['direccion'] or 'N/A'}
⭐ Rating: {lead['rating']} | 📝 Reviews: {lead['num_reviews']}
🌐 Web: {'✅ ' + lead['website_url'] if lead['tiene_web'] else '❌ No'}
📊 Score: {lead['score']}/100 | 🌡️ {get_temperatura(lead['score'])}
📈 Estado: {lead['estado']}
🏷️ Categoría: {lead['categoria']}

📝 *Notas: {lead.get('notas_scraping', 'N/A')}*

🔍 *Score breakdown:*
"""
        for k, v in score_detalle.items():
            if k != "score_total":
                info += f"  • {k}: +{v} pts\n"

        info += f"\n🎯 *Total: {lead['score']} pts*"

        if lead.get('google_maps_url'):
            info += f"\n\n🗺️ {lead['google_maps_url']}"

        return info

    def cmd_contactar_manual(self, lead_id: int) -> str:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return f"❌ Lead {lead_id} no encontrado"

        marcar_contactado_db(lead_id, "Contactado manualmente por admin")
        return f"✅ Lead #{lead_id} ({lead['nombre_negocio']}) marcado como contactado."

    def cmd_seguimiento(self) -> str:
        conn = get_db_conn()
        cur = conn.cursor()
        hoy = datetime.now()

        detalle_envios = []
        d2_count = d5_count = d10_count = 0

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
                try:
                    mensaje = MENSAJES_GENERICOS["es"]["seguimiento_d2"].format(nombre=lead["nombre_negocio"])
                    self.wa_api.send_message(lead["telefono"], mensaje)
                    d2_count += 1
                    detalle_envios.append(f"D2: {lead['nombre_negocio']} (Caso {lead['caso_negocio']})")
                    cur.execute("UPDATE public.leads_scrap SET estado='seguimiento_d2', updated_at=NOW() WHERE id=%s", (lead["id"],))
                except Exception as e:
                    detalle_envios.append(f"❌ D2 falló {lead['nombre_negocio']}: {e}")

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
                try:
                    mensaje = MENSAJES_GENERICOS["es"]["seguimiento_d5"].format(nombre=lead["nombre_negocio"])
                    self.wa_api.send_message(lead["telefono"], mensaje)
                    d5_count += 1
                    detalle_envios.append(f"D5: {lead['nombre_negocio']} (Caso {lead['caso_negocio']})")
                    cur.execute("UPDATE public.leads_scrap SET estado='seguimiento_d5', updated_at=NOW() WHERE id=%s", (lead["id"],))
                except Exception as e:
                    detalle_envios.append(f"❌ D5 falló {lead['nombre_negocio']}: {e}")

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
                try:
                    mensaje = MENSAJES_GENERICOS["es"]["seguimiento_d10"].format(nombre=lead["nombre_negocio"])
                    self.wa_api.send_message(lead["telefono"], mensaje)
                    d10_count += 1
                    detalle_envios.append(f"D10: {lead['nombre_negocio']} (Caso {lead['caso_negocio']})")
                    cur.execute("UPDATE public.leads_scrap SET estado='descartado', updated_at=NOW() WHERE id=%s", (lead["id"],))
                except Exception as e:
                    detalle_envios.append(f"❌ D10 falló {lead['nombre_negocio']}: {e}")

        conn.commit()
        cur.close()
        conn.close()

        detalle_str = "\n".join(detalle_envios[:10])
        if len(detalle_envios) > 10:
            detalle_str += f"\n... y {len(detalle_envios)-10} más"

        return MENSAJES_BOT["es"]["seguimiento_resultado"].format(
            d2=d2_count,
            d5=d5_count,
            d10=d10_count,
            total=d2_count+d5_count+d10_count,
            detalle=detalle_str or "Ningún seguimiento enviado"
        )


# ── INTEGRACIÓN ──────────────────────────────────────────────
"""
En tu webhook:

    from leads_bot_handler_v3 import LeadBotHandler, WhatsAppAPI

    wa_api = WhatsAppAPI(
        phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
        access_token=os.getenv("WHATSAPP_ACCESS_TOKEN")
    )
    lead_handler = LeadBotHandler(wa_api, ADMIN_PHONE="+212XXXXXXXXX")

    def handle_incoming_message(from_phone: str, message_text: str):
        response = lead_handler.handle_message(from_phone, message_text)
        if response:
            send_whatsapp_message(from_phone, response)
            return
        # ... flujo normal
"""

if __name__ == "__main__":
    print("✅ LeadBotHandler V3 con Estrategia Francotirador listo.")
    print("   Comandos: lead, si, no, caso A-G, estrategia, lead stats, seguimiento, help")
