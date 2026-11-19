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

# Guardar el scoring de los 3 modelos (escala 0-1, como en los notebooks) y la pérdida esperada (€)
pred = pred.reset_index()[['id_cliente', 'prediccion_pd', 'prediccion_ead', 'prediccion_lgd', 'perdida_esperada']]
pred.columns = ['id_cliente', 'pd', 'ead', 'lgd', 'perdida_esperada']
pred = pred.round({'pd': 3, 'ead': 3, 'lgd': 3, 'perdida_esperada': 2})
pred.to_csv(RUTA.parent / '06_resultados' / 'scoring.csv', index=False)

# Resumen (sin target no se pueden calcular AUC ni MAE)
print(f'Clientes puntuados:     {len(pred)}')
print(f"PD media:               {pred['pd'].mean():.3f}")
print(f"EAD media:              {pred['ead'].mean():.3f}")
print(f"LGD media:              {pred['lgd'].mean():.3f}")
print(f"Pérdida esperada total: {pred['perdida_esperada'].sum():,.0f}")
