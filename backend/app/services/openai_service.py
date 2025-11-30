from typing import List
from openai import AsyncOpenAI
from ..config import get_settings
from ..models import BacktestResult, ValidationResult


class OpenAIService:
    def __init__(self):
        self.settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=self.settings.openai_api_key,
        )
        self.model = "gpt-4o-mini"  # 使用較便宜的模型

    async def validate_backtest_result(
        self, result: BacktestResult
    ) -> ValidationResult:
        """
        使用 Azure OpenAI 驗證回測結果的正確性
        - 檢查價格區間計算是否正確
        - 檢查日期邏輯是否合理
        """
        prompt = f"""
你是一個金融數據驗證助手。請驗證以下 Earnings Call 回測數據的正確性：

股票代碼: {result.symbol}
公司名稱: {result.company_name}
市值: ${result.market_cap:,.0f}
Earnings 發佈日: {result.earnings_date}
交易日期: {result.trading_date}
收盤價: ${result.close_price:.2f}
+10% 價格: ${result.price_plus_10:.2f}
-10% 價格: ${result.price_minus_10:.2f}

請驗證：
1. +10% 價格是否等於 收盤價 × 1.10
2. -10% 價格是否等於 收盤價 × 0.90
3. 交易日期是否在 Earnings 發佈日之後（或同一天盤後發佈的情況）
4. 市值是否大於 1B USD

請以 JSON 格式回覆：
{{
    "is_valid": true/false,
    "issues": ["問題1", "問題2"] 或 [],
    "calculations": {{
        "expected_plus_10": 計算值,
        "expected_minus_10": 計算值,
        "plus_10_correct": true/false,
        "minus_10_correct": true/false
    }}
}}
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一個精確的金融數據驗證助手，專門檢查計算結果的正確性。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content

        import json

        try:
            validation_data = json.loads(content)
            is_valid = validation_data.get("is_valid", False)
            issues = validation_data.get("issues", [])

            return ValidationResult(
                symbol=result.symbol,
                is_valid=is_valid,
                message="驗證通過" if is_valid else f"發現問題: {', '.join(issues)}",
                details=validation_data,
            )
        except json.JSONDecodeError:
            return ValidationResult(
                symbol=result.symbol,
                is_valid=False,
                message="無法解析 AI 回應",
                details={"raw_response": content},
            )

    async def batch_validate(
        self, results: List[BacktestResult]
    ) -> List[ValidationResult]:
        """批次驗證多個回測結果"""
        validations = []
        for result in results:
            validation = await self.validate_backtest_result(result)
            validations.append(validation)
        return validations

    async def analyze_earnings_pattern(
        self, results: List[BacktestResult]
    ) -> dict:
        """分析 earnings 模式"""
        if not results:
            return {"error": "沒有數據可分析"}

        summary = "\n".join(
            [
                f"- {r.symbol}: 收盤${r.close_price:.2f}, EPS驚喜:{r.eps_surprise:.2%}{'↑' if r.eps_surprise and r.eps_surprise > 0 else '↓'}"
                for r in results[:20]  # 限制數量避免 token 過多
                if r.eps_surprise is not None
            ]
        )

        prompt = f"""
分析以下 Earnings Call 後的股價數據，找出模式：

{summary}

請分析：
1. EPS 驚喜與股價反應的相關性
2. 值得注意的異常值
3. 整體趨勢

以 JSON 格式回覆：
{{
    "correlation_analysis": "描述",
    "outliers": ["股票1", "股票2"],
    "trend": "描述",
    "insights": ["洞察1", "洞察2"]
}}
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一個金融分析專家，擅長分析 Earnings Call 數據。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        import json

        try:
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            return {"error": "無法解析回應", "raw": response.choices[0].message.content}
