import os
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://almedainstalacio-commits.github.io"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "1234")  # puedes cambiarlo luego

# -------------------------
# MODELO
# -------------------------
class Incidencia(BaseModel):
    centro: str
    edificio: str
    espacio: str
    descripcion: str
    prioridad: str
    solicitante: str

# -------------------------
# ASIGNACIÓN AUTOMÁTICA
# -------------------------
def asignar_operario(centro):
    if centro == "Pearson 9":
        return "Luis Lozano"
    if centro == "Pearson 22":
        return "J.A. Almeda"
    return ""

# -------------------------
# SIGUIENTE OT
# -------------------------
def obtener_siguiente_ot(conn):
    cur = conn.cursor()
    cur.execute("SELECT numero_ot FROM ordenes_trabajo")
    rows = cur.fetchall()

    max_num = 0
    for r in rows:
        if r[0]:
            try:
                num = int(r[0].replace("OT-", ""))
                if num > max_num:
                    max_num = num
            except:
                pass

    siguiente = max_num + 1
    return f"OT-{siguiente:05d}"

# -------------------------
# ENDPOINT
# -------------------------
@app.post("/incidencia")
def recibir_incidencia(data: Incidencia, x_token: str = Header(None)):

    # seguridad
    if x_token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    numero_ot = obtener_siguiente_ot(conn)
    operario = asignar_operario(data.centro)

    cur.execute("""
        INSERT INTO ordenes_trabajo
        (numero_ot, descripcion, estado, centro, edificio, espacio, area, prioridad, operario, origen, solicitante)
        VALUES (%s, %s, 'Abierta', %s, %s, %s, 'Otros', %s, %s, 'API', %s)
    """, (
        numero_ot,
        data.descripcion,
        data.centro,
        data.edificio,
        data.espacio,
        data.prioridad,
        operario,
        data.solicitante
    ))

    conn.commit()
    conn.close()

    return {"ok": True, "numero_ot": numero_ot}

# -------------------------
# TEST
# -------------------------
@app.get("/")
def home():
    return {"mensaje": "API funcionando"}
