'''
Puente entre la API y el motor de A_09 (funciones.py). No contiene lógica de ML:
reproduce paso a paso el flujo de ejecucion.py sobre un DataFrame recibido por la API.
'''
import pandas as pd
from funciones import *

# id_cliente ya forma parte de variables_finales: no hay columnas de identificación extra
COLUMNAS_ID = []

# Columnas originales de entrada (variables_finales sin las que generan las targets)
COLUMNAS_ENTRADA = [v for v in variables_finales if v not in variables_target] + COLUMNAS_ID


def calcular_cuota(principal, tipo_interes, num_cuotas):
    '''Cuota mensual con el sistema francés: principal * r / (1 - (1 + r)^-n),
    con r = interés anual / 12 / 100 y n = número de cuotas ('36 months' -> 36).
    Funciona con escalares o con Series de pandas. Reproduce imp_cuota del train al céntimo.'''
    n = pd.Series(num_cuotas).astype(str).str.extract(r'(\d+)')[0].astype(int).values
    r = pd.Series(tipo_interes).astype(float).values / 1200
    p = pd.Series(principal).astype(float).values
    with np.errstate(divide='ignore', invalid='ignore'):
        cuota = np.where(r > 0, p * r / (1 - (1 + r) ** -n), p / n)
    return np.round(cuota, 2)


def score_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Aplica el mismo flujo que ejecucion.py.
    Recibe los datos originales (operación + historial) y calcula imp_cuota.
    Devuelve un DataFrame con id_cliente, pd, ead, lgd y perdida_esperada.
    Nota: calidad_datos descarta los clientes con ingresos > 400.000 (no aparecen en la salida).
    '''
    df = df.copy()
    df['imp_cuota'] = calcular_cuota(df['principal'], df['tipo_interes'], df['num_cuotas'])
    df = df[COLUMNAS_ENTRADA]
    df = calidad_datos(df)
    df = crear_variables(df)
    pred = lanzar_ejecucion(df)

    pred = pred.reset_index()[['id_cliente', 'prediccion_pd', 'prediccion_ead', 'prediccion_lgd', 'perdida_esperada']]
    pred.columns = ['id_cliente', 'pd', 'ead', 'lgd', 'perdida_esperada']
    pred = pred.round({'pd': 3, 'ead': 3, 'lgd': 3, 'perdida_esperada': 2})
    return pred
