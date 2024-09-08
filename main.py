from keys import api, secret
from pybit.unified_trading import HTTP
import pandas as pd
import ta
import requests
from time import sleep
from datetime import datetime, timedelta, timezone

session = HTTP(
    api_key=api,
    api_secret=secret
)

# Config:
tp = 0.006  # Take Profit +0.6%
sl = 0.009  # Stop Loss -0.9%
timeframe = 30  # 30 minutes
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

def get_tickers():
    try:
        resp = session.get_tickers(category="linear")['result']['list']
        symbols = [elem['symbol'] for elem in resp if 'USDT' in elem['symbol'] and 'USDC' not in elem['symbol']]
        return symbols
    except Exception as err:
        print(err)
        return []

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
            send_tg(f'📈 BUY Order: {symbol}\n 📌 Order Price: {mark_price}\n 💹 Qty: {order_qty}\n ✔️ TP: {tp_price}\n ✖️ SL: {sl_price}\n 📊 Live trades: {len(pos)+1}')
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
            send_tg(f'📉 SELL Order: {symbol}\n 📌 Order price: {mark_price}\n 💹 Qty: {order_qty}\n ✔️ TP: {tp_price}\n ✖️ SL: {sl_price}\n 📊 Live trades: {len(pos)+1}')
    except Exception as err:
        print(f'Order placement error: {err}')
        send_tg(f'Error placing {side} order for {symbol}: {err}')

def rsi_signal(symbol):
    kl = klines(symbol)  # Assuming klines returns a DataFrame with 'Close' column
    if 'Close' not in kl.columns:
        raise ValueError("DataFrame must contain 'Close' column")

    # Calculate RSI and its SMA
    rsi_indicator = ta.momentum.RSIIndicator(kl['Close'], window=14)
    rsi = rsi_indicator.rsi()
    rsi_sma = ta.trend.sma_indicator(rsi, window=21)

    # Ensure there are enough data points
    if len(rsi) < 21:
        return 'none'

    # Get recent values
    rsi_prev3 = rsi.iloc[-3]
    rsi_prev = rsi.iloc[-2]
    rsi_curr = rsi.iloc[-1]
    rsi_sma_prev3 = rsi_sma.iloc[-3]
    rsi_sma_prev = rsi_sma.iloc[-2]
    rsi_sma_curr = rsi_sma.iloc[-1]

    # Check for RSI crossing SMA conditions
    #cross_above = (rsi_prev < rsi_sma_prev) and (rsi_curr > rsi_sma_curr)
    #cross_below = (rsi_prev > rsi_sma_prev) and (rsi_curr < rsi_sma_curr)

    #crossed_above_70 = (rsi_prev < rsi_sma_prev and rsi_curr > rsi_sma_curr and rsi_prev > 70 and rsi_curr > 70 and rsi_curr < rsi_sma_curr)
    #crossed_below_30 = (rsi_prev > rsi_sma_prev and rsi_curr < rsi_sma_curr and rsi_prev < 30 and rsi_curr < 30 and rsi_curr > rsi_sma_curr)
    below_up = (rsi_prev3 < 30 and rsi_prev < 30 and rsi_curr > 30 and rsi_prev > rsi_sma_prev)
    above_down = (rsi_prev3 > 70 and rsi_prev > 70 and rsi_curr < 70 and rsi_prev < rsi_sma_prev)

    # Generate signals based on additional conditions

    #if crossed_above_70:
        #return 'down'

    #if crossed_below_30:
        #return 'up'

    if above_down:
        return 'down'

    if below_up:
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

max_pos = 10  # Max current orders
symbols = get_tickers()  # Getting all symbols from the Bybit Derivatives

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

    if len(pos) < max_pos:
        for symbol in symbols:
            if symbol in pos:
                print(f'Skipping {symbol} because it is already in positions')
                #send_tg(f'Skipping {symbol} because it is already in positions')
                continue

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
    print('Waiting 2 mins')
    sleep(120)
