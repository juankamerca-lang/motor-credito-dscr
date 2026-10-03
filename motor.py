"""
Motor de scoring de crédito basado en DSCR.
Réplica de la hoja 'Caso Walmart - DSCR': mismas fórmulas, mismas tablas.
La política (pesos, rangos, escala) vive en politica.json, no en el código.
"""
import json
import math
import numpy as np
import pandas as pd

# Columnas que debe traer cada solicitud (una fila por empresa)
COLUMNAS = {
    "empresa": "Nombre de la empresa",
    "ventas": "Ventas del último año",
    "ventas_hace_3": "Ventas de hace 3 años (para el CAGR)",
    "ebitda": "EBITDA",
    "ebit": "EBIT (utilidad operativa)",
    "tasa_impuesto": "Tasa efectiva de impuesto (ej. 0.23)",
    "gasto_intereses": "Gasto por intereses del año (positivo)",
    "deuda_lp": "Créditos y préstamos de largo plazo",
    "deuda_cp": "Créditos y préstamos de corto plazo",
    "var_capital_trabajo": "Aumento del capital de trabajo (positivo = consume caja)",
    "capex": "Capex del año (positivo)",
    "monto_solicitado": "Monto del nuevo crédito",
    "plazo_anios": "Plazo del nuevo crédito en años",
}


def cargar_politica(ruta="politica.json"):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def pmt(tasa, n, valor):
    """Cuota anual fija, igual a -PMT() de Excel."""
    if n <= 0:
        return float("nan")
    if tasa == 0:
        return valor / n
    return valor * tasa / (1 - (1 + tasa) ** -n)


def buscar(valor, tabla):
    """Equivale a LOOKUP() de Excel: toma el último umbral <= valor.
    Si el valor queda por debajo del primer umbral (Excel daría #N/A),
    se asigna el peor tramo de la tabla."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return min(tabla, key=lambda f: f[1])
    elegido = None
    for fila in tabla:
        if valor >= fila[0]:
            elegido = fila
    return elegido if elegido else min(tabla, key=lambda f: f[1])


def evaluar(sol: dict, pol: dict, choque_ebitda=0.0, choque_tasa=0.0) -> dict:
    """Evalúa una solicitud. choque_ebitda: -0.2 = EBITDA cae 20 %.
    choque_tasa: 0.03 = la tasa del nuevo crédito sube 300 pb."""
    ventas = sol["ventas"]
    ebitda = sol["ebitda"] * (1 + choque_ebitda)
    ebit = sol["ebit"] + (ebitda - sol["ebitda"])  # el choque pega en EBIT igual que en EBITDA
    deuda = sol["deuda_lp"] + sol["deuda_cp"]

    # --- Parte 2: nuevo crédito y servicio de deuda ---
    kd = sol["gasto_intereses"] / deuda if deuda > 0 else 0.10
    tasa = kd + choque_tasa
    cuota = pmt(tasa, sol["plazo_anios"], sol["monto_solicitado"])
    servicio_actual = sol["gasto_intereses"] + sol["deuda_cp"]
    servicio_total = servicio_actual + cuota

    # --- Parte 1: flujo operativo y flujo de caja libre ---
    nopat = ebit * (1 - sol["tasa_impuesto"])
    depreciacion = ebitda - ebit
    flujo_operativo = nopat + depreciacion - sol["var_capital_trabajo"]
    fcl = flujo_operativo - sol["capex"]

    # --- Parte 3: indicadores del score ---
    ind = {
        "dscr": ebitda / servicio_total if servicio_total > 0 else float("inf"),
        # EBITDA <= 0 se trata como apalancamiento infinito (en Excel daría un ratio negativo = 100 pts, un error)
        "deuda_ebitda": (deuda + sol["monto_solicitado"]) / ebitda if ebitda > 0 else float("inf"),
        "margen_ebitda": ebitda / ventas if ventas > 0 else float("nan"),
        "crecimiento": (ventas / sol["ventas_hace_3"]) ** (1 / 3) - 1
        if sol["ventas_hace_3"] > 0 and ventas > 0 else float("nan"),
    }

    detalle, score = {}, 0.0
    for clave, cfg in pol["indicadores"].items():
        _, puntos, lectura = buscar(ind[clave], cfg["tabla"])
        aporte = cfg["peso"] * puntos
        score += aporte
        detalle[clave] = {"valor": ind[clave], "puntos": puntos, "aporte": aporte, "lectura": lectura}

    # --- Parte 4: capacidad de endeudamiento ---
    deuda_max = max(ebitda, 0) * pol["multiplo_max_ebitda"]
    capacidad = deuda_max - deuda
    cabe = sol["monto_solicitado"] <= capacidad
    dscr_fcl = fcl / servicio_total if servicio_total > 0 else float("inf")

    # --- Reglas de veto (la innovación sobre el modelo original) ---
    score_modelo = score
    alertas = []
    veto = pol.get("reglas_veto", {})
    if dscr_fcl < veto.get("dscr_fcl_minimo", 1.0):
        alertas.append(f"El flujo de caja libre no cubre el servicio de deuda (DSCR FCL {dscr_fcl:.2f})")
        if veto.get("activas"):
            score = min(score, veto["score_maximo_si_falla_fcl"])
    if not cabe:
        alertas.append("El crédito excede la capacidad de endeudamiento")
        if veto.get("activas"):
            score = min(score, veto["score_maximo_si_excede_capacidad"])

    _, calif, decision = buscar(score, [[u, c, d] for u, c, d in pol["escala"]])

    return {
        "empresa": sol.get("empresa", ""),
        "score": round(score, 1),
        "score_modelo": round(score_modelo, 1),
        "calificacion": calif,
        "decision": decision,
        "dscr": ind["dscr"],
        "deuda_ebitda": ind["deuda_ebitda"],
        "margen_ebitda": ind["margen_ebitda"],
        "crecimiento": ind["crecimiento"],
        "dscr_fcl": dscr_fcl,
        "tasa": tasa,
        "cuota": cuota,
        "servicio_total": servicio_total,
        "fcl": fcl,
        "capacidad_disponible": capacidad,
        "cabe": cabe,
        "monto_solicitado": sol["monto_solicitado"],
        "alertas": "; ".join(alertas),
        "detalle": detalle,
    }


def evaluar_lote(df: pd.DataFrame, pol: dict, **choques) -> pd.DataFrame:
    """Evalúa todas las filas de un DataFrame y devuelve una tabla de resultados."""
    filas = [evaluar(r, pol, **choques) for r in df.to_dict("records")]
    res = pd.DataFrame(filas).drop(columns=["detalle"])
    return res.sort_values("score", ascending=False).reset_index(drop=True)


def validar(df: pd.DataFrame):
    """Devuelve la lista de columnas faltantes."""
    return [c for c in COLUMNAS if c not in df.columns]


def monte_carlo(sol: dict, pol: dict, n=5000, vol_ebitda=0.15, vol_tasa=0.01, semilla=7):
    """Simula escenarios de EBITDA y tasa; devuelve la distribución del DSCR y del score."""
    rng = np.random.default_rng(semilla)
    ch_e = rng.normal(0, vol_ebitda, n)
    ch_t = rng.normal(0, vol_tasa, n)
    dscr, score = np.empty(n), np.empty(n)
    for i in range(n):
        r = evaluar(sol, pol, choque_ebitda=ch_e[i], choque_tasa=ch_t[i])
        dscr[i], score[i] = r["dscr"], r["score"]
    return dscr, score
