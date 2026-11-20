'''Validación de la entrada de la API: solo los datos de la operación.
El resto de variables del modelo salen del historial (api/data/demo_03_riesgos.csv)
e imp_cuota se calcula con el sistema francés.
'''
from pydantic import BaseModel, ConfigDict


class Entrada(BaseModel):
    model_config = ConfigDict(extra='ignore')   # cualquier otra columna enviada se ignora

    id_cliente: int
    principal: float                            # importe del préstamo
    tipo_interes: float                         # interés anual en %, p. ej. 18.06
    num_cuotas: str                             # ' 36 months' / ' 60 months'
    finalidad: str                              # debt_consolidation, credit_card ...
    vivienda: str                               # MORTGAGE / RENT / OWN ...
