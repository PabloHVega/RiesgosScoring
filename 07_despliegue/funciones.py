'''
FUNCIONES DEL PROYECTO RIESGOS SCORING (PD, EAD, LGD y pérdida esperada)

Flujo de ENTRENAMIENTO:  calidad_datos -> crear_variables -> lanzar_entrenamiento
Flujo de EJECUCIÓN:      calidad_datos -> crear_variables -> lanzar_ejecucion
'''
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, MinMaxScaler, Binarizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold, KFold
from sklearn.metrics import roc_auc_score, mean_absolute_error

RUTA = Path(__file__).parent                 # carpeta 07_despliegue
RUTA_ARTEFACTO = RUTA / 'artefacto_pipeline.pkl'
TARGETS = ['target_pd', 'target_ead', 'target_lgd']

# Variables originales necesarias para construir las targets (no existen en ejecución)
variables_target = ['estado', 'imp_amortizado', 'imp_recuperado']

# Variables ORIGINALES necesarias (identificador + predictoras + origen de las targets)
variables_finales = ['id_cliente',
                     'ingresos_verificados', 'vivienda', 'finalidad', 'num_cuotas',
                     'antigüedad_empleo', 'rating',
                     'ingresos', 'dti', 'num_lineas_credito', 'porc_uso_revolving',
                     'principal', 'tipo_interes', 'imp_cuota', 'num_derogatorios'] + variables_target


# =====================================================================
# 1. CALIDAD DE DATOS
# =====================================================================
def calidad_datos(df):
    """Aplica las correcciones de calidad con reglas fijas (no aprende de los datos).
    Recibe el df con variables_finales (con o sin targets) y devuelve el df corregido,
    indexado por id_cliente: imputación de nulos, tipos, recortes de dti y
    porc_uso_revolving a [0, 100], renombrado de dti a DTI y filtro de ingresos > 400.000.
    """
    df = df.copy().set_index('id_cliente')
    # Nulos: categórica a 'desconocido' y numéricas a cero
    df['antigüedad_empleo'] = df['antigüedad_empleo'].fillna('desconocido')
    var_num = df.select_dtypes(include='number').columns
    df[var_num] = df[var_num].fillna(0)
    df[['num_lineas_credito', 'num_derogatorios']] = df[['num_lineas_credito', 'num_derogatorios']].astype(int)
    # Valores sin sentido de negocio
    df['dti'] = np.clip(df['dti'], 0, 100)
    df['porc_uso_revolving'] = np.clip(df['porc_uso_revolving'], 0, 100)
    df = df.rename(columns={'dti': 'DTI'})
    # Atípicos: eliminar registros con ingresos superiores a 400.000
    df = df.loc[df['ingresos'] <= 400000]
    return df


# =====================================================================
# 2. CREACIÓN DE VARIABLES
# =====================================================================
def crear_variables(df):
    """Agrupa categorías poco frecuentes y, si están las variables de origen, crea las targets.
    target_pd: impago; target_ead: pendiente / principal; target_lgd: 1 - recuperado / pendiente.
    EAD y LGD se recortan a [0, 1]. Recibe el df tras calidad_datos y lo devuelve
    sin las variables de origen de las targets.
    """
    df = df.copy()
    df['vivienda'] = df['vivienda'].replace(['ANY', 'OTHER', 'NONE'], 'MORTGAGE')
    df['finalidad'] = df['finalidad'].replace(['wedding', 'renewable_energy', 'educational'], 'other')
    if 'estado' in df.columns:
        df['target_pd'] = np.where(df['estado'].isin(['Charged Off', 'Does not meet the credit policy. Status:Charged Off', 'Default']), 1, 0)
        pendiente = df['principal'] - df['imp_amortizado']
        df['target_ead'] = pendiente / df['principal']
        # Los nulos aparecen cuando el pendiente es cero
        df['target_lgd'] = (1 - (df['imp_recuperado'] / pendiente)).fillna(0)
        df[['target_ead', 'target_lgd']] = df[['target_ead', 'target_lgd']].clip(0, 1)
        df = df.drop(columns=variables_target)
    return df


# =====================================================================
# 3. TRANSFORMACIÓN DE VARIABLES
# =====================================================================
def transformar_variables(excluir=()):
    """Devuelve (sin ajustar) el ColumnTransformer común a los tres modelos.
    OHE en categóricas nominales, OrdinalEncoder + MinMax en antigüedad y rating,
    MinMax en numéricas y Binarizer en num_derogatorios. El resto de columnas se descarta.
    excluir: variables numéricas que no usa un modelo concreto (p. ej. tipo_interes en PD).
    """
    var_ohe = ['ingresos_verificados', 'vivienda', 'finalidad', 'num_cuotas']
    var_oe = ['antigüedad_empleo', 'rating']
    var_mms = [v for v in ['ingresos', 'DTI', 'num_lineas_credito', 'porc_uso_revolving', 'principal',
                           'tipo_interes', 'imp_cuota'] if v not in excluir]
    var_bin = ['num_derogatorios']

    orden_antigüedad_empleo = ['desconocido', '< 1 year', '1 year', '2 years', '3 years', '4 years',
                               '5 years', '6 years', '7 years', '8 years', '9 years', '10+ years']
    orden_rating = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
    oe_mms = Pipeline([('oe', OrdinalEncoder(categories=[orden_antigüedad_empleo, orden_rating],
                                             handle_unknown='use_encoded_value', unknown_value=-1)),
                       ('mms', MinMaxScaler())])

    return ColumnTransformer([('ohe', OneHotEncoder(sparse_output=False, handle_unknown='ignore'), var_ohe),
                              ('oe_mms', oe_mms, var_oe),
                              ('mms', MinMaxScaler(), var_mms),
                              ('bin', Binarizer(threshold=0), var_bin)],
                             remainder='drop')


# =====================================================================
# 4. MODELIZACIÓN
# =====================================================================
def modelizar(x, y, algoritmo, parrilla, cv, scoring, n_iter, nombre, excluir=()):
    """Construye Pipeline([transformar, algoritmo]) y busca hiperparámetros con RandomizedSearchCV.
    Recibe x, y, el algoritmo, su parrilla, la validación cruzada, la métrica, n_iter, el
    nombre del modelo y las variables a excluir. Muestra la métrica de CV y los mejores hiperparámetros.
    Devuelve el mejor pipeline reentrenado con todos los datos recibidos.
    """
    pipe = Pipeline([('transformar', transformar_variables(excluir)), ('algoritmo', algoritmo)])
    busqueda = RandomizedSearchCV(pipe, parrilla, n_iter=n_iter, cv=cv, scoring=scoring,
                                  n_jobs=-1, random_state=42)
    busqueda.fit(x, y)
    print(f'{nombre} | CV {scoring} = {busqueda.best_score_:.4f} | {busqueda.best_params_}')
    return busqueda.best_estimator_


# =====================================================================
# 5. ENTRENAMIENTO
# =====================================================================
def lanzar_entrenamiento(df):
    """Entrena los tres modelos y guarda un único artefacto {'pd', 'ead', 'lgd'} en RUTA_ARTEFACTO.
    PD se entrena con todos los clientes y EAD y LGD solo con los que incumplieron
    (target_pd == 1).
    Recibe el df tras calidad_datos y crear_variables (con targets).
    """
    x = df.drop(columns=TARGETS)
    defaults = df['target_pd'] == 1

    parrilla_pd = {'algoritmo__l1_ratio': [0, 0.5, 1],
                   'algoritmo__C': [0.01, 0.25, 0.5, 0.75, 1]}
    parrilla_reg = {'algoritmo__learning_rate': [0.01, 0.025, 0.05, 0.1],
                    'algoritmo__max_iter': [50, 100, 200],
                    'algoritmo__max_depth': [5, 10, 20],
                    'algoritmo__l2_regularization': [0, 0.25, 0.5, 0.75, 1]}

    artefacto = {}
    # PD sin tipo_interes: el interés lo fija el banco según el rating y, con el rating en el modelo,
    # su coeficiente salía negativo (a menor interés, más PD). El interés sigue entrando vía imp_cuota.
    artefacto['pd'] = modelizar(x, df['target_pd'],
                                LogisticRegression(solver='saga', penalty='elasticnet', max_iter=1000), parrilla_pd,
                                StratifiedKFold(n_splits=5, shuffle=True, random_state=42), 'roc_auc',
                                n_iter=15, nombre='PD', excluir=['tipo_interes'])
    for modelo in ['ead', 'lgd']:
        artefacto[modelo] = modelizar(x[defaults], df.loc[defaults, 'target_' + modelo],
                                      HistGradientBoostingRegressor(min_samples_leaf=50, scoring='neg_mean_absolute_percentage_error'),
                                      parrilla_reg, KFold(n_splits=3, shuffle=True, random_state=42),
                                      'neg_mean_absolute_error', n_iter=25, nombre=modelo.upper())

    with open(RUTA_ARTEFACTO, 'wb') as f:
        pickle.dump(artefacto, f)


# =====================================================================
# 6. EJECUCIÓN
# =====================================================================
def lanzar_ejecucion(df):
    """Carga el artefacto y predice PD (probabilidad), EAD y LGD (recortadas a [0, 1]).
    Calcula la pérdida esperada = PD x EAD x LGD x principal.
    Recibe el df tras calidad_datos y crear_variables y lo devuelve con las columnas
    prediccion_pd, prediccion_ead, prediccion_lgd y perdida_esperada.
    """
    with open(RUTA_ARTEFACTO, 'rb') as f:
        artefacto = pickle.load(f)
    x = df.drop(columns=TARGETS, errors='ignore')
    df = df.copy()
    df['prediccion_pd'] = artefacto['pd'].predict_proba(x)[:, 1]
    df['prediccion_ead'] = np.clip(artefacto['ead'].predict(x), 0, 1)
    df['prediccion_lgd'] = np.clip(artefacto['lgd'].predict(x), 0, 1)
    df['perdida_esperada'] = df['prediccion_pd'] * df['prediccion_ead'] * df['prediccion_lgd'] * df['principal']
    return df
