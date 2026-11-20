# API Riesgos Scoring — despliegue

API FastAPI que devuelve, por cliente, **PD, EAD, LGD y pérdida esperada** (`PD x EAD x LGD x principal`).
No contiene lógica de ML. El flujo es este:

```
JSON (datos de la operación) ──┐
                               ├─ merge por id_cliente ─> imp_cuota (sistema francés) ─> calidad_datos ─> crear_variables ─> lanzar_ejecucion
api/data/demo_03_riesgos.csv ──┘   (historial del cliente)
```

## Estructura

```
api_render/
├── api/main.py              endpoints; lee el historial al arrancar y lo une a la petición
├── api/schemas.py           validación de la entrada (6 variables de la operación)
├── api/scoring_utils.py     cálculo de imp_cuota + mismo flujo que ejecucion.py
├── api/data/demo_03_riesgos.csv   historial de clientes (simulado)
├── funciones.py             copia de 07_despliegue/funciones.py
├── artefacto_pipeline.pkl   copia del artefacto {'pd', 'ead', 'lgd'}
├── requirements.txt / runtime.txt
```

Si se reentrena el modelo (`07_despliegue/reentrenamiento.py`), hay que **volver a copiar** `funciones.py` y `artefacto_pipeline.pkl` a esta carpeta.

## De dónde sale cada variable

| Origen | Variables |
|---|---|
| **Petición a la API** (obligatorias) | `id_cliente, principal, tipo_interes, num_cuotas, finalidad, vivienda` |
| **Historial** `api/data/demo_03_riesgos.csv` | `ingresos, ingresos_verificados, rating, dti, antigüedad_empleo, num_lineas_credito, porc_uso_revolving, num_derogatorios` |
| **Calculada** | `imp_cuota = principal · r / (1 − (1 + r)^−n)`, con `r = tipo_interes / 1200` y `n` = nº de cuotas |

- El valor `'unknown'` del historial se lee como nulo, para que `calidad_datos` lo trate igual que en el entrenamiento (`'desconocido'`).
- Si un `id_cliente` no está en el historial, la API responde **404** con la lista de ids no encontrados. `GET /clientes` devuelve los ids disponibles.
- Los clientes con `ingresos > 400000` se descartan en `calidad_datos` y no aparecen en la respuesta.

## Prueba en local

```bash
cd 07_despliegue/deploy-ready/api_render
uvicorn api.main:app --reload
```

Documentación interactiva: http://127.0.0.1:8000/docs

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado, versión del build y nº de clientes en el historial |
| GET | `/debug` | Versión de Python y sklearn, y prueba de carga del artefacto |
| GET | `/clientes` | Ids disponibles en el historial |
| POST | `/score` | 1 registro (objeto) o N (lista). `?fields=pd&fields=lgd` filtra las columnas (siempre incluye `id_cliente`) |

**Salida**: `id_cliente, pd, ead, lgd, perdida_esperada`, con el mismo redondeo que `06_resultados/scoring.csv`.

## Ejemplos (clientes reales del historial)

Un registro:

```bash
curl -X POST http://127.0.0.1:8000/score -H "Content-Type: application/json" -d '{"id_cliente": 95167938, "principal": 12000.0, "tipo_interes": 13.49, "num_cuotas": " 36 months", "finalidad": "car", "vivienda": "MORTGAGE"}'
```

Respuesta: `[{"id_cliente":95167938,"pd":0.052,"ead":0.642,"lgd":0.888,"perdida_esperada":356.72}]`

Varios registros:

```bash
curl -X POST http://127.0.0.1:8000/score -H "Content-Type: application/json" -d '[{"id_cliente": 95167938, "principal": 12000.0, "tipo_interes": 13.49, "num_cuotas": " 36 months", "finalidad": "car", "vivienda": "MORTGAGE"}, {"id_cliente": 3379997, "principal": 35000.0, "tipo_interes": 19.05, "num_cuotas": " 36 months", "finalidad": "other", "vivienda": "RENT"}]'
```

En Windows/PowerShell es más cómodo usar `Invoke-RestMethod` o la página `/docs`.

## Despliegue en Render (Web Service)

1. Subir el repositorio a GitHub, incluidos `artefacto_pipeline.pkl` y `api/data/demo_03_riesgos.csv` (este último tiene una excepción en `.gitignore`, que excluye `*.csv`).
2. En Render: **New → Web Service** → conectar el repositorio.
3. Configuración:
   - **Root Directory**: `07_despliegue/deploy-ready/api_render`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
4. Variable de entorno recomendada: `PYTHON_VERSION=3.12.16` (Render puede ignorar `runtime.txt`).
5. Tras el despliegue, abrir `/debug` y comprobar que Python es 3.12, sklearn 1.9.1, `artefacto` es `<class 'dict'>` y `clientes_historial` vale 20.

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| La API no arranca: `FileNotFoundError ... demo_03_riesgos.csv` | El CSV no se subió (`*.csv` está en `.gitignore`) | Comprobar la excepción en `.gitignore` y que el CSV está en el commit |
| `/debug` muestra `artefacto_error` (`ModuleNotFoundError`, `AttributeError`) | Falta `funciones.py` junto a la API o el artefacto no se generó con `reentrenamiento.py` | Relanzar `reentrenamiento.py`, volver a copiar el artefacto y `funciones.py` |
| Error o warning de versión al cargar el `.pkl` | scikit-learn distinto al del entrenamiento | Mantener `scikit-learn==1.9.1` en `requirements.txt` |
| Python en `/debug` ≠ `runtime.txt` | Render ignora `runtime.txt` | Fijar `PYTHON_VERSION` o usar Docker |

Alternativa Docker (cambiar el servicio a tipo "Docker" en Render):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "10000"]
```
