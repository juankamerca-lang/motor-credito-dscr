# Motor de Crédito DSCR (prototipo)

Scorecard de crédito basado en DSCR, replicado de la hoja "Caso Walmart - DSCR".

## Archivos
- `app.py`: interfaz web (Streamlit).
- `motor.py`: lógica del score. No depende de la interfaz; se puede usar desde cualquier script.
- `politica.json`: pesos, tablas de puntaje, escala y reglas de veto. Se edita sin tocar código.
- `generar_datos.py`: crea solicitudes ficticias para pruebas.
- `solicitudes_ejemplo.xlsx` / `.csv`: 500 empresas ficticias (millones COP).

## Cómo ejecutarlo en tu computador
1. Instala Python 3.10 o superior (python.org).
2. Abre una terminal en esta carpeta y ejecuta:
       pip install -r requirements.txt
       streamlit run app.py
3. Se abre el navegador en http://localhost:8501

## Cómo publicarlo con un enlace (gratis)
1. Sube esta carpeta a un repositorio de GitHub.
2. Entra a share.streamlit.io, conecta tu cuenta de GitHub y elige `app.py`.
3. Obtienes un enlace público para mostrar en el congreso.

## Usar el motor sin interfaz
    import pandas as pd
    from motor import cargar_politica, evaluar_lote
    pol = cargar_politica()
    res = evaluar_lote(pd.read_excel("solicitudes_ejemplo.xlsx"), pol)
    res.to_excel("resultados.xlsx", index=False)
