- Me responderás siempre en español de España.
- Comenzarás cada mensaje con este emoji 🤖
- Siempre genera código para el script abierto, nunca para la ventana interactiva, salvo que se indique explícitamente lo contrario.
- La ventana interactiva solo se usará para verificar resultados o mensajes de error, pero no para generar código.
- No expliques el código si no se solicita.

## Estado del proyecto
- A_09: scripts 07_despliegue/funciones.py, reentrenamiento.py y ejecucion.py (genera 06_resultados/scoring.csv).
- A11 completada — API FastAPI en 07_despliegue/deploy-ready/api_render, desplegada en https://riesgosscoring.onrender.com
  - Endpoints: /health, /debug, /clientes, POST /score. Entrada [{id_cliente, principal, tipo_interes, num_cuotas, finalidad, vivienda}]; historial en api/data/demo_03_riesgos.csv; imp_cuota por sistema francés.
  - Salida: [{id_cliente, pd, ead, lgd, perdida_esperada}].
  - Render API: Root 07_despliegue/deploy-ready/api_render | Build pip install -r requirements.txt | Start uvicorn api.main:app --host 0.0.0.0 --port $PORT | PYTHON_VERSION 3.12.16

Fase actual: A_12 completada — App Streamlit
- App: 07_despliegue/app/ (consume <API_BASE_URL>/score, entrada [{...}]). API_BASE_URL se lee de la variable de entorno; por defecto https://riesgosscoring.onrender.com
- Local: API en terminal 1 (api_render, uvicorn api.main:app --reload); app en terminal 2 (07_despliegue/app, con API_BASE_URL=http://127.0.0.1:8000, streamlit run app.py)
- Render app (desplegada y funcionando, auto-deploy): Root 07_despliegue/app | Build pip install -r requirements.txt | Start streamlit run app.py --server.port $PORT --server.address 0.0.0.0 | PYTHON_VERSION 3.12.16
- Modelo PD: sin tipo_interes, max_iter=1000; OrdinalEncoder unknown_value=-1. AUC validación 0,6991. funciones.py y 08_Preproduccion.ipynb alineados
