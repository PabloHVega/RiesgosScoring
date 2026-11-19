import warnings
warnings.filterwarnings('ignore')

from funciones import *

# Cargar los datos de entrenamiento
df = pd.read_pickle(RUTA.parent / '02_datos' / '03_Entrenamiento' / 'train.pkl')
df = df[variables_finales]

# Preparar y entrenar (busca hiperparámetros y guarda el artefacto con PD, EAD y LGD)
df = calidad_datos(df)
df = crear_variables(df)
lanzar_entrenamiento(df)

# Evaluar sobre validación (datos nunca vistos). EAD y LGD solo sobre los defaults
df = pd.read_pickle(RUTA.parent / '02_datos' / '02_Validacion' / 'validacion.pkl')
df = crear_variables(calidad_datos(df[variables_finales]))
pred = lanzar_ejecucion(df)
defaults = pred['target_pd'] == 1
print('\nVALIDACIÓN')
print(f"AUC PD  = {roc_auc_score(pred['target_pd'], pred['prediccion_pd']):.4f}")
print(f"MAE EAD = {mean_absolute_error(pred.loc[defaults, 'target_ead'], pred.loc[defaults, 'prediccion_ead']):.4f}")
print(f"MAE LGD = {mean_absolute_error(pred.loc[defaults, 'target_lgd'], pred.loc[defaults, 'prediccion_lgd']):.4f}")
