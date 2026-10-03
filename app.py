"""
Motor de Crédito DSCR — prototipo en Streamlit.
Ejecutar:  streamlit run app.py
"""
import copy
import json
import io

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from motor import COLUMNAS, cargar_politica, evaluar, evaluar_lote, monte_carlo, validar
from generar_datos import generar

st.set_page_config(page_title="Motor de Crédito DSCR", page_icon="🏦", layout="wide")

ORDEN = ["AAA", "AA", "A", "BBB", "BB", "B"]
COLORES = {"AAA": "#1F5C4A", "AA": "#3E8E63", "A": "#7FB77E",
           "BBB": "#E3B341", "BB": "#E07B39", "B": "#B3261E"}

# Caso Walmart FY2025 (miles USD), tomado del archivo de Excel
WALMART = dict(empresa="Walmart Inc. (FY2025, miles USD)", ventas=680_985_000, ventas_hace_3=572_754_000,
               ebitda=43_212_000, ebit=28_554_000, tasa_impuesto=0.2338, gasto_intereses=2_728_000,
               deuda_lp=39_324_000, deuda_cp=6_466_000, var_capital_trabajo=454_000, capex=23_783_000,
               monto_solicitado=20_000_000, plazo_anios=5)


# ---------------------------------------------------------------- política (barra lateral)
@st.cache_data
def politica_base():
    return cargar_politica("politica.json")


pol = copy.deepcopy(politica_base())

with st.sidebar:
    st.header("Política de crédito")
    st.caption("Cambia los parámetros y todo se recalcula al instante.")

    pol["reglas_veto"]["activas"] = st.toggle(
        "Activar reglas de veto", value=False,
        help="Si el flujo de caja libre no cubre el servicio de deuda, el score queda máximo en BBB. "
             "Si el crédito excede la capacidad de endeudamiento, máximo en BB.")

    pol["multiplo_max_ebitda"] = st.slider("Múltiplo máximo de deuda (veces EBITDA)", 1.0, 6.0,
                                           float(pol["multiplo_max_ebitda"]), 0.5)

    st.subheader("Pesos del score")
    pesos = {}
    for k, cfg in pol["indicadores"].items():
        pesos[k] = st.slider(cfg["nombre"], 0, 100, int(cfg["peso"] * 100), 5)
    total = sum(pesos.values())
    if total == 0:
        st.error("Los pesos no pueden sumar cero.")
        st.stop()
    if total != 100:
        st.warning(f"Los pesos suman {total} %. Se normalizan a 100 %.")
    for k in pesos:
        pol["indicadores"][k]["peso"] = pesos[k] / total

    st.download_button("Descargar política (JSON)",
                       data=json.dumps(pol, indent=2, ensure_ascii=False),
                       file_name="politica_ajustada.json", mime="application/json")


def fmt(x, tipo="num"):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/a"
    return {"x": f"{x:,.2f}x", "pct": f"{x:.1%}", "num": f"{x:,.0f}"}[tipo]


def a_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Resultados")
    return buf.getvalue()


# ---------------------------------------------------------------- encabezado
st.title("Motor de Crédito DSCR")
st.write("Evalúa solicitudes de crédito con un scorecard de cobertura de deuda: "
         "una por una, en lote, o bajo escenarios de estrés.")

tab1, tab2, tab3, tab4 = st.tabs(["Una solicitud", "Evaluación masiva", "Prueba de estrés", "Política y método"])

# ================================================================ TAB 1: una solicitud
with tab1:
    st.caption("Viene cargado con el caso Walmart del Excel. Cambia cualquier cifra para ver el efecto.")
    c1, c2, c3 = st.columns(3)
    s = {}
    with c1:
        s["empresa"] = st.text_input("Empresa", WALMART["empresa"])
        s["ventas"] = st.number_input("Ventas último año", value=float(WALMART["ventas"]), step=1e6, format="%.0f")
        s["ventas_hace_3"] = st.number_input("Ventas hace 3 años", value=float(WALMART["ventas_hace_3"]), step=1e6, format="%.0f")
        s["ebitda"] = st.number_input("EBITDA", value=float(WALMART["ebitda"]), step=1e5, format="%.0f")
        s["ebit"] = st.number_input("EBIT", value=float(WALMART["ebit"]), step=1e5, format="%.0f")
    with c2:
        s["gasto_intereses"] = st.number_input("Gasto por intereses", value=float(WALMART["gasto_intereses"]), step=1e5, format="%.0f")
        s["deuda_lp"] = st.number_input("Deuda financiera largo plazo", value=float(WALMART["deuda_lp"]), step=1e5, format="%.0f")
        s["deuda_cp"] = st.number_input("Deuda financiera corto plazo", value=float(WALMART["deuda_cp"]), step=1e5, format="%.0f")
        s["tasa_impuesto"] = st.number_input("Tasa de impuesto", value=WALMART["tasa_impuesto"], step=0.01, format="%.4f")
    with c3:
        s["var_capital_trabajo"] = st.number_input("Aumento de capital de trabajo", value=float(WALMART["var_capital_trabajo"]), step=1e5, format="%.0f")
        s["capex"] = st.number_input("Capex", value=float(WALMART["capex"]), step=1e5, format="%.0f")
        s["monto_solicitado"] = st.number_input("Monto solicitado", value=float(WALMART["monto_solicitado"]), step=1e6, format="%.0f")
        s["plazo_anios"] = st.number_input("Plazo (años)", value=WALMART["plazo_anios"], min_value=1, max_value=30)

    r = evaluar(s, pol)
    st.divider()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Score", f"{r['score']:.0f} / 100",
              delta=None if r["score"] == r["score_modelo"] else f"{r['score'] - r['score_modelo']:.0f} por veto")
    m2.metric("Calificación", r["calificacion"])
    m3.metric("Decisión", r["decision"])
    m4.metric("Capacidad disponible", fmt(r["capacidad_disponible"]),
              delta="El crédito cabe" if r["cabe"] else "El crédito excede la capacidad",
              delta_color="normal" if r["cabe"] else "inverse")

    if r["alertas"]:
        for a in r["alertas"].split("; "):
            st.warning(a)

    g1, g2 = st.columns([3, 2])
    with g1:
        det = pd.DataFrame([{"Indicador": pol["indicadores"][k]["nombre"], "Aporte": v["aporte"],
                             "Puntos": v["puntos"], "Lectura": v["lectura"]} for k, v in r["detalle"].items()])
        fig = go.Figure(go.Waterfall(
            x=list(det["Indicador"]) + ["Score total"], y=list(det["Aporte"]) + [0],
            measure=["relative"] * len(det) + ["total"],
            text=[f"{v:.0f}" for v in det["Aporte"]] + [f"{r['score_modelo']:.0f}"], textposition="outside",
            connector={"line": {"color": "#9AA5B1"}},
            increasing={"marker": {"color": "#3E8E63"}}, totals={"marker": {"color": "#1F5C4A"}}))
        fig.update_layout(title="Cómo se construye el score", height=380, showlegend=False,
                          yaxis_range=[0, 110], margin=dict(t=50, b=10))
        st.plotly_chart(fig, width="stretch")
    with g2:
        st.dataframe(pd.DataFrame({
            "Indicador": ["DSCR (EBITDA)", "Deuda / EBITDA", "Margen EBITDA", "Crecimiento ventas",
                          "DSCR flujo de caja libre", "Tasa del crédito", "Cuota anual", "Servicio total"],
            "Valor": [fmt(r["dscr"], "x"), fmt(r["deuda_ebitda"], "x"), fmt(r["margen_ebitda"], "pct"),
                      fmt(r["crecimiento"], "pct"), fmt(r["dscr_fcl"], "x"), fmt(r["tasa"], "pct"),
                      fmt(r["cuota"]), fmt(r["servicio_total"])]}), hide_index=True, width="stretch")

    st.subheader("Simulación Monte Carlo")
    st.caption("En vez de un solo escenario, se simulan miles de combinaciones de EBITDA y tasa "
               "para estimar qué tan probable es que la empresa no cubra su deuda.")
    s1, s2, s3 = st.columns(3)
    vol_e = s1.slider("Volatilidad del EBITDA", 0.05, 0.50, 0.20, 0.05)
    vol_t = s2.slider("Volatilidad de la tasa (pb)", 0, 500, 150, 50) / 10_000
    n_sim = s3.select_slider("Escenarios", [1_000, 2_000, 5_000], value=2_000)
    dscr_sim, score_sim = monte_carlo(s, pol, n=n_sim, vol_ebitda=vol_e, vol_tasa=vol_t)
    rechazo = (score_sim < 60).mean()
    k1, k2, k3 = st.columns(3)
    k1.metric("Probabilidad DSCR < 1", f"{(dscr_sim < 1).mean():.1%}")
    k2.metric("Probabilidad de quedar en BB o B", f"{rechazo:.1%}")
    k3.metric("DSCR en el peor 5 %", fmt(np.percentile(dscr_sim, 5), "x"))
    fig = px.histogram(x=dscr_sim, nbins=60, labels={"x": "DSCR simulado"}, color_discrete_sequence=["#3E8E63"])
    fig.add_vline(x=1, line_dash="dash", line_color="#B3261E", annotation_text="DSCR = 1")
    fig.update_layout(height=300, yaxis_title="Escenarios", margin=dict(t=20, b=10))
    st.plotly_chart(fig, width="stretch")

# ================================================================ TAB 2: evaluación masiva
with tab2:
    st.write("Sube un Excel o CSV con una fila por solicitud, o prueba con 500 empresas ficticias.")
    c1, c2 = st.columns([3, 1])
    archivo = c1.file_uploader("Archivo de solicitudes", type=["xlsx", "csv"])
    plantilla = pd.DataFrame([{k: WALMART[k] for k in COLUMNAS}])
    c2.download_button("Descargar plantilla", a_excel(plantilla), "plantilla_solicitudes.xlsx")
    usar_ejemplo = c2.button("Usar 500 de ejemplo", type="primary")

    if usar_ejemplo:
        st.session_state["lote"] = generar(500)
    if archivo is not None:
        st.session_state["lote"] = pd.read_csv(archivo) if archivo.name.endswith(".csv") else pd.read_excel(archivo)

    with st.expander("Columnas que debe traer el archivo"):
        st.dataframe(pd.DataFrame({"Columna": COLUMNAS.keys(), "Contenido": COLUMNAS.values()}),
                     hide_index=True, width="stretch")

    if "lote" in st.session_state:
        df = st.session_state["lote"]
        faltan = validar(df)
        if faltan:
            st.error("Faltan estas columnas en el archivo: " + ", ".join(faltan))
            st.stop()

        res = evaluar_lote(df, pol)
        aprob = res["decision"].str.startswith("Aprueba")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Solicitudes", f"{len(res):,}")
        k2.metric("Aprobadas", f"{aprob.sum():,}", f"{aprob.mean():.0%} del total")
        k3.metric("Monto aprobable", fmt(res.loc[aprob, "monto_solicitado"].sum()))
        k4.metric("Aprobadas con flujo libre insuficiente",
                  f"{(aprob & (res['dscr_fcl'] < 1)).sum():,}",
                  help="Empresas aprobadas cuyo flujo de caja libre no cubre el servicio de la deuda.")

        g1, g2 = st.columns(2)
        with g1:
            conteo = res["calificacion"].value_counts().reindex(ORDEN, fill_value=0).reset_index()
            conteo.columns = ["Calificación", "Empresas"]
            fig = px.bar(conteo, x="Calificación", y="Empresas", color="Calificación",
                         color_discrete_map=COLORES, text="Empresas")
            fig.update_layout(showlegend=False, height=360, title="Distribución por calificación")
            st.plotly_chart(fig, width="stretch")
        with g2:
            vis = res.replace([np.inf, -np.inf], np.nan).dropna(subset=["dscr", "deuda_ebitda"])
            vis = vis[(vis["dscr"] < 8) & (vis["deuda_ebitda"] < 8)]
            fig = px.scatter(vis, x="deuda_ebitda", y="dscr", color="calificacion",
                             color_discrete_map=COLORES, category_orders={"calificacion": ORDEN},
                             hover_name="empresa", labels={"deuda_ebitda": "Deuda / EBITDA", "dscr": "DSCR"})
            fig.add_hline(y=1, line_dash="dash", line_color="#B3261E")
            fig.update_layout(height=360, title="Mapa de riesgo", legend_title="")
            st.plotly_chart(fig, width="stretch")

        filtro = st.multiselect("Filtrar por calificación", ORDEN, default=ORDEN)
        tabla = res[res["calificacion"].isin(filtro)][[
            "empresa", "score", "calificacion", "decision", "dscr", "deuda_ebitda",
            "margen_ebitda", "crecimiento", "dscr_fcl", "monto_solicitado", "cabe", "alertas"]]
        st.dataframe(tabla, hide_index=True, width="stretch", height=420, column_config={
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
            "dscr": st.column_config.NumberColumn("DSCR", format="%.2f"),
            "deuda_ebitda": st.column_config.NumberColumn("Deuda/EBITDA", format="%.2f"),
            "margen_ebitda": st.column_config.NumberColumn("Margen", format="percent"),
            "crecimiento": st.column_config.NumberColumn("CAGR", format="percent"),
            "dscr_fcl": st.column_config.NumberColumn("DSCR FCL", format="%.2f"),
            "monto_solicitado": st.column_config.NumberColumn("Monto", format="localized"),
            "cabe": st.column_config.CheckboxColumn("Cabe"),
        })
        st.download_button("Descargar resultados en Excel", a_excel(res), "resultados_scoring.xlsx", type="primary")
    else:
        st.info("Carga un archivo o usa las 500 solicitudes de ejemplo para empezar.")

# ================================================================ TAB 3: estrés
with tab3:
    if "lote" not in st.session_state:
        st.info("Primero carga un lote en la pestaña Evaluación masiva.")
    else:
        st.write("Aplica un choque a todo el portafolio y mira cuántas empresas cambian de calificación.")
        c1, c2 = st.columns(2)
        ch_e = c1.slider("Cambio en el EBITDA", -50, 20, -20, 5, format="%d%%") / 100
        ch_t = c2.slider("Cambio en la tasa del crédito (pb)", -200, 800, 300, 50) / 10_000

        df = st.session_state["lote"]
        base = evaluar_lote(df, pol)
        estres = evaluar_lote(df, pol, choque_ebitda=ch_e, choque_tasa=ch_t)
        m = base[["empresa", "calificacion", "decision", "monto_solicitado"]].merge(
            estres[["empresa", "calificacion", "decision"]], on="empresa", suffixes=("_base", "_estres"))

        ab = m["decision_base"].str.startswith("Aprueba")
        ae = m["decision_estres"].str.startswith("Aprueba")
        k1, k2, k3 = st.columns(3)
        k1.metric("Aprobadas en escenario base", f"{ab.sum():,}")
        k2.metric("Aprobadas bajo estrés", f"{ae.sum():,}", f"{ae.sum() - ab.sum():,}")
        k3.metric("Monto que deja de ser aprobable",
                  fmt(m.loc[ab & ~ae, "monto_solicitado"].sum()))

        matriz = pd.crosstab(m["calificacion_base"], m["calificacion_estres"]).reindex(
            index=ORDEN, columns=ORDEN, fill_value=0)
        fig = px.imshow(matriz, text_auto=True, color_continuous_scale="Greens", aspect="auto",
                        labels=dict(x="Calificación bajo estrés", y="Calificación base", color="Empresas"))
        fig.update_layout(title="Matriz de migración", height=430)
        st.plotly_chart(fig, width="stretch")
        st.caption("La diagonal son las empresas que conservan su calificación. "
                   "Lo que queda a la derecha de la diagonal son deterioros.")

# ================================================================ TAB 4: política y método
with tab4:
    st.write("El score suma cuatro indicadores, cada uno con su peso y su tabla de puntaje. "
             "Las tablas viven en `politica.json`: se pueden cambiar sin tocar el código.")
    cols = st.columns(2)
    for i, (k, cfg) in enumerate(pol["indicadores"].items()):
        with cols[i % 2]:
            st.markdown(f"**{cfg['nombre']}** · peso {cfg['peso']:.0%}")
            st.dataframe(pd.DataFrame(cfg["tabla"], columns=["Desde", "Puntos", "Lectura"]),
                         hide_index=True, width="stretch")
    st.markdown("**Escala de calificación**")
    st.dataframe(pd.DataFrame(pol["escala"], columns=["Score desde", "Calificación", "Decisión"]),
                 hide_index=True, width="stretch")
    st.markdown("""
**Fórmulas principales**

- Servicio de deuda actual = gasto por intereses + deuda de corto plazo
- Cuota del nuevo crédito = PMT(tasa, plazo, monto), con tasa = intereses / deuda financiera
- DSCR = EBITDA / (servicio actual + cuota nueva)
- Flujo de caja libre = EBIT × (1 − t) + depreciación − aumento de capital de trabajo − capex
- Capacidad disponible = EBITDA × múltiplo máximo − deuda actual
""")
