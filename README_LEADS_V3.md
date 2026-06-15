# 🎯 Leads Scrap → Neon → Bot ISA (V3 - Estrategia Francotirador)

## ✅ Novedades V3

| Feature | Descripción |
|---------|-------------|
| **Casos A-G** | Clasificación automática de leads según perfil digital |
| **Mensajes por Caso** | Cada caso tiene mensajes personalizados de scrap.txt |
| **Pack recomendado** | Presencia (250), WA Pro (400), Automatización (800), Completo (1200) |
| **Precio automático** | Cada lead tiene precio recomendado según su caso |
| **Endpoint /por-caso** | Dashboard de distribución por clasificación |
| **Comando /caso** | Bot filtra leads por Caso A-G |
| **Comando /estrategia** | Muestra resumen de estrategias por caso |

---

## 🎲 Sistema de Casos A-G (Estrategia Francotirador)

| Caso | Nombre | Condición | Pack | Precio | Ángulo de venta |
|------|--------|-----------|------|--------|-----------------|
| **A** | El Fantasma | Sin web, buen rating (≥4.0) | Presencia | 250 MAD | "No tener web = no tener carta" |
| **B** | El Influencer Cojo | Sin web, rating bajo (<4.0) | Completo | 1,200 MAD | "Necesita todo: presencia + reputación" |
| **C** | El Desactualizado | Web + rating bajo (<4.0) | Completo | 1,200 MAD | "Garantía 30 días o devolución" |
| **D** | El WhatsApp Caótico | Web + WA roto | WhatsApp Pro | 400 MAD | "Web bonita pero puerta cerrada" |
| **E** | La Mina de Oro | Web + buen rating + ≥500 reviews | Automatización | 800 MAD | "Ya tienen clientes, falta sistema" |
| **F** | El Semi-Digital | Web + rating medio + <100 reviews | Presencia Plus | 400 MAD | "Tienen estructura, falta visibilidad" |
| **G** | El Inalcanzable | Sin teléfono | Ninguno | 0 MAD | Buscar contacto alternativo |

---

## 📁 Archivos V3

| Archivo | Descarga |
|---------|----------|
| SQL Migration | [001_migration_leads_scrap_v3.sql](sandbox:///mnt/agents/output/001_migration_leads_scrap_v3.sql) |
| Endpoints FastAPI | [leads_router_v3.py](sandbox:///mnt/agents/output/leads_router_v3.py) |
| Bot WhatsApp | [leads_bot_handler_v3.py](sandbox:///mnt/agents/output/leads_bot_handler_v3.py) |

---

## 🚀 Instalación

### 1. Migración SQL
```bash
psql $DATABASE_URL -f 001_migration_leads_scrap_v3.sql
```

### 2. Integrar FastAPI
```python
from leads_router_v3 import router as leads_router
app.include_router(leads_router)
```

### 3. Integrar Bot
```python
from leads_bot_handler_v3 import LeadBotHandler, WhatsAppAPI

wa_api = WhatsAppAPI(
    phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
    access_token=os.getenv("WHATSAPP_ACCESS_TOKEN")
)
lead_handler = LeadBotHandler(wa_api, ADMIN_PHONE="+212XXXXXXXXX")
```

---

## 💬 Comandos del Bot (V3)

| Comando | Qué hace |
|---------|----------|
| `lead` | Muestra siguiente lead con **Caso, Pack y Precio** |
| `si` | Envía mensaje REAL por WhatsApp (valida teléfono primero) |
| `no` | Cancela y pasa al siguiente |
| `caso A` | Muestra leads del Caso A (Fantasma) |
| `caso E` | Muestra leads del Caso E (Mina de Oro) |
| `estrategia` | Muestra resumen de todas las estrategias |
| `lead stats` | Resumen con distribución por Caso |
| `lead info 5` | Info detallada incluyendo Caso y Pack |
| `seguimiento` | Ejecuta D2/D5/D10 automático |
| `help` | Ayuda completa |

---

## 📡 Endpoints API

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/leads/cargar` | POST | Subir Excel con clasificación automática |
| `/api/v1/leads/` | GET | Listar con filtros (incluye `caso`, `estrategia`) |
| `/api/v1/leads/por-caso` | GET | Distribución por Caso A-G |
| `/api/v1/leads/prioritarios` | GET | Score ≥ 60 |
| `/api/v1/leads/next` | GET | Siguiente lead + mensaje por Caso |
| `/api/v1/leads/{id}/mensaje` | POST | Generar mensaje según Caso del lead |
| `/api/v1/leads/{id}/contactar` | POST | Marcar contactado |
| `/api/v1/leads/{id}/respuesta` | POST | Registrar respuesta |
| `/api/v1/leads/seguimiento-automatico` | POST | D2/D5/D10 |
| `/api/v1/leads/stats/resumen` | GET | Dashboard con casos |

---

## 📝 Ejemplo de mensaje generado (Caso E - Mina de Oro)

> **Hola Restaurant Sed Nakhla! 👋**
>
> Soy Isa de Orchestrator ISA. Veo que Restaurant Sed Nakhla es muy popular en Google Maps (¡1,645 reseñas!). Mi sistema no es para que los encuentren (ya los encuentran), es para automatizar las reservas y pedidos que ya reciben y que su WhatsApp no colapse. Puedo ayudarles a gestionar ese volumen desde 800 MAD. ¿Tienen 5 minutos para una demo?

---

## 📝 Ejemplo de mensaje generado (Caso D - WhatsApp Caótico)

> **Hola مقهى الأمل! 👋**
>
> Soy Isa. Noté que tienen una web muy bonita, pero el link de WhatsApp no funciona. El 67% de los clientes abandonan si no reciben respuesta en 5 minutos. Tener la web con el WhatsApp roto es como tener la puerta del local cerrada. En 48 horas les conecto el Pack WhatsApp Pro (400 MAD) para que no pierdan ni un pedido.

---

## 🔥 Flujo completo

```
1. Subes Excel → Se clasifica automáticamente en Casos A-G
2. Escribes "lead" al bot → Muestra:
   - Nombre, Score, Temperatura
   - 🎲 Caso: Mina de Oro (E)
   - 💰 Pack: Automatización (800 MAD)
   - 📞 Teléfono válido ✅
   - 💬 Mensaje personalizado por Caso
3. Escribes "si" → Valida teléfono → Envía por WhatsApp → Marca contactado
4. [Día 2] Sin respuesta → Seguimiento D2 automático
5. [Día 5] Sin respuesta → Seguimiento D5
6. [Día 10] Sin respuesta → Seguimiento D10 → Descartado
```

---

## 🎯 Próximos pasos

1. Ejecutar migración SQL V3 en Neon
2. Integrar router y bot handler
3. Subir Excel de Outscraper → se clasifica automáticamente
4. Escribir "lead" al bot y empezar a contactar 🔥 hot leads con mensajes perfectos
5. Usar `caso E` para atacar primero las Minas de Oro (mayor ticket)
