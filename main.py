from keys import api, secret
from pybit.unified_trading import HTTP
import pandas as pd
import ta
import requests
from time import sleep

session = HTTP(
    api_key=api,
    api_secret=secret
)

# Config:
tp = 0.015  # Take Profit +0.9%
sl = 0.006  # Stop Loss -0.7%
timeframe = 30  # 15 minutes
mode = 1  # 1 - Isolated, 0 - Cross
leverage = 10
qty = 50  # Amount of USDT for one order

# Telegram Bot Configuration
TG_BOT_TOKEN = '7468594790:AAG5Sh15e2a0BFa9nTdBB75g-lSbEd5yPps'
TG_CHAT_ID = '-1002165200582'

def send_tg(text):
    try:
        url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage'
        data = {
            'chat_id': TG_CHAT_ID,
            'text': text
        }
        resp = requests.post(url, data=data)
        print(f'TG Response: {resp.status_code}, {resp.text}')
    except Exception as err:
        print(f'Telegram send error: {err}')

def get_balance():
    try:
        resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")['result']['list'][0]['coin'][0]['walletBalance']
        return float(resp)
    except Exception as err:
        print(err)
        return None

def klines(symbol):
    try:
        resp = session.get_kline(
            category='linear',
            symbol=symbol,
            interval=timeframe,
            limit=500
        )['result']['list']
        df = pd.DataFrame(resp)
        df.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Turnover']
        df = df.set_index('Time')
        df = df.astype(float)
        return df[::-1]  # Reverse to have the oldest data first
    except Exception as err:
        print(err)
        return pd.DataFrame()

def get_positions():
    try:
        resp = session.get_positions(
            category='linear',
            settleCoin='USDT'
        )['result']['list']
        return [elem['symbol'] for elem in resp if float(elem.get('size', 0)) > 0]
    except Exception as err:
        print(f'Error getting positions: {err}')
        return []

def get_pnl():
    try:
        response = session.get_closed_pnl(category="linear", limit=50)
        if 'result' not in response or 'list' not in response['result']:
            raise ValueError("Unexpected response structure")
        pnl_list = response['result']['list']
        total_pnl = 0
        for entry in pnl_list:
            try:
                total_pnl += float(entry['closedPnl'])
            except KeyError:
                print(f"Missing 'closedPnl' in entry: {entry}")
            except ValueError:
                print(f"Invalid 'closedPnl' value in entry: {entry}")
        return total_pnl
    except Exception as err:
        print(f"An error occurred: {err}")

def set_mode(symbol):
    try:
        resp = session.switch_margin_mode(
            category='linear',
            symbol=symbol,
            tradeMode=mode,
            buyLeverage=leverage,
            sellLeverage=leverage
        )
        print(resp)
    except Exception as err:
        print(err)

def get_precisions(symbol):
    try:
        resp = session.get_instruments_info(
            category='linear',
            symbol=symbol
        )['result']['list'][0]
        price = resp['priceFilter']['tickSize']
        price_precision = len(price.split('.')[1]) if '.' in price else 0
        qty = resp['lotSizeFilter']['qtyStep']
        qty_precision = len(qty.split('.')[1]) if '.' in qty else 0
        return price_precision, qty_precision
    except Exception as err:
        print(err)
        return 2, 2  # Default values if there's an error

def place_order_market(symbol, side):
    price_precision, qty_precision = get_precisions(symbol)
    mark_price = float(session.get_tickers(
        category='linear',
        symbol=symbol
    )['result']['list'][0]['markPrice'])
    print(f'Placing {side} order for {symbol}. Mark price: {mark_price}')
    order_qty = round(qty / mark_price, qty_precision)
    sleep(2)
    try:
        if side == 'buy':
            tp_price = round(mark_price + mark_price * tp, price_precision)
            sl_price = round(mark_price - mark_price * sl, price_precision)
            resp = session.place_order(
                category='linear',
                symbol=symbol,
                side='Buy',
                orderType='Market',
                qty=order_qty,
                takeProfit=tp_price,
                stopLoss=sl_price,
                tpTriggerBy='MarkPrice',
                slTriggerBy='MarkPrice'
            )
            send_tg(f'📈 BUY: {symbol}\n📌 Order Price: {mark_price}\n💹 Qty: {order_qty}\n➡️ TP: {tp_price}\n➡️ SL: {sl_price}\n📊 Total P&L: {get_pnl()}\n💳 Balance: {balance}')
        elif side == 'sell':
            tp_price = round(mark_price - mark_price * tp, price_precision)
            sl_price = round(mark_price + mark_price * sl, price_precision)
            resp = session.place_order(
                category='linear',
                symbol=symbol,
                side='Sell',
                orderType='Market',
                qty=order_qty,
                takeProfit=tp_price,
                stopLoss=sl_price,
                tpTriggerBy='MarkPrice',
                slTriggerBy='MarkPrice'
            )
            send_tg(f'📉 SELL: {symbol}\n📌 Order price: {mark_price}\n💹 Qty: {order_qty}\n➡️ TP: {tp_price}\n➡️ SL: {sl_price}\n📊 Total P&L: {get_pnl()}\n💳 Balance: {balance}')
    except Exception as err:
        print(f'Order placement error: {err}')
        send_tg(f'Error placing {side} order for {symbol}: {err}')

def rsi_signal(symbol):
    kl = klines(symbol)
    if 'Close' not in kl.columns:
        raise ValueError("DataFrame must contain 'Close' column")

    rsi_indicator = ta.momentum.RSIIndicator(kl['Close'], window=14)
    rsi = rsi_indicator.rsi()
    rsi_sma = ta.trend.sma_indicator(rsi, window=21)

    if len(rsi) < 21:
        return 'none'

    rsi_prev3 = rsi.iloc[-3]
    rsi_prev = rsi.iloc[-2]
    rsi_curr = rsi.iloc[-1]
    rsi_sma_prev3 = rsi_sma.iloc[-3]
    rsi_sma_prev = rsi_sma.iloc[-2]
    rsi_sma_curr = rsi_sma.iloc[-1]

    upp = (35 > rsi_curr and rsi_sma_curr < rsi_sma_prev and rsi_sma_prev3 > rsi_prev3 and rsi_sma_prev > rsi_prev and rsi_sma_curr < rsi_curr)
    dww = (65 < rsi_curr and rsi_sma_curr > rsi_sma_prev and rsi_sma_prev3 < rsi_prev3 and rsi_sma_prev < rsi_prev and rsi_sma_curr > rsi_curr)

    if dww:
        return 'down'
    if upp:
        return 'up'

    return 'none'

def williamsR(symbol):
    kl = klines(symbol)
    w = ta.momentum.WilliamsRIndicator(kl.High, kl.Low, kl.Close, lbp=24).williams_r()
    ema_w = ta.trend.ema_indicator(w, window=24)
    if w.iloc[-1] < -99.5:
        return 'up'
    elif w.iloc[-1] > -0.5:
        return 'down'
    elif w.iloc[-1] < -75 and w.iloc[-2] < -75 and w.iloc[-2] < ema_w.iloc[-2] and w.iloc[-1] > ema_w.iloc[-1]:
        return 'up'
    elif w.iloc[-1] > -25 and w.iloc[-2] > -25 and w.iloc[-2] > ema_w.iloc[-2] and w.iloc[-1] < ema_w.iloc[-1]:
        return 'down'
    return 'none'

max_pos = 5  # Max current orders
symbols = ['LINAUSDT' , 'AIUSDT' , 'ETHUSDT' , 'APEUSDT' , 'NULSUSDT' , 'CLOUDUSDT' , 'IDEXUSDT' , 'NEIROETHUSDT' , 'UNIUSDT' , 'NOTUSDT' , 'BSWUSDT' , 'REEFUSDT' , 'TRBUSDT' , 'SOLUSDT' , 'AVAXUSDT' , 'AAVEUSDT' , 'CRVUSDT' , 'LEVERUSDT']

while True:
    balance = get_balance()
    if balance is None:
        print('Cannot connect to API')
        sleep(120)  # Wait before retrying
        continue

    print(f'Balance: {balance}')
    pos = get_positions()
    if pos is None:
        pos = []  # Ensure pos is a list even if get_positions() returns None
    print(f'You have {len(pos)} positions: {pos}')

    for symbol in symbols:
        if symbol in pos:
            print(f'Skipping {symbol} because it is already in positions')
        else:
            signal = rsi_signal(symbol)
            if signal == 'up':
                print(f'Found BUY signal for {symbol}')
                set_mode(symbol)
                sleep(2)
                place_order_market(symbol, 'buy')
                sleep(5)
            elif signal == 'down':
                print(f'Found SELL signal for {symbol}')
                set_mode(symbol)
                sleep(2)
                place_order_market(symbol, 'sell')
                sleep(5)

    print('Waiting 5 mins')
    sleep(300)
