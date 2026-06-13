# 🚀 Orchestrator ISA OS v3.0 (AI-Powered)

## Sistema Operativo de Ventas y Digitalización

**Transforma documentos estáticos en un sistema ejecutable.**

---

## 📊 ANÁLISIS: v2.0 vs v3.0

### ✅ Lo que YA TIENE (v2.0 → v3.0 base)

| Módulo | Estado | Descripción |
|--------|--------|-------------|
| Validador de Negocios | ✅ | Score 0-10, 5 preguntas, pack recomendado |
| Generador de Cotizaciones | ✅ | HTML profesional en 2 segundos |
| CRM de Leads | ✅ | 15 estados del funnel completo |
| Dashboard KPIs | ✅ | Ingresos, tasa de cierre, progreso meta |
| PWA Móvil | ✅ | App nativa desde el navegador |
| Speeches por Nicho | ✅ | 12 tipos de negocio con copy personalizado |

### 🆕 Lo que SE AGREGÓ en v3.0

| Módulo | Estado | Descripción |
|--------|--------|-------------|
| **FASE 0: Scraping** | ✅ | Clasificación A/B/C/D/E de negocios |
| **Sistema de Referidos** | ✅ | Tracking + descuento 100 MAD automático |
| **Reportes Mensuales** | ✅ | HTML auto-generado para clientes |
| **Motor de Copywriting** | 🔄 | Integración OpenAI (próximo sprint) |
| **Video Hero IA** | 🔄 | Runway/Kling (próximo sprint) |
| **Automatización WA** | 🔄 | n8n/Make.com (próximo sprint) |

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│  CAPA DE PRESENTACIÓN                                       │
│  ├─ PWA Móvil (web/index.html)                              │
│  └─ Cotizaciones HTML (static/cotizaciones/)                │
├─────────────────────────────────────────────────────────────┤
│  CAPA DE API (api/main.py)                                  │
│  ├─ /api/validar → Score + Pack + Speech                    │
│  ├─ /api/cotizar → HTML cotización                          │
│  ├─ /api/leads → CRM completo                               │
│  ├─ /api/dashboard → KPIs                                   │
│  ├─ /api/seguimiento → Programar seguimientos               │
│  └─ /api/health → Health check                              │
├─────────────────────────────────────────────────────────────┤
│  MÓDULOS AUXILIARES                                         │
│  ├─ api/scraping.py → Clasificación A/B/C/D/E               │
│  ├─ api/referidos.py → Sistema de referidos                 │
│  ├─ api/reportes.py → Reportes mensuales auto               │
│  └─ api/validador_negocios.py → Script CLI legacy           │
├─────────────────────────────────────────────────────────────┤
│  BASE DE DATOS                                              │
│  ├─ leads (estados, scores, precios)                        │
│  ├─ cotizaciones (historial)                                │
│  ├─ seguimientos (programados)                              │
│  ├─ actividades (log)                                       │
│  └─ referidos (tracking)                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Instalación Rápida

### Opción 1: Render (Recomendado)

```bash
# 1. Sube a GitHub
git init
git add .
git commit -m "v3.0 AI-Powered"
git push origin main

# 2. En Render Dashboard → New Web Service → Connect GitHub
# 3. Render detecta render.yaml automáticamente
# 4. URL: https://orchestrator-isa-os.onrender.com
```

### Opción 2: Local

```bash
cd orchestrator-isa-os
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd api && uvicorn main:app --reload
# Abrir: http://localhost:8000
```

---

## 📱 Flujo de Uso (Desde la Calle)

### FASE 0: Antes de Salir (Scraping)
```
1. Extraes negocios de Google Maps (CSV)
2. Ejecutas: python api/scraping.py
3. El sistema clasifica: A/B/C/D/E
4. Priorizas: Casos A, B, E (urgentes)
```

### FASE 1: En la Calle (Validación)
```
1. Abres PWA en el móvil
2. Llenas: nombre, tipo, 5 preguntas (30 seg)
3. El sistema dice: "Score 8/10 → Pack Completo → 1,200 MAD"
4. Lees speech personalizado al dueño
5. Si interesa → Generas cotización → Compartes por WA
```

### FASE 2: Post-Venta (Mantenimiento)
```
1. Ejecutas servicio en 24-72h
2. Generas reporte mensual: python api/reportes.py
3. Envías reporte al cliente por WhatsApp
4. Mes 2+ → Pides referido → Descuento 100 MAD
```

---

## 🔧 Endpoints API

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/validar` | POST | Validar negocio, devuelve score y pack |
| `/api/cotizar` | POST | Generar cotización HTML |
| `/api/leads` | GET | Listar leads (filtro por estado) |
| `/api/leads/{id}` | GET | Detalle de lead |
| `/api/leads/{id}/estado` | POST | Cambiar estado |
| `/api/dashboard` | GET | KPIs del sistema |
| `/api/seguimiento` | POST | Registrar seguimiento |
| `/api/seguimientos/pendientes` | GET | Pendientes por enviar |
| `/api/health` | GET | Health check |

---

## ⚠️ CORRECCIONES CRÍTICAS APLICADAS

| Problema | Solución |
|----------|----------|
| SQLite en Render (datos se pierden) | **MIGRAR A NEON** antes de producción |
| render.yaml incompleto | Corregido: buildCommand + startCommand + healthCheck |
| Sin autenticación | Agregar `X-API-Key` header en producción |
| PWA sin manejo de errores | Mejorar con try/catch y mensajes de error |

---

## 🎯 Próximos Sprints

### Sprint 2: Automatización
- [ ] Integración n8n/Make.com para seguimientos automáticos
- [ ] WhatsApp Business API webhook
- [ ] Scheduler para reportes mensuales

### Sprint 3: Motor IA
- [ ] OpenAI GPT-4 para copywriting automático
- [ ] Generación de catálogos con IA
- [ ] Análisis de sentimiento de mensajes

### Sprint 4: Escalado
- [ ] PostgreSQL/Neon para producción
- [ ] Autenticación JWT
- [ ] Multi-tenant (varios vendedores)

# 🚀 Orchestrator ISA - Sistema Operativo de Ventas

Digitalización inteligente para negocios locales en Marruecos.

## 📊 Estado del Proyecto
- ✅ Portal de ventas completo
- ✅ 10 nichos objetivo identificados
- ✅ Scripts de venta personalizados
- ✅ Sistema de seguimiento automatizado
- ⏳ Dashboard de métricas (en desarrollo)
- ⏳ CRM integrado (en desarrollo)

## 🚀 Quick Start
```bash
# Clonar repositorio
git clone https://github.com/orchestrator-isa/orchestrator-isa-os.git

# Instalar dependencias
npm install

# Iniciar servidor de desarrollo
npm run dev
---

**Orchestrator ISA v3.0** | De documentos a sistema operativo

WhatsApp: +212 786 120 081 | orchestrator.isa@gmail.com
