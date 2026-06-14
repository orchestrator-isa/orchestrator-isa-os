# 🚀 Orchestrator ISA v13.4 — Migración Guide

## Novedades en v13.4

### 🔐 Autenticación (NUEVO)
- Tabla `usuarios` con roles `admin` | `vendedor`
- Tabla `sesiones` con cookies HTTP-only
- Login en `/login` → redirige a `/vendedor/venta`
- Middleware `@require_auth` y `@require_admin`
- Usuario admin por defecto: `admin` / `admin123`

### 🎯 Panel Vendedor `/vendedor/venta` (NUEVO)
- **Diagrama interactivo M0→M7** con nodos circulares clickeables
- **Selector de lead** con carga dinámica desde `/api/leads`
- **Speeches personalizados** por caso A-G con variables `{nombre}`, `{tipo_negocio}`, etc.
- **Botón 📋 Copiar** al portapapeles (Clipboard API)
- **Botón 📤 Enviar por WhatsApp** (`wa.me/{telefono}?text=...`)
- **Formulario de auditoría M3** con 5 preguntas → calcula score → clasifica caso A-G
- **Packs recomendados** filtrados por caso (solo muestra el recomendado destacado)
- **Persistencia de progreso** en `lead_historial` (momentos completados)
- **Navegación secuencial** M0→M1→M2... no se puede saltar
- **Propuesta de cierre M7** con cálculo automático de 50% anticipo
- **Responsive** optimizado para móvil (calle) y desktop (scraping)

### 🔄 Renovaciones Automáticas (NUEVO)
- Columnas nuevas en `leads`: `fecha_inicio_mantenimiento`, `pack_contratado`, `precio_mantenimiento_mensual`, `proxima_renovacion`
- Endpoint `GET /api/renovaciones/pendientes` — leads que renuevan en N días
- Endpoint `POST /api/leads/{id}/renovacion` — genera cotización de renovación
- Alerta en dashboard de renovaciones próximas

### 📊 Casos A-G + 7 Packs
| Caso | Nombre | Pack | Precio |
|------|--------|------|--------|
| A | El Fantasma | Base | 900 MAD |
| B | El Influencer Cojo | Base | 900 MAD |
| C | El Desactualizado | Completo | 1,200 MAD |
| D | El WhatsApp Caótico | WhatsApp Pro | 400 MAD |
| E | La Mina de Oro | Conversión | 2,500 MAD |
| F | El Semi-Digital | Automatización | 800 MAD |
| G | El Competidor Digital | — (No cliente) | — |

---

## 📁 Archivos Generados

```
/mnt/agents/output/
├── main_v13_4.py          ← Reemplaza tu main.py actual
├── login.html             ← Nuevo: página de login
├── portal_vendedor.html   ← Nuevo: panel de venta M0-M7
└── README_v13_4.md        ← Este archivo
```

---

## 🔧 Instalación

### 1. Reemplazar main.py
```bash
# Backup primero
cp main.py main_v13_3_backup.py

# Copiar nuevo
cp main_v13_4.py main.py
```

### 2. Copiar templates
```bash
# Crear si no existe
mkdir -p templates

# Copiar templates nuevos
cp login.html templates/
cp portal_vendedor.html templates/
```

### 3. Instalar dependencias (sin cambios)
```bash
pip install fastapi uvicorn jinja2 asyncpg pydantic
```

### 4. Variables de entorno (.env)
```bash
DATABASE_URL=postgresql://user:pass@host.neon.tech/db?sslmode=require
SECRET_KEY=tu_clave_secreta_aqui
PORT=8000
```

### 5. Migrar DB (automático)
El `lifespan` crea las nuevas tablas automáticamente al iniciar:
- `usuarios`
- `sesiones`
- Columnas nuevas en `leads`

### 6. Crear primer vendedor
```bash
curl -X POST http://localhost:8000/api/usuarios   -H "Content-Type: application/json"   -u admin:admin123   -d '{"username":"vendedor1","password":"pass123","nombre_display":"Isa","rol":"vendedor"}'
```

---

## 🚀 Uso

### Acceder al sistema
1. Ir a `http://localhost:8000/login`
2. Login con `admin` / `admin123`
3. Redirige automáticamente a `/vendedor/venta`

### Flujo de venta
1. **Seleccionar lead** del dropdown (o crear nuevo en `/portal/leads`)
2. **Hacer clic en M0** → confirmar preparación
3. **M1** → copiar speech personalizado → enviar por WA
4. **M2** → si pregunta precio, usar frases de desviación
5. **M3** → responder 5 preguntas → sistema clasifica caso A-G
6. **M4** → presentar diagnóstico con pérdidas estimadas
7. **M5** → mostrar packs (el recomendado destacado)
8. **M6** → manejar dudas con ejemplos USA
9. **M7** → generar propuesta → cerrar venta

### Landings públicas (sin login)
- `/l/p` — IA Boost Prufer (partners)
- `/l/w` — Web Express (clientes webs)

---

## 🔐 Seguridad

- Cookies HTTP-only + SameSite=Lax
- Contraseñas hasheadas con SHA-256 + SECRET_KEY
- Sesiones expiran en 7 días
- Roles: `admin` (CRUD usuarios) | `vendedor` (solo ventas)
- Todo el portal protegido excepto landings y login

---

## 📋 Próximos pasos (v13.5)

- [ ] WhatsApp Cloud API webhook (cuando Meta apruebe)
- [ ] Scheduler de seguimientos automáticos (D2, D5, D10, D30)
- [ ] OpenAI GPT-4 para speeches dinámicos
- [ ] Notificaciones push/email
- [ ] JWT tokens (reemplazar cookies simples)
- [ ] Multi-idioma en panel vendedor (ES/AR/FR/EN)

---

**Versión:** 13.4.0 | **Stack:** FastAPI + asyncpg + Neon + Jinja2 | **Marruecos 2026**
