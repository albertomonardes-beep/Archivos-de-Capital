import os
from datetime import datetime
from pymongo import MongoClient

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME     = "capital"

# Fecha desde la cual aplica la configuración de trading.
# Trades abiertos antes de esta fecha → configuracion en blanco (se maneja en Power BI).
FECHA_INICIO_CONFIGURACION = datetime(2025, 12, 17)

# instrumentName debe coincidir exactamente con los valores en la colección operaciones.
ACTIVOS = [
    {
        "instrumentName":           "AUDUSD",
        "nombre":                   "AUD/USD",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Multiplica",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "BTCUSD",
        "nombre":                   "Bitcoin/USD",
        "grupo":                    "Cripto",
        "apalancamiento":           20,
        "frenteUSD":                "Multiplica",
        "configuracion":            "Bitcoin",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "USCOCOA",
        "nombre":                   "Cocoa US",
        "grupo":                    "M. Primas",
        "apalancamiento":           20,
        "frenteUSD":                "Multiplica",
        "configuracion":            "",
        "fechaInicioConfiguracion":  None,
    },
    {
        "instrumentName":           "COFFEEARABICA",
        "nombre":                   "Coffee US",
        "grupo":                    "M. Primas",
        "apalancamiento":           20,
        "frenteUSD":                "Multiplica",
        "configuracion":            "",
        "fechaInicioConfiguracion":  None,
    },
    {
        "instrumentName":           "COPPER",
        "nombre":                   "Copper",
        "grupo":                    "M. Primas",
        "apalancamiento":           20,
        "frenteUSD":                "Multiplica",
        "configuracion":            "",
        "fechaInicioConfiguracion":  None,
    },
    {
        "instrumentName":           "EURUSD",
        "nombre":                   "EUR/USD",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Multiplica",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "GBPUSD",
        "nombre":                   "GBP/USD",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Multiplica",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "GOLD",
        "nombre":                   "Gold",
        "grupo":                    "Metales",
        "apalancamiento":           20,
        "frenteUSD":                "Multiplica",
        "configuracion":            "Metales",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "NOKSEK",
        "nombre":                   "NOK/SEK",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Ignorar",
        "configuracion":            "",
        "fechaInicioConfiguracion":  None,
    },
    {
        "instrumentName":           "SILVER",
        "nombre":                   "Silver",
        "grupo":                    "Metales",
        "apalancamiento":           20,
        "frenteUSD":                "Multiplica",
        "configuracion":            "Metales",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "SOLUSD",
        "nombre":                   "Solana/USD",
        "grupo":                    "Cripto",
        "apalancamiento":           20,
        "frenteUSD":                "Multiplica",
        "configuracion":            "",
        "fechaInicioConfiguracion":  None,
    },
    {
        "instrumentName":           "USDCAD",
        "nombre":                   "USD/CAD",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Igual",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "USDCHF",
        "nombre":                   "USD/CHF",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Igual",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "USDCNH",
        "nombre":                   "USD/CNH",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Igual",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "USDJPY",
        "nombre":                   "USD/JPY",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Igual",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "USDMXN",
        "nombre":                   "USD/MXN",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Igual",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "USDSEK",
        "nombre":                   "USD/SEK",
        "grupo":                    "Divisas",
        "apalancamiento":           50,
        "frenteUSD":                "Igual",
        "configuracion":            "Base Forex",
        "fechaInicioConfiguracion":  FECHA_INICIO_CONFIGURACION,
    },
    {
        "instrumentName":           "US100",
        "nombre":                   "US Tech 100",
        "grupo":                    "Indices",
        "apalancamiento":           20,
        "frenteUSD":                "Ignorar",
        "configuracion":            "",
        "fechaInicioConfiguracion":  None,
    },
]


def main():
    print("Conectando a MongoDB...")
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    db     = client[DB_NAME]
    col    = db["activos"]

    print(f"Cargando {len(ACTIVOS)} activos...")
    insertados   = 0
    actualizados = 0

    for activo in ACTIVOS:
        result = col.update_one(
            {"instrumentName": activo["instrumentName"]},
            {"$set": activo},
            upsert=True
        )
        if result.upserted_id:
            insertados += 1
            print(f"  [NUEVO]       {activo['instrumentName']} ({activo['nombre']})")
        elif result.modified_count:
            actualizados += 1
            print(f"  [ACTUALIZADO] {activo['instrumentName']} ({activo['nombre']})")
        else:
            print(f"  [SIN CAMBIOS] {activo['instrumentName']} ({activo['nombre']})")

    print()
    print(f"Completado: {insertados} insertados, {actualizados} actualizados.")
    client.close()


if __name__ == "__main__":
    main()
