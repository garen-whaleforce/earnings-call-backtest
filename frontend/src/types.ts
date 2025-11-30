export interface BacktestResult {
  symbol: string;
  company_name: string;
  market_cap: number;
  earnings_date: string;
  earnings_time?: string;  // 'BMO' (盤前) 或 'AMC' (盤後)
  price_before: number;    // 發佈前收盤價
  price_after: number;     // 發佈後收盤價
  price_change_pct: number; // 價格變動百分比
  date_before: string;     // 發佈前日期
  date_after: string;      // 發佈後日期
}

export interface BacktestRequest {
  start_date: string;
  end_date: string;
  min_market_cap: number;
}

export interface ValidationResult {
  symbol: string;
  is_valid: boolean;
  message: string;
  details?: Record<string, unknown>;
}
