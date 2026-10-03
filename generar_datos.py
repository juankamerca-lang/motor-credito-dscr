"""
Genera N solicitudes de crédito sintéticas (empresas ficticias) para probar el motor.
Unidades: millones de COP. Uso:  python generar_datos.py 500
"""
import sys
import numpy as np
import pandas as pd

SECTORES = ["Comercio", "Manufactura", "Agroindustria", "Construcción", "Transporte",
            "Servicios", "Tecnología", "Alimentos", "Textil", "Salud"]
FORMAS = ["S.A.S.", "S.A.", "Ltda."]
RAICES = ["Andina", "Del Valle", "Caribe", "Pacífico", "Central", "Orinoquía", "Sabana",
          "Altiplano", "Magdalena", "Cafetera", "Llanera", "Antioqueña", "Boyacense", "Santandereana"]


def generar(n=500, semilla=2026):
    rng = np.random.default_rng(semilla)
    sector = rng.choice(SECTORES, n)
    nombres = [f"{s} {rng.choice(RAICES)} {rng.choice(FORMAS)} #{i+1:03d}" for i, s in enumerate(sector)]

    ventas = rng.lognormal(mean=np.log(40_000), sigma=0.9, size=n)
    cagr = rng.normal(0.05, 0.06, n)
    margen = np.clip(rng.normal(0.14, 0.07, n), 0.01, 0.35)
    en_perdida = rng.random(n) < 0.03          # ~3 % de empresas con EBITDA negativo
    margen[en_perdida] = rng.uniform(-0.06, -0.005, en_perdida.sum())
    ebitda = ventas * margen
    peso_dep = rng.uniform(0.15, 0.45, n)
    ebit = ebitda - np.abs(ebitda) * peso_dep

    apalanc = np.clip(rng.lognormal(np.log(1.4), 0.55, n), 0.1, 7)
    deuda = np.abs(ebitda) * apalanc
    pct_cp = rng.uniform(0.05, 0.25, n)
    kd = rng.uniform(0.09, 0.16, n)

    df = pd.DataFrame({
        "empresa": nombres,
        "sector": sector,
        "ventas": ventas.round(0),
        "ventas_hace_3": (ventas / (1 + cagr) ** 3).round(0),
        "ebitda": ebitda.round(0),
        "ebit": ebit.round(0),
        "tasa_impuesto": np.clip(rng.normal(0.33, 0.03, n), 0.20, 0.40).round(3),
        "gasto_intereses": (deuda * kd).round(0),
        "deuda_lp": (deuda * (1 - pct_cp)).round(0),
        "deuda_cp": (deuda * pct_cp).round(0),
        "var_capital_trabajo": (ventas * rng.normal(0.004, 0.012, n)).round(0),
        "capex": (np.abs(ebitda) * rng.uniform(0.03, 0.30, n)).round(0),
        "monto_solicitado": (np.abs(ebitda) * rng.uniform(0.15, 0.9, n)).round(-1),
        "plazo_anios": rng.choice([3, 4, 5, 7], n, p=[0.25, 0.25, 0.35, 0.15]),
    })
    return df


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    df = generar(n)
    df.to_excel("solicitudes_ejemplo.xlsx", index=False, sheet_name="Solicitudes")
    df.to_csv("solicitudes_ejemplo.csv", index=False, encoding="utf-8-sig")
    print(f"{n} solicitudes generadas (millones COP).")
