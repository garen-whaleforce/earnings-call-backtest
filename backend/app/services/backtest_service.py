from datetime import date, timedelta
from typing import Optional, List, Dict
from .fmp_service import FMPService
from .finnhub_service import FinnhubService
from ..models import BacktestResult, BacktestRequest
from ..config import get_settings


class BacktestService:
    def __init__(self):
        self.fmp = FMPService()
        self.finnhub = FinnhubService()
        self.settings = get_settings()

    async def run_backtest(self, request: BacktestRequest) -> List[BacktestResult]:
        """
        執行回測：
        1. 從 earnings-calendar 取得指定日期範圍的所有 earnings events
        2. 取得公司 profile 並篩選市值
        3. 根據盤前/盤後判斷正確的價格比較區間
        4. 計算價格變動百分比，只返回 >10% 的股票

        價格比較邏輯：
        - 盤前 (BMO): 前一天收盤 vs 當天收盤
        - 盤後 (AMC): 當天收盤 vs 隔天收盤
        """
        results = []

        # 1. 從 earnings-calendar 取得所有 earnings events
        earnings_events = await self.fmp.get_earnings_calendar(
            request.start_date, request.end_date
        )

        if not earnings_events:
            return results

        # 1.5 先取得大市值股票清單（用於快速過濾）
        large_cap_symbols = await self.fmp.get_large_cap_symbols_set(request.min_market_cap)

        # 2. 過濾 earnings events，只保留大市值股票
        if large_cap_symbols:
            filtered_events = [e for e in earnings_events if e.symbol in large_cap_symbols]
        else:
            # 如果 screener 失敗，使用所有 events（後續會用 profile 過濾）
            filtered_events = earnings_events

        # 去重 earnings events（同一股票同一天只保留一筆）
        seen_events = set()
        deduplicated_events = []
        for e in filtered_events:
            event_key = f"{e.symbol}_{e.earnings_date.isoformat()}"
            if event_key not in seen_events:
                seen_events.add(event_key)
                deduplicated_events.append(e)
        filtered_events = deduplicated_events

        unique_symbols = list(set(e.symbol for e in filtered_events))

        # 取得 profiles（移除 200 限制，因為已經預先過濾過）
        all_profiles = await self.fmp.batch_get_profiles(unique_symbols)

        threshold = self.settings.price_change_threshold  # 10%

        # 2.5 預先批次取得 Finnhub earnings time（僅限 30 天內的資料）
        finnhub_times = await self._get_finnhub_earnings_times(
            request.start_date, request.end_date
        )

        # 3. 處理每個 earnings event（使用過濾後的列表）
        for event in filtered_events:
            profile = all_profiles.get(event.symbol)

            # 篩選市值
            if not profile or profile.market_cap < request.min_market_cap:
                continue

            # 先取得 earnings date 附近的價格資料（用於判斷盤前/盤後和計算漲跌）
            try:
                prices = await self.fmp.get_prices_around_earnings(
                    event.symbol, event.earnings_date
                )
            except Exception:
                continue

            if not prices or len(prices) < 2:
                continue

            # 取得 earnings time（優先使用 Finnhub，再 fallback 到 FMP transcript）
            earnings_time_value = await self._get_earnings_time(
                event.symbol, event.earnings_date, finnhub_times
            )

            # 判斷盤前/盤後並取得正確的比較價格
            earnings_time, price_before, price_after = self._determine_prices(
                event.earnings_date, prices, earnings_time_value
            )

            if not price_before or not price_after:
                continue

            # 計算價格變動百分比
            price_change_pct = (price_after.close - price_before.close) / price_before.close

            # 只保留變動 > threshold 或 < -threshold 的
            if abs(price_change_pct) < threshold:
                continue

            results.append(
                BacktestResult(
                    symbol=event.symbol,
                    company_name=profile.company_name,
                    market_cap=profile.market_cap,
                    earnings_date=event.earnings_date,
                    earnings_time=earnings_time,
                    price_before=price_before.close,
                    price_after=price_after.close,
                    price_change_pct=round(price_change_pct, 4),
                    date_before=price_before.date,
                    date_after=price_after.date,
                )
            )

        # 按價格變動百分比排序（絕對值大的在前）
        results.sort(key=lambda x: abs(x.price_change_pct), reverse=True)

        return results

    def _determine_prices(self, earnings_date: date, prices: list, transcript_time: Optional[str] = None):
        """
        根據價格資料判斷盤前/盤後，並返回正確的比較價格

        判斷邏輯：
        - 只使用 transcript_time（從 earnings call transcript 判斷）
        - 如果 transcript_time 為 None，則跳過該筆資料

        Returns:
            (earnings_time, price_before, price_after)
        """
        # 將價格按日期排序
        sorted_prices = sorted(prices, key=lambda x: x.date if isinstance(x.date, date) else date.fromisoformat(str(x.date)))

        # 建立日期到價格的映射
        price_map = {}
        for p in sorted_prices:
            p_date = p.date if isinstance(p.date, date) else date.fromisoformat(str(p.date))
            price_map[p_date] = p

        # 找到 earnings_date 當天或最近的交易日
        earnings_day_price = None
        day_before_price = None
        day_after_price = None

        # 找 earnings_date 當天的價格
        if earnings_date in price_map:
            earnings_day_price = price_map[earnings_date]

        # 找 earnings_date 之前最近的交易日
        for i in range(1, 6):
            check_date = earnings_date - timedelta(days=i)
            if check_date in price_map:
                day_before_price = price_map[check_date]
                break

        # 找 earnings_date 之後最近的交易日
        for i in range(1, 6):
            check_date = earnings_date + timedelta(days=i)
            if check_date in price_map:
                day_after_price = price_map[check_date]
                break

        # 如果 earnings_date 當天沒有交易（週末/假日），使用之後最近的交易日
        if not earnings_day_price and day_after_price:
            # earnings_date 是非交易日
            # 只有在有 transcript_time 時才處理
            if transcript_time:
                return (transcript_time, day_before_price, day_after_price)
            return (None, None, None)

        if not earnings_day_price or not day_before_price:
            # 資料不足
            return (None, None, None)

        # 只使用 transcript_time（從 transcript 判斷的結果）
        # 如果沒有 transcript_time，跳過該筆資料
        if not transcript_time:
            return (None, None, None)

        if transcript_time == "BMO":
            # 盤前發佈 (BMO)：前一天收盤 vs 當天收盤
            return ("BMO", day_before_price, earnings_day_price)
        else:
            # 盤後發佈 (AMC)：當天收盤 vs 隔天收盤
            if day_after_price:
                return ("AMC", earnings_day_price, day_after_price)
            else:
                return (None, None, None)

    async def get_single_stock_backtest(
        self, symbol: str, earnings_date: date
    ) -> Optional[BacktestResult]:
        """取得單一股票在特定 earnings date 的回測結果"""
        profile = await self.fmp.get_company_profile(symbol)
        if not profile:
            return None

        price_before = await self.fmp.get_price_before_earnings(symbol, earnings_date)
        if not price_before:
            return None

        price_after = await self.fmp.get_next_trading_day_price(symbol, earnings_date)
        if not price_after:
            return None

        price_change_pct = (price_after.close - price_before.close) / price_before.close

        return BacktestResult(
            symbol=symbol,
            company_name=profile.company_name,
            market_cap=profile.market_cap,
            earnings_date=earnings_date,
            price_before=price_before.close,
            price_after=price_after.close,
            price_change_pct=round(price_change_pct, 4),
            date_before=price_before.date,
            date_after=price_after.date,
        )

    async def search_stock_earnings(
        self, symbol: str, start_date: date, end_date: date
    ) -> List[BacktestResult]:
        """
        查詢單一股票在指定時間範圍內的所有 earnings call 資料
        返回：earnings call 時間（盤前/盤後）、發佈前股價、發佈後股價、漲跌幅

        注意：對於歷史資料（超過 30 天），可能無法準確判斷盤前/盤後，
        此時會使用「當天收盤 vs 隔天收盤」作為預設比較方式。
        """
        results = []

        # 1. 取得公司 profile
        profile = await self.fmp.get_company_profile(symbol)
        if not profile:
            return results

        # 2. 使用專門的歷史 earnings API 取得該股票的所有 earnings events
        stock_events = await self.fmp.get_stock_earnings_history(symbol, start_date, end_date)

        if not stock_events:
            return results

        # 2.5 預先批次取得 Finnhub earnings time（僅限 30 天內的資料）
        finnhub_times = await self._get_finnhub_earnings_times(start_date, end_date)

        # 3. 處理每個 earnings event
        for event in stock_events:
            try:
                prices = await self.fmp.get_prices_around_earnings(
                    event.symbol, event.earnings_date
                )
            except Exception:
                continue

            if not prices or len(prices) < 2:
                continue

            # 取得 earnings time（優先使用 Finnhub，再 fallback 到 FMP transcript）
            earnings_time_value = await self._get_earnings_time(
                event.symbol, event.earnings_date, finnhub_times
            )

            # 判斷盤前/盤後並取得正確的比較價格
            earnings_time, price_before, price_after = self._determine_prices(
                event.earnings_date, prices, earnings_time_value
            )

            # 對於股票歷史查詢，如果無法判斷盤前/盤後，使用 fallback 邏輯
            # 預設使用「當天收盤 vs 隔天收盤」（假設盤後發佈）
            if not price_before or not price_after:
                earnings_time, price_before, price_after = self._determine_prices_fallback(
                    event.earnings_date, prices
                )

            if not price_before or not price_after:
                continue

            # 計算價格變動百分比
            price_change_pct = (price_after.close - price_before.close) / price_before.close

            results.append(
                BacktestResult(
                    symbol=event.symbol,
                    company_name=profile.company_name,
                    market_cap=profile.market_cap,
                    earnings_date=event.earnings_date,
                    earnings_time=earnings_time,
                    price_before=price_before.close,
                    price_after=price_after.close,
                    price_change_pct=round(price_change_pct, 4),
                    date_before=price_before.date,
                    date_after=price_after.date,
                )
            )

        # 按日期排序（最新的在前）
        results.sort(key=lambda x: x.earnings_date, reverse=True)

        return results

    def _determine_prices_fallback(self, earnings_date: date, prices: list):
        """
        當無法判斷盤前/盤後時的 fallback 邏輯
        使用「當天收盤 vs 隔天收盤」作為預設比較方式

        Returns:
            (earnings_time, price_before, price_after)
            earnings_time 為 None 表示無法判斷
        """
        # 將價格按日期排序
        sorted_prices = sorted(prices, key=lambda x: x.date if isinstance(x.date, date) else date.fromisoformat(str(x.date)))

        # 建立日期到價格的映射
        price_map = {}
        for p in sorted_prices:
            p_date = p.date if isinstance(p.date, date) else date.fromisoformat(str(p.date))
            price_map[p_date] = p

        # 找 earnings_date 當天的價格
        earnings_day_price = None
        if earnings_date in price_map:
            earnings_day_price = price_map[earnings_date]

        # 找 earnings_date 之後最近的交易日
        day_after_price = None
        for i in range(1, 6):
            check_date = earnings_date + timedelta(days=i)
            if check_date in price_map:
                day_after_price = price_map[check_date]
                break

        # 如果 earnings_date 當天沒有交易，找之前最近的交易日
        if not earnings_day_price:
            for i in range(1, 6):
                check_date = earnings_date - timedelta(days=i)
                if check_date in price_map:
                    earnings_day_price = price_map[check_date]
                    break

        if earnings_day_price and day_after_price:
            # 使用當天收盤 vs 隔天收盤，earnings_time 設為 None
            return (None, earnings_day_price, day_after_price)

        return (None, None, None)

    async def _get_finnhub_earnings_times(
        self, start_date: date, end_date: date
    ) -> Dict[str, str]:
        """
        批次取得指定日期範圍內的 Finnhub earnings time 資料

        只會查詢距今 30 天內的資料（Finnhub 限制）
        """
        today = date.today()
        finnhub_cutoff = today - timedelta(days=30)

        # 調整查詢範圍，只查詢 Finnhub 可用的日期
        query_start = max(start_date, finnhub_cutoff)
        query_end = min(end_date, today)

        if query_start > query_end:
            # 整個範圍都超出 Finnhub 可查詢範圍
            return {}

        return await self.finnhub.batch_get_earnings_time(query_start, query_end)

    async def _get_earnings_time(
        self,
        symbol: str,
        earnings_date: date,
        finnhub_times: Dict[str, str]
    ) -> Optional[str]:
        """
        取得特定股票在特定日期的 earnings time

        優先順序：
        1. Finnhub（僅限 30 天內的資料，直接從 finnhub_times dict 取得）
        2. FMP transcript（用於歷史資料）

        Returns:
            "BMO" - Before Market Open (盤前)
            "AMC" - After Market Close (盤後)
            None - 無法判斷
        """
        # 1. 先檢查 Finnhub 預先批次取得的資料
        cache_key = f"{symbol}_{earnings_date.isoformat()}"
        if cache_key in finnhub_times:
            return finnhub_times[cache_key]

        # 2. 檢查是否在 Finnhub 可查詢範圍內但沒有資料
        today = date.today()
        days_diff = (today - earnings_date).days
        if days_diff <= 30:
            # 在範圍內但 Finnhub 沒有資料，嘗試單獨查詢一次
            finnhub_time = await self.finnhub.get_earnings_time(symbol, earnings_date)
            if finnhub_time:
                return finnhub_time

        # 3. Fallback 到 FMP transcript 方式
        return await self.fmp.get_earnings_time_from_transcript(symbol, earnings_date)
