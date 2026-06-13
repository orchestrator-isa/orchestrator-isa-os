#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orquestrator ISA ChatCommerce v13.1
FastAPI + SQLAlchemy + Neon DB + WhatsApp Cloud API
Marruecos - ES/FR/AR(Darija) Multilingual Bot
"""

import os, sys, json, hmac, hashlib, asyncio, logging, re, random, string, time, uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from collections import defaultdict
from decimal import Decimal
from enum import Enum as PyEnum

from fastapi import FastAPI, Request, Response, HTTPException, Depends, BackgroundTasks, APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum, BigInteger, Numeric, UniqueConstraint, Index, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship, joinedload
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func

from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings
from api.cotizar import router as cotizar_router
import aiohttp

app = FastAPI()
app.include_router(cotizar_router, prefix="/api")

# ==========================================
# CONFIGURACION
# ==========================================

class Settings(BaseSettings):
    APP_NAME: str = "ISA ChatCommerce Orquestrator"
    APP_VERSION: str = "13.1.0"
    DEBUG: bool = False
    DATABASE_URL: str = "postgresql://user:pass@neon-host/db"
    WHATSAPP_API_VERSION: str = "v18.0"
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "isa_webhook_verify_2024"
    WHATSAPP_APP_SECRET: str = ""
    WEBHOOK_BASE_URL: str = "https://isa-orquestrator.onrender.com"
    ADMIN_API_KEY: str = ""
    ADMIN_JWT_SECRET: str = ""
    BUSINESS_NAME: str = "Cafe Al Hizam Al Akhdar"
    BUSINESS_PHONE: str = "+212600000000"
    BUSINESS_CURRENCY: str = "MAD"
    RATE_LIMIT_MESSAGES_PER_MINUTE: int = 30
    RATE_LIMIT_MESSAGES_PER_HOUR: int = 200
    RESERVA_ANTELACION_MINIMA: int = 30
    RESERVA_DIAS_MAXIMO: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ISA.Orquestrator")

# ==========================================
# DATABASE MODELS
# ==========================================

Base = declarative_base()

class EstadoPedido(PyEnum):
    PENDIENTE = "pendiente"; CONFIRMADO = "confirmado"; EN_PREPARACION = "en_preparacion"
    LISTO = "listo"; EN_CAMINO = "en_camino"; ENTREGADO = "entregado"; CANCELADO = "cancelado"

class EstadoPago(PyEnum):
    PENDIENTE = "pendiente"; PROCESANDO = "procesando"; COMPLETADO = "completado"
    FALLIDO = "fallido"; REEMBOLSADO = "reembolsado"

class EstadoReserva(PyEnum):
    PENDIENTE = "pendiente"; FASE_DATOS = "fase_datos"; HORA_MESA = "hora_mesa"
    CONFIRMADA = "confirmada"; CANCELADA = "cancelada"; COMPLETADA = "completada"

class Idioma(PyEnum):
    ES = "es"; FR = "fr"; AR = "ar"; EN = "en"

class TipoMensaje(PyEnum):
    TEXTO = "texto"; IMAGEN = "imagen"; UBICACION = "ubicacion"
    BOTON = "boton"; INTERACTIVO = "interactivo"; DOCUMENTO = "documento"

class TipoCliente(PyEnum):
    NUEVO = "nuevo"; RECURRENTE = "recurrente"; VIP = "vip"

class Mensaje(Base):
    __tablename__ = "mensajes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wa_message_id = Column(String(255), unique=True, nullable=True)
    telefono_cliente = Column(String(20), nullable=False, index=True)
    tipo = Column(Enum(TipoMensaje), nullable=False)
    contenido = Column(Text, nullable=False)
    direccion = Column(String(10), nullable=False)
    metadata_json = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    __table_args__ = (
        Index("idx_mensajes_telefono_created", "telefono_cliente", "created_at"),
        Index("idx_mensajes_trimestre", text("DATE_TRUNC('quarter', created_at)"), "telefono_cliente"),
    )

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telefono = Column(String(20), unique=True, nullable=False, index=True)
    nombre = Column(String(100), nullable=True)
    apellido = Column(String(100), nullable=True)
    direccion = Column(Text, nullable=True)
    ubicacion_lat = Column(Numeric(10, 8), nullable=True)
    ubicacion_lng = Column(Numeric(11, 8), nullable=True)
    idioma_preferido = Column(Enum(Idioma), default=Idioma.ES)
    tipo = Column(Enum(TipoCliente), default=TipoCliente.NUEVO)
    visitas_count = Column(Integer, default=0)
    total_gastado = Column(Numeric(12, 2), default=Decimal("0.00"))
    ultima_visita = Column(DateTime(timezone=True), nullable=True)
    carrito_activo = Column(JSONB, default={})
    estado_flujo = Column(String(50), default="inicio")
    estado_flujo_data = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    pedidos = relationship("Pedido", back_populates="cliente", lazy="dynamic")
    reservaciones = relationship("Reservacion", back_populates="cliente", lazy="dynamic")

class Categoria(Base):
    __tablename__ = "categorias"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre_es = Column(String(100), nullable=False)
    nombre_fr = Column(String(100), nullable=True)
    nombre_ar = Column(String(100), nullable=True)
    orden = Column(Integer, default=0)
    activa = Column(Boolean, default=True)
    emoji = Column(String(10), nullable=True)
    productos = relationship("Producto", back_populates="categoria", lazy="dynamic")

class Producto(Base):
    __tablename__ = "productos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categoria_id = Column(UUID(as_uuid=True), ForeignKey("categorias.id"), nullable=False)
    nombre_es = Column(String(100), nullable=False)
    nombre_fr = Column(String(100), nullable=True)
    nombre_ar = Column(String(100), nullable=True)
    descripcion_es = Column(Text, nullable=True)
    descripcion_fr = Column(Text, nullable=True)
    descripcion_ar = Column(Text, nullable=True)
    precio = Column(Numeric(10, 2), nullable=False)
    imagen_url = Column(Text, nullable=True)
    disponible = Column(Boolean, default=True)
    es_destacado = Column(Boolean, default=False)
    opciones_json = Column(JSONB, default={})
    alergenos = Column(ARRAY(String), default=[])
    tiempo_preparacion_min = Column(Integer, default=15)
    stock_ilimitado = Column(Boolean, default=True)
    stock_actual = Column(Integer, nullable=True)
    orden = Column(Integer, default=0)
    categoria = relationship("Categoria", back_populates="productos")
    items_pedido = relationship("ItemPedido", back_populates="producto", lazy="dynamic")

class Pedido(Base):
    __tablename__ = "pedidos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo_pedido = Column(String(20), unique=True, nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)
    estado = Column(Enum(EstadoPedido), default=EstadoPedido.PENDIENTE)
    tipo_entrega = Column(String(20), default="delivery")
    direccion_entrega = Column(Text, nullable=True)
    lat_entrega = Column(Numeric(10, 8), nullable=True)
    lng_entrega = Column(Numeric(11, 8), nullable=True)
    notas = Column(Text, nullable=True)
    subtotal = Column(Numeric(12, 2), default=Decimal("0.00"))
    costo_envio = Column(Numeric(10, 2), default=Decimal("0.00"))
    propina = Column(Numeric(10, 2), default=Decimal("0.00"))
    descuento = Column(Numeric(10, 2), default=Decimal("0.00"))
    total = Column(Numeric(12, 2), default=Decimal("0.00"))
    estado_pago = Column(Enum(EstadoPago), default=EstadoPago.PENDIENTE)
    metodo_pago = Column(String(50), nullable=True)
    referencia_pago = Column(String(100), nullable=True)
    pagado_at = Column(DateTime(timezone=True), nullable=True)
    confirmado_at = Column(DateTime(timezone=True), nullable=True)
    listo_at = Column(DateTime(timezone=True), nullable=True)
    entregado_at = Column(DateTime(timezone=True), nullable=True)
    cancelado_at = Column(DateTime(timezone=True), nullable=True)
    motivo_cancelacion = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    cliente = relationship("Cliente", back_populates="pedidos")
    items = relationship("ItemPedido", back_populates="pedido", lazy="dynamic")

class ItemPedido(Base):
    __tablename__ = "items_pedido"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pedido_id = Column(UUID(as_uuid=True), ForeignKey("pedidos.id"), nullable=False)
    producto_id = Column(UUID(as_uuid=True), ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, default=1)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    opciones_seleccionadas = Column(JSONB, default={})
    notas_item = Column(Text, nullable=True)
    subtotal = Column(Numeric(12, 2), nullable=False)
    pedido = relationship("Pedido", back_populates="items")
    producto = relationship("Producto", back_populates="items_pedido")

class Reservacion(Base):
    __tablename__ = "reservaciones"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo_reserva = Column(String(20), unique=True, nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)
    estado = Column(Enum(EstadoReserva), default=EstadoReserva.PENDIENTE)
    nombre_reserva = Column(String(100), nullable=True)
    telefono_reserva = Column(String(20), nullable=True)
    num_personas = Column(Integer, default=2)
    ocasion = Column(String(50), nullable=True)
    hora_reserva = Column(DateTime(timezone=True), nullable=True)
    mesa_asignada = Column(String(20), nullable=True)
    zona = Column(String(50), nullable=True)
    ai_confirmada = Column(Boolean, default=False)
    ai_confirmada_at = Column(DateTime(timezone=True), nullable=True)
    ai_motivo_rechazo = Column(Text, nullable=True)
    confirmada_manual = Column(Boolean, default=False)
    confirmada_manual_por = Column(String(100), nullable=True)
    confirmada_manual_at = Column(DateTime(timezone=True), nullable=True)
    notas = Column(Text, nullable=True)
    recordatorio_enviado = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    cliente = relationship("Cliente", back_populates="reservaciones")

class LogActividad(Base):
    __tablename__ = "log_actividad"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(String(50), nullable=False)
    subtipo = Column(String(50), nullable=True)
    telefono = Column(String(20), nullable=True)
    pedido_id = Column(UUID(as_uuid=True), nullable=True)
    reserva_id = Column(UUID(as_uuid=True), nullable=True)
    datos_json = Column(JSONB, default={})
    mensaje = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("idx_log_tipo_created", "tipo", "created_at"),
        Index("idx_log_telefono", "telefono", "created_at"),
    )

class ConfiguracionNegocio(Base):
    __tablename__ = "configuracion_negocio"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clave = Column(String(100), unique=True, nullable=False)
    valor = Column(Text, nullable=True)
    tipo_dato = Column(String(20), default="string")
    descripcion = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

engine = create_engine(settings.DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True, echo=settings.DEBUG)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


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

# ==========================================
# UTILIDADES
# ==========================================

def generar_codigo(tipo="PED"):
    fecha = datetime.now().strftime("%y%m%d")
    random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{tipo}-{fecha}-{random_suffix}"

def normalizar_telefono(numero):
    limpio = re.sub(r"[^0-9]", "", numero)
    if limpio.startswith("0") and len(limpio) == 10:
        limpio = "212" + limpio[1:]
    if not limpio.startswith("+"):
        limpio = "+" + limpio
    return limpio

def detectar_idioma(texto):
    texto_lower = texto.lower().strip()
    palabras_darija = ["سلام","بغيت","شحال","واخا","خاصني","عافاك","جوج","ثلاثة","ربعة","خمسة","عشرة","بزاف","صافي","هادا","هادي","شنو","فين","علاش","كيفاش","واش","بلا","عندي","عندك","ديالي","دير","دخل","خرج","طلب","اكل","شراب","قهوة","عصير","شاي"]
    palabras_fr = ["bonjour","salut","je","tu","il","nous","vous","ils","elles","merci","s'il","combien","commande","menu","prix","livraison","reservation","table","heure","jour","soir","matin","oui","non"]
    palabras_en = ["hello","hi","i ","you","he ","she","we ","they","thanks","please","how","much","order","menu","price","delivery","reservation","table","time","day","evening","morning","yes","no"]
    for palabra in palabras_darija:
        if palabra in texto_lower: return Idioma.AR
    for palabra in palabras_fr:
        if palabra in texto_lower: return Idioma.FR
    for palabra in palabras_en:
        if palabra in texto_lower: return Idioma.EN
    return Idioma.ES

def formatear_moneda(monto):
    return f"{monto:.2f} DH"

def truncar_texto(texto, max_len=4096):
    if len(texto) <= max_len: return texto
    return texto[:max_len-3] + "..."



class RateLimiter:
    def __init__(self):
        self.minute_windows = defaultdict(list)
        self.hour_windows = defaultdict(list)
        self.lock = asyncio.Lock()

    async def is_allowed(self, telefono):
        async with self.lock:
            now = time.time()
            self.minute_windows[telefono] = [t for t in self.minute_windows[telefono] if now - t < 60]
            self.hour_windows[telefono] = [t for t in self.hour_windows[telefono] if now - t < 3600]
            if len(self.minute_windows[telefono]) >= settings.RATE_LIMIT_MESSAGES_PER_MINUTE: return False
            if len(self.hour_windows[telefono]) >= settings.RATE_LIMIT_MESSAGES_PER_HOUR: return False
            self.minute_windows[telefono].append(now)
            self.hour_windows[telefono].append(now)
            return True

rate_limiter = RateLimiter()

# ==========================================
# TRADUCCIONES / MENSAJES MULTILINGUE
# ==========================================

MENSAJES = {
    "bienvenida": {
        Idioma.ES: "🌟 *{business}*

¡Hola {nombre}! Bienvenido/a a nuestro asistente de pedidos por WhatsApp.

📋 *Menú* - Ver productos
🛒 *Pedido* - Hacer un pedido
📅 *Reserva* - Reservar mesa
❓ *Ayuda* - Hablar con alguien

¿Qué te gustaría hacer?",
        Idioma.FR: "🌟 *{business}*

Bonjour {nombre}! Bienvenue sur notre assistant de commandes WhatsApp.

📋 *Menu* - Voir les produits
🛒 *Commande* - Passer une commande
📅 *Réservation* - Réserver une table
❓ *Aide* - Parler à quelqu'un

Que souhaitez-vous faire?",
        Idioma.AR: "🌟 *{business}*

سلام {nombre}! مرحبا بيك فمساعد الطلبات ديال الواتساب.

📋 *منيو* - شوف المنتجات
🛒 *طلب* - دير طلبية
📅 *حجز* - حجز الطابلة
❓ *مساعدة* - هضر مع شي واحد

شنو باغي تدير?",
        Idioma.EN: "🌟 *{business}*

Hello {nombre}! Welcome to our WhatsApp ordering assistant.

📋 *Menu* - View products
🛒 *Order* - Place an order
📅 *Reserve* - Book a table
❓ *Help* - Talk to someone

What would you like to do?"
    },
    "carrito_actual": {
        Idioma.ES: "🛒 *TU CARRITO*

{items}

Subtotal: {subtotal}
Envío: {envio}
*TOTAL: {total}*

✅ *Confirmar* - Enviar pedido
📝 *Nota* - Agregar nota
📍 *Dirección* - Cambiar dirección
🗑️ *Vaciar* - Borrar todo
➕ *Seguir* - Agregar más",
        Idioma.FR: "🛒 *VOTRE PANIER*

{items}

Sous-total: {subtotal}
Livraison: {envio}
*TOTAL: {total}*

✅ *Confirmer* - Envoyer la commande
📝 *Note* - Ajouter une note
📍 *Adresse* - Changer l'adresse
🗑️ *Vider* - Tout supprimer
➕ *Continuer* - Ajouter plus",
        Idioma.AR: "🛒 *السلة ديالك*

{items}

المجموع: {subtotal}
التوصيل: {envio}
*الجملة: {total}*

✅ *أكد* - سيفط الطلبية
📝 *ملاحظة* - زيد ملاحظة
📍 *العنوان* - بدّل العنوان
🗑️ *فرغ* - مسح كلشي
➕ *زيد* - زيد حوايج",
        Idioma.EN: "🛒 *YOUR CART*

{items}

Subtotal: {subtotal}
Delivery: {envio}
*TOTAL: {total}*

✅ *Confirm* - Send order
📝 *Note* - Add note
📍 *Address* - Change address
🗑️ *Empty* - Delete all
➕ *More* - Add more items"
    },
    "pedido_confirmado": {
        Idioma.ES: "✅ *¡PEDIDO CONFIRMADO!*

Código: *{codigo}*

{items}
Total: {total}

⏱️ Tiempo estimado: {tiempo} min
📍 {tipo_entrega}

Te avisaremos cuando esté listo. ¡Gracias!",
        Idioma.FR: "✅ *COMMANDE CONFIRMÉE!*

Code: *{codigo}*

{items}
Total: {total}

⏱️ Temps estimé: {tiempo} min
📍 {tipo_entrega}

Nous vous informerons quand c'est prêt. Merci!",
        Idioma.AR: "✅ *الطلبية تأكدات!*

الكود: *{codigo}*

{items}
الجملة: {total}

⏱️ الوقت المتوقع: {tiempo} دقيقة
📍 {tipo_entrega}

غادي نعلّموك منين تكون جاهزة. شكرا!",
        Idioma.EN: "✅ *ORDER CONFIRMED!*

Code: *{codigo}*

{items}
Total: {total}

⏱️ Estimated time: {tiempo} min
📍 {tipo_entrega}

We'll notify you when ready. Thanks!"
    },
    "reserva_fase_p": {
        Idioma.ES: "📅 *RESERVA DE MESA*

¿Para cuántas personas? (máx 20)",
        Idioma.FR: "📅 *RÉSERVATION DE TABLE*

Pour combien de personnes? (max 20)",
        Idioma.AR: "📅 *حجز الطابلة*

شحال ديال الناس? (حتى 20)",
        Idioma.EN: "📅 *TABLE RESERVATION*

How many people? (max 20)"
    },
    "reserva_fase_f": {
        Idioma.ES: "📅 *DATOS DE LA RESERVA*

Personas: {num_personas}

¿A nombre de quién? (o escribe 'yo')",
        Idioma.FR: "📅 *DÉTAILS DE LA RÉSERVATION*

Personnes: {num_personas}

Au nom de qui? (ou écrivez 'moi')",
        Idioma.AR: "📅 *تفاصيل الحجز*

الناس: {num_personas}

بسميت مين? (ولا كتب 'أنا')",
        Idioma.EN: "📅 *RESERVATION DETAILS*

People: {num_personas}

Under whose name? (or type 'me')"
    },
    "reserva_fase_h": {
        Idioma.ES: "📅 *HORA Y ZONA*

¿Qué día y hora? (ej: mañana 20:00, o 15/06 19:30)

Zonas disponibles:
🌿 Terraza
🛋️ Salón principal
⭐ VIP",
        Idioma.FR: "📅 *HEURE ET ZONE*

Quel jour et heure? (ex: demain 20h, ou 15/06 19h30)

Zones disponibles:
🌿 Terrasse
🛋️ Salle principale
⭐ VIP",
        Idioma.AR: "📅 *الوقت والبلاصة*

نهار ووقت? (مثلا: غدا 20:00، ولا 15/06 19:30)

البلاصات المتوفرة:
🌿 التاراس
🛋️ الصالون
⭐ في.آي.بي",
        Idioma.EN: "📅 *TIME AND AREA*

What day and time? (e.g., tomorrow 8pm, or 06/15 7:30pm)

Available areas:
🌿 Terrace
🛋️ Main hall
⭐ VIP"
    },
    "reserva_confirmada_ai": {
        Idioma.ES: "✅ *¡RESERVA CONFIRMADA!*

Código: *{codigo}*
📅 {fecha_hora}
👥 {num_personas} personas
🪑 Mesa: {mesa}
📍 Zona: {zona}

Nombre: {nombre}

⏰ Te esperamos. ¡Gracias!",
        Idioma.FR: "✅ *RÉSERVATION CONFIRMÉE!*

Code: *{codigo}*
📅 {fecha_hora}
👥 {num_personas} personnes
🪑 Table: {mesa}
📍 Zone: {zona}

Nom: {nombre}

⏰ Nous vous attendons. Merci!",
        Idioma.AR: "✅ *الحجز تأكد!*

الكود: *{codigo}*
📅 {fecha_hora}
👥 {num_personas} شخص
🪑 الطابلة: {mesa}
📍 البلاصة: {zona}

السمية: {nombre}

⏰ كنستناك. شكرا!",
        Idioma.EN: "✅ *RESERVATION CONFIRMED!*

Code: *{codigo}*
📅 {fecha_hora}
👥 {num_personas} people
🪑 Table: {mesa}
📍 Area: {zona}

Name: {nombre}

⏰ We await you. Thanks!"
    },
    "error_generico": {
        Idioma.ES: "😅 Ups, algo salió mal. ¿Puedes intentar de nuevo? O escribe *AYUDA* para hablar con alguien.",
        Idioma.FR: "😅 Oups, une erreur s'est produite. Pouvez-vous réessayer? Ou écrivez *AIDE* pour parler à quelqu'un.",
        Idioma.AR: "😅 ويلي، شي حاجة خرجات غالطة. جرّب مرة أخرى? ولا كتب *مساعدة* باش تهضر مع شي واحد.",
        Idioma.EN: "😅 Oops, something went wrong. Can you try again? Or type *HELP* to talk to someone."
    },
    "rate_limit": {
        Idioma.ES: "⏳ *Tranquilo* 😊

Estás enviando mensajes muy rápido. Dame un segundo para procesar...",
        Idioma.FR: "⏳ *Doucement* 😊

Vous envoyez des messages trop vite. Donnez-moi une seconde pour traiter...",
        Idioma.AR: "⏳ *برّاك* 😊

كتبعت الرسايل بزاف بسرعة. عطيني شوية الوقت باش نهضّر...",
        Idioma.EN: "⏳ *Easy* 😊

You're sending messages too fast. Give me a second to process..."
    },
    "ayuda_humanos": {
        Idioma.ES: "👨‍💼 *Conectando con atención...*

Un momento, por favor. Nuestro equipo te atenderá personalmente.

Mientras tanto, tu pedido/carrito sigue guardado.",
        Idioma.FR: "👨‍💼 *Connexion avec un conseiller...*

Un instant, s'il vous plaît. Notre équipe vous répondra personnellement.

En attendant, votre panier reste sauvegardé.",
        Idioma.AR: "👨‍💼 *كنوصلوك بشي واحد...*

شوية صبر عافاك. الفريق ديالنا غادي يجاوبك بشخص.

فالوقت هادا، السلة ديالك محفوظة.",
        Idioma.EN: "👨‍💼 *Connecting to support...*

One moment, please. Our team will attend you personally.

Meanwhile, your cart remains saved."
    }
}

def obtener_mensaje(clave, idioma, **kwargs):
    if clave not in MENSAJES:
        return f"[Missing: {clave}]"
    mensajes_idioma = MENSAJES[clave]
    if idioma not in mensajes_idioma:
        for fallback in [Idioma.ES, Idioma.FR, Idioma.EN, Idioma.AR]:
            if fallback in mensajes_idioma:
                idioma = fallback
                break
    plantilla = mensajes_idioma.get(idioma, mensajes_idioma.get(Idioma.ES, "Error"))
    try:
        return plantilla.format(**kwargs)
    except KeyError:
        return plantilla

# ==========================================
# WHATSAPP CLOUD API - Cliente
# ==========================================

class WhatsAppClient:
    def __init__(self):
        self.base_url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    async def enviar_texto(self, to, body, preview_url=False):
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalizar_telefono(to),
            "type": "text",
            "text": {"preview_url": preview_url, "body": truncar_texto(body)}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                result = await resp.json()
                if resp.status != 200:
                    logger.error(f"WA API error: {result}")
                return result

    async def enviar_interactivo_lista(self, to, header, body, footer, button_text, sections):
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalizar_telefono(to),
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": header},
                "body": {"text": truncar_texto(body, 1024)},
                "footer": {"text": footer},
                "action": {"button": button_text, "sections": sections}
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                return await resp.json()

    async def enviar_interactivo_botones(self, to, body, buttons):
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalizar_telefono(to),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": truncar_texto(body, 1024)},
                "action": {"buttons": buttons}
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                return await resp.json()

    async def enviar_imagen(self, to, image_url, caption=""):
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalizar_telefono(to),
            "type": "image",
            "image": {"link": image_url, "caption": truncar_texto(caption, 1024)}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                return await resp.json()

    async def enviar_ubicacion(self, to, lat, lng, name, address):
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalizar_telefono(to),
            "type": "location",
            "location": {"latitude": lat, "longitude": lng, "name": name, "address": address}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                return await resp.json()

    async def marcar_leido(self, message_id):
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                return await resp.json()

wa_client = WhatsAppClient()

# ==========================================
# BOT FSM - Maquina de Estados
# ==========================================

class BotState:
    INICIO = "inicio"
    MENU_CATEGORIAS = "menu_categorias"
    MENU_PRODUCTOS = "menu_productos"
    PRODUCTO_DETALLE = "producto_detalle"
    CARRITO = "carrito"
    CARRITO_NOTA = "carrito_nota"
    CARRITO_DIRECCION = "carrito_direccion"
    CONFIRMACION_PEDIDO = "confirmacion_pedido"
    RESERVA_PERSONAS = "res_p"
    RESERVA_DATOS = "res_f"
    RESERVA_HORA_MESA = "res_h"
    RESERVA_CONFIRMACION = "res_c"
    AYUDA = "ayuda"
    ESTADO_PEDIDO = "estado_pedido"

class BotProcessor:
    def __init__(self, db, wa):
        self.db = db
        self.wa = wa

    def get_or_create_cliente(self, telefono):
        telefono = normalizar_telefono(telefono)
        cliente = self.db.query(Cliente).filter(Cliente.telefono == telefono).first()
        if not cliente:
            cliente = Cliente(telefono=telefono, idioma_preferido=Idioma.ES, estado_flujo=BotState.INICIO, estado_flujo_data={})
            self.db.add(cliente)
            self.db.commit()
            self.db.refresh(cliente)
            logger.info(f"Nuevo cliente creado: {telefono}")
        return cliente

    def guardar_mensaje(self, telefono, tipo, contenido, direccion, wa_message_id=None, metadata=None):
        mensaje = Mensaje(wa_message_id=wa_message_id, telefono_cliente=normalizar_telefono(telefono), tipo=tipo, contenido=contenido[:4000], direccion=direccion, metadata_json=metadata or {})
        self.db.add(mensaje)
        self.db.commit()

    def log_actividad(self, tipo, subtipo=None, telefono=None, datos=None, mensaje=None):
        log = LogActividad(tipo=tipo, subtipo=subtipo, telefono=telefono, datos_json=datos or {}, mensaje=mensaje)
        self.db.add(log)
        self.db.commit()

    async def procesar_mensaje(self, telefono, texto, message_id, message_type="text", interactive_data=None):
        if not await rate_limiter.is_allowed(telefono):
            await self.wa.enviar_texto(telefono, obtener_mensaje("rate_limit", Idioma.ES))
            return

        self.guardar_mensaje(telefono, TipoMensaje.TEXTO, texto, "inbound", message_id)
        cliente = self.get_or_create_cliente(telefono)

        if len(texto) <= 50 or cliente.visitas_count == 0:
            idioma_detectado = detectar_idioma(texto)
            if idioma_detectado != cliente.idioma_preferido:
                cliente.idioma_preferido = idioma_detectado
                self.db.commit()

        idioma = cliente.idioma_preferido
        texto_lower = texto.lower().strip()

        # Comandos globales
        if any(p in texto_lower for p in ["ayuda", "aide", "مساعدة", "help"]):
            await self.handle_ayuda(cliente, idioma); return
        if any(p in texto_lower for p in ["menu", "menú", "منيو"]):
            await self.handle_menu_categorias(cliente, idioma); return
        if any(p in texto_lower for p in ["pedido", "commande", "طلب", "order"]):
            await self.handle_menu_categorias(cliente, idioma); return
        if any(p in texto_lower for p in ["reserva", "réservation", "حجز", "reserve"]):
            await self.handle_reserva_inicio(cliente, idioma); return
        if any(p in texto_lower for p in ["carrito", "panier", "سلة", "cart"]):
            await self.handle_ver_carrito(cliente, idioma); return
        if any(p in texto_lower for p in ["estado", "état", "حالة", "status"]):
            await self.handle_estado_pedido(cliente, idioma); return
        if any(p in texto_lower for p in ["hola", "bonjour", "salam", "hello", "salut", "hi"]):
            await self.handle_bienvenida(cliente, idioma); return

        # FSM routing
        estado = cliente.estado_flujo
        if estado == BotState.INICIO:
            await self.handle_bienvenida(cliente, idioma)
        elif estado == BotState.MENU_CATEGORIAS:
            await self.handle_seleccion_categoria(cliente, texto, idioma)
        elif estado == BotState.MENU_PRODUCTOS:
            await self.handle_seleccion_producto(cliente, texto, idioma)
        elif estado == BotState.PRODUCTO_DETALLE:
            await self.handle_cantidad_producto(cliente, texto, idioma)
        elif estado == BotState.CARRITO:
            await self.handle_accion_carrito(cliente, texto, idioma)
        elif estado == BotState.CARRITO_NOTA:
            await self.handle_guardar_nota(cliente, texto, idioma)
        elif estado == BotState.CARRITO_DIRECCION:
            await self.handle_guardar_direccion(cliente, texto, idioma)
        elif estado == BotState.CONFIRMACION_PEDIDO:
            await self.handle_confirmacion_final(cliente, texto, idioma)
        elif estado == BotState.RESERVA_PERSONAS:
            await self.handle_reserva_personas(cliente, texto, idioma)
        elif estado == BotState.RESERVA_DATOS:
            await self.handle_reserva_datos(cliente, texto, idioma)
        elif estado == BotState.RESERVA_HORA_MESA:
            await self.handle_reserva_hora_mesa(cliente, texto, idioma)
        elif estado == BotState.RESERVA_CONFIRMACION:
            await self.handle_reserva_confirmacion(cliente, texto, idioma)
        elif estado == BotState.AYUDA:
            await self.wa.enviar_texto(telefono, obtener_mensaje("ayuda_humanos", idioma))
        else:
            cliente.estado_flujo = BotState.INICIO
            cliente.estado_flujo_data = {}
            self.db.commit()
            await self.handle_bienvenida(cliente, idioma)

    async def handle_bienvenida(self, cliente, idioma):
        nombre = cliente.nombre or ""
        mensaje = obtener_mensaje("bienvenida", idioma, business=settings.BUSINESS_NAME, nombre=nombre)
        buttons = [
            {"type": "reply", "reply": {"id": "menu", "title": "📋 Menú" if idioma == Idioma.ES else "📋 Menu" if idioma == Idioma.FR else "📋 المنيو" if idioma == Idioma.AR else "📋 Menu"}},
            {"type": "reply", "reply": {"id": "pedido", "title": "🛒 Pedido" if idioma == Idioma.ES else "🛒 Commande" if idioma == Idioma.FR else "🛒 طلب" if idioma == Idioma.AR else "🛒 Order"}},
            {"type": "reply", "reply": {"id": "reserva", "title": "📅 Reserva" if idioma == Idioma.ES else "📅 Réservation" if idioma == Idioma.FR else "📅 حجز" if idioma == Idioma.AR else "📅 Reserve"}}
        ]
        await self.wa.enviar_interactivo_botones(cliente.telefono, mensaje, buttons)
        cliente.estado_flujo = BotState.INICIO
        cliente.visitas_count += 1
        cliente.ultima_visita = datetime.now(timezone.utc)
        self.db.commit()

    async def handle_menu_categorias(self, cliente, idioma):
        categorias = self.db.query(Categoria).filter(Categoria.activa == True).order_by(Categoria.orden).all()
        if not categorias:
            await self.wa.enviar_texto(cliente.telefono, "📝 Menú en actualización. Vuelve pronto." if idioma == Idioma.ES else "📝 Menu en cours de mise à jour." if idioma == Idioma.FR else "📝 المنيو كيتحدّث." if idioma == Idioma.AR else "📝 Menu being updated.")
            return

        sections = [{"title": "Categorías" if idioma == Idioma.ES else "Catégories" if idioma == Idioma.FR else "الأصناف" if idioma == Idioma.AR else "Categories", "rows": []}]
        for cat in categorias:
            nombre = cat.nombre_es
            if idioma == Idioma.FR and cat.nombre_fr: nombre = cat.nombre_fr
            elif idioma == Idioma.AR and cat.nombre_ar: nombre = cat.nombre_ar
            emoji = cat.emoji or "🍽️"
            sections[0]["rows"].append({"id": f"cat_{cat.id}", "title": f"{emoji} {nombre}", "description": "Ver productos" if idioma == Idioma.ES else "Voir produits" if idioma == Idioma.FR else "شوف المنتجات" if idioma == Idioma.AR else "View products"})
        sections[0]["rows"].append({"id": "volver_inicio", "title": "🏠 Inicio" if idioma == Idioma.ES else "🏠 Accueil" if idioma == Idioma.FR else "🏠 البداية" if idioma == Idioma.AR else "🏠 Home", "description": ""})

        header = "📋 MENÚ"
        body = "Elige una categoría:" if idioma == Idioma.ES else "Choisissez une catégorie:" if idioma == Idioma.FR else "ختار الصنف:" if idioma == Idioma.AR else "Choose a category:"
        footer = settings.BUSINESS_NAME
        button = "Ver categorías" if idioma == Idioma.ES else "Voir catégories" if idioma == Idioma.FR else "شوف الأصناف" if idioma == Idioma.AR else "View categories"

        await self.wa.enviar_interactivo_lista(cliente.telefono, header, body, footer, button, sections)
        cliente.estado_flujo = BotState.MENU_CATEGORIAS
        self.db.commit()

    async def handle_seleccion_categoria(self, cliente, texto, idioma):
        if texto.startswith("cat_"):
            cat_id = texto.replace("cat_", "")
        elif texto == "volver_inicio":
            await self.handle_bienvenida(cliente, idioma); return
        else:
            cat = self.db.query(Categoria).filter(Categoria.activa == True).filter(
                (Categoria.nombre_es.ilike(f"%{texto}%")) |
                (Categoria.nombre_fr.ilike(f"%{texto}%")) |
                (Categoria.nombre_ar.ilike(f"%{texto}%"))
            ).first()
            if not cat:
                await self.handle_menu_categorias(cliente, idioma); return
            cat_id = str(cat.id)

        productos = self.db.query(Producto).filter(Producto.categoria_id == cat_id, Producto.disponible == True).order_by(Producto.orden).all()
        if not productos:
            await self.wa.enviar_texto(cliente.telefono, "No hay productos en esta categoría ahora." if idioma == Idioma.ES else "Pas de produits." if idioma == Idioma.FR else "ماكاينش منتجات." if idioma == Idioma.AR else "No products.")
            await self.handle_menu_categorias(cliente, idioma); return

        sections = [{"title": "Productos" if idioma == Idioma.ES else "Produits" if idioma == Idioma.FR else "المنتجات" if idioma == Idioma.AR else "Products", "rows": []}]
        for prod in productos:
            nombre = prod.nombre_es
            if idioma == Idioma.FR and prod.nombre_fr: nombre = prod.nombre_fr
            elif idioma == Idioma.AR and prod.nombre_ar: nombre = prod.nombre_ar
            precio = formatear_moneda(prod.precio)
            sections[0]["rows"].append({"id": f"prod_{prod.id}", "title": f"{nombre}", "description": f"{precio} - {prod.tiempo_preparacion_min}min"})
        sections[0]["rows"].append({"id": "volver_categorias", "title": "⬅️ Volver" if idioma == Idioma.ES else "⬅️ Retour" if idioma == Idioma.FR else "⬅️ رجع" if idioma == Idioma.AR else "⬅️ Back", "description": ""})

        cat = self.db.query(Categoria).filter(Categoria.id == cat_id).first()
        cat_nombre = cat.nombre_es if cat else "Productos"
        header = f"🍽️ {cat_nombre}"
        body = "Elige un producto:" if idioma == Idioma.ES else "Choisissez un produit:" if idioma == Idioma.FR else "ختار منتج:" if idioma == Idioma.AR else "Choose a product:"
        footer = f"💰 Precios en {settings.BUSINESS_CURRENCY}"
        button = "Ver productos" if idioma == Idioma.ES else "Voir produits" if idioma == Idioma.FR else "شوف المنتجات" if idioma == Idioma.AR else "View products"

        await self.wa.enviar_interactivo_lista(cliente.telefono, header, body, footer, button, sections)
        cliente.estado_flujo = BotState.MENU_PRODUCTOS
        cliente.estado_flujo_data = {**cliente.estado_flujo_data, "categoria_id": cat_id}
        self.db.commit()

    async def handle_seleccion_producto(self, cliente, texto, idioma):
        if texto == "volver_categorias":
            cat_id = cliente.estado_flujo_data.get("categoria_id")
            if cat_id: await self.handle_seleccion_categoria(cliente, f"cat_{cat_id}", idioma)
            else: await self.handle_menu_categorias(cliente, idioma)
            return

        if texto.startswith("prod_"): prod_id = texto.replace("prod_", "")
        else:
            prod = self.db.query(Producto).filter(Producto.disponible == True).filter(
                (Producto.nombre_es.ilike(f"%{texto}%")) |
                (Producto.nombre_fr.ilike(f"%{texto}%")) |
                (Producto.nombre_ar.ilike(f"%{texto}%"))
            ).first()
            if not prod:
                await self.wa.enviar_texto(cliente.telefono, "No encontré ese producto." if idioma == Idioma.ES else "Produit non trouvé." if idioma == Idioma.FR else "ما لقيتش المنتج." if idioma == Idioma.AR else "Product not found.")
                return
            prod_id = str(prod.id)

        prod = self.db.query(Producto).filter(Producto.id == prod_id).first()
        if not prod or not prod.disponible:
            await self.wa.enviar_texto(cliente.telefono, "Producto no disponible." if idioma == Idioma.ES else "Produit indisponible." if idioma == Idioma.FR else "المنتج ما كاينش." if idioma == Idioma.AR else "Product unavailable.")
            await self.handle_menu_categorias(cliente, idioma); return

        nombre = prod.nombre_es
        if idioma == Idioma.FR and prod.nombre_fr: nombre = prod.nombre_fr
        elif idioma == Idioma.AR and prod.nombre_ar: nombre = prod.nombre_ar
        descripcion = prod.descripcion_es or ""
        if idioma == Idioma.FR and prod.descripcion_fr: descripcion = prod.descripcion_fr
        elif idioma == Idioma.AR and prod.descripcion_ar: descripcion = prod.descripcion_ar
        precio = formatear_moneda(prod.precio)

        mensaje = f"*{nombre}*
💰 {precio}
📝 {descripcion}

¿Cuántos quieres? (1-10)" if idioma == Idioma.ES else f"*{nombre}*
💰 {precio}
📝 {descripcion}

Combien? (1-10)" if idioma == Idioma.FR else f"*{nombre}*
💰 {precio}
📝 {descripcion}

شحال? (1-10)" if idioma == Idioma.AR else f"*{nombre}*
💰 {precio}
📝 {descripcion}

How many? (1-10)"
        buttons = [{"type": "reply", "reply": {"id": f"cant_{i}", "title": f"{i}x"}} for i in range(1,6)] + [{"type": "reply", "reply": {"id": "volver_productos", "title": "⬅️"}}]

        if prod.imagen_url: await self.wa.enviar_imagen(cliente.telefono, prod.imagen_url, mensaje)
        else: await self.wa.enviar_interactivo_botones(cliente.telefono, mensaje, buttons)

        cliente.estado_flujo = BotState.PRODUCTO_DETALLE
        cliente.estado_flujo_data = {**cliente.estado_flujo_data, "producto_id": prod_id}
        self.db.commit()

    async def handle_cantidad_producto(self, cliente, texto, idioma):
        if texto == "volver_productos":
            cat_id = cliente.estado_flujo_data.get("categoria_id")
            if cat_id: await self.handle_seleccion_categoria(cliente, f"cat_{cat_id}", idioma)
            else: await self.handle_menu_categorias(cliente, idioma)
            return

        cantidad = 1
        if texto.startswith("cant_"):
            try: cantidad = int(texto.replace("cant_", ""))
            except: cantidad = 1
        else:
            nums = re.findall(r"\d+", texto)
            if nums: cantidad = int(nums[0])
        cantidad = max(1, min(cantidad, 20))

        prod_id = cliente.estado_flujo_data.get("producto_id")
        if not prod_id: await self.handle_menu_categorias(cliente, idioma); return

        prod = self.db.query(Producto).filter(Producto.id == prod_id).first()
        if not prod: await self.handle_menu_categorias(cliente, idioma); return

        carrito = cliente.carrito_activo or {"items": [], "total": 0}
        item_existente = None
        for item in carrito["items"]:
            if item["producto_id"] == prod_id: item_existente = item; break

        if item_existente:
            item_existente["cantidad"] += cantidad
            item_existente["subtotal"] = float(item_existente["cantidad"] * float(prod.precio))
        else:
            nombre = prod.nombre_es
            if idioma == Idioma.FR and prod.nombre_fr: nombre = prod.nombre_fr
            elif idioma == Idioma.AR and prod.nombre_ar: nombre = prod.nombre_ar
            carrito["items"].append({"producto_id": prod_id, "nombre": nombre, "precio_unitario": float(prod.precio), "cantidad": cantidad, "subtotal": float(cantidad * float(prod.precio)), "notas": "", "opciones": {}})

        carrito["total"] = sum(item["subtotal"] for item in carrito["items"])
        cliente.carrito_activo = carrito
        self.db.commit()
        await self.handle_ver_carrito(cliente, idioma, mensaje_extra=f"✅ Agregado: {cantidad}x {nombre}")

    async def handle_ver_carrito(self, cliente, idioma, mensaje_extra=""):
        carrito = cliente.carrito_activo or {"items": [], "total": 0}
        if not carrito["items"]:
            mensaje = (mensaje_extra + "

" if mensaje_extra else "") + ("🛒 Tu carrito está vacío." if idioma == Idioma.ES else "🛒 Votre panier est vide." if idioma == Idioma.FR else "🛒 السلة ديالك خاوية." if idioma == Idioma.AR else "🛒 Your cart is empty.")
            await self.wa.enviar_texto(cliente.telefono, mensaje)
            await self.handle_menu_categorias(cliente, idioma); return

        items_str = ""
        for i, item in enumerate(carrito["items"], 1):
            items_str += f"{i}. {item['nombre']} x{item['cantidad']} = {item['subtotal']:.2f} DH
"

        subtotal = Decimal(str(carrito["total"])); envio = Decimal("0.00"); total = subtotal + envio
        mensaje = obtener_mensaje("carrito_actual", idioma, items=items_str, subtotal=formatear_moneda(subtotal), envio=formatear_moneda(envio), total=formatear_moneda(total))
        if mensaje_extra: mensaje = mensaje_extra + "

" + mensaje

        buttons = [
            {"type": "reply", "reply": {"id": "confirmar", "title": "✅ Confirmar" if idioma == Idioma.ES else "✅ Confirmer" if idioma == Idioma.FR else "✅ أكد" if idioma == Idioma.AR else "✅ Confirm"}},
            {"type": "reply", "reply": {"id": "nota", "title": "📝 Nota" if idioma == Idioma.ES else "📝 Note" if idioma == Idioma.FR else "📝 ملاحظة" if idioma == Idioma.AR else "📝 Note"}},
            {"type": "reply", "reply": {"id": "direccion", "title": "📍 Dirección" if idioma == Idioma.ES else "📍 Adresse" if idioma == Idioma.FR else "📍 العنوان" if idioma == Idioma.AR else "📍 Address"}}
        ]
        await self.wa.enviar_interactivo_botones(cliente.telefono, mensaje, buttons)
        cliente.estado_flujo = BotState.CARRITO
        self.db.commit()

    async def handle_accion_carrito(self, cliente, texto, idioma):
        if texto == "confirmar": await self.handle_confirmar_pedido(cliente, idioma)
        elif texto == "nota":
            await self.wa.enviar_texto(cliente.telefono, "📝 Escribe tu nota:" if idioma == Idioma.ES else "📝 Écrivez votre note:" if idioma == Idioma.FR else "📝 كتب ملاحظة:" if idioma == Idioma.AR else "📝 Write your note:")
            cliente.estado_flujo = BotState.CARRITO_NOTA; self.db.commit()
        elif texto == "direccion":
            await self.wa.enviar_texto(cliente.telefono, "📍 Envía tu dirección:" if idioma == Idioma.ES else "📍 Envoyez votre adresse:" if idioma == Idioma.FR else "📍 سيفط العنوان:" if idioma == Idioma.AR else "📍 Send your address:")
            cliente.estado_flujo = BotState.CARRITO_DIRECCION; self.db.commit()
        elif texto in ["vaciar", "vider", "فرغ", "empty"]:
            cliente.carrito_activo = {"items": [], "total": 0}; self.db.commit()
            await self.wa.enviar_texto(cliente.telefono, "🗑️ Carrito vaciado." if idioma == Idioma.ES else "🗑️ Panier vidé." if idioma == Idioma.FR else "🗑️ السلة فرغات." if idioma == Idioma.AR else "🗑️ Cart emptied.")
            await self.handle_menu_categorias(cliente, idioma)
        elif texto in ["seguir", "continuer", "زيد", "more"]:
            await self.handle_menu_categorias(cliente, idioma)
        else: await self.handle_ver_carrito(cliente, idioma)

    async def handle_guardar_nota(self, cliente, texto, idioma):
        carrito = cliente.carrito_activo or {"items": [], "total": 0}
        carrito["notas"] = texto; cliente.carrito_activo = carrito; self.db.commit()
        await self.wa.enviar_texto(cliente.telefono, "📝 Nota guardada." if idioma == Idioma.ES else "📝 Note enregistrée." if idioma == Idioma.FR else "📝 الملاحظة تحفظات." if idioma == Idioma.AR else "📝 Note saved.")
        await self.handle_ver_carrito(cliente, idioma)

    async def handle_guardar_direccion(self, cliente, texto, idioma):
        tipo_entrega = "delivery"
        if any(p in texto.lower() for p in ["recogida", "retrait", "جيبها", "pickup", "pasar"]):
            tipo_entrega = "recogida"; direccion = "Recogida en local"
        else: direccion = texto
        carrito = cliente.carrito_activo or {"items": [], "total": 0}
        carrito["direccion"] = direccion; carrito["tipo_entrega"] = tipo_entrega; cliente.carrito_activo = carrito
        if tipo_entrega == "delivery": cliente.direccion = direccion
        self.db.commit()
        await self.wa.enviar_texto(cliente.telefono, f"📍 Guardado: {direccion}")
        await self.handle_ver_carrito(cliente, idioma)

    async def handle_confirmar_pedido(self, cliente, idioma):
        carrito = cliente.carrito_activo or {"items": [], "total": 0}
        if not carrito["items"]: await self.handle_ver_carrito(cliente, idioma); return
        if not carrito.get("direccion") and not cliente.direccion:
            await self.wa.enviar_texto(cliente.telefono, "📍 Necesito una dirección:" if idioma == Idioma.ES else "📍 J'ai besoin d'une adresse:" if idioma == Idioma.FR else "📍 خاصني العنوان:" if idioma == Idioma.AR else "📍 I need an address:")
            cliente.estado_flujo = BotState.CARRITO_DIRECCION; self.db.commit(); return

        items_str = ""
        for i, item in enumerate(carrito["items"], 1):
            items_str += f"{i}. {item['nombre']} x{item['cantidad']} = {item['subtotal']:.2f} DH
"
        subtotal = Decimal(str(carrito["total"])); envio = Decimal("0.00"); total = subtotal + envio

        resumen = f"🧾 *RESUMEN DEL PEDIDO*

{items_str}
Subtotal: {formatear_moneda(subtotal)}
Envío: {formatear_moneda(envio)}
*TOTAL: {formatear_moneda(total)}*

📍 {carrito.get('direccion', cliente.direccion or 'No especificada')}
"
        if carrito.get("notas"): resumen += f"📝 {carrito['notas']}
"
        resumen += "
¿Confirmas?"

        buttons = [
            {"type": "reply", "reply": {"id": "si_confirmar", "title": "✅ Sí, confirmar" if idioma == Idioma.ES else "✅ Oui, confirmer" if idioma == Idioma.FR else "✅ إييه، أكد" if idioma == Idioma.AR else "✅ Yes, confirm"}},
            {"type": "reply", "reply": {"id": "no_cancelar", "title": "❌ No, cancelar" if idioma == Idioma.ES else "❌ Non, annuler" if idioma == Idioma.FR else "❌ لا، cancel" if idioma == Idioma.AR else "❌ No, cancel"}},
            {"type": "reply", "reply": {"id": "modificar", "title": "📝 Modificar" if idioma == Idioma.ES else "📝 Modifier" if idioma == Idioma.FR else "📝 بدّل" if idioma == Idioma.AR else "📝 Modify"}}
        ]
        await self.wa.enviar_interactivo_botones(cliente.telefono, resumen, buttons)
        cliente.estado_flujo = BotState.CONFIRMACION_PEDIDO; self.db.commit()

    async def handle_confirmacion_final(self, cliente, texto, idioma):
        if texto in ["no_cancelar", "cancelar", "annuler", "cancel", "لا"]:
            cliente.carrito_activo = {"items": [], "total": 0}; cliente.estado_flujo = BotState.INICIO; self.db.commit()
            await self.wa.enviar_texto(cliente.telefono, "❌ Pedido cancelado." if idioma == Idioma.ES else "❌ Commande annulée." if idioma == Idioma.FR else "❌ الطلبية cancelات." if idioma == Idioma.AR else "❌ Order cancelled.")
            await self.handle_bienvenida(cliente, idioma); return
        if texto in ["modificar", "modifier", "بدّل", "modify"]:
            await self.handle_ver_carrito(cliente, idioma); return
        if texto in ["si_confirmar", "sí", "oui", "إييه", "yes", "confirmar"]:
            await self.crear_pedido(cliente, idioma)
        else: await self.handle_confirmar_pedido(cliente, idioma)

    async def crear_pedido(self, cliente, idioma):
        carrito = cliente.carrito_activo or {"items": [], "total": 0}
        if not carrito["items"]: return
        codigo = generar_codigo("PED")
        subtotal = Decimal(str(carrito["total"])); envio = Decimal("0.00"); total = subtotal + envio

        pedido = Pedido(codigo_pedido=codigo, cliente_id=cliente.id, estado=EstadoPedido.PENDIENTE, tipo_entrega=carrito.get("tipo_entrega", "delivery"), direccion_entrega=carrito.get("direccion", cliente.direccion), notas=carrito.get("notas", ""), subtotal=subtotal, costo_envio=envio, total=total, estado_pago=EstadoPago.PENDIENTE)
        self.db.add(pedido); self.db.flush()

        tiempo_max = 0
        for item_data in carrito["items"]:
            prod = self.db.query(Producto).filter(Producto.id == item_data["producto_id"]).first()
            if prod:
                item = ItemPedido(pedido_id=pedido.id, producto_id=item_data["producto_id"], cantidad=item_data["cantidad"], precio_unitario=Decimal(str(item_data["precio_unitario"])), opciones_seleccionadas=item_data.get("opciones", {}), notas_item=item_data.get("notas", ""), subtotal=Decimal(str(item_data["subtotal"])))
                self.db.add(item)
                tiempo_max = max(tiempo_max, prod.tiempo_preparacion_min)

        cliente.carrito_activo = {"items": [], "total": 0}; cliente.estado_flujo = BotState.INICIO
        cliente.total_gastado = (cliente.total_gastado or Decimal("0.00")) + total
        if cliente.visitas_count >= 5: cliente.tipo = TipoCliente.RECURRENTE
        if cliente.total_gastado >= Decimal("5000.00"): cliente.tipo = TipoCliente.VIP
        self.db.commit()

        items_str = ""
        for item in pedido.items:
            items_str += f"• {item.producto.nombre_es} x{item.cantidad} = {item.subtotal:.2f} DH
"

        mensaje = obtener_mensaje("pedido_confirmado", idioma, codigo=codigo, items=items_str, total=formatear_moneda(total), tiempo=tiempo_max + 10, tipo_entrega="Delivery" if pedido.tipo_entrega == "delivery" else "Recogida en local" if idioma == Idioma.ES else "Retrait sur place" if idioma == Idioma.FR else "جيبها من عندنا" if idioma == Idioma.AR else "Pickup")
        await self.wa.enviar_texto(cliente.telefono, mensaje)
        self.log_actividad("bot", "pedido_creado", cliente.telefono, {"pedido_id": str(pedido.id), "codigo": codigo, "total": float(total)})

    async def handle_reserva_inicio(self, cliente, idioma):
        mensaje = obtener_mensaje("reserva_fase_p", idioma)
        buttons = [{"type": "reply", "reply": {"id": f"pers_{i}", "title": f"{i} {'personas' if idioma == Idioma.ES else 'personnes' if idioma == Idioma.FR else 'ناس' if idioma == Idioma.AR else 'people'}"}} for i in [2, 4, 6, 8]]
        buttons.append({"type": "reply", "reply": {"id": "volver_inicio", "title": "🏠"}})
        await self.wa.enviar_interactivo_botones(cliente.telefono, mensaje, buttons)
        cliente.estado_flujo = BotState.RESERVA_PERSONAS
        cliente.estado_flujo_data = {"reserva": {}}
        self.db.commit()

    async def handle_reserva_personas(self, cliente, texto, idioma):
        if texto == "volver_inicio": await self.handle_bienvenida(cliente, idioma); return
        num_personas = 2
        if texto.startswith("pers_"):
            try: num_personas = int(texto.replace("pers_", ""))
            except: num_personas = 2
        else:
            nums = re.findall(r"\d+", texto)
            if nums: num_personas = int(nums[0])
        num_personas = max(1, min(num_personas, 50))

        flujo_data = cliente.estado_flujo_data or {}
        flujo_data["reserva"] = flujo_data.get("reserva", {})
        flujo_data["reserva"]["num_personas"] = num_personas
        cliente.estado_flujo_data = flujo_data

        mensaje = obtener_mensaje("reserva_fase_f", idioma, num_personas=num_personas)
        await self.wa.enviar_texto(cliente.telefono, mensaje)
        cliente.estado_flujo = BotState.RESERVA_DATOS; self.db.commit()

    async def handle_reserva_datos(self, cliente, texto, idioma):
        flujo_data = cliente.estado_flujo_data or {}
        reserva_data = flujo_data.get("reserva", {})
        if texto.lower() in ["yo", "moi", "أنا", "me", "moi-même"]:
            nombre = cliente.nombre or "Cliente"
        else:
            nombre = texto
            if not cliente.nombre: cliente.nombre = nombre

        reserva_data["nombre"] = nombre; reserva_data["telefono"] = cliente.telefono
        flujo_data["reserva"] = reserva_data; cliente.estado_flujo_data = flujo_data

        mensaje = obtener_mensaje("reserva_fase_h", idioma)
        await self.wa.enviar_texto(cliente.telefono, mensaje)
        cliente.estado_flujo = BotState.RESERVA_HORA_MESA; self.db.commit()

    async def handle_reserva_hora_mesa(self, cliente, texto, idioma):
        flujo_data = cliente.estado_flujo_data or {}
        reserva_data = flujo_data.get("reserva", {})

        fecha_hora = None; zona = "salón"
        texto_lower = texto.lower()
        if any(p in texto_lower for p in ["terraza", "terrasse", "تاراس", "terrace", "taras"]): zona = "terraza"
        elif any(p in texto_lower for p in ["vip", "في.آي.بي", "في اي بي"]): zona = "VIP"
        elif any(p in texto_lower for p in ["salón", "salle", "صالون", "hall", "salon"]): zona = "salón"

        try:
            if "mañana" in texto_lower or "demain" in texto_lower or "غدا" in texto_lower or "tomorrow" in texto_lower:
                fecha_hora = datetime.now(timezone.utc) + timedelta(days=1)
                fecha_hora = fecha_hora.replace(hour=20, minute=0, second=0)
            else:
                hora_match = re.search(r"(\d{1,2})[h:](\d{2})", texto)
                if hora_match:
                    hora = int(hora_match.group(1)); minuto = int(hora_match.group(2))
                    fecha_hora = datetime.now(timezone.utc)
                    fecha_hora = fecha_hora.replace(hour=hora, minute=minuto, second=0)
                    if fecha_hora < datetime.now(timezone.utc): fecha_hora += timedelta(days=1)
                else:
                    fecha_hora = datetime.now(timezone.utc)
                    fecha_hora = fecha_hora.replace(hour=20, minute=0, second=0)
                    if fecha_hora < datetime.now(timezone.utc): fecha_hora += timedelta(days=1)
        except Exception:
            fecha_hora = datetime.now(timezone.utc) + timedelta(days=1)
            fecha_hora = fecha_hora.replace(hour=20, minute=0, second=0)

        reserva_data["fecha_hora"] = fecha_hora.isoformat(); reserva_data["zona"] = zona
        ai_confirmada = True; mesa_asignada = "VIP-1" if zona == "VIP" else "T-3" if zona == "terraza" else "S-5"
        reserva_data["mesa_asignada"] = mesa_asignada; reserva_data["ai_confirmada"] = ai_confirmada
        flujo_data["reserva"] = reserva_data; cliente.estado_flujo_data = flujo_data

        codigo = generar_codigo("RES")
        reservacion = Reservacion(codigo_reserva=codigo, cliente_id=cliente.id, estado=EstadoReserva.CONFIRMADA if ai_confirmada else EstadoReserva.PENDIENTE, nombre_reserva=reserva_data.get("nombre"), telefono_reserva=reserva_data.get("telefono"), num_personas=reserva_data.get("num_personas", 2), hora_reserva=fecha_hora, mesa_asignada=mesa_asignada, zona=zona, ai_confirmada=ai_confirmada, ai_confirmada_at=datetime.now(timezone.utc) if ai_confirmada else None)
        self.db.add(reservacion)
        cliente.estado_flujo = BotState.INICIO; self.db.commit()

        fecha_str = fecha_hora.strftime("%d/%m/%Y %H:%M")
        if ai_confirmada:
            mensaje = obtener_mensaje("reserva_confirmada_ai", idioma, codigo=codigo, fecha_hora=fecha_str, num_personas=reserva_data.get("num_personas", 2), mesa=mesa_asignada, zona=zona.capitalize(), nombre=reserva_data.get("nombre", "Cliente"))
        else:
            mensaje = obtener_mensaje("reserva_ai_rechazo", idioma, codigo=codigo, motivo="Horario no disponible")

        await self.wa.enviar_texto(cliente.telefono, mensaje)
        self.log_actividad("bot", "reserva_creada", cliente.telefono, {"reserva_id": str(reservacion.id), "codigo": codigo, "ai_confirmada": ai_confirmada})

    async def handle_reserva_confirmacion(self, cliente, texto, idioma):
        await self.wa.enviar_texto(cliente.telefono, "⏳ Tu reserva está siendo revisada." if idioma == Idioma.ES else "⏳ Votre réservation est en cours de révision." if idioma == Idioma.FR else "⏳ الحجز ديالك فالانتظار." if idioma == Idioma.AR else "⏳ Your reservation is being reviewed.")
        cliente.estado_flujo = BotState.INICIO; self.db.commit()

    async def handle_ayuda(self, cliente, idioma):
        cliente.estado_flujo = BotState.AYUDA; self.db.commit()
        await self.wa.enviar_texto(cliente.telefono, obtener_mensaje("ayuda_humanos", idioma))
        self.log_actividad("bot", "ayuda_solicitada", cliente.telefono, {"nombre": cliente.nombre, "estado": "esperando_agente"})

    async def handle_estado_pedido(self, cliente, idioma):
        pedido = self.db.query(Pedido).filter(Pedido.cliente_id == cliente.id).order_by(Pedido.created_at.desc()).first()
        if not pedido:
            await self.wa.enviar_texto(cliente.telefono, "No tienes pedidos activos." if idioma == Idioma.ES else "Vous n'avez pas de commandes actives." if idioma == Idioma.FR else "ما عندكش طلبيات نشطة." if idioma == Idioma.AR else "You have no active orders.")
            return

        estado_str = {EstadoPedido.PENDIENTE: "⏳ Pendiente", EstadoPedido.CONFIRMADO: "✅ Confirmado", EstadoPedido.EN_PREPARACION: "👨‍🍳 En preparación", EstadoPedido.LISTO: "🍽️ Listo", EstadoPedido.EN_CAMINO: "🚚 En camino", EstadoPedido.ENTREGADO: "✅ Entregado", EstadoPedido.CANCELADO: "❌ Cancelado"}.get(pedido.estado, str(pedido.estado))

        mensaje = f"🧾 *PEDIDO {pedido.codigo_pedido}*

Estado: {estado_str}
Total: {formatear_moneda(pedido.total)}
Fecha: {pedido.created_at.strftime('%d/%m/%Y %H:%M')}
"
        if pedido.confirmado_at: mensaje += f"Confirmado: {pedido.confirmado_at.strftime('%H:%M')}
"
        if pedido.listo_at: mensaje += f"Listo: {pedido.listo_at.strftime('%H:%M')}
"
        await self.wa.enviar_texto(cliente.telefono, mensaje)

# ==========================================
# FASTAPI APP
# ==========================================

security = HTTPBearer(auto_error=False)

def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="No token provided")
    if credentials.credentials != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid token")
    return credentials.credentials

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} iniciado")
    yield
    logger.info("👋 Shutting down gracefully")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Orquestrator ISA ChatCommerce - WhatsApp Ordering Bot for Morocco",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


# ==========================================
# WEBHOOK ENDPOINTS
# ==========================================

@app.get("/webhook")
async def webhook_verify(hub_mode=None, hub_verify_token=None, hub_challenge=None):
    logger.info(f"Webhook verify: mode={hub_mode}, token={hub_verify_token}")
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("✅ Webhook verified successfully")
        return PlainTextResponse(content=hub_challenge)
    logger.warning("❌ Webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def webhook_receive(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if settings.WHATSAPP_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        body = await request.body()
        expected = "sha256=" + hmac.new(settings.WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("❌ Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
        payload = json.loads(body)
    else:
        payload = await request.json()

    logger.debug(f"Webhook payload: {json.dumps(payload, indent=2)[:500]}")
    background_tasks.add_task(process_webhook_payload, payload, db)
    return JSONResponse(content={"status": "received"})

async def process_webhook_payload(payload, db):
    try:
        if payload.get("object") != "whatsapp_business_account":
            return
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" in value:
                    for msg in value["messages"]:
                        await process_incoming_message(msg, db)
                if "statuses" in value:
                    for status in value["statuses"]:
                        logger.info(f"Message status: {status.get('status')} for {status.get('id')}")
                if "errors" in value:
                    for error in value["errors"]:
                        logger.error(f"WhatsApp error: {error}")
    except Exception as e:
        logger.exception("Error processing webhook")

async def process_incoming_message(msg, db):
    try:
        telefono = msg.get("from")
        message_id = msg.get("id")
        message_type = msg.get("type")
        if not telefono: return

        telefono = normalizar_telefono(telefono)
        contenido = ""; tipo_mensaje = TipoMensaje.TEXTO; metadata = {}

        if message_type == "text":
            contenido = msg.get("text", {}).get("body", "")
        elif message_type == "interactive":
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "list_reply":
                contenido = interactive.get("list_reply", {}).get("id", "")
                metadata["title"] = interactive.get("list_reply", {}).get("title", "")
            elif interactive.get("type") == "button_reply":
                contenido = interactive.get("button_reply", {}).get("id", "")
                metadata["title"] = interactive.get("button_reply", {}).get("title", "")
            tipo_mensaje = TipoMensaje.INTERACTIVO
        elif message_type == "image":
            contenido = msg.get("image", {}).get("caption", "[imagen]")
            metadata["image_id"] = msg.get("image", {}).get("id")
            tipo_mensaje = TipoMensaje.IMAGEN
        elif message_type == "location":
            loc = msg.get("location", {})
            contenido = f"LOC:{loc.get('latitude')},{loc.get('longitude')}"
            metadata["location"] = loc
            tipo_mensaje = TipoMensaje.UBICACION
        elif message_type == "document":
            contenido = msg.get("document", {}).get("caption", "[documento]")
            tipo_mensaje = TipoMensaje.DOCUMENTO
        else:
            contenido = f"[{message_type}]"

        processor = BotProcessor(db, wa_client)
        await processor.procesar_mensaje(telefono=telefono, texto=contenido, message_id=message_id, message_type=message_type, interactive_data=metadata)

        if message_id:
            await wa_client.marcar_leido(message_id)
    except Exception as e:
        logger.exception(f"Error processing message from {telefono}")
        try:
            await wa_client.enviar_texto(telefono, "😅 Ups, algo salió mal. Intenta de nuevo o escribe AYUDA.")
        except Exception:
            pass

# ==========================================
# ADMIN API ENDPOINTS
# ==========================================

@app.get("/admin/stats")
async def admin_stats(db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total_pedidos_hoy = db.query(Pedido).filter(Pedido.created_at >= hoy).count()
    ingresos_hoy = db.query(func.sum(Pedido.total)).filter(Pedido.created_at >= hoy, Pedido.estado != EstadoPedido.CANCELADO).scalar() or Decimal("0.00")
    pedidos_pendientes = db.query(Pedido).filter(Pedido.estado.in_([EstadoPedido.PENDIENTE, EstadoPedido.CONFIRMADO, EstadoPedido.EN_PREPARACION])).count()
    nuevos_clientes = db.query(Cliente).filter(Cliente.created_at >= hoy).count()
    reservas_pendientes = db.query(Reservacion).filter(Reservacion.estado.in_([EstadoReserva.PENDIENTE, EstadoReserva.FASE_DATOS, EstadoReserva.HORA_MESA])).count()

    siete_dias = hoy - timedelta(days=7)
    top_productos = db.query(Producto.nombre_es, func.sum(ItemPedido.cantidad).label("total_vendido")).join(ItemPedido).join(Pedido).filter(Pedido.created_at >= siete_dias, Pedido.estado != EstadoPedido.CANCELADO).group_by(Producto.id).order_by(func.sum(ItemPedido.cantidad).desc()).limit(5).all()

    return {
        "total_pedidos_hoy": total_pedidos_hoy,
        "total_ingresos_hoy": float(ingresos_hoy),
        "pedidos_pendientes": pedidos_pendientes,
        "nuevos_clientes_hoy": nuevos_clientes,
        "reservas_pendientes": reservas_pendientes,
        "productos_mas_vendidos": [{"nombre": p[0], "cantidad": int(p[1])} for p in top_productos]
    }

@app.get("/admin/pedidos")
async def admin_pedidos(estado=None, limit=50, offset=0, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    query = db.query(Pedido).options(joinedload(Pedido.cliente))
    if estado: query = query.filter(Pedido.estado == estado)
    total = query.count()
    pedidos = query.order_by(Pedido.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "pedidos": [{"id": str(p.id), "codigo": p.codigo_pedido, "cliente": p.cliente.nombre or p.cliente.telefono, "telefono": p.cliente.telefono, "estado": p.estado.value, "total": float(p.total), "tipo_entrega": p.tipo_entrega, "created_at": p.created_at.isoformat() if p.created_at else None} for p in pedidos]
    }

@app.patch("/admin/pedidos/{pedido_id}")
async def admin_update_pedido(pedido_id: str, estado: str, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido: raise HTTPException(status_code=404, detail="Pedido no encontrado")
    try: nuevo_estado = EstadoPedido(estado)
    except ValueError: raise HTTPException(status_code=400, detail="Estado invalido")

    pedido.estado = nuevo_estado
    now = datetime.now(timezone.utc)
    if nuevo_estado == EstadoPedido.CONFIRMADO: pedido.confirmado_at = now
    elif nuevo_estado == EstadoPedido.LISTO: pedido.listo_at = now
    elif nuevo_estado == EstadoPedido.ENTREGADO: pedido.entregado_at = now
    elif nuevo_estado == EstadoPedido.CANCELADO: pedido.cancelado_at = now
    db.commit()

    try:
        processor = BotProcessor(db, wa_client)
        idioma = pedido.cliente.idioma_preferido
        estado_msg = {
            EstadoPedido.CONFIRMADO: "✅ Tu pedido ha sido confirmado." if idioma == Idioma.ES else "✅ Votre commande est confirmée." if idioma == Idioma.FR else "✅ الطلبية ديالك تأكدات." if idioma == Idioma.AR else "✅ Your order is confirmed.",
            EstadoPedido.EN_PREPARACION: "👨‍🍳 Tu pedido está en preparación." if idioma == Idioma.ES else "👨‍🍳 Votre commande est en préparation." if idioma == Idioma.FR else "👨‍🍳 الطلبية ديالك كتحضر." if idioma == Idioma.AR else "👨‍🍳 Your order is being prepared.",
            EstadoPedido.LISTO: "🍽️ ¡Tu pedido está listo!" if idioma == Idioma.ES else "🍽️ Votre commande est prête!" if idioma == Idioma.FR else "🍽️ الطلبية ديالك جاهزة!" if idioma == Idioma.AR else "🍽️ Your order is ready!",
            EstadoPedido.EN_CAMINO: "🚚 Tu pedido está en camino." if idioma == Idioma.ES else "🚚 Votre commande est en route." if idioma == Idioma.FR else "🚚 الطلبية ديالك فالطريق." if idioma == Idioma.AR else "🚚 Your order is on the way.",
            EstadoPedido.ENTREGADO: "✅ Pedido entregado. ¡Buen provecho!" if idioma == Idioma.ES else "✅ Commande livrée. Bon appétit!" if idioma == Idioma.FR else "✅ الطلبية وصلات. بالصحة!" if idioma == Idioma.AR else "✅ Order delivered. Enjoy!",
            EstadoPedido.CANCELADO: "❌ Tu pedido ha sido cancelado." if idioma == Idioma.ES else "❌ Votre commande a été annulée." if idioma == Idioma.FR else "❌ الطلبية cancelات." if idioma == Idioma.AR else "❌ Your order has been cancelled."
        }.get(nuevo_estado, f"Estado actualizado: {nuevo_estado.value}")
        await wa_client.enviar_texto(pedido.cliente.telefono, estado_msg)
    except Exception as e:
        logger.error(f"Error notificando cliente: {e}")

    return {"status": "updated", "pedido_id": pedido_id, "nuevo_estado": estado}

@app.get("/admin/reservaciones")
async def admin_reservaciones(estado=None, fecha=None, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    query = db.query(Reservacion).options(joinedload(Reservacion.cliente))
    if estado: query = query.filter(Reservacion.estado == estado)
    if fecha:
        try:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
            query = query.filter(Reservacion.hora_reserva >= fecha_dt, Reservacion.hora_reserva < fecha_dt + timedelta(days=1))
        except ValueError: pass
    reservaciones = query.order_by(Reservacion.hora_reserva).all()
    return {
        "reservaciones": [{"id": str(r.id), "codigo": r.codigo_reserva, "cliente": r.nombre_reserva or r.cliente.nombre or r.cliente.telefono, "telefono": r.cliente.telefono, "num_personas": r.num_personas, "hora": r.hora_reserva.isoformat() if r.hora_reserva else None, "mesa": r.mesa_asignada, "zona": r.zona, "estado": r.estado.value, "ai_confirmada": r.ai_confirmada} for r in reservaciones]
    }

@app.patch("/admin/reservaciones/{reserva_id}")
async def admin_update_reserva(reserva_id: str, estado=None, mesa=None, confirmada_manual=None, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    reserva = db.query(Reservacion).filter(Reservacion.id == reserva_id).first()
    if not reserva: raise HTTPException(status_code=404, detail="Reserva no encontrada")
    if estado:
        try: reserva.estado = EstadoReserva(estado)
        except ValueError: raise HTTPException(status_code=400, detail="Estado invalido")
    if mesa: reserva.mesa_asignada = mesa
    if confirmada_manual is not None:
        reserva.confirmada_manual = confirmada_manual
        reserva.confirmada_manual_at = datetime.now(timezone.utc)
        reserva.confirmada_manual_por = "admin"
        if confirmada_manual: reserva.estado = EstadoReserva.CONFIRMADA
    db.commit()

    try:
        if reserva.estado == EstadoReserva.CONFIRMADA:
            idioma = reserva.cliente.idioma_preferido
            fecha_str = reserva.hora_reserva.strftime("%d/%m/%Y %H:%M") if reserva.hora_reserva else ""
            mensaje = obtener_mensaje("reserva_confirmada_ai", idioma, codigo=reserva.codigo_reserva, fecha_hora=fecha_str, num_personas=reserva.num_personas, mesa=reserva.mesa_asignada or "Asignada", zona=reserva.zona or "Principal", nombre=reserva.nombre_reserva or "Cliente")
            await wa_client.enviar_texto(reserva.cliente.telefono, mensaje)
    except Exception as e:
        logger.error(f"Error notificando cliente de reserva: {e}")

    return {"status": "updated", "reserva_id": reserva_id}

@app.get("/admin/clientes")
async def admin_clientes(search=None, tipo=None, limit=50, offset=0, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    query = db.query(Cliente)
    if search: query = query.filter((Cliente.telefono.ilike(f"%{search}%")) | (Cliente.nombre.ilike(f"%{search}%")) | (Cliente.apellido.ilike(f"%{search}%")))
    if tipo:
        try: query = query.filter(Cliente.tipo == TipoCliente(tipo))
        except ValueError: pass
    total = query.count()
    clientes = query.order_by(Cliente.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "clientes": [{"id": str(c.id), "telefono": c.telefono, "nombre": c.nombre, "apellido": c.apellido, "idioma": c.idioma_preferido.value if c.idioma_preferido else None, "tipo": c.tipo.value if c.tipo else None, "visitas": c.visitas_count, "total_gastado": float(c.total_gastado) if c.total_gastado else 0, "ultima_visita": c.ultima_visita.isoformat() if c.ultima_visita else None, "created_at": c.created_at.isoformat() if c.created_at else None} for c in clientes]
    }

@app.get("/admin/productos")
async def admin_productos(categoria_id=None, disponible=None, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    query = db.query(Producto).options(joinedload(Producto.categoria))
    if categoria_id: query = query.filter(Producto.categoria_id == categoria_id)
    if disponible is not None: query = query.filter(Producto.disponible == disponible)
    productos = query.order_by(Producto.orden).all()
    return {
        "productos": [{"id": str(p.id), "nombre": p.nombre_es, "nombre_fr": p.nombre_fr, "nombre_ar": p.nombre_ar, "precio": float(p.precio), "disponible": p.disponible, "categoria": p.categoria.nombre_es if p.categoria else None, "stock": p.stock_actual if not p.stock_ilimitado else None} for p in productos]
    }

@app.patch("/admin/productos/{producto_id}")
async def admin_update_producto(producto_id: str, disponible=None, precio=None, stock=None, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto: raise HTTPException(status_code=404, detail="Producto no encontrado")
    if disponible is not None: producto.disponible = disponible
    if precio is not None: producto.precio = Decimal(str(precio))
    if stock is not None:
        producto.stock_actual = stock
        if stock <= 0 and not producto.stock_ilimitado: producto.disponible = False
    db.commit()
    return {"status": "updated", "producto_id": producto_id}

# ==========================================
# PUBLIC API (Clientes)
# ==========================================

@app.get("/api/menu")
async def public_menu(idioma="es", db: Session = Depends(get_db)):
    try: lang = Idioma(idioma)
    except ValueError: lang = Idioma.ES

    categorias = db.query(Categoria).filter(Categoria.activa == True).order_by(Categoria.orden).all()
    resultado = []
    for cat in categorias:
        productos = db.query(Producto).filter(Producto.categoria_id == cat.id, Producto.disponible == True).order_by(Producto.orden).all()
        cat_data = {
            "id": str(cat.id),
            "nombre": cat.nombre_es if lang == Idioma.ES else cat.nombre_fr if lang == Idioma.FR and cat.nombre_fr else cat.nombre_ar if lang == Idioma.AR and cat.nombre_ar else cat.nombre_es,
            "emoji": cat.emoji,
            "productos": [{"id": str(p.id), "nombre": p.nombre_es if lang == Idioma.ES else p.nombre_fr if lang == Idioma.FR and p.nombre_fr else p.nombre_ar if lang == Idioma.AR and p.nombre_ar else p.nombre_es, "descripcion": p.descripcion_es if lang == Idioma.ES else p.descripcion_fr if lang == Idioma.FR and p.descripcion_fr else p.descripcion_ar if lang == Idioma.AR and p.descripcion_ar else p.descripcion_es, "precio": float(p.precio), "imagen": p.imagen_url, "tiempo_preparacion": p.tiempo_preparacion_min} for p in productos]
        }
        resultado.append(cat_data)
    return {"menu": resultado}

@app.get("/api/estado-pedido/{codigo}")
async def public_estado_pedido(codigo: str, db: Session = Depends(get_db)):
    pedido = db.query(Pedido).filter(Pedido.codigo_pedido == codigo).first()
    if not pedido: raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return {
        "codigo": pedido.codigo_pedido,
        "estado": pedido.estado.value,
        "total": float(pedido.total),
        "tipo_entrega": pedido.tipo_entrega,
        "created_at": pedido.created_at.isoformat() if pedido.created_at else None,
        "confirmado_at": pedido.confirmado_at.isoformat() if pedido.confirmado_at else None,
        "listo_at": pedido.listo_at.isoformat() if pedido.listo_at else None,
        "entregado_at": pedido.entregado_at.isoformat() if pedido.entregado_at else None
    }

# ==========================================
# HEALTH & INFO
# ==========================================

@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "environment": "production" if not settings.DEBUG else "development",
        "business": settings.BUSINESS_NAME,
        "features": ["whatsapp_bot", "multilingual_es_fr_ar_en", "persistent_cart", "reservations", "admin_dashboard", "rate_limiting", "order_tracking"]
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=settings.DEBUG, log_level="debug" if settings.DEBUG else "info")

