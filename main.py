"""
API - Tabla de Posiciones Liga Chilena (Primera División)
Stack: FastAPI + BeautifulSoup + Requests
Fuente: ESPN Chile (https://www.espn.cl)

Instalación:
    pip install fastapi uvicorn requests beautifulsoup4

Ejecución:
    uvicorn main:app --reload

Endpoints:
    GET /tabla           → Tabla de posiciones completa
    GET /tabla/{equipo}  → Posición de un equipo específico
    GET /health          → Estado de la API
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
from typing import Optional
import time

# ── Configuración ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Liga Chilena API",
    description="Tabla de posiciones del Campeonato Nacional de Chile (Primera División)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/logos", StaticFiles(directory="logos"), name="logos")

@app.get("/")
def index():
    return FileResponse("tabla.html")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

ESPN_URL = "https://www.espn.cl/futbol/posiciones/_/liga/chi.1"

# Cache simple en memoria (evita scrapear en cada request)
_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 300  # segundos (5 minutos)


# ── Scraper ───────────────────────────────────────────────────────────────────

def scrape_tabla() -> list[dict]:
    """Scrapea ESPN Chile y retorna la tabla de posiciones."""
    resp = requests.get(ESPN_URL, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # ESPN usa dos tablas separadas: nombres y estadísticas
    tablas = soup.find_all("table")
    if len(tablas) < 2:
        raise ValueError("No se encontró la tabla de posiciones en la página.")

    # Tabla izquierda → nombres de equipos
    nombres = [
        td.get_text(strip=True)
        for td in tablas[0].find_all("span", class_="hide-mobile")
    ]

    # Tabla derecha → estadísticas (PJ, G, E, P, GF, GC, DG, PTS)
    filas_stats = tablas[1].find_all("tr")[1:]  # saltar encabezado

    tabla = []
    for i, fila in enumerate(filas_stats):
        celdas = [td.get_text(strip=True) for td in fila.find_all("td")]
        if len(celdas) < 8:
            continue

        equipo = nombres[i] if i < len(nombres) else f"Equipo {i+1}"

        tabla.append({
            "posicion":        i + 1,
            "equipo":          equipo,
            "partidos_jugados": int(celdas[0]),
            "ganados":         int(celdas[1]),
            "empatados":       int(celdas[2]),
            "perdidos":        int(celdas[3]),
            "goles_favor":     int(celdas[4]),
            "goles_contra":    int(celdas[5]),
            "diferencia_goles": int(celdas[6]),
            "puntos":          int(celdas[7]),
        })

    return tabla


def get_tabla_cached() -> list[dict]:
    """Retorna la tabla desde cache o hace scraping si expiró."""
    now = time.time()
    if _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]

    data = scrape_tabla()
    _cache["data"] = data
    _cache["timestamp"] = now
    return data


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "fuente": ESPN_URL}


@app.get("/tabla")
def get_tabla(refresh: bool = False):
    """
    Retorna la tabla de posiciones completa del Campeonato Nacional.

    - **refresh**: fuerza actualización ignorando el cache
    """
    if refresh:
        _cache["data"] = None

    try:
        tabla = get_tabla_cached()
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Error al obtener datos: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "liga":   "Campeonato Nacional - Primera División",
        "pais":   "Chile",
        "equipos": len(tabla),
        "tabla":  tabla,
    }


@app.get("/tabla/{equipo}")
def get_equipo(equipo: str):
    """
    Retorna la posición y estadísticas de un equipo específico.

    - **equipo**: nombre o parte del nombre del equipo (no sensible a mayúsculas)
    """
    try:
        tabla = get_tabla_cached()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    equipo_lower = equipo.lower()
    resultados = [
        e for e in tabla
        if equipo_lower in e["equipo"].lower()
    ]

    if not resultados:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró ningún equipo con el nombre '{equipo}'",
        )

    return resultados
