# DS4B Risk Score Analyzer — app Streamlit

Interfaz de usuario de la API de riesgos (A11). Para un cliente y un préstamo, muestra la **pérdida esperada (EL)**, el **nivel de riesgo** y los indicadores **PD, EAD y LGD**.

La app **no contiene lógica de ML**: construye el JSON a partir del formulario, lo envía a `POST /score` y presenta la respuesta. El modelo, el historial del cliente y el cálculo de `imp_cuota` están en la API (`07_despliegue/deploy-ready/api_render`).

```
07_despliegue/app/
├── app.py                 configuración → cliente HTTP → payload → UI → visualización
├── idea/design_spec.json  diseño acordado (incluye "decisiones_contrato")
├── assets/                logo.png y favicon.png (opcionales; la app funciona sin ellos)
├── requirements.txt
└── README.md
```

## Qué envía y qué muestra

| Formulario | Campo de la API |
|---|---|
| Cliente (20 con historial) | `id_cliente` |
| Importe (1.000–40.000 €) | `principal` |
| Tipo de interés (1–31 %) | `tipo_interes` |
| Duración (12, 24, 36, 48, 60 meses) | `num_cuotas`: el modelo solo conoce 36 y 60, así que 12 y 24 se envían como `" 36 months"` y 48 como `" 60 months"` (la app avisa) |
| Finalidad (en castellano) | `finalidad` (categoría real) |
| Situación vivienda (Hipoteca/Propia/Alquiler) | `vivienda` (MORTGAGE/OWN/RENT) |

Con la respuesta (`pd`, `ead`, `lgd`, `perdida_esperada`), la app muestra:
- **EL en €** y **EL % sobre el importe**.
- **Nivel de riesgo** según EL %: bajo si es menor del 5 %, medio entre el 5 % y el 10 %, y alto si supera el 10 %.
- Una barra de impacto con el umbral en el 10 %.
- Indicadores de PD, EAD (también en €) y LGD.

Los umbrales están en el bloque de configuración de `app.py`.

## Local (dos terminales, con el entorno `RiesgosScoring` activado)

1. **Terminal 1 (API):**
   ```
   cd 07_despliegue/deploy-ready/api_render
   uvicorn api.main:app --reload
   ```
   Para comprobar que funciona, abre http://127.0.0.1:8000/docs.
2. **Terminal 2 (app), sin cerrar la 1:**
   ```
   cd 07_despliegue/app
   streamlit run app.py
   ```
   La app se abre en http://localhost:8501.
3. Ejecuta `pip install -r requirements.txt` solo si te faltan paquetes.

## Render (después de validar en local)

1. La API tiene que estar desplegada y responder: https://riesgosscoring.onrender.com/health
2. En `app.py`, cambia `API_BASE_URL = 'http://127.0.0.1:8000'` por `API_BASE_URL = 'https://riesgosscoring.onrender.com'` (`127.0.0.1` no sirve en Render). Después haz commit y push.
3. En Render, ve a **New → Web Service** y elige el mismo repositorio:
   - **Root Directory**: `07_despliegue/app`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
   - **Environment**: `PYTHON_VERSION` = `3.12.16`
   - **Instance Type**: Free
4. Si falla el deploy, copia el log de build o de ejecución y pásaselo al agente.

## Cold start

En el plan Free, la API se suspende tras 15 minutos sin uso y la primera llamada puede tardar unos 50 segundos. Al pulsar **Calcular riesgo**, la app despierta la API (espera hasta 3 minutos) y reintenta una vez si hay un timeout o un fallo de conexión. Si aun así falla, basta con volver a pulsar el botón.
