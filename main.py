from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI()

# Servir archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def landing():
    return FileResponse("index.html")

@app.get("/catalogo")
def catalogo():
    return FileResponse("catalogo.html")

@app.get("/catalogo.html")
def catalogo_html():
    return FileResponse("catalogo.html")
