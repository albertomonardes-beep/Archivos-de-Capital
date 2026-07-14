import os
import requests
from datetime import datetime, timedelta
from pymongo import MongoClient

CAPITAL_API_KEY    = os.getenv("CAPITAL_API_KEY")
CAPITAL_PASSWORD   = os.getenv("CAPITAL_PASSWORD")
CAPITAL_IDENTIFIER = os.getenv("CAPITAL_IDENTIFIER")
MONGODB_URI        = os.getenv("MONGODB_URI")
TELEGRAM_TOKEN     = (os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID   = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
DB_NAME            = "capital"

# Mapeo de nombres nuevos (API) a nombres canónicos históricos en MongoDB
NOMBRE_CANONICO = {
    "XAUUSD":  "Gold",
    "XAGUSD":  "Silver",
    "USCOCOA": "COCOA US",
}

OPERACIONES_COLUMNS = ['date', 'dateUtc', 'transactionType', 'note', 'reference', 'size', 'currency', 'status', 'instrumentName', 'dealId']

TRADES_COLUMNS = ['date', 'dateUTC', 'dealId', 'epic', 'type', 'status', 'source',
                  'details_dealReference', 'details_direction', 'details_currency',
                  'details_size', 'details_level', 'details_openPrice',
                  'details_stopLevel', 'details_profitLevel',
                  'details_guaranteedStop', 'details_workingOrderId',
                  'details_marketName']


class CapitalComAPI:
    def __init__(self, api_key, identifier, password):
        self.api_key = api_key
        self.identifier = identifier
        self.password = password
        self.base_url = "https://api-capital.backend-capital.com"
        self.session_token = None
        self.cst = None

    def login(self):
        url = f"{self.base_url}/api/v1/session"
        headers = {"X-CAP-API-KEY": self.api_key, "Content-Type": "application/json"}
        payload = {
            "identifier": self.identifier,
            "password": self.password,
            "encryptedPassword": False
        }
        print("Login en Capital.com...")
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            self.cst = response.headers.get('CST')
            self.session_token = response.headers.get('X-SECURITY-TOKEN')
            print("OK")
            return True
        print(f"Error login: {response.status_code}")
        return False

    def get_transactions_history(self, from_date, to_date):
        if not self.session_token:
            return []
        all_transactions = []
        current_date = from_date
        while current_date <= to_date:
            url = f"{self.base_url}/api/v1/history/transactions"
            headers = {
                "X-CAP-API-KEY": self.api_key,
                "X-SECURITY-TOKEN": self.session_token,
                "CST": self.cst
            }
            params = {
                'from': current_date.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%S"),
                'to': current_date.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%S")
            }
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                if response.status_code == 200:
                    transactions = response.json().get('transactions', [])
                    if transactions:
                        all_transactions.extend(transactions)
                        print(f"  {current_date.strftime('%d-%m-%Y')}: {len(transactions)} operaciones")
            except:
                pass
            current_date += timedelta(days=1)
        return all_transactions

    def get_activity_history_detailed(self, date_obj):
        if not self.session_token:
            return []
        url = f"{self.base_url}/api/v1/history/activity"
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "X-SECURITY-TOKEN": self.session_token,
            "CST": self.cst
        }
        params = {
            'from': date_obj.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%S"),
            'to': date_obj.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%S"),
            'detailed': 'true'
        }
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                return response.json().get('activities', [])
        except:
            pass
        return []


def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, str(v)))
        else:
            items.append((new_key, v))
    return dict(items)


def enviar_telegram(mensaje):
    print("Enviando mensaje Telegram...")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no configurados")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}, timeout=10)
        print(f"Telegram respuesta: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error enviando Telegram: {e}")


def connect_to_mongodb():
    print("Conectando a MongoDB...")
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    print("OK")
    return db


def get_last_date(collection, date_field='date'):
    last = collection.find_one(sort=[(date_field, -1)])
    if last and date_field in last:
        date_val = last[date_field]
        if isinstance(date_val, str):
            return datetime.fromisoformat(date_val.replace('Z', '+00:00'))
        if isinstance(date_val, datetime):
            return date_val
    return None


def build_filter(doc, unique_field):
    """Retorna el filtro de búsqueda para el upsert.
    Si el campo único (dealId) está vacío —como ocurre en ajustes de
    financiación/swaps— usa una clave compuesta para evitar colisiones."""
    val = doc.get(unique_field, '')
    if val:
        return {unique_field: val}
    return {
        'date':            doc.get('date', ''),
        'transactionType': doc.get('transactionType', ''),
        'reference':       doc.get('reference', ''),
        'size':            doc.get('size', ''),
        'instrumentName':  doc.get('instrumentName', ''),
    }


def fix_existing_open_prices(trades_col):
    """Rellena details_openPrice con details_level para registros WORKING_ORDER/EXECUTED donde falta."""
    result = trades_col.update_many(
        {
            'type': 'WORKING_ORDER',
            'status': 'EXECUTED',
            '$or': [
                {'details_openPrice': {'$exists': False}},
                {'details_openPrice': None},
                {'details_openPrice': 0},
                {'details_openPrice': 0.0}
            ]
        },
        [{'$set': {'details_openPrice': '$details_level'}}]
    )
    print(f"  {result.modified_count} registros actualizados con precio de apertura")


def normalizar_instrumento(nombre):
    """Traduce el nombre nuevo de Capital.com al nombre canónico histórico."""
    return NOMBRE_CANONICO.get(nombre, nombre)


def crear_prima_diaria_doc(record):
    """
    Crea un documento para operaciones a partir de un registro POSITION/SYSTEM
    de la actividad. El campo 'details_level' contiene la tasa diaria y
    'details_size' el tamaño; el costo real = -(level × size).
    """
    level = record.get('details_level')
    size  = record.get('details_size')
    if level is None or size is None:
        return None
    try:
        costo = -round(float(level) * float(size), 2)
    except (TypeError, ValueError):
        return None
    if costo == 0:
        return None

    date_str = record.get('date', '')
    deal_id  = record.get('dealId', '')

    return {
        'date':            date_str,
        'dateUtc':         record.get('dateUTC', ''),
        'transactionType': 'SWAP',
        'note':            'Daily premium',
        'reference':       f"daily_prem_{deal_id}_{date_str[:10]}",
        'size':            costo,
        'currency':        record.get('details_currency', 'USD'),
        'status':          'ACCEPTED',
        'instrumentName':  normalizar_instrumento(record.get('epic', '')),
        'dealId':          deal_id,
    }


def migrar_primas_existentes(db):
    """Backfill: genera registros en operaciones para primas diarias
    que ya están en trades pero que aún no tienen entrada en operaciones."""
    print("Migrando primas diarias existentes desde trades...")
    registros = list(db["trades"].find(
        {"type": "POSITION", "source": "SYSTEM"},
        {"date": 1, "dateUTC": 1, "dealId": 1, "epic": 1,
         "details_level": 1, "details_size": 1, "details_currency": 1}
    ))
    if not registros:
        print("  Sin registros de primas en trades")
        return
    docs = [d for r in registros for d in [crear_prima_diaria_doc(r)] if d]
    if docs:
        insert_data(db["operaciones"], docs, unique_field='reference')
    else:
        print("  Sin primas diarias para migrar")


def migrar_nombres_canonicos(db):
    """Corrige en MongoDB los registros ya insertados con nombres nuevos."""
    print("Normalizando nombres de activos en registros existentes...")
    total = 0
    for nuevo, canonico in NOMBRE_CANONICO.items():
        r = db["operaciones"].update_many(
            {"instrumentName": nuevo},
            {"$set": {"instrumentName": canonico}}
        )
        if r.modified_count:
            print(f"  operaciones: {r.modified_count} '{nuevo}' → '{canonico}'")
            total += r.modified_count

        r = db["trades"].update_many(
            {"details_marketName": nuevo},
            {"$set": {"details_marketName": canonico}}
        )
        if r.modified_count:
            print(f"  trades: {r.modified_count} '{nuevo}' → '{canonico}'")
            total += r.modified_count

    if total == 0:
        print("  Sin registros que migrar")


def insert_data(collection, data_list, unique_field=None):
    if not data_list:
        return 0
    if unique_field:
        inserted = 0
        for doc in data_list:
            filter_query = build_filter(doc, unique_field)
            result = collection.update_one(
                filter_query,
                {"$setOnInsert": doc},
                upsert=True
            )
            if result.upserted_id:
                inserted += 1
        print(f"  {inserted} nuevos registros insertados (de {len(data_list)} revisados)")
        return inserted
    else:
        result = collection.insert_many(data_list)
        print(f"  {len(result.inserted_ids)} registros insertados")
        return len(result.inserted_ids)


def calculate_open_trades_from_mongodb(db):
    """
    Detecta trades abiertos comparando trades WO+EXECUTED contra cierres en operaciones.
    Un trade está abierto si su prefijo (primeros 34 chars del dealId) aparece en
    trades como WO+EXECUTED pero no tiene cierre correspondiente en operaciones.
    """
    wo_executed = list(db["trades"].find(
        {"type": "WORKING_ORDER", "status": "EXECUTED"},
        {"dealId": 1, "epic": 1, "details_marketName": 1, "details_direction": 1,
         "details_size": 1, "details_level": 1, "details_openPrice": 1,
         "details_stopLevel": 1, "details_currency": 1}
    ))
    trade_closures = list(db["operaciones"].find(
        {"transactionType": "TRADE"},
        {"dealId": 1}
    ))

    closed_prefixes = set(
        doc["dealId"][:34] for doc in trade_closures
        if doc.get("dealId") and len(doc["dealId"]) >= 34
    )

    wo_by_prefix = {}
    for doc in wo_executed:
        deal_id = doc.get("dealId", "")
        if not deal_id or len(deal_id) < 34:
            continue
        prefix = deal_id[:34]
        if prefix not in wo_by_prefix:
            wo_by_prefix[prefix] = doc

    open_docs = []
    for prefix, trade in wo_by_prefix.items():
        if prefix not in closed_prefixes:
            open_docs.append({
                "dealId":         trade.get("dealId", ""),
                "epic":           trade.get("epic", ""),
                "instrumentName": trade.get("details_marketName", ""),
                "direction":      trade.get("details_direction", ""),
                "size":           trade.get("details_size"),
                "level":          trade.get("details_level"),
                "openLevel":      trade.get("details_openPrice"),
                "stopLevel":      trade.get("details_stopLevel"),
                "currency":       trade.get("details_currency", ""),
                "date":           datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            })
    return open_docs


def main():
    print("=" * 50)
    print("CAPITAL.COM -> MONGODB")
    print("=" * 50)
    print()

    capital = CapitalComAPI(CAPITAL_API_KEY, CAPITAL_IDENTIFIER, CAPITAL_PASSWORD)
    if not capital.login():
        return

    db = connect_to_mongodb()
    operaciones_col = db["operaciones"]
    trades_col = db["trades"]
    posiciones_col = db["posiciones_abiertas"]

    print()
    migrar_nombres_canonicos(db)

    print()
    migrar_primas_existentes(db)

    print()
    print("Corrigiendo precios de apertura faltantes en registros existentes...")
    fix_existing_open_prices(trades_col)

    print()
    print("Verificando últimas fechas en MongoDB...")

    ops_last   = get_last_date(operaciones_col, 'date')
    trades_last = get_last_date(trades_col, 'date')

    print(f"  Operaciones: {ops_last}")
    print(f"  Trades:      {trades_last}")
    print()

    today = datetime.now()

    # Se busca desde el mismo día del último registro (no +1) para no perder
    # registros tardíos del mismo día, como ajustes de financiación (swaps).
    # La deduplicación en insert_data evita reinsertar duplicados.
    ops_start    = ops_last.replace(tzinfo=None,    hour=0, minute=0, second=0, microsecond=0) if ops_last    else datetime(2024, 10, 31)
    trades_start = trades_last.replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0) if trades_last else datetime(2024, 10, 31)

    print(f"  Buscando operaciones desde: {ops_start.strftime('%d/%m/%Y')}")
    print(f"  Buscando trades desde:      {trades_start.strftime('%d/%m/%Y')}")

    if ops_start > today and trades_start > today:
        print("Todo está actualizado.")
        enviar_telegram(f"✅ Capital.com al día\nNo hay datos nuevos que descargar.\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        return

    print("Descargando Operaciones...")
    ops_insertadas = 0
    ops_data = capital.get_transactions_history(ops_start, today)
    if ops_data:
        ops_processed = []
        for item in ops_data:
            doc = {col: item.get(col, '') for col in OPERACIONES_COLUMNS}
            doc['instrumentName'] = normalizar_instrumento(doc.get('instrumentName', ''))
            try:
                doc['size'] = float(doc['size']) if doc['size'] != '' else None
            except (ValueError, TypeError):
                pass
            ops_processed.append(doc)
        print(f"  {len(ops_processed)} operaciones descargadas")
        ops_insertadas = insert_data(operaciones_col, ops_processed, unique_field='reference')
    else:
        print("  Sin nuevas operaciones")

    print()
    print("Descargando Trades...")
    trades_insertados = 0
    trades_data = []
    current = trades_start
    while current <= today:
        trades = capital.get_activity_history_detailed(current)
        if trades:
            trades_data.extend(trades)
        current += timedelta(days=1)

    if trades_data:
        trades_processed = []
        primas_procesadas = []
        numeric_trade_fields = ['details_size', 'details_level', 'details_openPrice',
                                'details_stopLevel', 'details_profitLevel']
        for item in trades_data:
            flat = flatten_dict(item)
            record = {col: flat.get(col, '') for col in TRADES_COLUMNS}
            for field in numeric_trade_fields:
                try:
                    record[field] = float(record[field]) if record[field] != '' else None
                except (ValueError, TypeError):
                    pass
            record['details_marketName'] = normalizar_instrumento(record.get('details_marketName', ''))
            # Rellenar openPrice faltante para órdenes ejecutadas
            if not record.get('details_openPrice') and record.get('type') == 'WORKING_ORDER' and record.get('status') == 'EXECUTED':
                record['details_openPrice'] = record.get('details_level')
            # Detectar prima diaria (POSITION/SYSTEM) y preparar entrada en operaciones
            if record.get('type') == 'POSITION' and record.get('source') == 'SYSTEM':
                prima_doc = crear_prima_diaria_doc(record)
                if prima_doc:
                    primas_procesadas.append(prima_doc)
            trades_processed.append(record)
        print(f"  {len(trades_processed)} trades descargados")
        trades_insertados = insert_data(trades_col, trades_processed, unique_field='dealId')
        if primas_procesadas:
            print("  Insertando primas diarias en operaciones...")
            insert_data(operaciones_col, primas_procesadas, unique_field='reference')
    else:
        print("  Sin nuevos trades")

    print()
    print("Actualizando posiciones abiertas...")
    open_positions = calculate_open_trades_from_mongodb(db)
    posiciones_col.delete_many({})
    if open_positions:
        posiciones_col.insert_many(open_positions)
        print(f"  {len(open_positions)} posiciones abiertas guardadas")
    else:
        print("  Sin posiciones abiertas")

    print()
    print("=" * 50)
    print("COMPLETADO")
    print("=" * 50)

    if ops_insertadas == 0 and trades_insertados == 0:
        enviar_telegram(f"✅ Capital.com al día\nNo hay datos nuevos que insertar.\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    else:
        mensaje = (
            f"✅ Capital.com actualizado\n"
            f"📊 Operaciones nuevas: {ops_insertadas}\n"
            f"📈 Trades nuevos: {trades_insertados}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        enviar_telegram(mensaje)


def lambda_handler(event, context):
    try:
        main()
    except Exception as e:
        print(f"Error crítico: {e}")
        enviar_telegram(f"❌ Error en Capital.com Lambda\n{str(e)}\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        raise
    return {"statusCode": 200}


if __name__ == "__main__":
    main()
