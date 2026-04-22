import os
import re
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2

app = FastAPI(title="API Incidencias")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pearson9mant.github.io",
        "https://almedainstalacio-commits.github.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")

ASIGNACION_OPERARIO_POR_CENTRO = {
    "Pearson 9": "Luis Lozano",
    "Pearson 22": "J.A. Almeda",
}


class IncidenciaIn(BaseModel):
    asunto: str = ""
    body: str = ""
    remitente: str = ""


def conectar():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Falta DATABASE_URL")
    return psycopg2.connect(database_url)


def limpiar_texto(valor):
    if valor is None:
        return ""
    texto = str(valor).replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n+", "\n", texto)
    return texto.strip()


def normalizar_centro(valor: str) -> str:
    v = limpiar_texto(valor).lower()
    if v in ("pearson 9", "pearson9", "p9"):
        return "Pearson 9"
    if v in ("pearson 22", "pearson22", "p22"):
        return "Pearson 22"
    return limpiar_texto(valor)


def normalizar_prioridad(valor: str) -> str:
    v = limpiar_texto(valor).lower()
    if v in ("alta", "urgente", "muy alta"):
        return "Alta"
    if v in ("baja",):
        return "Baja"
    return "Media"


def operario_por_centro(centro: str) -> str:
    return ASIGNACION_OPERARIO_POR_CENTRO.get(centro, "")


def extraer_campos(body: str, asunto: str, remitente: str):
    body = limpiar_texto(body)
    campos = {}

    for linea in body.split("\n"):
        l = limpiar_texto(linea)
        ll = l.lower()

        if ll.startswith("centro:"):
            campos["centro"] = limpiar_texto(l.split(":", 1)[1])
        elif ll.startswith("edificio:"):
            campos["edificio"] = limpiar_texto(l.split(":", 1)[1])
        elif ll.startswith("aula/espacio:") or ll.startswith("espacio:") or ll.startswith("aula:"):
            campos["espacio"] = limpiar_texto(l.split(":", 1)[1])
        elif ll.startswith("incidencia:") or ll.startswith("descripcion:"):
            campos["descripcion"] = limpiar_texto(l.split(":", 1)[1])
        elif ll.startswith("prioridad:"):
            campos["prioridad"] = limpiar_texto(l.split(":", 1)[1])
        elif ll.startswith("solicitante:"):
            campos["solicitante"] = limpiar_texto(l.split(":", 1)[1])
        elif ll.startswith("area:"):
            campos["area"] = limpiar_texto(l.split(":", 1)[1])

    centro = normalizar_centro(campos.get("centro", ""))
    edificio = limpiar_texto(campos.get("edificio", ""))
    espacio = limpiar_texto(campos.get("espacio", ""))
    descripcion = limpiar_texto(campos.get("descripcion", "")) or limpiar_texto(asunto)
    prioridad = normalizar_prioridad(campos.get("prioridad", ""))
    solicitante = limpiar_texto(campos.get("solicitante", "")) or limpiar_texto(remitente)
    area = limpiar_texto(campos.get("area", "")) or "Otros"
    operario = operario_por_centro(centro)

    return {
        "centro": centro,
        "edificio": edificio,
        "espacio": espacio,
        "descripcion": descripcion,
        "prioridad": prioridad,
        "solicitante": solicitante,
        "area": area,
        "operario": operario,
    }


def obtener_siguiente_numero_ot(cur):
    cur.execute("SELECT numero_ot FROM ordenes_trabajo WHERE numero_ot IS NOT NULL")
    activas = cur.fetchall()

    cur.execute("SELECT numero_ot FROM historico_ordenes WHERE numero_ot IS NOT NULL")
    historicas = cur.fetchall()

    numeros = []
    for fila in activas + historicas:
        valor = fila[0]
        if not valor:
            continue
        texto = str(valor).strip().upper()
        try:
            if texto.startswith("OT-"):
                numero = int(texto.replace("OT-", "").strip())
            else:
                numero = int(texto)
            numeros.append(numero)
        except Exception:
            pass

    siguiente = max(numeros) + 1 if numeros else 1
    return f"OT-{siguiente:05d}"


@app.post("/api/incidencias")
def crear_incidencia(payload: IncidenciaIn, x_webhook_token: str = Header(default="")):
    if not WEBHOOK_TOKEN or x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")

    datos = extraer_campos(payload.body, payload.asunto, payload.remitente)

    conn = conectar()
    cur = conn.cursor()

    try:
        numero_ot = obtener_siguiente_numero_ot(cur)

        cur.execute(
            """
            INSERT INTO ordenes_trabajo
            (numero_ot, descripcion, estado, centro, edificio, espacio, area,
             prioridad, operario, origen, solicitante, fecha_origen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                numero_ot,
                datos["descripcion"],
                "Abierta",
                datos["centro"],
                datos["edificio"],
                datos["espacio"],
                datos["area"],
                datos["prioridad"],
                datos["operario"],
                "OUTLOOK",
                datos["solicitante"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

        conn.commit()
        return {"ok": True, "numero_ot": numero_ot, "datos": datos}
    finally:
        cur.close()
        conn.close()
