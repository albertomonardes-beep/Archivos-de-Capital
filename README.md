# Capital.com → MongoDB → Power BI

Automatización para descargar datos de trading de Capital.com, almacenarlos en MongoDB Atlas y visualizarlos en Power BI.

---

## ¿Qué hace este proyecto?

1. **Descarga** operaciones y trades desde la API de Capital.com
2. **Almacena** los datos en MongoDB Atlas (sin duplicados)
3. **Notifica** por Telegram cuando termina o si hay un error
4. **Visualiza** los datos en Power BI conectado a MongoDB

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

1. Subir `capital_downloader_v2.zip` en AWS Lambda → pestaña **Código** → **Cargar desde** → **Archivo ZIP**
2. Hacer clic en **Implementar**
3. Ejecutar un **Test** para verificar

### Programación (EventBridge)

La función está programada para ejecutarse automáticamente. Actualmente configurada a las **19:39**.

---

## Base de datos MongoDB

- **Base de datos:** `capital`
- **Colección operaciones:** transacciones de Capital.com (campo único: `dealId`)
- **Colección trades:** historial de actividad detallado (campo único: `dealId`)

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
5. Arrastrar las colecciones `operaciones` y `trades` al área central
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

---

## Historial de cambios

| Versión | Cambio |
|---|---|
| v1 | Script inicial con pandas y dotenv |
| v2 | Fix error 404 Telegram: `.strip()` al token. Eliminadas dependencias innecesarias para Lambda. Agregado `lambda_handler` |
| v3 | Fix mensaje Telegram: ahora muestra registros realmente insertados, no descargados |
