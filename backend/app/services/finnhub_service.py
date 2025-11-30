from datetime import date, timedelta
from typing import Optional, Dict
import httpx
from ..config import get_settings


class FinnhubService:
    """
    Finnhub API 服務
    主要用於取得 earnings calendar 的 hour 欄位（bmo/amc/dmh）

    注意：Finnhub 的 earnings calendar 只有約 1 個月的歷史資料
    超過 1 個月的資料需要 fallback 到 FMP transcript 方式
    """

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.finnhub_base_url
        self.api_key = self.settings.finnhub_api_key
        # 快取 earnings time 資料（避免重複 API 呼叫）
        self._earnings_time_cache: Dict[str, Optional[str]] = {}

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        """發送 GET 請求到 Finnhub API"""
        if params is None:
            params = {}
        params["token"] = self.api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.base_url}/{endpoint}"
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def get_earnings_calendar(
        self, from_date: date, to_date: date
    ) -> list:
        """
        取得指定日期範圍的 earnings calendar

        回傳格式：
        {
            "earningsCalendar": [
                {
                    "date": "2025-11-24",
                    "epsActual": 2.15,
                    "epsEstimate": 2.08,
                    "hour": "amc",  # bmo/amc/dmh 或空字串
                    "quarter": 1,
                    "revenueActual": 2073000000,
                    "revenueEstimate": 2046940000,
                    "symbol": "KEYS",
                    "year": 2025
                }
            ]
        }
        """
        try:
            data = await self._get(
                "calendar/earnings",
                {
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                }
            )
            return data.get("earningsCalendar", [])
        except Exception:
            return []

    async def get_earnings_time(
        self, symbol: str, earnings_date: date
    ) -> Optional[str]:
        """
        取得特定股票在特定日期的 earnings time (BMO/AMC)

        優先使用快取，若無則查詢 Finnhub API
        只有在 earnings_date 距今不超過 30 天時才查詢

        Returns:
            "BMO" - Before Market Open (盤前)
            "AMC" - After Market Close (盤後)
            None - 無資料或超出查詢範圍
        """
        # 檢查快取
        cache_key = f"{symbol}_{earnings_date.isoformat()}"
        if cache_key in self._earnings_time_cache:
            return self._earnings_time_cache[cache_key]

        # 檢查日期是否在 Finnhub 可查詢範圍內（約 30 天）
        today = date.today()
        days_diff = (today - earnings_date).days
        if days_diff > 30:
            # 超過 30 天，Finnhub 可能沒資料
            self._earnings_time_cache[cache_key] = None
            return None

        # 查詢 Finnhub API
        try:
            # 查詢該日期前後 1 天的範圍，確保能找到
            from_date = earnings_date - timedelta(days=1)
            to_date = earnings_date + timedelta(days=1)

            earnings_list = await self.get_earnings_calendar(from_date, to_date)

            # 找到對應的 symbol 和日期
            for earning in earnings_list:
                if earning.get("symbol") == symbol:
                    earning_date_str = earning.get("date", "")
                    if earning_date_str == earnings_date.isoformat():
                        hour = earning.get("hour", "")
                        result = self._map_hour_to_time(hour)
                        self._earnings_time_cache[cache_key] = result
                        return result

            # 找不到對應資料
            self._earnings_time_cache[cache_key] = None
            return None

        except Exception:
            self._earnings_time_cache[cache_key] = None
            return None

    async def batch_get_earnings_time(
        self, from_date: date, to_date: date
    ) -> Dict[str, str]:
        """
        批次取得指定日期範圍內所有股票的 earnings time

        Returns:
            Dict[str, str] - key 為 "SYMBOL_YYYY-MM-DD"，value 為 "BMO" 或 "AMC"
        """
        result = {}

        # 檢查日期是否在 Finnhub 可查詢範圍內
        today = date.today()
        days_diff = (today - from_date).days
        if days_diff > 30:
            # 整個範圍都超過 30 天，直接返回空結果
            return result

        try:
            earnings_list = await self.get_earnings_calendar(from_date, to_date)

            for earning in earnings_list:
                symbol = earning.get("symbol", "")
                earning_date = earning.get("date", "")
                hour = earning.get("hour", "")

                if symbol and earning_date and hour:
                    time = self._map_hour_to_time(hour)
                    if time:
                        cache_key = f"{symbol}_{earning_date}"
                        result[cache_key] = time
                        # 同時更新快取
                        self._earnings_time_cache[cache_key] = time

            return result

        except Exception:
            return result

    def _map_hour_to_time(self, hour: str) -> Optional[str]:
        """
        將 Finnhub 的 hour 欄位轉換為 BMO/AMC

        Finnhub hour 欄位：
        - "bmo" -> BMO (Before Market Open)
        - "amc" -> AMC (After Market Close)
        - "dmh" -> None (During Market Hours，不確定)
        - "" -> None (無資料)
        """
        hour_lower = hour.lower() if hour else ""

        if hour_lower == "bmo":
            return "BMO"
        elif hour_lower == "amc":
            return "AMC"
        else:
            # dmh 或空字串不確定，返回 None
            return None
