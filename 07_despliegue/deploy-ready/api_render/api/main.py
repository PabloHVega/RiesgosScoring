from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import ValidationError

from api.schemas import Entrada
from api.scoring_utils import score_dataframe

BUILD_VERSION = 'v2'
COLUMNAS_SALIDA = ['id_cliente', 'pd', 'ead', 'lgd', 'perdida_esperada']

# Historial de clientes: se lee una vez al arrancar la API
RUTA_HISTORIAL = Path(__file__).parent / 'data' / 'demo_03_riesgos.csv'
# 'unknown' en el CSV equivale a un nulo: calidad_datos lo convertirá en 'desconocido' como en el train
HISTORIAL = pd.read_csv(RUTA_HISTORIAL, encoding='utf-8', na_values=['unknown'])

app = FastAPI(title='Riesgos Scoring API',
              description='PD, EAD, LGD y pérdida esperada: datos de la operación (API) + historial del cliente (CSV)')


@app.get('/health')
def health():
    return {'status': 'ok', 'build': BUILD_VERSION, 'clientes_historial': len(HISTORIAL)}


@app.get('/debug')
def debug():
    '''Versiones de Python y librerías, y prueba de carga del artefacto.'''
    import sys, pickle, sklearn
    from funciones import RUTA_ARTEFACTO
    info = {'build': BUILD_VERSION, 'python': sys.version, 'sklearn': sklearn.__version__,
            'historial': str(RUTA_HISTORIAL.name), 'clientes_historial': len(HISTORIAL)}
    try:
        with open(RUTA_ARTEFACTO, 'rb') as f:
            info['artefacto'] = str(type(pickle.load(f)))
    except Exception as e:
        info['artefacto_error'] = f'{type(e).__name__}: {e}'
    return info


@app.get('/clientes')
def clientes():
    '''Ids de cliente disponibles en el historial.'''
    return HISTORIAL['id_cliente'].tolist()


# Documenta el cuerpo de /score en /docs (1 registro o lista), ya que se parsea a mano con Request
EJEMPLO = {'id_cliente': 95167938, 'principal': 12000.0, 'tipo_interes': 13.49,
           'num_cuotas': ' 36 months', 'finalidad': 'car', 'vivienda': 'MORTGAGE'}
CUERPO_SCORE = {'requestBody': {'required': True, 'content': {'application/json': {
    'schema': {'oneOf': [Entrada.model_json_schema(),
                         {'type': 'array', 'items': Entrada.model_json_schema()}]},
    'examples': {
        'un_cliente': {'summary': 'Un cliente', 'value': EJEMPLO},
        'varios_clientes': {'summary': 'Varios clientes', 'value': [
            EJEMPLO, {'id_cliente': 3379997, 'principal': 35000.0, 'tipo_interes': 19.05,
                      'num_cuotas': ' 36 months', 'finalidad': 'other', 'vivienda': 'RENT'}]}}}}}}


@app.post('/score', openapi_extra=CUERPO_SCORE)
async def score(request: Request,
                fields: Optional[List[str]] = Query(None, description='Columnas a devolver')):
    body = await request.json()
    registros = [body] if isinstance(body, dict) else body          # 1 o N registros
    try:
        datos = [Entrada(**r).model_dump() for r in registros]
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors(include_url=False))

    # Unir los datos de la operación (API) con el historial del cliente (CSV)
    operaciones = pd.DataFrame(datos)
    no_encontrados = sorted(set(operaciones['id_cliente']) - set(HISTORIAL['id_cliente']))
    if no_encontrados:
        raise HTTPException(status_code=404,
                            detail={'error': 'Clientes sin historial', 'id_cliente': no_encontrados})
    df = operaciones.merge(HISTORIAL, on='id_cliente', how='left')

    resultado = score_dataframe(df)

    fields = fields or COLUMNAS_SALIDA
    fields = [c for c in fields if c in resultado.columns]
    if 'id_cliente' not in fields:
        fields.insert(0, 'id_cliente')
    return resultado[fields].to_dict(orient='records')
