from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import subprocess
import os
import json

router = APIRouter(prefix="/api/scraping", tags=["scraping"])

class ScrapingJob(BaseModel):
    location: str = Field("tetouan", pattern="^(tetouan|tanger|chefchaouen|asilah|larache|marrakech|casablanca|rabat)$")
    query: str = Field("restaurantes", min_length=2)
    max_results: int = Field(50, ge=10, le=200)
    categoria: Optional[str] = None

jobs = {}

def generar_job_id() -> str:
    return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

@router.post("/ejecutar")
async def ejecutar_scraping(job: ScrapingJob, background_tasks: BackgroundTasks, request: Request):
    job_id = generar_job_id()
    data_dir = os.getenv("DATA_DIR", "./data")

    jobs[job_id] = {
        "job_id": job_id,
        "estado": "pendiente",
        "location": job.location,
        "query": job.query,
        "resultados": None,
        "archivo_csv": None,
        "archivo_json": None,
        "error": None,
        "fecha_inicio": datetime.now(),
        "fecha_fin": None
    }

    background_tasks.add_task(
        _ejecutar_scraper,
        job_id=job_id,
        location=job.location,
        query=job.query,
        max_results=job.max_results,
        data_dir=data_dir
    )

    return {
        "status": "accepted",
        "job_id": job_id,
        "mensaje": f"Scraping iniciado para '{job.query}' en {job.location}",
        "check_status": f"/api/scraping/status/{job_id}"
    }

async def _ejecutar_scraper(job_id: str, location: str, query: str, max_results: int, data_dir: str):
    jobs[job_id]["estado"] = "ejecutando"

    try:
        os.makedirs(data_dir, exist_ok=True)

        result = subprocess.run(
            [
                "node", "scripts/scraper.js",
                "--location", location,
                "--query", query,
                "--max-results", str(max_results),
                "--output-dir", data_dir,
                "--headless", "true"
            ],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            jobs[job_id]["estado"] = "error"
            jobs[job_id]["error"] = result.stderr
            jobs[job_id]["fecha_fin"] = datetime.now()
            return

        csv_files = sorted(
            [f for f in os.listdir(data_dir) if f.startswith(f"leads_{query}_{location}_") and f.endswith(".csv")],
            key=lambda x: os.path.getmtime(os.path.join(data_dir, x)),
            reverse=True
        )
        json_files = sorted(
            [f for f in os.listdir(data_dir) if f.startswith(f"leads_{query}_{location}_") and f.endswith(".json")],
            key=lambda x: os.path.getmtime(os.path.join(data_dir, x)),
            reverse=True
        )

        if csv_files:
            jobs[job_id]["archivo_csv"] = csv_files[0]
        if json_files:
            jobs[job_id]["archivo_json"] = json_files[0]
            try:
                with open(os.path.join(data_dir, json_files[0]), 'r') as f:
                    data = json.load(f)
                    jobs[job_id]["resultados"] = len(data)
            except:
                pass

        jobs[job_id]["estado"] = "completado"
        jobs[job_id]["fecha_fin"] = datetime.now()

    except subprocess.TimeoutExpired:
        jobs[job_id]["estado"] = "error"
        jobs[job_id]["error"] = "Timeout: El scraping tardó más de 5 minutos"
        jobs[job_id]["fecha_fin"] = datetime.now()
    except Exception as e:
        jobs[job_id]["estado"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["fecha_fin"] = datetime.now()

@router.get("/status/{job_id}")
async def obtener_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return jobs[job_id]

@router.get("/jobs")
async def listar_jobs(estado: Optional[str] = None, limit: int = 20):
    lista = list(jobs.values())
    if estado:
        lista = [j for j in lista if j["estado"] == estado]
    lista.sort(key=lambda x: x["fecha_inicio"], reverse=True)
    return {"jobs": lista[:limit], "total": len(lista)}

@router.get("/resultados/{job_id}")
async def obtener_resultados(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    job = jobs[job_id]
    if job["estado"] != "completado":
        raise HTTPException(status_code=400, detail="Job no completado aún")

    data_dir = os.getenv("DATA_DIR", "./data")

    if job.get("archivo_json"):
        json_path = os.path.join(data_dir, job["archivo_json"])
        try:
            with open(json_path, 'r') as f:
                resultados = json.load(f)
            return {
                "job_id": job_id,
                "total_resultados": len(resultados),
                "resultados": resultados
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error leyendo resultados: {str(e)}")

    raise HTTPException(status_code=404, detail="No hay archivo de resultados")

@router.get("/archivos")
async def listar_archivos(request: Request):
    data_dir = os.getenv("DATA_DIR", "./data")
    try:
        archivos = []
        for f in os.listdir(data_dir):
            if f.startswith("leads_") and (f.endswith(".csv") or f.endswith(".json")):
                stat = os.stat(os.path.join(data_dir, f))
                archivos.append({
                    "nombre": f,
                    "tipo": "csv" if f.endswith(".csv") else "json",
                    "tamano_kb": round(stat.st_size / 1024, 2),
                    "fecha": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "location": f.split("_")[2] if len(f.split("_")) > 2 else "unknown",
                    "query": f.split("_")[1] if len(f.split("_")) > 1 else "unknown"
                })

        archivos.sort(key=lambda x: x["fecha"], reverse=True)
        return {"archivos": archivos, "total": len(archivos)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/archivos/{nombre}")
async def eliminar_archivo(nombre: str):
    data_dir = os.getenv("DATA_DIR", "./data")
    filepath = os.path.join(data_dir, nombre)

    if not os.path.abspath(filepath).startswith(os.path.abspath(data_dir)):
        raise HTTPException(status_code=403, detail="Ruta no permitida")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    os.remove(filepath)
    return {"status": "deleted", "archivo": nombre}

@router.get("/config")
async def obtener_config():
    return {
        "locations_disponibles": ["tetouan", "tanger", "chefchaouen", "asilah", "larache", "marrakech", "casablanca", "rabat"],
        "queries_sugeridos": [
            "restaurantes", "cafés", "salón de belleza", "barbería", "tienda de ropa",
            "farmacia", "clínica dental", "gimnasio", "hotel", "riads"
        ],
        "max_results_default": 50,
        "max_results_maximo": 200,
        "timeout_segundos": 300
    }
