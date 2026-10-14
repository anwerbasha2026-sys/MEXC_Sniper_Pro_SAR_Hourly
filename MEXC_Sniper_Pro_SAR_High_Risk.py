"""
MEXC Sniper Pro - safer Spot starter implementation.
Important: test in demo mode first. This is not a profitability guarantee.
Install: pip install customtkinter ccxt
"""
import json
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import ccxt
import customtkinter as ctk

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

APP_DIR = Path.home() / ".mexc_sniper_pro"
SETTINGS_FILE = APP_DIR / "settings.json"


class MexcTradingApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MEXC Sniper Pro — SAR Hourly Auto Scanner / Spot")
        # Fit common 1024x768 screens while allowing resizing.
        self.geometry("1000x700")
        self.minsize(900, 600)

        self.is_running = False
        self.bot_thread = None
        self.exchange = None
        self.current_trade = None
        self.closed_trades = []
        self.total_pnl = 0.0
        self.demo_balance = 1000.0
        self.manual_close_event = threading.Event()
        self.trade_lock = threading.Lock()
        self.ui_queue = []
        self.queue_lock = threading.Lock()
        self.closing = False

        self._build_sidebar()
        self._build_dashboard()
        self._load_settings()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._process_ui_queue)

    def _build_sidebar(self):
        # Scrollable settings panel keeps every control reachable on small screens.
        sidebar = ctk.CTkScrollableFrame(self, width=285, corner_radius=0)
        sidebar.pack(side="left", fill="both", padx=10, pady=10)

        ctk.CTkLabel(sidebar, text="⚙️ الإعدادات والربط",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 12))

        ctk.CTkLabel(sidebar, text="MEXC API Key").pack(anchor="w", padx=15)
        self.api_key_entry = ctk.CTkEntry(sidebar, placeholder_text="API Key", show="*")
        self.api_key_entry.pack(fill="x", padx=15, pady=(3, 8))

        ctk.CTkLabel(sidebar, text="MEXC Secret Key").pack(anchor="w", padx=15)
        self.secret_key_entry = ctk.CTkEntry(sidebar, placeholder_text="Secret Key", show="*")
        self.secret_key_entry.pack(fill="x", padx=15, pady=(3, 8))

        self.mode_switch = ctk.CTkSwitch(
            sidebar, text="الوضع التجريبي (Demo)", command=self._on_mode_change
        )
        self.mode_switch.pack(anchor="w", padx=15, pady=8)
        self.mode_switch.select()

        self.demo_frame = ctk.CTkFrame(sidebar, fg_color="#1f1f1f")
        self.demo_frame.pack(fill="x", padx=15, pady=6)
        ctk.CTkLabel(self.demo_frame, text="رصيد تجريبي (USDT)").pack(anchor="w", padx=10, pady=(6, 0))
        self.demo_balance_label = ctk.CTkLabel(
            self.demo_frame, text=f"{self.demo_balance:,.2f} USDT",
            font=ctk.CTkFont(size=15, weight="bold"), text_color="#2ecc71"
        )
        self.demo_balance_label.pack(anchor="w", padx=10, pady=(0, 6))

        ctk.CTkLabel(sidebar, text="الرصيد التجريبي الابتدائي (USDT)").pack(anchor="w", padx=15, pady=(4, 0))
        self.demo_balance_entry = ctk.CTkEntry(sidebar)
        self.demo_balance_entry.insert(0, "1000")
        self.demo_balance_entry.pack(fill="x", padx=15, pady=(3, 8))
        ctk.CTkButton(
            sidebar, text="تطبيق الرصيد التجريبي",
            command=self.apply_demo_balance
        ).pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(sidebar, text="زوج التداول (Spot)").pack(anchor="w", padx=15, pady=(6, 0))
        self.symbol_entry = ctk.CTkEntry(sidebar)
        self.symbol_entry.insert(0, "BTC/USDT")
        self.symbol_entry.pack(fill="x", padx=15, pady=(3, 8))

        self.auto_scan_switch = ctk.CTkSwitch(
            sidebar, text="اختيار العملات تلقائياً (SAR)")
        self.auto_scan_switch.select()
        self.auto_scan_switch.pack(anchor="w", padx=15, pady=(2, 8))
        ctk.CTkLabel(sidebar, text="عدد العملات المرشحة (5–20)").pack(anchor="w", padx=15)
        self.scan_limit_entry = ctk.CTkEntry(sidebar)
        self.scan_limit_entry.insert(0, "12")
        self.scan_limit_entry.pack(fill="x", padx=15, pady=(3, 8))
        ctk.CTkLabel(sidebar, text="مستوى المخاطرة: مرتفع (تلقائي)", text_color="#f1c40f").pack(anchor="w", padx=15, pady=(2, 0))
        ctk.CTkLabel(sidebar, text="يفضّل العملات عالية التذبذب: نطاق حركة إرشادي 8–30% خلال 24 ساعة. مخاطرة وخسائر محتملة أعلى.", wraplength=250, justify="left").pack(anchor="w", padx=15, pady=(1, 6))
        ctk.CTkLabel(sidebar, text="حجم التداول الأدنى (USDT/24h)").pack(anchor="w", padx=15)
        self.min_volume_entry = ctk.CTkEntry(sidebar)
        self.min_volume_entry.insert(0, "100000")
        self.min_volume_entry.pack(fill="x", padx=15, pady=(3, 8))

        ctk.CTkLabel(sidebar, text="مبلغ الصفقة (التجريبي يستخدم كامل الرصيد؛ الحقيقي يستخدم الرصيد الحر)").pack(anchor="w", padx=15)
        self.amount_entry = ctk.CTkEntry(sidebar)
        self.amount_entry.insert(0, "10")
        self.amount_entry.pack(fill="x", padx=15, pady=(3, 8))

        ctk.CTkButton(sidebar, text="💾 حفظ الإعدادات", command=self.save_settings).pack(fill="x", padx=15, pady=(8, 5))
        self.start_btn = ctk.CTkButton(
            sidebar, text="▶ تشغيل البوت", fg_color="green",
            hover_color="darkgreen", command=self.start_bot
        )
        self.start_btn.pack(fill="x", padx=15, pady=(10, 5))
        self.stop_btn = ctk.CTkButton(
            sidebar, text="⏹ إيقاف البوت", fg_color="#a93226",
            hover_color="#78281f", state="disabled", command=self.stop_bot
        )
        self.stop_btn.pack(fill="x", padx=15, pady=5)
        self.status_label = ctk.CTkLabel(sidebar, text="الحالة: متوقف 🔴", text_color="gray")
        self.status_label.pack(pady=12)

        ctk.CTkLabel(
            sidebar,
            text="تنبيه: اختبر تجريبياً أولاً.\nلا تمنح API صلاحية السحب.",
            text_color="#e67e22", wraplength=255, justify="left"
        ).pack(anchor="w", padx=12, pady=12)

    def _build_dashboard(self):
        main = ctk.CTkFrame(self)
        main.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        cards = ctk.CTkFrame(main, fg_color="transparent")
        cards.pack(fill="x", pady=8)

        pnl_card = ctk.CTkFrame(cards)
        pnl_card.pack(side="left", fill="both", expand=True, padx=4)
        ctk.CTkLabel(pnl_card, text="إجمالي الربح/الخسارة").pack(pady=(9, 2))
        self.pnl_label = ctk.CTkLabel(pnl_card, text="$0.00", font=ctk.CTkFont(size=17, weight="bold"))
        self.pnl_label.pack(pady=(0, 9))

        price_card = ctk.CTkFrame(cards)
        price_card.pack(side="left", fill="both", expand=True, padx=4)
        ctk.CTkLabel(price_card, text="سعر السوق").pack(pady=(9, 2))
        self.price_label = ctk.CTkLabel(price_card, text="—", font=ctk.CTkFont(size=17, weight="bold"))
        self.price_label.pack(pady=(0, 9))

        signal_card = ctk.CTkFrame(cards)
        signal_card.pack(side="left", fill="both", expand=True, padx=4)
        ctk.CTkLabel(signal_card, text="إشارة الاتجاه (PSAR)").pack(pady=(9, 2))
        self.signal_label = ctk.CTkLabel(signal_card, text="بانتظار التشغيل", font=ctk.CTkFont(size=13, weight="bold"))
        self.signal_label.pack(pady=(0, 9))

        trade_frame = ctk.CTkFrame(main)
        trade_frame.pack(fill="x", pady=8, padx=4)
        header = ctk.CTkFrame(trade_frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(header, text="📌 الصفقة النشطة", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        self.close_btn = ctk.CTkButton(
            header, text="إغلاق الصفقة يدوياً", fg_color="#D35400",
            hover_color="#A04000", state="disabled", command=self.close_trade_manually
        )
        self.close_btn.pack(side="right")
        self.trade_label = ctk.CTkLabel(trade_frame, text="لا توجد صفقة مفتوحة", text_color="gray")
        self.trade_label.pack(pady=14)

        scan_frame = ctk.CTkFrame(main)
        scan_frame.pack(fill="both", expand=True, pady=(4, 2), padx=4)
        ctk.CTkLabel(scan_frame, text="🔎 حالة الماسح وأسباب قرار الاستراتيجية",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=5)
        scan_cols = ("symbol", "sar", "ema", "decision", "price")
        self.scan_tree = ttk.Treeview(scan_frame, columns=scan_cols, show="headings", height=5)
        for col, title, width in [
            ("symbol", "الزوج", 105), ("sar", "اتجاه SAR", 105),
            ("ema", "تأكيد EMA 200 (4h)", 155),
            ("decision", "الحالة / سبب عدم الدخول", 330), ("price", "السعر", 115)
        ]:
            self.scan_tree.heading(col, text=title)
            self.scan_tree.column(col, width=width, anchor="center")
        self.scan_tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._scan_rows = {}

        history = ctk.CTkFrame(main)
        history.pack(fill="both", expand=True, pady=8, padx=4)
        ctk.CTkLabel(history, text="📜 سجل الصفقات", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=10, pady=5)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#2b2b2b", foreground="white",
                        fieldbackground="#2b2b2b", rowheight=25)
        style.map("Treeview", background=[("selected", "#1f538d")])
        self.tree = ttk.Treeview(
            history, columns=("time", "symbol", "entry", "exit", "amount", "pnl"),
            show="headings"
        )
        for col, title, width in [
            ("time", "التاريخ والوقت", 140), ("symbol", "الزوج", 100),
            ("entry", "الدخول", 100), ("exit", "الخروج", 100),
            ("amount", "الكمية", 100), ("pnl", "الربح/الخسارة USDT", 140)
        ]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

    def _update_scan_row(self, symbol, sar_text, ema_text, decision, price="—"):
        """Thread-safe UI update for a per-symbol strategy explanation row."""
        self._ui(self._render_scan_row, symbol, sar_text, ema_text, decision, price)

    def _render_scan_row(self, symbol, sar_text, ema_text, decision, price):
        values = (symbol, sar_text, ema_text, decision, price)
        item = self._scan_rows.get(symbol)
        if item and self.scan_tree.exists(item):
            self.scan_tree.item(item, values=values)
        else:
            item = self.scan_tree.insert("", "end", values=values)
            self._scan_rows[symbol] = item
        # Keep the newest scanned pairs visible without allowing an unbounded table.
        children = self.scan_tree.get_children()
        while len(children) > 30:
            old = children[0]
            self.scan_tree.delete(old)
            for key, value in list(self._scan_rows.items()):
                if value == old:
                    del self._scan_rows[key]
                    break

    def apply_demo_balance(self):
        if self.current_trade:
            messagebox.showwarning(
                "لا يمكن تغيير الرصيد",
                "أغلق الصفقة التجريبية المفتوحة أولاً، ثم غيّر الرصيد."
            )
            return
        try:
            value = float(self.demo_balance_entry.get().strip())
            if value <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("رصيد غير صحيح", "أدخل رصيداً تجريبياً أكبر من صفر.")
            return
        self.demo_balance = value
        self.demo_balance_label.configure(text=f"{self.demo_balance:,.2f} USDT")
        self.save_settings(show_message=False)
        messagebox.showinfo("تم تحديث الرصيد", f"الرصيد التجريبي أصبح {value:,.2f} USDT.")

    def _on_mode_change(self):
        if self.mode_switch.get() == 1:
            self.demo_frame.pack(fill="x", padx=15, pady=6)
        else:
            self.demo_frame.pack_forget()
            messagebox.showwarning(
                "تنبيه أمان",
                "الوضع الحقيقي ينفذ أوامر Spot بأموال فعلية. تأكد من المفاتيح والمبلغ والزوج. "
                "استخدم API بصلاحية التداول فقط ومن دون السحب."
            )

    def _ui(self, callback, *args, **kwargs):
        with self.queue_lock:
            self.ui_queue.append((callback, args, kwargs))

    def _process_ui_queue(self):
        if self.closing:
            return
        with self.queue_lock:
            items, self.ui_queue = self.ui_queue, []
        for callback, args, kwargs in items:
            try:
                callback(*args, **kwargs)
            except Exception:
                pass
        self.after(150, self._process_ui_queue)

    def _set_status(self, text, color="gray"):
        self.status_label.configure(text=text, text_color=color)

    def start_bot(self):
        if self.is_running:
            return
        auto_scan = bool(self.auto_scan_switch.get())
        symbol = self.symbol_entry.get().strip().upper()
        try:
            amount = float(self.amount_entry.get())
            if amount <= 0:
                raise ValueError
            scan_limit = int(self.scan_limit_entry.get())
            min_volume = float(self.min_volume_entry.get())
            if not 5 <= scan_limit <= 20 or min_volume < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("إعدادات غير صحيحة", "تحقق من مبلغ الصفقة وعدد العملات (5–20) وحجم التداول.")
            return
        if not auto_scan and (not symbol or "/" not in symbol):
            messagebox.showerror("زوج غير صحيح", "أدخل الزوج بصيغة مثل BTC/USDT أو فعّل الاختيار التلقائي.")
            return
        is_demo = self.mode_switch.get() == 1
        api_key = self.api_key_entry.get().strip()
        secret = self.secret_key_entry.get().strip()
        if not is_demo and (not api_key or not secret):
            messagebox.showerror("مفاتيح ناقصة", "أدخل API Key و Secret Key للوضع الحقيقي.")
            return
        description = (f"اختيار تلقائي من أفضل {scan_limit} أزواج USDT" if auto_scan else symbol)
        if not is_demo:
            if not messagebox.askyesno("تأكيد التداول الحقيقي", f"سيتم التداول الحقيقي Spot باستخدام {description}.\nملاحظة: سيستخدم البوت الرصيد الحر المتاح تقريباً بالكامل لكل دخول. هل تريد المتابعة؟"):
                return

        self.save_settings(show_message=False)
        self.is_running = True
        self.manual_close_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._set_status("الحالة: جارٍ الاتصال وفحص العملات…", "#f1c40f")
        self.bot_thread = threading.Thread(
            target=self._run_strategy,
            args=(symbol, amount, is_demo, api_key, secret, auto_scan, scan_limit, min_volume),
            daemon=True
        )
        self.bot_thread.start()

    def stop_bot(self):
        self.is_running = False
        self._ui(self.start_btn.configure, state="normal")
        self._ui(self.stop_btn.configure, state="disabled")
        self._ui(self._set_status, "الحالة: يتوقف بعد انتهاء الطلب الجاري…", "gray")

    def close_trade_manually(self):
        if not self.current_trade:
            messagebox.showinfo("معلومة", "لا توجد صفقة مفتوحة.")
            return
        if not messagebox.askyesno("تأكيد الإغلاق", "هل تريد إرسال أمر بيع لإغلاق كمية الصفقة المسجلة؟"):
            return
        self.manual_close_event.set()
        self.close_btn.configure(state="disabled", text="جارٍ طلب الإغلاق…")

    def _make_exchange(self, api_key, secret):
        ex = ccxt.mexc({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "timeout": 30000,
            # MEXC signed private requests can fail when the PC clock drifts.
            # CCXT will calculate the exchange/local time offset before signing.
            "options": {
                "defaultType": "spot",
                "adjustForTimeDifference": True,
                "recvWindow": 10000,
            },
        })
        # Sync server time before loading markets/currencies. This is especially
        # important because load_markets may call the signed capital/config endpoint.
        try:
            ex.load_time_difference()
        except Exception:
            # Some CCXT versions/adapters may not expose time sync; retain the
            # automatic adjustment option and let the actual request report details.
            pass
        try:
            ex.load_markets()
        except ccxt.AuthenticationError as exc:
            message = str(exc)
            if "700002" in message or "signature" in message.lower():
                raise RuntimeError(
                    "رفضت MEXC التوقيع (700002). تحقق من Secret Key المنسوخ دون مسافات، "
                    "وأعد حفظ المفاتيح. تمت مزامنة وقت الخادم تلقائياً؛ إذا استمر الخطأ "
                    "أنشئ API Key جديداً بصلاحية قراءة الحساب وSpot Trading فقط."
                ) from exc
            if "700003" in message or "timestamp" in message.lower() or "recvwindow" in message.lower():
                raise RuntimeError(
                    "رفضت MEXC توقيت الطلب. فعّل ضبط الوقت تلقائياً في Windows ثم اختر "
                    "مزامنة الآن، وتأكد من أن التاريخ والمنطقة الزمنية صحيحان."
                ) from exc
            if "700007" in message or "permission" in message.lower():
                raise RuntimeError(
                    "مفتاح API لا يملك صلاحية قراءة بيانات الحساب المطلوبة. فعّل صلاحية "
                    "قراءة الحساب/الأصول في MEXC، ولا تفعّل السحب."
                ) from exc
            if "700006" in message:
                raise RuntimeError(
                    "عنوان IP الحالي غير مسموح به لمفتاح API (700006). حدّث قائمة IP المسموح "
                    "في إعدادات المفتاح على MEXC أو أزل القيد إن كان ذلك مناسباً وآمناً."
                ) from exc
            raise
        return ex

    @staticmethod
    def _psar_signal(ohlcv, step=0.02, max_step=0.20):
        """Return the PSAR trend using completed OHLC candles only.

        Returns True for bullish, False for bearish, or None if data is
        insufficient/invalid. The caller should pass CLOSED candles only.
        """
        if not isinstance(ohlcv, (list, tuple)) or len(ohlcv) < 5:
            return None
        if not (0 < step <= max_step <= 1):
            raise ValueError("إعدادات PSAR غير صحيحة: يجب أن يكون 0 < step <= max_step <= 1")
        try:
            highs = [float(c[2]) for c in ohlcv]
            lows = [float(c[3]) for c in ohlcv]
            closes = [float(c[4]) for c in ohlcv]
        except (TypeError, ValueError, IndexError):
            return None
        if any(not all(map(lambda x: x == x and abs(x) != float('inf'), row))
               for row in zip(highs, lows, closes)):
            return None
        if any(h <= 0 or l <= 0 or c <= 0 or h < l or c > h or c < l
               for h, l, c in zip(highs, lows, closes)):
            return None

        # Seed the initial trend from the first two completed closes.
        bullish = closes[1] >= closes[0]
        sar = min(lows[0], lows[1]) if bullish else max(highs[0], highs[1])
        ep = max(highs[0], highs[1]) if bullish else min(lows[0], lows[1])
        af = step

        for i in range(2, len(ohlcv)):
            prior_sar = sar
            candidate = prior_sar + af * (ep - prior_sar)

            if bullish:
                # In an uptrend PSAR cannot rise above either of the last
                # two completed candle lows.
                candidate = min(candidate, lows[i - 1], lows[i - 2])
                if lows[i] <= candidate:
                    bullish = False
                    sar = ep
                    ep = lows[i]
                    af = step
                else:
                    sar = candidate
                    if highs[i] > ep:
                        ep = highs[i]
                        af = min(max_step, af + step)
            else:
                # In a downtrend PSAR cannot fall below either of the last
                # two completed candle highs.
                candidate = max(candidate, highs[i - 1], highs[i - 2])
                if highs[i] >= candidate:
                    bullish = True
                    sar = ep
                    ep = highs[i]
                    af = step
                else:
                    sar = candidate
                    if lows[i] < ep:
                        ep = lows[i]
                        af = min(max_step, af + step)
        return bullish

    @staticmethod
    def _ema(values, period=200):
        """EMA over closed-candle closes; return None when history is short."""
        if len(values) < period or period < 2:
            return None
        alpha = 2.0 / (period + 1.0)
        value = sum(values[:period]) / period
        for price in values[period:]:
            value = alpha * price + (1.0 - alpha) * value
        return value

    def _scan_spot_candidates(self, exchange, scan_limit=12, min_quote_volume=100000):
        """Select higher-volatility USDT spot pairs, ranked by movement first.

        This is a heuristic high-risk filter, not a guarantee of profit. It prefers
        absolute 24h price change of 8%-30%, requires minimum quote volume, and
        excludes leveraged wrappers. High volatility can increase losses and slippage.
        """
        markets = exchange.markets or exchange.load_markets()
        tickers = exchange.fetch_tickers()
        rows = []
        for symbol, market in markets.items():
            try:
                if (not market.get("active", True) or not market.get("spot", False)
                        or market.get("quote") != "USDT" or not market.get("base")):
                    continue
                base = str(market.get("base", "")).upper()
                if any(tag in base for tag in ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S")):
                    continue
                ticker = tickers.get(symbol) or {}
                quote_volume = float(ticker.get("quoteVolume") or 0)
                last = float(ticker.get("last") or 0)
                if last <= 0 or quote_volume < min_quote_volume:
                    continue
                pct = ticker.get("percentage")
                if pct is not None:
                    movement_pct = abs(float(pct))
                else:
                    high = float(ticker.get("high") or 0)
                    low = float(ticker.get("low") or 0)
                    movement_pct = ((high - low) / last * 100.0) if high > 0 and low > 0 else None
                # If the exchange supplies no usable volatility data, skip the pair
                # rather than pretending it has medium risk.
                if movement_pct is None or not 8.0 <= movement_pct <= 30.0:
                    continue
                # Rank by highest movement first; use liquidity as a tie-breaker.
                rows.append((movement_pct, quote_volume, symbol))
            except (TypeError, ValueError, ZeroDivisionError):
                continue
        rows.sort(reverse=True)
        return [symbol for _, _, symbol in rows[:scan_limit]]

    def _run_strategy(self, symbol, trade_budget, is_demo, api_key, secret,
                      auto_scan=False, scan_limit=12, min_quote_volume=100000):
        try:
            exchange = self._make_exchange(api_key, secret)
            self.exchange = exchange
            if not auto_scan:
                market = exchange.market(symbol)
                if not market.get("spot", False):
                    raise RuntimeError("الزوج المحدد ليس سوق Spot.")
            self._ui(self._set_status, "متصل؛ فحص السيولة واتجاه SAR/EMA 🟢", "green")
            # Per-symbol state prevents duplicate entries and evaluates only newly closed bars.
            states = {}
            last_scan_at = 0.0
            candidates = [symbol] if not auto_scan else []
            while self.is_running:
                try:
                    now = time.monotonic()
                    if auto_scan and not self.current_trade and (not candidates or now - last_scan_at >= 60):
                        candidates = self._scan_spot_candidates(exchange, scan_limit, min_quote_volume)
                        last_scan_at = now
                        if not candidates:
                            self._ui(self._set_status, "لا توجد أزواج تستوفي السيولة ونطاق المخاطرة المتوسط (1–8%)؛ إعادة الفحص…", "#e67e22")
                            time.sleep(8)
                            continue
                        self._ui(self._set_status, f"فحص {len(candidates)} زوجاً متوسط الحركة؛ انتظار انعكاس SAR وتأكيد EMA 200", "green")

                    # Once a position is open, monitor its own symbol only until it is closed.
                    symbols_to_check = [self.current_trade["symbol"]] if self.current_trade else candidates
                    entered_or_exited = False
                    for active_symbol in symbols_to_check:
                        if not self.is_running:
                            break
                        market = exchange.market(active_symbol)
                        if not market.get("spot", False):
                            continue
                        ohlcv = exchange.fetch_ohlcv(active_symbol, timeframe="1h", limit=250)
                        if not ohlcv or len(ohlcv) < 8:
                            self._update_scan_row(active_symbol, "غير متاح", "لم يُفحص", "بيانات شموع غير كافية")
                            continue
                        closed = ohlcv[:-1]  # exclude the still-forming hourly candle
                        if len(closed) < 5:
                            continue
                        closed_ts = closed[-1][0]
                        state = states.setdefault(active_symbol, {"ts": None, "signal": None})
                        # Manual close must not wait for the next completed minute candle.
                        if (self.current_trade and self.current_trade["symbol"] == active_symbol
                                and self.manual_close_event.is_set()):
                            ticker_now = exchange.fetch_ticker(active_symbol)
                            market_price = float(ticker_now.get("last") or closed[-1][4])
                            trade_now = self.current_trade
                            with self.trade_lock:
                                if self.current_trade is trade_now:
                                    self._sell_position(exchange, market_price, is_demo, "إغلاق يدوي")
                            self.manual_close_event.clear()
                            entered_or_exited = True
                            break
                        if state["ts"] == closed_ts:
                            continue
                        old_signal = state["signal"]
                        signal = self._psar_signal(closed)
                        state["ts"], state["signal"] = closed_ts, signal
                        if signal is None:
                            self._update_scan_row(active_symbol, "غير محدد", "لم يُفحص", "بيانات SAR غير كافية")
                            continue
                        ticker = exchange.fetch_ticker(active_symbol)
                        price = float(ticker.get("last") or closed[-1][4])
                        sar_text = "صاعد 🟢" if signal else "هابط 🔴"
                        self._update_scan_row(active_symbol, sar_text, "بانتظار إشارة انعكاس",
                                              "اتجاه مرصود؛ ننتظر شمعة مغلقة تؤكد الانعكاس", f"{price:.8g}")
                        if self.current_trade and self.current_trade["symbol"] == active_symbol:
                            self._ui(self.price_label.configure, text=f"${price:,.8f}".rstrip("0").rstrip("."))
                            self._ui(self.signal_label.configure,
                                     text="اتجاه صاعد 🟢" if signal else "اتجاه هابط 🔴",
                                     text_color="green" if signal else "red")
                            trade = self.current_trade
                            pnl = (price - trade["entry_price"]) * trade["amount"]
                            pnl_pct = (price / trade["entry_price"] - 1.0) * 100.0
                            self._ui(self.trade_label.configure,
                                     text=(f'{trade["symbol"]} | دخول: {trade["entry_price"]:.8g} | '
                                           f'الكمية: {trade["amount"]:.8g} | قيمة الدخول: {trade["cost"]:.4f} USDT\n'
                                           f'ربح/خسارة غير محققة (تقريبي): {pnl:.4f} USDT ({pnl_pct:.2f}%)'),
                                     text_color="green" if pnl >= 0 else "red")
                            reason = None
                            if self.manual_close_event.is_set():
                                reason = "إغلاق يدوي"
                            elif old_signal is True and signal is False:
                                reason = "انعكاس PSAR مؤكد بعد إغلاق شمعة الساعة"
                            if reason:
                                with self.trade_lock:
                                    if self.current_trade is trade:
                                        self._sell_position(exchange, price, is_demo, reason)
                                self.manual_close_event.clear()
                                entered_or_exited = True
                                break
                        elif not self.current_trade:
                            self._update_scan_row(active_symbol, sar_text, "لم يُختبر بعد",
                                                  "لا يوجد انعكاس صاعد جديد؛ بانتظار إشارة SAR التالية", f"{price:.8g}")
                        if (not self.current_trade and old_signal is False and signal is True
                              and self.is_running):
                            # Confirm the hourly SAR reversal with the 4-hour EMA 200 trend.
                            candles_4h = exchange.fetch_ohlcv(active_symbol, timeframe="4h", limit=220)
                            if not candles_4h or len(candles_4h) < 202:
                                self._update_scan_row(active_symbol, "انعكاس صاعد 🟢", "بيانات غير كافية",
                                                      "لا توجد شموع 4h كافية لحساب EMA 200", f"{price:.8g}")
                                continue
                            closed_4h = candles_4h[:-1]
                            closes_4h = [float(c[4]) for c in closed_4h]
                            ema200 = self._ema(closes_4h, 200)
                            if ema200 is None or closes_4h[-1] <= ema200:
                                self._update_scan_row(active_symbol, "انعكاس صاعد 🟢", "مرفوض 🔴",
                                                      f"السعر {closes_4h[-1]:.8g} ليس أعلى من EMA 200 ({ema200:.8g})" if ema200 is not None else "تعذر حساب EMA 200",
                                                      f"{price:.8g}")
                                continue
                            self._ui(self.price_label.configure, text=f"${price:,.8f}".rstrip("0").rstrip("."))
                            self._update_scan_row(active_symbol, "انعكاس صاعد 🟢", "مؤكد 🟢",
                                                  "فرصة دخول مؤكدة؛ إرسال أمر شراء", f"{price:.8g}")
                            self._ui(self.signal_label.configure, text=f"{active_symbol}: انعكاس صاعد + EMA 200 🟢", text_color="green")
                            self._ui(self._set_status, f"تأكيد فرصة {active_symbol}؛ تنفيذ شراء {'تجريبي' if is_demo else 'حقيقي'}", "green")
                            self._buy_position(exchange, active_symbol, price, trade_budget, is_demo)
                            entered_or_exited = True
                            break
                    # Refresh candidate universe after a position closes, so the next scan is fresh.
                    if auto_scan and not self.current_trade and entered_or_exited:
                        candidates = []
                    time.sleep(8 if auto_scan else 3)
                except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as exc:
                    self._ui(self._set_status, f"مشكلة اتصال؛ إعادة المحاولة: {exc}", "#e67e22")
                    time.sleep(5)
                except Exception as exc:
                    self._ui(self._set_status, f"خطأ تداول: {exc}", "#e74c3c")
                    time.sleep(5)
        except Exception as exc:
            self._ui(messagebox.showerror, "تعذر تشغيل البوت", str(exc))
        finally:
            self.is_running = False
            self._ui(self.start_btn.configure, state="normal")
            self._ui(self.stop_btn.configure, state="disabled")
            self._ui(self._set_status, "الحالة: متوقف 🔴", "gray")

    def _buy_position(self, exchange, symbol, price, budget, is_demo):
        if self.current_trade:
            return
        if is_demo:
            # في الوضع التجريبي أيضاً يستخدم كامل الرصيد المتاح للصفقة.
            spend = self.demo_balance
            if spend < 5:
                self._ui(self._set_status, "الرصيد التجريبي غير كافٍ", "#e67e22")
                return
            qty = spend / price
            self.demo_balance -= spend
            self._ui(self.demo_balance_label.configure, text=f"{self.demo_balance:,.2f} USDT")
            order_id = "DEMO-" + datetime.now().strftime("%Y%m%d%H%M%S")
            entry = price
            cost = spend
        else:
            balance = exchange.fetch_balance()
            free_usdt = float(balance.get("free", {}).get("USDT", 0) or 0)
            # استثمار كامل الرصيد الحر المتاح بعد احتياطي صغير للرسوم.
            # هذا يتجاوز مبلغ الصفقة المحدد في الوضع الحقيقي.
            spend = max(0.0, free_usdt * 0.995)
            if spend < 5:
                self._ui(self._set_status, f"رصيد USDT الحر غير كافٍ: {free_usdt:.4f}", "#e67e22")
                return
            raw_qty = spend / price
            qty_str = exchange.amount_to_precision(symbol, raw_qty)
            qty = float(qty_str)
            if qty <= 0:
                raise RuntimeError("الكمية بعد التقريب تساوي صفراً.")
            order = exchange.create_market_buy_order(symbol, qty)
            qty = float(order.get("filled") or 0)
            if qty <= 0:
                # لا نفترض أن الأمر نجح إذا لم تتوفر كمية منفذة مؤكدة.
                raise RuntimeError(f"أمر الشراء {order.get('id')} لا يعرض كمية منفذة مؤكدة؛ تحقق من سجل الأوامر في MEXC قبل إعادة التشغيل.")
            entry = float(order.get("average") or order.get("price") or price)
            cost = float(order.get("cost") or (entry * qty))
            order_id = order.get("id")
        self.current_trade = {
            "symbol": symbol, "entry_price": entry, "amount": qty,
            "cost": cost, "order_id": order_id,
            "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "demo": is_demo
        }
        self._ui(self.close_btn.configure, state="normal", text="إغلاق الصفقة يدوياً")
        self._ui(self.trade_label.configure, text=f"تم فتح الصفقة: {symbol} | الكمية {qty:.8g}", text_color="white")
        self._ui(self._set_status, "الحالة: صفقة مفتوحة 🟢", "green")

    def _sell_position(self, exchange, price, is_demo, reason):
        trade = self.current_trade
        if not trade:
            return
        symbol = trade["symbol"]
        qty = float(trade["amount"])
        entry = float(trade["entry_price"])
        if is_demo:
            exit_price = price
            proceeds = qty * exit_price
            pnl = proceeds - float(trade["cost"])
            self.demo_balance += proceeds
            self._ui(self.demo_balance_label.configure, text=f"{self.demo_balance:,.2f} USDT")
        else:
            qty_str = exchange.amount_to_precision(symbol, qty)
            sell_qty = float(qty_str)
            if sell_qty <= 0:
                raise RuntimeError("كمية البيع بعد التقريب غير صالحة.")
            # بيع كمية الصفقة المسجلة فقط، لا كامل رصيد العملة.
            order = exchange.create_market_sell_order(symbol, sell_qty)
            filled = float(order.get("filled") or 0)
            if filled <= 0:
                raise RuntimeError(f"لم تؤكد المنصة تنفيذ أمر البيع {order.get('id')}. تحقق من سجل الأوامر.")
            exit_price = float(order.get("average") or order.get("price") or price)
            pnl = (exit_price - entry) * filled
            qty = filled
        self.total_pnl += pnl
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pnl_text = f"{pnl:+.4f}"
        self._ui(
            self.tree.insert, "", 0,
            values=(stamp, symbol, f"{entry:.8g}", f"{exit_price:.8g}", f"{qty:.8g}", pnl_text)
        )
        self._ui(self.pnl_label.configure, text=f"{self.total_pnl:+.4f} USDT",
                 text_color="green" if self.total_pnl >= 0 else "red")
        self._ui(self.trade_label.configure, text=f"أُغلقت الصفقة ({reason}). لا توجد صفقة نشطة.", text_color="gray")
        self._ui(self.close_btn.configure, state="disabled", text="إغلاق الصفقة يدوياً")
        self.current_trade = None
        self._ui(self._set_status, f"آخر إجراء: إغلاق بسبب {reason}", "gray")

    def save_settings(self, show_message=True):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            # لا نحفظ مفاتيح API في ملف نصي لتقليل مخاطر تسريبها.
            data = {
                "symbol": self.symbol_entry.get().strip().upper(),
                "amount": self.amount_entry.get().strip(),
                "demo_balance": self.demo_balance_entry.get().strip(),
                "demo": bool(self.mode_switch.get()),
                "auto_scan": bool(self.auto_scan_switch.get()),
                "scan_limit": self.scan_limit_entry.get().strip(),
                "min_quote_volume": self.min_volume_entry.get().strip(),
            }
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            if show_message:
                messagebox.showinfo("تم الحفظ", "تم حفظ إعدادات التداول غير السرية. أدخل مفاتيح API عند كل تشغيل.")
        except Exception as exc:
            if show_message:
                messagebox.showerror("فشل الحفظ", str(exc))

    def _load_settings(self):
        try:
            if not SETTINGS_FILE.exists():
                return
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.symbol_entry.delete(0, "end")
            self.symbol_entry.insert(0, data.get("symbol", "BTC/USDT"))
            self.amount_entry.delete(0, "end")
            self.amount_entry.insert(0, data.get("amount", "10"))
            self.demo_balance_entry.delete(0, "end")
            saved_demo_balance = data.get("demo_balance", "1000")
            self.demo_balance_entry.insert(0, str(saved_demo_balance))
            try:
                self.demo_balance = max(0.0, float(saved_demo_balance))
                self.demo_balance_label.configure(text=f"{self.demo_balance:,.2f} USDT")
            except (TypeError, ValueError):
                self.demo_balance = 1000.0
            self.auto_scan_switch.select() if data.get("auto_scan", True) else self.auto_scan_switch.deselect()
            self.scan_limit_entry.delete(0, "end")
            self.scan_limit_entry.insert(0, str(data.get("scan_limit", "12")))
            self.min_volume_entry.delete(0, "end")
            self.min_volume_entry.insert(0, str(data.get("min_quote_volume", "100000")))
            if data.get("demo", True):
                self.mode_switch.select()
            else:
                self.mode_switch.deselect()
                self.demo_frame.pack_forget()
        except Exception:
            pass

    def _on_close(self):
        if self.is_running:
            if not messagebox.askyesno("إغلاق التطبيق", "البوت يعمل. إيقافه وإغلاق الواجهة؟ قد تبقى أي صفقة مفتوحة على المنصة."):
                return
            self.is_running = False
        self.closing = True
        self.destroy()


if __name__ == "__main__":
    app = MexcTradingApp()
    app.mainloop()
