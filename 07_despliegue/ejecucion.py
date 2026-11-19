import warnings
warnings.filterwarnings('ignore')

from funciones import *

# Cargar los datos nuevos (sin las variables que generan las targets)
df = pd.read_csv(RUTA / 'datos_nuevos.csv')
df = df[[v for v in variables_finales if v not in variables_target]]

# Preparar y predecir
df = calidad_datos(df)
df = crear_variables(df)
pred = lanzar_ejecucion(df)

# Guardar solo las columnas útiles
pred = pred.reset_index()[['id_cliente', 'prediccion_pd', 'prediccion_ead', 'prediccion_lgd', 'perdida_esperada']]
pred.to_csv(RUTA / 'predicciones.csv', index=False)

# Resumen (sin target no se pueden calcular AUC ni MAE)
print(f'Clientes puntuados:     {len(pred)}')
print(f"PD media:               {pred['prediccion_pd'].mean():.4f}")
print(f"EAD media:              {pred['prediccion_ead'].mean():.4f}")
print(f"LGD media:              {pred['prediccion_lgd'].mean():.4f}")
print(f"Pérdida esperada total: {pred['perdida_esperada'].sum():,.0f}")
