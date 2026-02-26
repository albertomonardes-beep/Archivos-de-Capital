# Capital.com → MongoDB → Power BI

Automatización para descargar datos de trading de Capital.com, almacenarlos en MongoDB Atlas y visualizarlos en Power BI.

---

## ¿Qué hace este proyecto?

1. **Descarga** operaciones y trades desde la API de Capital.com
2. **Almacena** los datos en MongoDB Atlas (sin duplicados, como números correctamente tipados)
3. **Enriquece** los datos con parámetros fijos por activo (grupo, configuración, apalancamiento)
4. **Notifica** por Telegram cuando termina o si hay un error
5. **Visualiza** los datos en Power BI conectado a MongoDB vía script Python

---

## Arquitectura

```
Capital.com API → AWS Lambda → MongoDB Atlas → Power BI
                                    ↓
                               Telegram Bot
```

---

## Archivos

| Archivo | Descripción |
|---|---|
| `capital_downloader.py` | Script principal que corre en AWS Lambda |
| `cargar_activos.py` | Script de ejecución única para cargar la colección `activos` en MongoDB |

---

## Configuración en AWS Lambda

### Variables de entorno requeridas

| Variable | Descripción |
|---|---|
| `CAPITAL_API_KEY` | API Key de Capital.com |
| `CAPITAL_IDENTIFIER` | Email o usuario de Capital.com |
| `CAPITAL_PASSWORD` | Contraseña de Capital.com |
| `MONGODB_URI` | URI de conexión a MongoDB Atlas |
| `TELEGRAM_TOKEN` | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | ID del chat de Telegram |

### Despliegue

1. Subir el ZIP en AWS Lambda → pestaña **Código** → **Cargar desde** → **Archivo ZIP**
2. Hacer clic en **Implementar**
3. Ejecutar un **Test** para verificar

### Programación (EventBridge)

La función está programada para ejecutarse automáticamente con dos triggers:

| Schedule (UTC) | Hora local (Chile UTC-3) | Propósito |
|---|---|---|
| `cron(0 2 * * ? *)` | 23:00 | Captura operaciones del día, incluyendo swaps |
| `cron(30 9 * * ? *)` | 06:30 | Verificación matutina |

> ⚠️ **Importante:** Capital.com publica las transacciones de swap en su API con un delay de aproximadamente 2-3 horas después de aplicarlas (~19:00 local). Por eso el trigger vespertino está configurado a las 23:00 y no a las 19:30. Correrlo antes del delay hace que los swaps no aparezcan en el historial de la API aún, y quedan para el run de las 6:30.

---

## Base de datos MongoDB

- **Base de datos:** `capital`

| Colección | Descripción | Campo único |
|---|---|---|
| `operaciones` | Transacciones de Capital.com (trades, swaps, depósitos, rebates, correcciones) | `reference` (clave compuesta si está vacío) |
| `trades` | Historial de actividad detallado | `dealId` |
| `activos` | Parámetros fijos por instrumento | `instrumentName` |

> **Tipos de transacción en `operaciones`:** `Deposit`, `TRADE`, `SWAP`, `Rebate`, `TRADE_CORRECTION`, `VOID`

### Colección `activos`

Contiene información estática por instrumento, cargada con `cargar_activos.py`:

| Campo | Descripción |
|---|---|
| `instrumentName` | Código del activo en Capital.com (ej: `EURUSD`) |
| `nombre` | Nombre legible (ej: `EUR/USD`) |
| `grupo` | Categoría (Divisas, Metales, Cripto, M. Primas, Indices) |
| `apalancamiento` | Apalancamiento máximo del activo |
| `frenteUSD` | Relación con el USD (Multiplica, Igual, Ignorar) |
| `configuracion` | Nombre de la configuración de trading aplicada |
| `fechaInicioConfiguracion` | Fecha desde la cual aplica la configuración (17-12-2025) |

> Los trades abiertos **antes** de `fechaInicioConfiguracion` no aplican configuración. Esta lógica se maneja en Power BI con la columna calculada `ConfiguracionAplicada`.

### Cargar o actualizar activos

Ejecutar localmente (una sola vez, o cuando se agreguen/modifiquen activos):

```powershell
$env:MONGODB_URI="mongodb+srv://..."
python cargar_activos.py
```

El script usa upsert, por lo que es seguro correrlo más de una vez.

---

## Procedimiento de backfill

Si se detectan registros faltantes en `operaciones` (por ejemplo, tras corregir un bug de deduplicación), se puede forzar una descarga completa desde el inicio:

1. En `capital_downloader.py`, reemplazar temporalmente:
   ```python
   ops_start    = ops_last.replace(...) if ops_last else datetime(2024, 10, 31)
   trades_start = trades_last.replace(...) if trades_last else datetime(2024, 10, 31)
   ```
   por:
   ```python
   ops_start    = datetime(2024, 10, 31)
   trades_start = datetime(2024, 10, 31)
   ```
2. Subir el código a Lambda y hacer Deploy
3. Aumentar el **Timeout** a **15 minutos** en Configuración general
4. Ejecutar un **Test** — solo inserta registros nuevos, no duplica los existentes
5. Revertir ambos cambios (código y timeout)

---

## Notificaciones Telegram

El bot envía un mensaje en tres situaciones:

- ✅ **Al día:** no hay datos nuevos que insertar
- ✅ **Actualizado:** con el conteo de registros realmente insertados
- ❌ **Error:** con la descripción del error

---

## Conexión con Power BI

La conexión se realiza mediante un **script Python** dentro de Power BI, que se conecta directamente a MongoDB Atlas sin necesidad de drivers ODBC.

### Requisitos previos

Tener instalado en Python local:

```powershell
python -m pip install pymongo pandas matplotlib
```

### Script de conexión

En Power BI → **Obtener datos** → **Script de Python** → pegar:

```python
import pymongo
import pandas as pd

uri = "mongodb+srv://USUARIO:CONTRASEÑA@cluster0.2eqgp4q.mongodb.net/?appName=Cluster0"
client = pymongo.MongoClient(uri)
db = client["capital"]

operaciones = pd.DataFrame(list(db["operaciones"].find())).drop(columns=["_id"], errors="ignore")
trades = pd.DataFrame(list(db["trades"].find())).drop(columns=["_id"], errors="ignore")
activos = pd.DataFrame(list(db["activos"].find())).drop(columns=["_id"], errors="ignore")

# Separador decimal: reemplazar "." por "," para respetar configuración regional
campos_operaciones = ["size"]
for col in campos_operaciones:
    if col in operaciones.columns:
        operaciones[col] = operaciones[col].apply(lambda x: str(x).replace(".", ",") if pd.notna(x) and str(x) not in ["", "nan", "None"] else None)

campos_trades = ["details_size", "details_level", "details_openPrice", "details_stopLevel", "details_profitLevel"]
for col in campos_trades:
    if col in trades.columns:
        trades[col] = trades[col].apply(lambda x: str(x).replace(".", ",") if pd.notna(x) and str(x) not in ["", "nan", "None"] else None)

for col in ["date", "dateUtc"]:
    if col in operaciones.columns:
        operaciones[col] = pd.to_datetime(operaciones[col], errors="coerce", utc=True).dt.tz_localize(None)

for col in ["date", "dateUTC"]:
    if col in trades.columns:
        trades[col] = pd.to_datetime(trades[col], errors="coerce", utc=True).dt.tz_localize(None)

client.close()
```

### Configuración Power BI → Opciones → Script de Python

Verificar que el directorio de Python esté correctamente configurado en:
**Archivo → Opciones → Creación de scripts de Python**

### Pasos en Power Query tras cargar

> ⚠️ **Importante:** Power BI crea una copia independiente del script por cada tabla. Al actualizar el script, hay que hacerlo en **cada tabla por separado** (operaciones, trades y activos).

Para cada tabla:
1. **Transformar datos** → seleccionar la tabla
2. Clic en el engranaje ⚙️ del paso **Origen**
3. Reemplazar el script con la versión actualizada → **Aceptar**
4. Eliminar el paso **Tipo cambiado** (clic en la X)
5. **Cerrar y aplicar**

### Relaciones en Power BI

Crear en la vista **Modelo** en este orden:

| Tabla origen | Campo | Tabla destino | Campo |
|---|---|---|---|
| `operaciones` | `instrumentName` | `activos` | `instrumentName` |
| `trades` | `dealId` | `operaciones` | `dealId` |

El modelo queda en cadena: `activos ← operaciones ← trades`

> ⚠️ No crear relación directa entre `trades` y `activos` — genera rutas ambiguas en Power BI. Los datos de `activos` llegan a `trades` a través de `operaciones`.

### Tabla Calendario

Tabla calculada con todos los días consecutivos desde el inicio del proyecto:

```dax
Calendario = CALENDAR(DATE(2024, 10, 31), TODAY())
```

> La columna de fecha se llama `[Date]`. `TODAY()` se recalcula automáticamente en cada apertura/refresco del archivo.

#### Columnas calculadas en Calendario

**Trades cerrados:**
```dax
Trades cerrados =
VAR vFecha = Calendario[Date]
RETURN
COUNTROWS(
    FILTER(
        ALL(operaciones),
        DATEVALUE(LEFT(operaciones[date], 10)) = vFecha
            && LOWER(operaciones[note]) = "trade closed"
    )
)
```

**Trades abiertos:**
```dax
Trades Abiertos =
VAR vFecha = Calendario[Date]
VAR vFechaStr = FORMAT(vFecha, "YYYY-MM-DD")
VAR totalEjecutados =
    COUNTROWS(
        FILTER(
            ALL(trades),
            LEFT(trades[date], 10) = vFechaStr
                && trades[type] = "WORKING_ORDER"
                && trades[status] = "EXECUTED"
        )
    )
VAR cerradosEseDia =
    COUNTROWS(
        FILTER(
            ALL(operaciones),
            LEFT(operaciones[date], 10) = vFechaStr
                && operaciones[note] = "Trade closed"
        )
    )
RETURN MAX(0, totalEjecutados - cerradosEseDia)
```

> **Lógica:** En la tabla `trades`, cada apertura y cada cierre de un trade genera un registro `WORKING_ORDER + EXECUTED`. Por lo tanto: aperturas del día = total `WORKING_ORDER+EXECUTED` del día − cierres del día (obtenidos de `operaciones`).
>
> **Valores confirmados en `trades[type]`:** `POSITION`, `WORKING_ORDER`, `SWAP`, `STOP_AND_LIMIT`, `Edit`
> **Valores confirmados en `trades[status]`:** `ACCEPTED`, `EXECUTED`, `MODIFIED`, `REJECTED`

**Deposit** (requiere `status = "processed"`):
```dax
Deposit =
VAR vFechaStr = FORMAT(Calendario[Date], "YYYY-MM-DD")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 10) = vFechaStr
            && operaciones[transactionType] = "DEPOSIT"
            && LOWER(operaciones[status]) = "processed"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Swap:**
```dax
Swap =
VAR vFechaStr = FORMAT(Calendario[Date], "YYYY-MM-DD")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 10) = vFechaStr
            && operaciones[transactionType] = "SWAP"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

> ⚠️ **Nota timing swaps:** Capital.com aplica los swaps a las ~21:00 hora Chile (00:00 UTC del día siguiente). Los swaps capturados por el run de las 06:30 pueden aparecer con la fecha UTC (día siguiente). Si el balance queda desfasado, verificar las fechas de los registros SWAP en MongoDB.

**Rebate:**
```dax
Rebate =
VAR vFechaStr = FORMAT(Calendario[Date], "YYYY-MM-DD")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 10) = vFechaStr
            && operaciones[transactionType] = "REBATE"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Trade Correction:**
```dax
Trade Correction =
VAR vFechaStr = FORMAT(Calendario[Date], "YYYY-MM-DD")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 10) = vFechaStr
            && operaciones[transactionType] = "TRADE_CORRECTION"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Void:**
```dax
Void =
VAR vFechaStr = FORMAT(Calendario[Date], "YYYY-MM-DD")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 10) = vFechaStr
            && operaciones[transactionType] = "VOID"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**PnL Diario** (suma de P&L de trades cerrados ese día):
```dax
PnL Diario =
VAR vFechaStr = FORMAT(Calendario[Date], "YYYY-MM-DD")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 10) = vFechaStr
            && operaciones[transactionType] = "TRADE"
            && operaciones[note] = "Trade closed"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Resultado Diario** (suma de todas las columnas anteriores):
```dax
Resultado Diario =
Calendario[Deposit]
    + Calendario[Swap]
    + Calendario[Rebate]
    + Calendario[Trade Correction]
    + Calendario[Void]
    + Calendario[PnL Diario]
```

**Balance Final** (suma acumulada de Resultado Diario):
```dax
Balance Final =
CALCULATE(
    SUM(Calendario[Resultado Diario]),
    FILTER(
        ALL(Calendario),
        Calendario[Date] <= EARLIER(Calendario[Date])
    )
)
```

**Balance Inicial** (Balance Final del día anterior):
```dax
Balance Inicial = Calendario[Balance Final] - Calendario[Resultado Diario]
```

#### Medidas en Calendario

**Balance Inicial Hoy** (para usar en tarjeta):
```dax
Balance Inicial Hoy =
CALCULATE(
    MAX(Calendario[Balance Inicial]),
    Calendario[Date] = TODAY()
)
```

---

### Tabla CalendarioMensual

Tabla calculada con el primer día de cada mes desde el inicio del proyecto:

```dax
CalendarioMensual =
FILTER(
    CALENDAR(DATE(2024, 10, 1), EOMONTH(TODAY(), 0)),
    DAY([Date]) = 1
)
```

> Cada fila representa un mes. La columna de fecha se llama `[Date]` y contiene el primer día del mes (ej: 2024-10-01, 2024-11-01, etc.). `TODAY()` se recalcula automáticamente.

#### Columnas calculadas en CalendarioMensual

**Mes** (etiqueta de texto legible):
```dax
Mes = FORMAT(CalendarioMensual[Date], "MMM YYYY")
```

**Trades cerrados:**
```dax
Trades cerrados =
VAR vMesStr = FORMAT(CalendarioMensual[Date], "YYYY-MM")
RETURN
COUNTROWS(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 7) = vMesStr
            && LOWER(operaciones[note]) = "trade closed"
    )
)
```

**Trades Abiertos:**
```dax
Trades Abiertos =
VAR vMesStr = FORMAT(CalendarioMensual[Date], "YYYY-MM")
VAR totalEjecutados =
    COUNTROWS(
        FILTER(
            ALL(trades),
            LEFT(trades[date], 7) = vMesStr
                && trades[type] = "WORKING_ORDER"
                && trades[status] = "EXECUTED"
        )
    )
VAR cerradosEseMes =
    COUNTROWS(
        FILTER(
            ALL(operaciones),
            LEFT(operaciones[date], 7) = vMesStr
                && operaciones[note] = "Trade closed"
        )
    )
RETURN MAX(0, totalEjecutados - cerradosEseMes)
```

**Deposit:**
```dax
Deposit =
VAR vMesStr = FORMAT(CalendarioMensual[Date], "YYYY-MM")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 7) = vMesStr
            && operaciones[transactionType] = "DEPOSIT"
            && LOWER(operaciones[status]) = "processed"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Swap:**
```dax
Swap =
VAR vMesStr = FORMAT(CalendarioMensual[Date], "YYYY-MM")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 7) = vMesStr
            && operaciones[transactionType] = "SWAP"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Rebate:**
```dax
Rebate =
VAR vMesStr = FORMAT(CalendarioMensual[Date], "YYYY-MM")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 7) = vMesStr
            && operaciones[transactionType] = "REBATE"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Trade Correction:**
```dax
Trade Correction =
VAR vMesStr = FORMAT(CalendarioMensual[Date], "YYYY-MM")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 7) = vMesStr
            && operaciones[transactionType] = "TRADE_CORRECTION"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Void:**
```dax
Void =
VAR vMesStr = FORMAT(CalendarioMensual[Date], "YYYY-MM")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 7) = vMesStr
            && operaciones[transactionType] = "VOID"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**PnL Mensual** (suma de P&L de trades cerrados ese mes):
```dax
PnL Mensual =
VAR vMesStr = FORMAT(CalendarioMensual[Date], "YYYY-MM")
RETURN
SUMX(
    FILTER(
        ALL(operaciones),
        LEFT(operaciones[date], 7) = vMesStr
            && operaciones[transactionType] = "TRADE"
            && operaciones[note] = "Trade closed"
    ),
    IF(ISBLANK(operaciones[size]) || operaciones[size] = "", 0, VALUE(operaciones[size]))
)
```

**Resultado Mensual** (suma de todas las columnas anteriores):
```dax
Resultado Mensual =
CalendarioMensual[Deposit]
    + CalendarioMensual[Swap]
    + CalendarioMensual[Rebate]
    + CalendarioMensual[Trade Correction]
    + CalendarioMensual[Void]
    + CalendarioMensual[PnL Mensual]
```

**Balance Final** (suma acumulada de Resultado Mensual):
```dax
Balance Final =
CALCULATE(
    SUM(CalendarioMensual[Resultado Mensual]),
    FILTER(
        ALL(CalendarioMensual),
        CalendarioMensual[Date] <= EARLIER(CalendarioMensual[Date])
    )
)
```

**Balance Inicial** (Balance Final del mes anterior):
```dax
Balance Inicial = CalendarioMensual[Balance Final] - CalendarioMensual[Resultado Mensual]
```

---

### Columna calculada ConfiguracionAplicada

En vista **Datos** → tabla `operaciones` → **Nueva columna**:

```
ConfiguracionAplicada =
IF(
    LEFT(operaciones[date], 10) >= "2025-12-17",
    RELATED(activos[configuracion]),
    ""
)
```

---

## Historial de cambios

| Versión | Cambio |
|---|---|
| v1 | Script inicial con pandas y dotenv |
| v2 | Fix error 404 Telegram: `.strip()` al token. Eliminadas dependencias innecesarias para Lambda. Agregado `lambda_handler` |
| v3 | Fix mensaje Telegram: ahora muestra registros realmente insertados, no descargados |
| v4 | Fix swaps/financiación: registros sin `dealId` usaban clave compuesta incorrecta. Fix rango de fechas: buscaba desde el día siguiente al último registro |
| v5 | Nueva colección `activos` con parámetros fijos por instrumento. Nuevo script `cargar_activos.py` |
| v6 | Fix separador decimal: campos numéricos (`size`, `details_size`, etc.) se almacenan como float en MongoDB. Conexión Power BI migrada de ODBC a script Python. Columna `ConfiguracionAplicada` con comparación de texto en DAX |
| v7 | Fix timing swaps: Capital.com publica los swaps en la API con ~2-3h de delay. Trigger vespertino movido de 22:30 UTC (19:30 local) a 02:00 UTC (23:00 local) en EventBridge para garantizar que los swaps estén disponibles al momento de la consulta |
| v8 | Fix tipos de transacción faltantes (Rebate, TRADE_CORRECTION, VOID): el campo único para deduplicación de `operaciones` cambia de `dealId` a `reference`. TRADE_CORRECTION y VOID comparten `dealId` con el TRADE original, provocando que el filtro los descartara como duplicados |
| v9 | Power BI: columna `Trades Abiertos` en tabla `Calendario`. Lógica: `WORKING_ORDER+EXECUTED` del día en `trades` menos `Trade closed` del día en `operaciones`. Los dealIds entre ambas tablas no coinciden directamente, por lo que el linkeo por ID no es viable. |
| v10 | Power BI: columnas `Deposit`, `Swap`, `Rebate`, `Trade Correction`, `Void`, `PnL Diario`, `Resultado Diario`, `Balance Final`, `Balance Inicial` en tabla `Calendario`. Medida `Balance Inicial Hoy` para tarjeta. Nota: `operaciones[date]` es tipo texto en Power BI — usar `LEFT(date, 10)` y `FORMAT()` para comparar fechas. Bug corregido: registro SWAP duplicado del 2026-02-20 eliminado directamente en MongoDB Atlas. |
| v11 | Power BI: nueva tabla calculada `CalendarioMensual` con columna `Mes`, `Trades cerrados`, `Trades Abiertos`, `Deposit`, `Swap`, `Rebate`, `Trade Correction`, `Void`, `PnL Mensual`, `Resultado Mensual`, `Balance Final`, `Balance Inicial`. Misma lógica que `Calendario` diario pero agrupando por mes usando `LEFT(date, 7)` y `FORMAT(date, "YYYY-MM")`. |
