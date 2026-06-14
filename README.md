# 🚀 Orchestrator ISA OS v13.2

Sistema de gestión de leads, cotizaciones, referidos y scraping para negocios en Marruecos.

**Stack:** FastAPI + asyncpg + PostgreSQL/Neon + Puppeteer + Render

---

## 📁 Estructura

```
orchestrator-isa-os/
├── main.py                 # Backend FastAPI (async, DB real, routers integrados)
├── api/
│   ├── api_cotizar.py      # Cotizaciones con packs detallados
│   ├── referidos.py        # Sistema de referidos con comisiones
│   ├── reportes.py         # Reportes de leads, cotizaciones y financiero
│   └── scraping.py         # Control de jobs de scraping con background tasks
├── scripts/
│   └── scraper.js          # Scraper de Google Maps (selectores robustos)
├── templates/              # Portal HTML (Jinja2)
│   ├── portal.html
│   ├── portal_leads.html   # CRUD completo con modal
│   ├── portal_dashboard.html # Gráficos y embudo
│   └── ...
├── static/                 # Assets PWA
├── package.json            # Dependencias Node.js (Puppeteer 24+)
├── requirements.txt        # Dependencias Python (asyncpg + FastAPI)
├── render.yaml             # Config Render.com con DB y health check
└── .env.example            # Variables de entorno documentadas
```

---

## 🚀 Deploy en Render (1 click)

1. **Fork/push** este repo a GitHub
2. En Render: **New → Blueprint**
3. Selecciona el repo → Render detecta `render.yaml`
4. Configura `DATABASE_URL` si usas Neon externo
5. Deploy automático con health check

---

## 🖥️ Desarrollo local

```bash
# 1. Python
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Node.js (para scraper)
npm install

# 3. Base de datos
cp .env.example .env
# Edita DATABASE_URL en .env (Neon o local PostgreSQL)

# 4. Iniciar servidor
python main.py
# → http://localhost:8000

# 5. Probar scraper
npm run scrape:tetouan
npm run scrape:tanger
```

---

## 🔌 API Completa

### Leads (Legacy en main.py)
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/leads` | Crear lead |
| GET | `/api/leads` | Listar leads (filtro: `?estado=prospeccion`) |
| GET | `/api/leads/{id}` | Obtener lead |
| PATCH | `/api/leads/{id}` | Actualizar lead |
| DELETE | `/api/leads/{id}` | Eliminar lead |

### Cotizaciones (`/api/cotizar`)
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/cotizar/` | Crear cotización con cálculo automático |
| GET | `/api/cotizar/packs` | Listar todos los packs con precios |
| GET | `/api/cotizar/historial` | Historial de cotizaciones |
| PATCH | `/api/cotizar/{id}` | Actualizar estado/descuento |

### Referidos (`/api/referidos`)
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/referidos/` | Registrar nuevo referido |
| GET | `/api/referidos/` | Listar referidos |
| GET | `/api/referidos/{id}` | Obtener referido |
| PATCH | `/api/referidos/{id}` | Actualizar estado/comisión |
| GET | `/api/referidos/estadisticas/resumen` | Stats de referidos |
| GET | `/api/referidos/codigo/{codigo}` | Verificar código |

### Reportes (`/api/reportes`)
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/reportes/leads` | Reporte de leads (agrupar por estado/ciudad/etc) |
| GET | `/api/reportes/cotizaciones` | Reporte de cotizaciones |
| GET | `/api/reportes/financiero` | Reporte financiero mensual |
| GET | `/api/reportes/scraping` | Efectividad del scraping |

### Scraping (`/api/scraping`)
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/scraping/ejecutar` | Ejecutar scraper en background |
| GET | `/api/scraping/status/{job_id}` | Estado del job |
| GET | `/api/scraping/jobs` | Listar jobs |
| GET | `/api/scraping/resultados/{job_id}` | Resultados JSON |
| GET | `/api/scraping/archivos` | Listar archivos CSV/JSON |
| DELETE | `/api/scraping/archivos/{nombre}` | Eliminar archivo |
| GET | `/api/scraping/config` | Configuración disponible |

### General
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/` | Portal principal |
| GET | `/portal/*` | Vistas del portal |
| GET | `/api/dashboard` | Métricas agregadas |
| GET | `/api/scraping/status` | Estado del scraper (legacy) |
| GET | `/health` | Health check con DB |

---

## 📊 Packs y Precios

| Pack | Entrada (MAD) | Mantenimiento (MAD) | Descripción |
|------|---------------|---------------------|-------------|
| **Presencia Digital** | 250 | 150 | Landing + Redes sociales básicas |
| **WhatsApp Pro** | 400 | 200 | Bot de pedidos + catálogo |
| **Automatización** | 800 | 350 | Flujos automáticos + API |
| **Pack Completo** | 1200 | 500 | Solución integral + PWA |

---

## 🛡️ Correcciones sobre la propuesta original

| Aspecto | Propuesta original | Versión corregida |
|---------|-------------------|-------------------|
| DB | `leads_db = []` (memoria) | **asyncpg + PostgreSQL/Neon** con tablas reales |
| TemplateRenderer | No existe en FastAPI | **Jinja2Templates** correcto |
| IDs | No se asignaban | **SERIAL PRIMARY KEY** autoincremental |
| Selectores scraper | `.hfpxzc` frágil | **Múltiples fallbacks** + robustez |
| CORS | No había | **Middleware CORS** configurado |
| Health check | No había | **Endpoint `/health`** con check de DB |
| Variables entorno | Hardcodeadas | **`os.getenv`** + `.env.example` |
| Dashboard | Métricas básicas | **Gráficos de barras, embudo, por ciudad/pack** |
| Leads UI | Datos de ejemplo | **CRUD completo** con modal de creación |
| Cotizaciones | Endpoint simple | **Packs detallados** + historial + descuentos |
| Referidos | No existía | **Sistema completo** con códigos y comisiones |
| Reportes | No existía | **4 tipos de reportes** con agrupaciones |
| Scraping API | Solo status | **Jobs async** + resultados + gestión de archivos |

---

## 📱 PWA

El portal es una Progressive Web App. En Chrome:
**⋮ → Más herramientas → Crear acceso directo...** (o "Agregar a pantalla de inicio" en móvil)

---

## 📄 Licencia

MIT — Orchestrator ISA
