from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import requests
from bs4 import BeautifulSoup
import time

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

_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 300


def scrape_tabla():
    resp = requests.get(ESPN_URL, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    tablas = soup.find_all("table")
    if len(tablas) < 2:
        raise ValueError("No se encontró la tabla de posiciones en la página.")

    nombres = [
        td.get_text(strip=True)
        for td in tablas[0].find_all("span", class_="hide-mobile")
    ]

    filas_stats = tablas[1].find_all("tr")[1:]

    tabla = []
    for i, fila in enumerate(filas_stats):
        celdas = [td.get_text(strip=True) for td in fila.find_all("td")]
        if len(celdas) < 8:
            continue

        equipo = nombres[i] if i < len(nombres) else f"Equipo {i+1}"

        tabla.append({
            "posicion":         i + 1,
            "equipo":           equipo,
            "partidos_jugados": int(celdas[0]),
            "ganados":          int(celdas[1]),
            "empatados":        int(celdas[2]),
            "perdidos":         int(celdas[3]),
            "goles_favor":      int(celdas[4]),
            "goles_contra":     int(celdas[5]),
            "diferencia_goles": int(celdas[6]),
            "puntos":           int(celdas[7]),
        })

    return tabla


def get_tabla_cached():
    now = time.time()
    if _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]
    data = scrape_tabla()
    _cache["data"] = data
    _cache["timestamp"] = now
    return data


@app.get("/health")
def health_check():
    return {"status": "ok", "fuente": ESPN_URL}


@app.get("/tabla")
def get_tabla(refresh: bool = False):
    if refresh:
        _cache["data"] = None
    try:
        tabla = get_tabla_cached()
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Error al obtener datos: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "liga":    "Campeonato Nacional - Primera División",
        "pais":    "Chile",
        "equipos": len(tabla),
        "tabla":   tabla,
    }


@app.get("/tabla/{equipo}")
def get_equipo(equipo: str):
    try:
        tabla = get_tabla_cached()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    resultados = [e for e in tabla if equipo.lower() in e["equipo"].lower()]

    if not resultados:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró ningún equipo con el nombre '{equipo}'",
        )

    return resultados