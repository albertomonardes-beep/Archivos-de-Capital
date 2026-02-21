# Capital.com → MongoDB → Power BI

Automatización para descargar datos de trading de Capital.com, almacenarlos en MongoDB Atlas y visualizarlos en Power BI.

---

## ¿Qué hace este proyecto?

1. **Descarga** operaciones y trades desde la API de Capital.com
2. **Almacena** los datos en MongoDB Atlas (sin duplicados)
3. **Enriquece** los datos con parámetros fijos por activo (grupo, configuración, apalancamiento)
4. **Notifica** por Telegram cuando termina o si hay un error
5. **Visualiza** los datos en Power BI conectado a MongoDB

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

La función está programada para ejecutarse automáticamente. Actualmente configurada a las **19:39**.

---

## Base de datos MongoDB

- **Base de datos:** `capital`

| Colección | Descripción | Campo único |
|---|---|---|
| `operaciones` | Transacciones de Capital.com (trades, swaps, depósitos) | `dealId` (clave compuesta para registros sin dealId) |
| `trades` | Historial de actividad detallado | `dealId` |
| `activos` | Parámetros fijos por instrumento | `instrumentName` |

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

> Los trades abiertos **antes** de `fechaInicioConfiguracion` no aplican configuración. Esta lógica se maneja en Power BI comparando la fecha del trade con este campo.

### Cargar o actualizar activos

Ejecutar localmente (una sola vez, o cuando se agreguen/modifiquen activos):

```powershell
$env:MONGODB_URI="mongodb+srv://..."
python cargar_activos.py
```

El script usa upsert, por lo que es seguro correrlo más de una vez.

---

## Notificaciones Telegram

El bot envía un mensaje en tres situaciones:

- ✅ **Al día:** no hay datos nuevos que insertar
- ✅ **Actualizado:** con el conteo de registros realmente insertados
- ❌ **Error:** con la descripción del error

---

## Conexión con Power BI

Se usa el conector **MongoDB Atlas SQL** (disponible en Power BI → Obtener datos).

### Requisito previo

Instalar el driver ODBC de MongoDB desde:
https://www.mongodb.com/try/download/odbc-driver

### Configuración de Data Federation en MongoDB Atlas

Para que el conector funcione, se debe crear una instancia de Data Federation:

1. En Atlas → **Data Federation** → **Create New Federated Database**
2. Elegir **Set up manually**
3. Nombre: `Capital-Federation`, Cloud Provider: **AWS**
4. Clic en **Add Data Sources** → **Atlas Cluster** → elegir **capital**
5. Arrastrar las colecciones `operaciones`, `trades` y `activos` al área central
6. Clic en **Create**
7. Ir a **Configuration** → vista **JSON** y reemplazar con:

```json
{
  "databases": [
    {
      "name": "capital",
      "collections": [
        {
          "name": "operaciones",
          "dataSources": [
            {
              "storeName": "Cluster0",
              "database": "capital",
              "collection": "operaciones"
            }
          ]
        },
        {
          "name": "trades",
          "dataSources": [
            {
              "storeName": "Cluster0",
              "database": "capital",
              "collection": "trades"
            }
          ]
        },
        {
          "name": "activos",
          "dataSources": [
            {
              "storeName": "Cluster0",
              "database": "capital",
              "collection": "activos"
            }
          ]
        }
      ]
    }
  ],
  "stores": [
    {
      "name": "Cluster0",
      "provider": "atlas",
      "clusterName": "Cluster0"
    }
  ]
}
```

### URI de conexión Atlas SQL

```
mongodb://albertomonardes_db_user:CONTRASEÑA@capital-federation-1ezmkp.a.query.mongodb.net/?ssl=true&authSource=admin&appName=Capital-Federation
```

### Parámetros en Power BI

- **Obtener datos** → **MongoDB Atlas SQL**
- **MongoDB URI:** URI de arriba (reemplazar CONTRASEÑA)
- **Database:** `capital`
- **Modo:** Importar

### Relaciones en Power BI

Crear las siguientes relaciones en el modelo de datos:

| Tabla origen | Campo | Tabla destino | Campo |
|---|---|---|---|
| `operaciones` | `instrumentName` | `activos` | `instrumentName` |
| `trades` | `epic` | `activos` | `instrumentName` |

---

## Historial de cambios

| Versión | Cambio |
|---|---|
| v1 | Script inicial con pandas y dotenv |
| v2 | Fix error 404 Telegram: `.strip()` al token. Eliminadas dependencias innecesarias para Lambda. Agregado `lambda_handler` |
| v3 | Fix mensaje Telegram: ahora muestra registros realmente insertados, no descargados |
| v4 | Fix swaps/financiación: registros sin `dealId` usaban clave compuesta incorrecta causando que no se insertaran. Fix rango de fechas: buscaba desde el día siguiente al último registro, perdiendo registros tardíos del mismo día |
| v5 | Nueva colección `activos` con parámetros fijos por instrumento. Nuevo script `cargar_activos.py` para carga inicial |
