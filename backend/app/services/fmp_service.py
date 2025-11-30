import httpx
import asyncio
from datetime import date, timedelta
from typing import Optional, Union, List, Dict, Set
from ..config import get_settings
from ..models import EarningsEvent, StockPrice, CompanyProfile


class FMPService:
    # 類別級別的大市值股票快取
    _large_cap_cache: Dict[float, Set[str]] = {}

    def __init__(self):
        self.settings = get_settings()
        # 使用新的 stable API
        self.base_url = "https://financialmodelingprep.com/stable"
        self.api_key = self.settings.fmp_api_key

    async def get_large_cap_symbols_set(self, min_market_cap: float) -> Set[str]:
        """取得大市值股票的 symbol 集合（用於快速過濾）"""
        # 檢查快取
        if min_market_cap in self._large_cap_cache:
            return self._large_cap_cache[min_market_cap]

        symbols = set()
        try:
            data = await self._get(
                "stock-screener",
                {
                    "marketCapMoreThan": int(min_market_cap),
                    "isActivelyTrading": True,
                    "exchange": "NYSE,NASDAQ,AMEX",
                    "limit": 5000,
                },
            )
            symbols = {item["symbol"] for item in data if item.get("symbol")}
            # 快取結果
            self._large_cap_cache[min_market_cap] = symbols
        except Exception:
            pass

        return symbols

    async def _get(self, endpoint: str, params: dict = None) -> Union[dict, list]:
        """Make GET request to FMP API"""
        if params is None:
            params = {}
        params["apikey"] = self.api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/{endpoint}", params=params)
            response.raise_for_status()
            return response.json()

    async def get_earnings_calendar(
        self, from_date: date, to_date: date
    ) -> List[EarningsEvent]:
        """從 earnings-calendar API 取得指定日期範圍的所有 earnings events"""
        events = []

        try:
            data = await self._get(
                "earnings-calendar",
                {
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                },
            )

            if not isinstance(data, list):
                return events

            for item in data:
                symbol = item.get("symbol")
                earnings_date_str = item.get("date")

                if not symbol or not earnings_date_str:
                    continue

                # 只處理純美股（排除其他交易所和 ADR）
                # 排除帶有 "." 的（非美股交易所）
                if "." in symbol:
                    continue
                # 排除 ADR（常見後綴模式）
                # 常見 ADR 後綴: Y, F, CY, GF, HY, TY, PY, LY, EY, AY, UY
                adr_suffixes = ('ADR', 'ADS', 'CY', 'GF', 'HY', 'TY', 'PY', 'LY', 'EY', 'AY', 'UY')
                if symbol.endswith(adr_suffixes):
                    continue
                # 排除單字母 Y 或 F 結尾的 ADR（如 BABAF, TCEHY）
                if len(symbol) > 3 and symbol[-1] in ('Y', 'F') and symbol[:-1].isalpha():
                    continue

                try:
                    earnings_date = date.fromisoformat(earnings_date_str)
                except ValueError:
                    continue

                events.append(
                    EarningsEvent(
                        symbol=symbol,
                        company_name=symbol,
                        earnings_date=earnings_date,
                        fiscal_quarter=None,
                        fiscal_year=None,
                        eps_actual=item.get("epsActual"),
                        eps_estimate=item.get("epsEstimated"),
                        revenue_actual=item.get("revenueActual"),
                        revenue_estimate=item.get("revenueEstimated"),
                    )
                )
        except Exception:
            pass

        return events

    async def get_earnings_from_income_statements(
        self, symbols: List[str], from_date: date, to_date: date
    ) -> List[EarningsEvent]:
        """從 income-statement 取得 earnings 資料（備用方法）"""
        events = []

        for symbol in symbols:
            try:
                data = await self._get(
                    "income-statement",
                    {"symbol": symbol, "period": "quarter", "limit": 8},
                )

                for item in data:
                    filing_date_str = item.get("filingDate")
                    if not filing_date_str:
                        continue

                    filing_date = date.fromisoformat(filing_date_str)

                    # 篩選日期範圍
                    if from_date <= filing_date <= to_date:
                        events.append(
                            EarningsEvent(
                                symbol=symbol,
                                company_name=symbol,
                                earnings_date=filing_date,
                                fiscal_quarter=item.get("period"),
                                fiscal_year=int(item.get("fiscalYear", 0)) if item.get("fiscalYear") else None,
                                eps_actual=item.get("epsDiluted"),
                                revenue_actual=item.get("revenue"),
                            )
                        )
            except Exception:
                # 跳過無法取得資料的股票
                continue

        return events

    async def get_large_cap_symbols(self, min_market_cap: float = 1_000_000_000) -> List[str]:
        """取得市值大於指定值的股票列表"""
        # 使用 stock screener 或 stock list
        try:
            data = await self._get(
                "stock-screener",
                {"marketCapMoreThan": int(min_market_cap), "limit": 500},
            )
            return [item["symbol"] for item in data if item.get("symbol")]
        except Exception:
            # 如果 screener 不可用，使用預設的大型股列表
            return [
                "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
                "UNH", "JNJ", "V", "XOM", "JPM", "WMT", "MA", "PG", "HD", "CVX",
                "MRK", "ABBV", "LLY", "PEP", "KO", "COST", "AVGO", "TMO", "MCD",
                "CSCO", "ACN", "ABT", "DHR", "ADBE", "CRM", "NKE", "TXN", "AMD",
                "NEE", "PM", "UNP", "HON", "QCOM", "LOW", "ORCL", "INTC", "IBM",
                "KEYS", "SNOW", "CRWD", "ZS", "PANW", "DDOG", "NET", "MDB", "TEAM"
            ]

    async def get_company_profile(self, symbol: str) -> Optional[CompanyProfile]:
        """取得公司資料，包含市值"""
        data = await self._get("profile", {"symbol": symbol})

        if not data:
            return None

        profile = data[0]
        return CompanyProfile(
            symbol=symbol,
            company_name=profile.get("companyName", ""),
            market_cap=profile.get("marketCap", 0),
            sector=profile.get("sector"),
            industry=profile.get("industry"),
        )

    async def get_historical_price(
        self, symbol: str, target_date: date
    ) -> Optional[StockPrice]:
        """取得指定日期的股價（如果該日非交易日，會找最近的交易日）"""
        from_date = target_date - timedelta(days=5)
        to_date = target_date + timedelta(days=5)

        data = await self._get(
            "historical-price-eod/full",
            {
                "symbol": symbol,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
        )

        if not data:
            return None

        # 新 API 直接返回 list
        historical = data if isinstance(data, list) else data.get("historical", [])
        if not historical:
            return None

        # 按日期排序（升序）
        historical_sorted = sorted(historical, key=lambda x: x["date"])

        # 找到 target_date 當天或之後最近的交易日
        closest_price = None
        for price_data in historical_sorted:
            price_date = date.fromisoformat(price_data["date"])
            if price_date >= target_date:
                closest_price = price_data
                break

        # 如果找不到之後的交易日，就取最後一天
        if not closest_price:
            closest_price = historical_sorted[-1]

        return StockPrice(
            symbol=symbol,
            date=closest_price["date"],
            open=closest_price["open"],
            high=closest_price["high"],
            low=closest_price["low"],
            close=closest_price["close"],
            volume=closest_price["volume"],
        )

    async def get_next_trading_day_price(
        self, symbol: str, earnings_date: date
    ) -> Optional[StockPrice]:
        """取得 Earnings Call 發佈後最近一個交易日的收盤價"""
        # Earnings 通常在盤後發佈，所以我們要找「下一個」交易日
        next_day = earnings_date + timedelta(days=1)
        return await self.get_historical_price(symbol, next_day)

    async def get_price_before_earnings(
        self, symbol: str, earnings_date: date
    ) -> Optional[StockPrice]:
        """取得 Earnings Call 發佈前最近一個交易日的收盤價"""
        # 找 earnings_date 當天或之前的交易日
        from_date = earnings_date - timedelta(days=5)
        to_date = earnings_date

        data = await self._get(
            "historical-price-eod/full",
            {
                "symbol": symbol,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
        )

        if not data:
            return None

        historical = data if isinstance(data, list) else data.get("historical", [])
        if not historical:
            return None

        # 按日期排序（降序），取最近的
        historical_sorted = sorted(historical, key=lambda x: x["date"], reverse=True)

        # 取 earnings_date 當天或之前最近的交易日
        for price_data in historical_sorted:
            price_date = date.fromisoformat(price_data["date"])
            if price_date <= earnings_date:
                return StockPrice(
                    symbol=symbol,
                    date=price_data["date"],
                    open=price_data["open"],
                    high=price_data["high"],
                    low=price_data["low"],
                    close=price_data["close"],
                    volume=price_data["volume"],
                )

        return None

    async def batch_get_profiles(self, symbols: List[str]) -> Dict[str, CompanyProfile]:
        """批次取得多個公司的 profile（使用並行處理加速）"""
        profiles = {}

        async def fetch_profile(symbol: str) -> tuple:
            try:
                profile = await self.get_company_profile(symbol)
                return (symbol, profile)
            except Exception:
                return (symbol, None)

        # 使用 semaphore 限制並行數量，避免 API 限速
        semaphore = asyncio.Semaphore(10)

        async def fetch_with_limit(symbol: str) -> tuple:
            async with semaphore:
                return await fetch_profile(symbol)

        # 並行取得所有 profiles
        tasks = [fetch_with_limit(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks)

        for symbol, profile in results:
            if profile:
                profiles[symbol] = profile

        return profiles

    async def get_prices_around_earnings(
        self, symbol: str, earnings_date: date
    ) -> List[StockPrice]:
        """
        取得 earnings date 前後的股價資料（用於判斷盤前/盤後和計算漲跌）
        返回 earnings_date 前 5 天到後 5 天的所有交易日價格
        """
        from_date = earnings_date - timedelta(days=7)
        to_date = earnings_date + timedelta(days=7)

        data = await self._get(
            "historical-price-eod/full",
            {
                "symbol": symbol,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
        )

        if not data:
            return []

        historical = data if isinstance(data, list) else data.get("historical", [])
        if not historical:
            return []

        prices = []
        for price_data in historical:
            prices.append(
                StockPrice(
                    symbol=symbol,
                    date=price_data["date"],
                    open=price_data["open"],
                    high=price_data["high"],
                    low=price_data["low"],
                    close=price_data["close"],
                    volume=price_data["volume"],
                )
            )

        return prices

    async def get_stock_earnings_history(
        self, symbol: str, from_date: date, to_date: date
    ) -> List[EarningsEvent]:
        """
        取得特定股票在指定日期範圍內的所有歷史 earnings events
        使用 earnings-calendar API 取得真正的 earnings call 發佈日期
        （而非 SEC 10-Q filing 日期）

        注意：
        - earnings-calendar API 每次最多回傳 4000 筆且無法按 symbol 過濾
        - API 有 90 天日期範圍限制
        - 但當日期範圍太大時（如 earnings season），4000 筆會被截斷
        - 我們需要將查詢範圍分成更小的區塊（3 天），確保不會遺漏資料
        - 例如：5/1~5/8（7天）回傳 4000 筆，導致 AAPL 等大公司被截斷
        """
        events = []
        seen_dates = set()  # 避免重複
        # 使用 3 天區塊避免 4000 筆限制導致資料截斷
        # earnings season 高峰期（如 5/1 前後）每天有 1000+ 家公司發佈
        # 測試顯示 7 天區塊在 earnings season 仍會達到 4000 筆上限
        # 例如：5/1~5/8 回傳 4000 筆，導致 AAPL 等大公司被截斷
        MAX_DAYS = 3

        try:
            # 將日期範圍分成最多 3 天的區塊查詢
            current_start = from_date
            while current_start <= to_date:
                # 計算區塊結束日期（最多 7 天後或 to_date）
                chunk_end = min(current_start + timedelta(days=MAX_DAYS), to_date)

                data = await self._get(
                    "earnings-calendar",
                    {
                        "from": current_start.isoformat(),
                        "to": chunk_end.isoformat(),
                    }
                )

                if isinstance(data, list):
                    for item in data:
                        # 只處理目標 symbol
                        if item.get("symbol") != symbol:
                            continue

                        earnings_date_str = item.get("date")
                        if not earnings_date_str:
                            continue

                        try:
                            earnings_date = date.fromisoformat(earnings_date_str)
                        except ValueError:
                            continue

                        # 避免重複
                        if earnings_date in seen_dates:
                            continue
                        seen_dates.add(earnings_date)

                        events.append(
                            EarningsEvent(
                                symbol=symbol,
                                company_name=symbol,
                                earnings_date=earnings_date,
                                fiscal_quarter=None,
                                fiscal_year=None,
                                eps_actual=item.get("epsActual"),
                                eps_estimate=item.get("epsEstimated"),
                                revenue_actual=item.get("revenueActual"),
                                revenue_estimate=item.get("revenueEstimated"),
                            )
                        )

                # 移到下一個區塊（下一天開始）
                current_start = chunk_end + timedelta(days=1)

        except Exception:
            pass

        # 按日期排序（最新的在前）
        events.sort(key=lambda x: x.earnings_date, reverse=True)
        return events

    async def get_earnings_time_from_transcript(self, symbol: str, earnings_date: date) -> Optional[str]:
        """
        從 earnings call transcript 判斷是盤前還是盤後發佈
        回傳: 'BMO' (Before Market Open), 'AMC' (After Market Close), 或 None
        """
        # 根據 earnings_date 推算可能的季度（嘗試多個季度）
        year = earnings_date.year
        month = earnings_date.month

        # 根據月份推算最可能的季度
        # Q1: 1-3月報告通常在 4-5 月發佈
        # Q2: 4-6月報告通常在 7-8 月發佈
        # Q3: 7-9月報告通常在 10-11 月發佈
        # Q4: 10-12月報告通常在 1-2 月發佈（隔年）
        possible_quarters = []
        if month in (1, 2):
            possible_quarters = [(year - 1, 4), (year, 1)]  # 去年 Q4 或今年 Q1
        elif month in (4, 5):
            possible_quarters = [(year, 1), (year, 2)]  # Q1 或 Q2
        elif month in (7, 8):
            possible_quarters = [(year, 2), (year, 3)]  # Q2 或 Q3
        elif month in (10, 11):
            possible_quarters = [(year, 3), (year, 4)]  # Q3 或 Q4
        else:
            # 其他月份，嘗試最近的季度
            quarter = (month - 1) // 3 + 1
            possible_quarters = [(year, quarter), (year, quarter - 1 if quarter > 1 else 4)]

        for yr, qtr in possible_quarters:
            try:
                data = await self._get(
                    "earning-call-transcript",
                    {"symbol": symbol, "year": yr, "quarter": qtr},
                )

                if not data or len(data) == 0:
                    continue

                content = data[0].get("content", "").lower()

                # 從 transcript 內容判斷時間
                if "good morning" in content[:500]:
                    return "BMO"  # Before Market Open (盤前)
                elif "good afternoon" in content[:500] or "good evening" in content[:500]:
                    return "AMC"  # After Market Close (盤後)
            except Exception:
                continue

        return None
