const puppeteer = require('puppeteer');
const fs = require('fs').promises;
const path = require('path');
const { program } = require('commander');

program
  .option('--location <location>', 'Ciudad a buscar', 'tetouan')
  .option('--query <query>', 'Tipo de negocio', 'restaurantes')
  .option('--max-results <n>', 'Máximo de resultados', '50')
  .option('--output-dir <dir>', 'Directorio de salida', './data')
  .option('--headless <bool>', 'Modo headless', 'true')
  .parse(process.argv);

const opts = program.opts();

// ─── Selectores robustos con múltiples fallbacks ───
const SELECTORS = {
  resultCards: [
    '[data-result-index] a',
    '.hfpxzc',
    'a[href*="/maps/place/"]',
    '[jstcache] a[href^="https://www.google.com/maps/place"]'
  ],
  nameFromCard: [
    'aria-label',
    'h3',
    '.qBF1Pd',
    '[data-result-index] span'
  ],
  detailsPanel: [
    '[data-panel-id]',
    '[role="main"]',
    '.m6QErb'
  ]
};

async function scrapeGoogleMaps(query, location, maxResults = 50) {
  console.log(`🔍 Buscando "${query}" en ${location}, Marruecos...`);
  console.log(`📊 Objetivo: ${maxResults} resultados`);

  const browser = await puppeteer.launch({
    headless: opts.headless === 'true',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-accelerated-2d-canvas',
      '--disable-gpu',
      '--window-size=1920,1080'
    ],
    defaultViewport: { width: 1920, height: 1080 }
  });

  try {
    const page = await browser.newPage();

    // Rotación de user agents
    const userAgents = [
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ];
    await page.setUserAgent(userAgents[Math.floor(Math.random() * userAgents.length)]);

    // Configurar geolocalización en Marruecos
    await page.setGeolocation({ latitude: 35.5711, longitude: -5.3726 });
    const context = browser.defaultBrowserContext();
    await context.overridePermissions('https://www.google.com', ['geolocation']);

    const searchQuery = encodeURIComponent(`${query} en ${location}, Marruecos`);
    const url = `https://www.google.com/maps/search/${searchQuery}`;

    console.log(`🌐 Navegando a: ${url}`);
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });

    // Esperar a que carguen resultados con múltiples selectores
    let selectorFound = null;
    for (const sel of SELECTORS.resultCards) {
      try {
        await page.waitForSelector(sel, { timeout: 8000 });
        selectorFound = sel;
        console.log(`✅ Selector encontrado: ${sel}`);
        break;
      } catch (e) {
        continue;
      }
    }

    if (!selectorFound) {
      // Intentar con captura de pantalla para depuración
      const debugPath = path.join(opts.outputDir, `debug_${Date.now()}.png`);
      await page.screenshot({ path: debugPath, fullPage: true });
      console.log(`⚠️  No se encontraron resultados. Debug guardado en: ${debugPath}`);
      return [];
    }

    // Scroll infinito para cargar más resultados
    console.log('📜 Haciendo scroll para cargar más resultados...');
    await autoScroll(page, maxResults);

    // Extraer datos con múltiples estrategias
    const businesses = await page.evaluate((selectors) => {
      const results = [];
      const seen = new Set();

      // Estrategia 1: Tarjetas de resultado
      document.querySelectorAll(selectors.resultCards[0]).forEach(el => {
        const href = el.getAttribute('href') || '';
        if (!href.includes('/maps/place/')) return;

        const name = el.getAttribute('aria-label') || 
                     el.querySelector('h3')?.textContent?.trim() ||
                     el.querySelector('.qBF1Pd')?.textContent?.trim() ||
                     'Sin nombre';

        if (seen.has(href)) return;
        seen.add(href);

        // Buscar dirección en elementos hermanos o padres
        let address = '';
        const container = el.closest('[data-result-index]') || el.parentElement;
        if (container) {
          address = container.querySelector('.W4Efsd, .rllt__details, .bXlT7b')?.textContent?.trim() || '';
        }

        // Extraer teléfono si está visible
        let phone = '';
        const phoneEl = container?.querySelector('[data-item-id*="phone"]');
        if (phoneEl) phone = phoneEl.textContent?.trim() || '';

        results.push({
          nombre: name,
          direccion: address,
          telefono: phone,
          link: href,
          ciudad: location,
          tipo_negocio: query,
          fuente: 'google_maps',
          score: 5 // Score base, se ajusta manualmente después
        });
      });

      return results;
    }, SELECTORS);

    console.log(`✅ Encontrados: ${businesses.length} negocios`);

    // Guardar en CSV
    await fs.mkdir(opts.outputDir, { recursive: true });
    const timestamp = Date.now();
    const filename = `leads_${query}_${location}_${timestamp}.csv`;
    const filepath = path.join(opts.outputDir, filename);

    const csv = [
      'nombre,direccion,telefono,link,ciudad,tipo_negocio,fuente,score',
      ...businesses.map(b => 
        `"${(b.nombre || '').replace(/"/g, '""')}","${(b.direccion || '').replace(/"/g, '""')}","${(b.telefono || '').replace(/"/g, '""')}","${b.link}","${b.ciudad}","${b.tipo_negocio}","${b.fuente}",${b.score}`
      )
    ].join('\n');

    await fs.writeFile(filepath, csv, 'utf-8');
    console.log(`📁 CSV guardado en: ${filepath}`);

    // También guardar JSON para procesamiento posterior
    const jsonFile = `leads_${query}_${location}_${timestamp}.json`;
    const jsonPath = path.join(opts.outputDir, jsonFile);
    await fs.writeFile(jsonPath, JSON.stringify(businesses, null, 2), 'utf-8');
    console.log(`📁 JSON guardado en: ${jsonPath}`);

    return businesses;

  } catch (error) {
    console.error('❌ Error durante el scraping:', error.message);
    throw error;
  } finally {
    await browser.close();
  }
}

async function autoScroll(page, maxResults) {
  await page.evaluate(async (max) => {
    await new Promise((resolve) => {
      let totalHeight = 0;
      let resultsCount = 0;
      const distance = 400;
      const timer = setInterval(() => {
        const scrollHeight = document.body.scrollHeight;
        const results = document.querySelectorAll('[data-result-index]');
        resultsCount = results.length;

        window.scrollBy(0, distance);
        totalHeight += distance;

        if (resultsCount >= max || totalHeight >= scrollHeight || totalHeight > 8000) {
          clearInterval(timer);
          resolve();
        }
      }, 300);
    });
  }, maxResults);
}

// Ejecutar
scrapeGoogleMaps(opts.query, opts.location, parseInt(opts.maxResults))
  .then((results) => {
    console.log('\n🎉 Scraping completado exitosamente');
    console.log(`📊 Total de negocios scrapeados: ${results.length}`);
    process.exit(0);
  })
  .catch(err => {
    console.error('\n💥 Error fatal:', err.message);
    process.exit(1);
  });
