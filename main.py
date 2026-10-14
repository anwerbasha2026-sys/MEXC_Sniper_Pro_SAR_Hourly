"""MEXC Sniper Pro SAR Hourly - Android/Kivy edition.
Spot only. Hourly PSAR entries/exits on closed candles; 4h EMA200 entry filter.
"""
import json, threading, time, os
from datetime import datetime
from pathlib import Path

import ccxt
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.switch import Switch
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.popup import Popup
from kivy.utils import get_color_from_hex


def psar_trend(candles, step=0.02, max_step=0.20):
    """Return bullish bool from closed OHLCV candles; None on invalid/short data."""
    if not isinstance(candles, (list, tuple)) or len(candles) < 5:
        return None
    try:
        highs = [float(c[2]) for c in candles]
        lows = [float(c[3]) for c in candles]
        closes = [float(c[4]) for c in candles]
    except (TypeError, ValueError, IndexError):
        return None
    for h, l, c in zip(highs, lows, closes):
        if not all(map(lambda x: x == x and abs(x) != float('inf'), (h, l, c))):
            return None
        if l <= 0 or h < l or c < l or c > h:
            return None
    bullish = closes[1] >= closes[0]
    sar = min(lows[0], lows[1]) if bullish else max(highs[0], highs[1])
    ep = max(highs[0], highs[1]) if bullish else min(lows[0], lows[1])
    af = step
    for i in range(2, len(candles)):
        candidate = sar + af * (ep - sar)
        if bullish:
            candidate = min(candidate, lows[i-1], lows[i-2])
            if lows[i] <= candidate:
                bullish, sar, ep, af = False, ep, lows[i], step
            else:
                sar = candidate
                if highs[i] > ep:
                    ep, af = highs[i], min(max_step, af + step)
        else:
            candidate = max(candidate, highs[i-1], highs[i-2])
            if highs[i] >= candidate:
                bullish, sar, ep, af = True, ep, highs[i], step
            else:
                sar = candidate
                if lows[i] < ep:
                    ep, af = lows[i], min(max_step, af + step)
    return bullish


def ema(values, period=200):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = alpha * price + (1.0 - alpha) * value
    return value


class SniperMobile(App):
    def build(self):
        Window.clearcolor = get_color_from_hex('#0b1220')
        self.title = 'MEXC Sniper Pro SAR Hourly'
        self.running = False
        self._live_confirmed = False
        self.worker = None
        self.exchange = None
        self.trade = None
        self.demo_balance = 1000.0
        self.total_pnl = 0.0
        self.logs = []
        self.lock = threading.RLock()
        self.manual_close = threading.Event()
        self.last_candle = {}
        self.settings_path = Path(self.user_data_dir) / 'settings.json'
        root = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        root.add_widget(Label(text='MEXC SNIPER PRO  •  SAR 1H / SPOT', size_hint_y=None, height=dp(38), bold=True, font_size='18sp', color=get_color_from_hex('#57d9a3')))
        self.status = Label(text='STOPPED • Demo mode', size_hint_y=None, height=dp(28), color=get_color_from_hex('#f5c76b'))
        root.add_widget(self.status)
        tabs = TabbedPanel(do_default_tab=False, tab_width=dp(115), background_color=get_color_from_hex('#17243a'))
        self.dashboard = self._make_tab('Dashboard')
        self.live_tab = self._make_tab('Live Trades')
        self.settings_tab = self._make_tab('Settings')
        tabs.add_widget(self.dashboard); tabs.add_widget(self.live_tab); tabs.add_widget(self.settings_tab)
        root.add_widget(tabs)
        self._build_dashboard(); self._build_live(); self._build_settings(); self._load_settings()
        Clock.schedule_interval(self._refresh_ui, 1)
        return root

    def _make_tab(self, title):
        tab = TabbedPanelItem(text=title)
        scroll = ScrollView(do_scroll_x=False)
        body = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8), size_hint_y=None)
        body.bind(minimum_height=body.setter('height'))
        scroll.add_widget(body); tab.add_widget(scroll); tab.body = body
        return tab

    def _label(self, text, height=34, size=15, color='#e6edf7'):
        return Label(text=text, size_hint_y=None, height=dp(height), font_size=f'{size}sp', color=get_color_from_hex(color), halign='left', valign='middle')

    def _input(self, hint='', text='', password=False):
        return TextInput(hint_text=hint, text=str(text), password=password, multiline=False, size_hint_y=None, height=dp(44), padding=(dp(10), dp(10)), foreground_color=get_color_from_hex('#e6edf7'), background_color=get_color_from_hex('#17243a'), hint_text_color=get_color_from_hex('#8493aa'), cursor_color=get_color_from_hex('#57d9a3'))

    def _button(self, text, callback, color='#176b52'):
        b = Button(text=text, size_hint_y=None, height=dp(46), background_normal='', background_color=get_color_from_hex(color), color=get_color_from_hex('#ffffff'))
        b.bind(on_release=lambda *_: callback())
        return b

    def _build_dashboard(self):
        b = self.dashboard.body
        b.add_widget(self._label('Market overview', 34, 18, '#57d9a3'))
        self.balance_label = self._label('USDT balance: Demo 1,000.00', 38, 17)
        b.add_widget(self.balance_label)
        self.price_label = self._label('Last price: —', 34)
        b.add_widget(self.price_label)
        self.signal_label = self._label('PSAR 1H: waiting for closed candle', 38)
        b.add_widget(self.signal_label)
        self.pnl_label = self._label('Session realized P/L: 0.0000 USDT', 34)
        b.add_widget(self.pnl_label)
        b.add_widget(self._label('Entry: bullish PSAR reversal + price above closed-candle 4H EMA200. Exit: bearish PSAR reversal on closed 1H candle.', 80, 14, '#aebbd0'))
        b.add_widget(self._button('START BOT', self.start_bot))
        b.add_widget(self._button('STOP BOT', self.stop_bot, '#8b2e3a'))
        b.add_widget(self._button('MANUAL CLOSE TRADE', self.close_trade, '#a75c1c'))
        self.log_label = self._label('Activity log\nReady.', 220, 13, '#aebbd0'); self.log_label.valign='top'; b.add_widget(self.log_label)

    def _build_live(self):
        b = self.live_tab.body
        b.add_widget(self._label('LIVE TRADES / OPEN POSITION', 42, 18, '#57d9a3'))
        self.live_trade_label = self._label('No open trade', 100, 16)
        b.add_widget(self.live_trade_label)
        b.add_widget(self._button('Refresh balance', self.refresh_balance))
        b.add_widget(self._button('Close open trade', self.close_trade, '#a75c1c'))
        b.add_widget(self._label('This screen shows the position tracked by this app. Verify exchange balances and order history on MEXC too.', 85, 13, '#aebbd0'))

    def _build_settings(self):
        b = self.settings_tab.body
        b.add_widget(self._label('TRADING SETTINGS', 42, 18, '#57d9a3'))
        b.add_widget(self._label('API Key (not saved)', 25, 13)); self.api_key = self._input('MEXC API Key'); b.add_widget(self.api_key)
        b.add_widget(self._label('Secret Key (not saved)', 25, 13)); self.secret = self._input('MEXC Secret Key', password=True); b.add_widget(self.secret)
        b.add_widget(self._label('Mode: Demo by default', 28, 14))
        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        self.demo_switch = Switch(active=True); row.add_widget(self.demo_switch); row.add_widget(self._label('Demo ON / OFF', 38, 14)); b.add_widget(row)
        b.add_widget(self._label('Spot pair (used when auto scan is off)', 25, 13)); self.symbol = self._input('BTC/USDT', 'BTC/USDT'); b.add_widget(self.symbol)
        row2 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8)); self.auto_switch = Switch(active=True); row2.add_widget(self.auto_switch); row2.add_widget(self._label('Auto scan top liquid USDT pairs', 38, 14)); b.add_widget(row2)
        b.add_widget(self._label('Number of candidates (5–20)', 25, 13)); self.scan_limit = self._input(text='12'); b.add_widget(self.scan_limit)
        b.add_widget(self._label('Minimum 24h quote volume (USDT)', 25, 13)); self.min_volume = self._input(text='100000'); b.add_widget(self.min_volume)
        b.add_widget(self._label('Initial demo balance (USDT)', 25, 13)); self.demo_amount = self._input(text='1000'); b.add_widget(self.demo_amount)
        b.add_widget(self._button('SAVE SETTINGS', self.save_settings))
        b.add_widget(self._label('Real mode uses up to 99.5% of free USDT to leave a fee buffer. API must be Spot trading only; never enable withdrawals.', 76, 13, '#f5c76b'))

    def _log(self, msg):
        stamp = datetime.now().strftime('%H:%M:%S')
        self.logs.insert(0, f'[{stamp}] {msg}')
        self.logs = self.logs[:12]
        Clock.schedule_once(lambda _dt: setattr(self.log_label, 'text', 'Activity log\n' + '\n'.join(self.logs)), 0)

    def _set_status(self, msg):
        Clock.schedule_once(lambda _dt: setattr(self.status, 'text', msg), 0)

    def _make_exchange(self):
        key, secret = self.api_key.text.strip(), self.secret.text.strip()
        cfg = {'enableRateLimit': True, 'timeout': 20000, 'options': {'defaultType': 'spot'}}
        if not self.demo_switch.active:
            if not key or not secret:
                raise ValueError('Enter API Key and Secret in Settings. They are not stored by the app.')
            cfg.update(apiKey=key, secret=secret)
        ex = ccxt.mexc(cfg)
        ex.load_markets()
        return ex

    def start_bot(self):
        if self.running: return
        if not self.demo_switch.active and not self._live_confirmed:
            box = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(10))
            box.add_widget(Label(text='LIVE SPOT trading will send real orders and can lose your funds. Confirm the MEXC API has Spot trading permission only and withdrawals are disabled.', halign='center'))
            actions = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
            popup = Popup(title='Confirm REAL trading', content=box, size_hint=(0.88, 0.48), auto_dismiss=False)
            cancel = Button(text='Cancel')
            confirm = Button(text='I understand — continue', background_normal='', background_color=get_color_from_hex('#8b2e3a'))
            cancel.bind(on_release=lambda *_: popup.dismiss())
            def confirmed(*_):
                popup.dismiss(); self._live_confirmed = True; self.start_bot()
            confirm.bind(on_release=confirmed)
            actions.add_widget(cancel); actions.add_widget(confirm); box.add_widget(actions); popup.open()
            return
        self._live_confirmed = False
        try:
            limit, volume, demo_bal = int(self.scan_limit.text), float(self.min_volume.text), float(self.demo_amount.text)
            if not 5 <= limit <= 20 or volume < 0 or demo_bal <= 0: raise ValueError
            if not self.auto_switch.active and '/' not in self.symbol.text: raise ValueError
        except Exception:
            self._log('Invalid settings. Check scan limit, volume, demo balance, and symbol.'); return
        if not self.demo_switch.active:
            self._log('LIVE SPOT mode confirmed by user.')
        self.running = True
        self.manual_close.clear()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()
        self._set_status('RUNNING • ' + ('DEMO' if self.demo_switch.active else 'LIVE SPOT'))
        self._log('Bot started. Signals use completed 1H candles.')

    def stop_bot(self):
        self.running = False
        self._set_status('STOPPING / STOPPED')
        self._log('Stop requested. An already-open exchange position is not automatically sold by stopping.')

    def close_trade(self):
        if not self.trade:
            self._log('No tracked open position.'); return
        self.manual_close.set(); self._log('Manual close requested; bot will send sell order on next position check.')

    def refresh_balance(self):
        if self.demo_switch.active:
            self._log(f'Demo balance: {self.demo_balance:.4f} USDT'); return
        threading.Thread(target=self._balance_worker, daemon=True).start()

    def _balance_worker(self):
        try:
            if self.exchange is None: self.exchange = self._make_exchange()
            bal = self.exchange.fetch_balance()
            free = float((bal.get('free') or {}).get('USDT') or 0)
            total = float((bal.get('total') or {}).get('USDT') or 0)
            self._log(f'MEXC USDT balance: free {free:.4f}, total {total:.4f}')
        except Exception as e: self._log(f'Balance error: {type(e).__name__}: {e}')

    def _run(self):
        try:
            self.exchange = self._make_exchange()
            ex = self.exchange
            candidates = []
            last_scan = 0
            while self.running:
                try:
                    if self.auto_switch.active and not self.trade and (not candidates or time.time()-last_scan >= 60):
                        tickers = ex.fetch_tickers()
                        rows=[]
                        for sym, t in tickers.items():
                            m = ex.markets.get(sym, {})
                            if not sym.endswith('/USDT') or not m or not m.get('spot', True) or not m.get('active', True): continue
                            qv = t.get('quoteVolume')
                            if qv is None and t.get('baseVolume') and t.get('last'): qv=float(t['baseVolume'])*float(t['last'])
                            if qv is None or float(qv) < float(self.min_volume.text or 100000): continue
                            rows.append((float(qv), sym))
                        rows.sort(reverse=True)
                        candidates=[s for _,s in rows[:int(self.scan_limit.text or 12)]]
                        last_scan=time.time()
                        self._log(f'Scanner refreshed: {len(candidates)} liquid Spot pairs.')
                    symbols = [self.trade['symbol']] if self.trade else ([self.symbol.text.strip().upper()] if not self.auto_switch.active else candidates)
                    for sym in symbols:
                        if not self.running: break
                        candles = ex.fetch_ohlcv(sym, timeframe='1h', limit=250)
                        closed = candles[:-1] if candles else []
                        if len(closed) < 205: continue
                        signal = psar_trend(closed)
                        previous = psar_trend(closed[:-1])
                        price = float((ex.fetch_ticker(sym) or {}).get('last') or closed[-1][4])
                        Clock.schedule_once(lambda _dt, p=price, s=sym: setattr(self.price_label, 'text', f'{s} • {p:.8g}'))
                        Clock.schedule_once(lambda _dt, bull=signal: setattr(self.signal_label, 'text', 'PSAR 1H: BULLISH' if bull else 'PSAR 1H: BEARISH'))
                        if self.trade and self.trade['symbol'] == sym:
                            self._update_trade_view(price)
                            if self.manual_close.is_set() or (previous is True and signal is False):
                                self._sell(ex, price, 'Manual close' if self.manual_close.is_set() else 'Closed 1H PSAR reversal')
                                self.manual_close.clear(); candidates=[]; break
                        elif not self.trade and previous is False and signal is True:
                            candles4 = ex.fetch_ohlcv(sym, timeframe='4h', limit=220)
                            closed4 = candles4[:-1] if candles4 else []
                            e = ema([float(c[4]) for c in closed4], 200)
                            if e is None or float(closed4[-1][4]) <= e: continue
                            self._buy(ex, sym, price)
                            if self.trade: candidates=[]; break
                    time.sleep(60)
                except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                    self._log(f'Network issue; retrying: {type(e).__name__}'); time.sleep(8)
                except Exception as e:
                    self._log(f'Cycle error: {type(e).__name__}: {e}'); time.sleep(8)
        except Exception as e:
            self._log(f'Start error: {type(e).__name__}: {e}')
        finally:
            self.running=False; self._set_status('STOPPED')

    def _buy(self, ex, symbol, price):
        if self.trade: return
        demo = self.demo_switch.active
        if demo:
            spend = self.demo_balance * 0.995
            if spend < 5: self._log('Demo balance too low.'); return
            qty = float(ex.amount_to_precision(symbol, spend / price))
            if qty <= 0: return
            self.demo_balance -= spend; cost=spend; entry=price; order_id='DEMO-'+str(int(time.time()))
        else:
            bal=ex.fetch_balance(); free=float((bal.get('free') or {}).get('USDT') or 0)
            spend=free*0.995
            if spend < 5: self._log(f'Free USDT too low: {free:.4f}'); return
            market=ex.market(symbol)
            qty=float(ex.amount_to_precision(symbol, spend/price))
            if qty <= 0: self._log('Order quantity rounded to zero.'); return
            limits=(market.get('limits') or {}).get('cost') or {}
            min_cost=float(limits.get('min') or 0)
            if qty*price < min_cost: self._log(f'Order below exchange minimum cost ({min_cost}).'); return
            order=ex.create_market_buy_order(symbol, qty)
            qty=float(order.get('filled') or 0)
            if qty <= 0: raise RuntimeError(f'Buy {order.get("id")} has no confirmed filled quantity; verify MEXC order history.')
            entry=float(order.get('average') or order.get('price') or price); cost=float(order.get('cost') or entry*qty); order_id=order.get('id')
        self.trade={'symbol':symbol,'amount':qty,'entry_price':entry,'cost':cost,'order_id':order_id,'demo':demo,'opened_at':datetime.now().isoformat(timespec='seconds')}
        self._log(f'BUY {symbol} qty={qty:.8g} entry={entry:.8g} mode={"DEMO" if demo else "LIVE"}')
        self._update_trade_view(price)

    def _sell(self, ex, price, reason):
        trade=self.trade
        if not trade: return
        symbol=trade['symbol']; qty=float(trade['amount']); entry=float(trade['entry_price'])
        if trade['demo']:
            exit_price=price; proceeds=qty*exit_price; pnl=proceeds-float(trade['cost']); self.demo_balance += proceeds
        else:
            qty=float(ex.amount_to_precision(symbol, qty))
            if qty <= 0: raise RuntimeError('Invalid sell quantity after precision formatting.')
            order=ex.create_market_sell_order(symbol, qty)
            filled=float(order.get('filled') or 0)
            if filled <= 0: raise RuntimeError(f'Sell {order.get("id")} has no confirmed filled quantity; verify MEXC order history.')
            exit_price=float(order.get('average') or order.get('price') or price); pnl=(exit_price-entry)*filled; qty=filled
        self.total_pnl += pnl
        self._log(f'SELL {symbol} qty={qty:.8g} exit={exit_price:.8g} P/L≈{pnl:+.4f} USDT • {reason}')
        self.trade=None
        Clock.schedule_once(lambda _dt: setattr(self.pnl_label,'text',f'Session realized P/L: {self.total_pnl:+.4f} USDT'))
        self._update_trade_view(price)

    def _update_trade_view(self, price):
        t=self.trade
        if t:
            pnl=(price-t['entry_price'])*t['amount']
            text=f"{t['symbol']}\nEntry: {t['entry_price']:.8g}\nQty: {t['amount']:.8g}\nCost: {t['cost']:.4f} USDT\nUnrealized P/L (approx): {pnl:+.4f} USDT\nOpened: {t['opened_at']}"
        else: text='No open trade tracked by this app.'
        Clock.schedule_once(lambda _dt, v=text: setattr(self.live_trade_label,'text',v))
        if self.demo_switch.active:
            Clock.schedule_once(lambda _dt: setattr(self.balance_label,'text',f'Demo balance: {self.demo_balance:,.2f} USDT'))

    def _refresh_ui(self, _dt):
        if self.logs: self.log_label.text='Activity log\n'+'\n'.join(self.logs)
        if self.trade: self._update_trade_view(float(self.trade['entry_price']))

    def save_settings(self):
        try:
            data={'symbol':self.symbol.text.strip().upper(),'auto_scan':self.auto_switch.active,'scan_limit':self.scan_limit.text,'min_volume':self.min_volume.text,'demo_balance':self.demo_amount.text,'demo':self.demo_switch.active}
            self.settings_path.parent.mkdir(parents=True,exist_ok=True)
            self.settings_path.write_text(json.dumps(data,indent=2),encoding='utf-8')
            self._log('Settings saved. API keys are intentionally not saved.')
        except Exception as e: self._log(f'Save settings failed: {type(e).__name__}: {e}')

    def _load_settings(self):
        try:
            if not self.settings_path.exists(): return
            d=json.loads(self.settings_path.read_text(encoding='utf-8'))
            self.symbol.text=d.get('symbol','BTC/USDT'); self.auto_switch.active=bool(d.get('auto_scan',True))
            self.scan_limit.text=str(d.get('scan_limit',12)); self.min_volume.text=str(d.get('min_volume',100000))
            self.demo_amount.text=str(d.get('demo_balance',1000)); self.demo_switch.active=bool(d.get('demo',True))
            self.demo_balance=max(0,float(self.demo_amount.text))
        except Exception: pass

    def on_stop(self):
        self.running=False


if __name__ == '__main__':
    SniperMobile().run()
