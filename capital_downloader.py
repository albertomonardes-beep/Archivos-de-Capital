import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

CAPITAL_API_KEY    = os.getenv("CAPITAL_API_KEY")
CAPITAL_PASSWORD   = os.getenv("CAPITAL_PASSWORD")
CAPITAL_IDENTIFIER = os.getenv("CAPITAL_IDENTIFIER")
MONGODB_URI        = os.getenv("MONGODB_URI")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
DB_NAME            = "capital"

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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}, timeout=10)
    except:
        pass


def connect_to_mongodb():
    print("Conectando a MongoDB...")
    client = MongoClient(MONGODB_URI)
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


def insert_data(collection, data_list, unique_field=None):
    if not data_list:
        return
    if unique_field:
        inserted = 0
        for doc in data_list:
            result = collection.update_one(
                {unique_field: doc.get(unique_field)},
                {"$setOnInsert": doc},
                upsert=True
            )
            if result.upserted_id:
                inserted += 1
        print(f"  {inserted} nuevos registros insertados (de {len(data_list)} revisados)")
    else:
        result = collection.insert_many(data_list)
        print(f"  {len(result.inserted_ids)} registros insertados")


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

    print()
    print("Verificando últimas fechas en MongoDB...")

    ops_last   = get_last_date(operaciones_col, 'date')
    trades_last = get_last_date(trades_col, 'date')

    print(f"  Operaciones: {ops_last}")
    print(f"  Trades:      {trades_last}")
    print()

    today = datetime.now()

    ops_start    = ops_last    + timedelta(days=1) if ops_last    else datetime(2024, 10, 31)
    trades_start = trades_last + timedelta(days=1) if trades_last else datetime(2024, 10, 31)

    if ops_start > today and trades_start > today:
        print("Todo está actualizado.")
        return

    print("Descargando Operaciones...")
    ops_data = capital.get_transactions_history(ops_start, today)
    if ops_data:
        ops_processed = [{col: item.get(col, '') for col in OPERACIONES_COLUMNS} for item in ops_data]
        print(f"  {len(ops_processed)} operaciones descargadas")
        insert_data(operaciones_col, ops_processed, unique_field='dealId')
    else:
        print("  Sin nuevas operaciones")

    print()
    print("Descargando Trades...")
    trades_data = []
    for date in pd.date_range(trades_start, today):
        trades = capital.get_activity_history_detailed(date)
        if trades:
            trades_data.extend(trades)

    if trades_data:
        trades_processed = []
        for item in trades_data:
            flat = flatten_dict(item)
            record = {col: flat.get(col, '') for col in TRADES_COLUMNS}
            trades_processed.append(record)
        print(f"  {len(trades_processed)} trades descargados")
        insert_data(trades_col, trades_processed, unique_field='dealId')
    else:
        print("  Sin nuevos trades")

    print()
    print("=" * 50)
    print("COMPLETADO")
    print("=" * 50)

    mensaje = (
        f"✅ Capital.com actualizado\n"
        f"📊 Operaciones nuevas: {len(ops_processed) if ops_data else 0}\n"
        f"📈 Trades nuevos: {len(trades_processed) if trades_data else 0}\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    enviar_telegram(mensaje)


if __name__ == "__main__":
    main()
