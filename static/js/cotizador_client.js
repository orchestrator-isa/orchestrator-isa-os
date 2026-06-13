// === CLIENTE JS PARA CONECTAR COTIZADOR CON API ===
// Guardar en: static/js/cotizador_client.js

const API_BASE = window.location.origin; // o 'https://tu-api.render.com'

/**
 * Genera una cotización vía API y devuelve HTML + resumen
 * @param {Object} data - Datos del formulario
 */
async function generarCotizacionAPI(data) {
    try {
        const response = await fetch(`${API_BASE}/api/cotizar`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Error generando cotización');
        }

        const result = await response.json();

        // Guardar en localStorage para referencia
        localStorage.setItem('isa_last_cotizacion', JSON.stringify({
            id: result.cotizacion_id,
            negocio: data.negocio,
            total: result.resumen.total_entrada,
            fecha: result.fecha
        }));

        return result;

    } catch (error) {
        console.error('Error:', error);
        throw error;
    }
}

/**
 * Envía cotización por WhatsApp usando la URL pre-armada del backend
 * @param {string} whatsappUrl - URL generada por el backend
 */
function enviarWhatsApp(whatsappUrl) {
    window.open(whatsappUrl, '_blank');
}

/**
 * Descarga la cotización como archivo HTML
 * @param {string} html - Contenido HTML
 * @param {string} filename - Nombre del archivo
 */
function descargarCotizacion(html, filename) {
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'cotizacion.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/**
 * Obtiene los datos del formulario del cotizador HTML
 */
function obtenerDatosFormulario() {
    // Leer selección del catálogo (localStorage)
    const packData = JSON.parse(localStorage.getItem('isa_selected_pack') || 'null');
    const microsData = JSON.parse(localStorage.getItem('isa_selected_micros') || '[]');

    // Leer datos del formulario
    return {
        negocio: document.getElementById('negocio').value,
        tipo: document.getElementById('tipo').value,
        dueno: document.getElementById('dueno').value,
        telefono: document.getElementById('telefono').value,
        email: document.getElementById('email').value,
        ciudad: document.getElementById('ciudad').value,
        pack: packData ? packData.pack : null,
        micros: microsData,
        notas: document.getElementById('notas').value,
        descuento: 0 // Se puede agregar campo de descuento
    };
}

/**
 * Actualiza el resumen lateral con los datos de la API
 */
function actualizarResumenAPI(resumen) {
    document.getElementById('resPack').textContent = resumen.pack_nombre || '—';
    document.getElementById('resPackPrice').textContent = `${resumen.pack_precio} MAD`;
    document.getElementById('resMicrosCount').textContent = `${resumen.micros_cantidad} items`;
    document.getElementById('resMicrosPrice').textContent = `${resumen.micros_total} MAD`;
    document.getElementById('resTotal').textContent = `${resumen.total_entrada} MAD`;
    document.getElementById('resMant').textContent = `${resumen.mantenimiento_mensual} MAD/mes`;
}

// === INTEGRACIÓN CON BOTONES DEL COTIZADOR ===

// Reemplazar la función generarCotizacion() del portal_cotizador.html
// con esta versión que usa la API:

async function generarCotizacionBackend() {
    const negocio = document.getElementById('negocio').value;
    const telefono = document.getElementById('telefono').value;

    if (!negocio || !telefono) {
        showToast('⚠️ Completá nombre del negocio y teléfono');
        return;
    }

    const packData = JSON.parse(localStorage.getItem('isa_selected_pack') || 'null');
    const microsData = JSON.parse(localStorage.getItem('isa_selected_micros') || '[]');

    if (!packData && microsData.length === 0) {
        showToast('⚠️ Seleccioná al menos un pack o microservicio');
        return;
    }

    showToast('⏳ Generando cotización...');

    try {
        const data = {
            negocio: negocio,
            tipo: document.getElementById('tipo').value || 'negocio local',
            dueno: document.getElementById('dueno').value,
            telefono: telefono,
            email: document.getElementById('email').value,
            ciudad: document.getElementById('ciudad').value || 'Marruecos',
            pack: packData ? packData.pack : null,
            micros: microsData,
            notas: document.getElementById('notas').value,
            descuento: 0
        };

        const result = await generarCotizacionAPI(data);

        // Actualizar resumen con datos reales del backend
        actualizarResumenAPI(result.resumen);

        // Descargar HTML
        descargarCotizacion(result.html, `cotizacion_${result.cotizacion_id}.html`);

        // Guardar URL de WhatsApp para el botón de enviar
        window._lastWhatsappUrl = result.whatsapp_url;
        window._lastCotizacionId = result.cotizacion_id;

        showToast(`✅ Cotización ${result.cotizacion_id} generada`);

    } catch (error) {
        showToast(`❌ ${error.message}`);
    }
}

// Reemplazar enviarWhatsApp() para usar la URL del backend
function enviarWhatsAppBackend() {
    if (window._lastWhatsappUrl) {
        window.open(window._lastWhatsappUrl, '_blank');
    } else {
        // Fallback: generar URL básica
        const telefono = document.getElementById('telefono').value;
        const negocio = document.getElementById('negocio').value;
        const dueno = document.getElementById('dueno').value || 'Estimado';

        if (!telefono) {
            showToast('⚠️ Ingresá el teléfono del cliente');
            return;
        }

        const mensaje = `Hola ${dueno}! 👋 Soy Isa de Orchestrator ISA. Te preparé una propuesta para *${negocio}*. ¿La revisaste?`;
        const waUrl = `https://wa.me/${telefono.replace(/\D/g, '')}?text=${encodeURIComponent(mensaje)}`;
        window.open(waUrl, '_blank');
    }
}

