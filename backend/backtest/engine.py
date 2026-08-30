"""
回测引擎 - 支持策略回测和绩效分析
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from backend.data.stock_data import get_data_provider, norm_ticker


class BacktestEngine:
    """回测引擎"""

    def __init__(self):
        self.data_provider = get_data_provider()

    def run_backtest(
        self,
        code: str,
        strategy: str = 'yang_yongxing',
        initial_capital: float = 100000,
        commission_rate: float = 0.001,  # 千分之一手续费
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict:
        """
        执行回测
        """
        code = norm_ticker(code)

        # 获取K线数据
        df = self.data_provider.get_kline(code, count=500)
        if df.empty:
            raise Exception("无法获取K线数据")

        # 日期过滤
        df['date'] = pd.to_datetime(df['date'])
        if start_date:
            df = df[df['date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['date'] <= pd.to_datetime(end_date)]

        if df.empty or len(df) < 30:
            raise Exception("回测周期内数据不足（至少需要30个交易日）")

        df = df.reset_index(drop=True)

        # 根据策略生成交易信号
        if strategy == 'yang_yongxing':
            signals = self._yang_yongxing_signals(df)
        else:
            raise Exception(f"不支持的策略: {strategy}")

        # 执行回测
        portfolio = self._execute_strategy(df, signals, initial_capital, commission_rate)

        # 计算绩效指标
        performance = self._calculate_performance(portfolio, initial_capital)

        # 准备净值曲线数据（转为原生Python类型以支持JSON序列化）
        equity_curve = []
        for _, row in portfolio.iterrows():
            equity_curve.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'equity': float(row['equity']),
                'benchmark': float(row['benchmark'])
            })

        # 交易记录
        trades = self._extract_trades(portfolio)

        return {
            'code': code,
            'strategy': strategy,
            'strategy_name': '杨永兴尾盘战法',
            'initial_capital': initial_capital,
            'commission_rate': commission_rate,
            'start_date': df['date'].iloc[0].strftime('%Y-%m-%d'),
            'end_date': df['date'].iloc[-1].strftime('%Y-%m-%d'),
            'performance': performance,
            'equity_curve': equity_curve,
            'trades': trades,
            'total_days': int(len(df)),
            'signal_count': int(len(signals[signals['signal'] != 0]))
        }

    def _yang_yongxing_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        生成杨永兴尾盘战法交易信号
        简化版回测：用日K线模拟尾盘战法
        买入条件：
        1. 当日涨幅3%-5%
        2. 近30日至少1次涨停
        3. 量比大于1（用成交量/近5日均量替代）
        4. 换手率5%-10%（用成交量/流通股本估算，这里简化处理）
        卖出条件：次日开盘价或最高价止盈
        """
        signals = pd.DataFrame(index=df.index)
        signals['signal'] = 0  # 0: 无信号, 1: 买入, -1: 卖出

        # 计算每日涨幅
        df['change_pct'] = df['close'].pct_change() * 100

        # 计算近5日均量（用于估算量比）
        df['vol_ma5'] = df['volume'].rolling(5).mean()
        df['volume_ratio'] = df['volume'] / df['vol_ma5']

        # 标记涨停日
        df['is_limit_up'] = False
        for i in range(1, len(df)):
            change = (df.iloc[i]['close'] - df.iloc[i - 1]['close']) / df.iloc[i - 1]['close'] * 100
            if change >= 9.8:
                df.at[i, 'is_limit_up'] = True

        # 近30日涨停次数
        df['limit_up_30d'] = df['is_limit_up'].rolling(30).sum()

        # 生成买入信号
        for i in range(30, len(df) - 1):
            change_pct = df.iloc[i]['change_pct']
            limit_up_count = df.iloc[i]['limit_up_30d']
            vol_ratio = df.iloc[i]['volume_ratio']

            # 简化条件：涨幅3%-5%，近30日有涨停，量比>1
            if (3 <= change_pct <= 5 and
                limit_up_count >= 1 and
                vol_ratio > 1):
                signals.at[i, 'signal'] = 1  # 当日收盘前买入

        return signals

    def _execute_strategy(
        self,
        df: pd.DataFrame,
        signals: pd.DataFrame,
        initial_capital: float,
        commission_rate: float
    ) -> pd.DataFrame:
        """
        执行策略，计算每日资产净值
        """
        portfolio = pd.DataFrame()
        portfolio['date'] = df['date']
        portfolio['close'] = df['close']
        portfolio['open'] = df['open']
        portfolio['high'] = df['high']
        portfolio['low'] = df['low']

        cash = initial_capital
        shares = 0
        position = 0  # 0: 空仓, 1: 持仓
        entry_price = 0
        entry_date = None

        equity_list = []
        position_list = []
        trade_dates = []
        buy_prices = []
        sell_prices = []

        for i in range(len(df)):
            date = df.iloc[i]['date']
            close = df.iloc[i]['close']
            open_price = df.iloc[i]['open']
            high = df.iloc[i]['high']

            current_equity = cash + shares * close

            # 处理买入信号（当日收盘价买入）
            if signals.iloc[i]['signal'] == 1 and position == 0:
                # 全仓买入（扣除手续费）
                buy_amount = cash
                commission = buy_amount * commission_rate
                shares = int((buy_amount - commission) / close / 100) * 100  # 整手买入
                if shares > 0:
                    cost = shares * close + shares * close * commission_rate
                    cash -= cost
                    position = 1
                    entry_price = close
                    entry_date = date
                    trade_dates.append(date)
                    buy_prices.append(close)

            # 持仓状态下，次日卖出（简化：次日开盘价卖出，或冲高止盈）
            elif position == 1 and i > 0:
                # 检查是否是买入后的第二天
                if entry_date is not None and date > entry_date:
                    # 简化策略：次日开盘卖出
                    sell_price = open_price
                    sell_amount = shares * sell_price
                    commission = sell_amount * commission_rate
                    cash += sell_amount - commission
                    shares = 0
                    position = 0
                    sell_prices.append(sell_price)
                    entry_date = None

            # 更新当日净值
            current_equity = cash + shares * close
            equity_list.append(current_equity)
            position_list.append(position)

        portfolio['equity'] = equity_list
        portfolio['position'] = position_list

        # 计算基准收益（买入持有）
        if len(df) > 0:
            initial_price = df.iloc[0]['close']
            portfolio['benchmark'] = initial_capital * (df['close'] / initial_price)
        else:
            portfolio['benchmark'] = initial_capital

        return portfolio

    def _calculate_performance(self, portfolio: pd.DataFrame, initial_capital: float) -> Dict:
        """
        计算绩效指标
        """
        equity = portfolio['equity'].values
        dates = portfolio['date']
        benchmark = portfolio['benchmark'].values

        # 总收益率
        total_return = (equity[-1] - initial_capital) / initial_capital * 100

        # 基准收益率
        benchmark_return = (benchmark[-1] - initial_capital) / initial_capital * 100

        # 年化收益率
        days = len(portfolio)
        years = days / 252
        if years > 0:
            annual_return = ((equity[-1] / initial_capital) ** (1 / years) - 1) * 100
        else:
            annual_return = 0

        # 最大回撤
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak * 100
        max_drawdown = drawdown.min()

        # 夏普比率（假设无风险利率3%）
        daily_returns = np.diff(equity) / equity[:-1]
        if len(daily_returns) > 0 and np.std(daily_returns) > 0:
            risk_free_rate = 0.03 / 252
            sharpe_ratio = (np.mean(daily_returns) - risk_free_rate) / np.std(daily_returns) * np.sqrt(252)
        else:
            sharpe_ratio = 0

        # 胜率
        position = portfolio['position'].values
        trade_days = np.sum(np.diff(position) != 0) // 2  # 完整交易次数

        # 计算每笔交易盈亏
        wins = 0
        total_trades = 0
        in_position = False
        entry_idx = 0

        for i in range(1, len(position)):
            if position[i] == 1 and position[i-1] == 0:
                in_position = True
                entry_idx = i
            elif position[i] == 0 and position[i-1] == 1 and in_position:
                in_position = False
                total_trades += 1
                if equity[i] > equity[entry_idx - 1]:
                    wins += 1

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # 盈亏比
        profits = []
        losses = []
        in_position = False
        entry_equity = 0

        for i in range(1, len(equity)):
            if position[i] == 1 and position[i-1] == 0:
                in_position = True
                entry_equity = equity[i-1]
            elif position[i] == 0 and position[i-1] == 1 and in_position:
                in_position = False
                pnl = equity[i] - entry_equity
                if pnl > 0:
                    profits.append(pnl)
                else:
                    losses.append(abs(pnl))

        avg_profit = np.mean(profits) if profits else 0
        avg_loss = np.mean(losses) if losses else 0
        profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0

        return {
            'total_return': round(float(total_return), 2),
            'annual_return': round(float(annual_return), 2),
            'max_drawdown': round(float(max_drawdown), 2),
            'sharpe_ratio': round(float(sharpe_ratio), 2),
            'win_rate': round(float(win_rate), 2),
            'profit_loss_ratio': round(float(profit_loss_ratio), 2),
            'total_trades': int(total_trades),
            'winning_trades': int(wins),
            'losing_trades': int(total_trades - wins),
            'benchmark_return': round(float(benchmark_return), 2),
            'excess_return': round(float(total_return - benchmark_return), 2),
            'final_equity': round(float(equity[-1]), 2),
            'avg_profit': round(float(avg_profit), 2),
            'avg_loss': round(float(avg_loss), 2)
        }

    def _extract_trades(self, portfolio: pd.DataFrame) -> List[Dict]:
        """提取交易记录"""
        trades = []
        position = portfolio['position'].values
        equity = portfolio['equity'].values
        dates = portfolio['date']
        close = portfolio['close'].values

        in_position = False
        entry_date = None
        entry_price = 0
        entry_equity = 0

        for i in range(1, len(position)):
            if position[i] == 1 and position[i-1] == 0:
                in_position = True
                entry_date = dates.iloc[i]
                entry_price = close[i]
                entry_equity = equity[i-1]
            elif position[i] == 0 and position[i-1] == 1 and in_position:
                in_position = False
                exit_date = dates.iloc[i]
                exit_price = close[i]
                pnl = equity[i] - entry_equity
                pnl_pct = pnl / entry_equity * 100

                trades.append({
                    'entry_date': entry_date.strftime('%Y-%m-%d') if entry_date else '',
                    'exit_date': exit_date.strftime('%Y-%m-%d'),
                    'entry_price': round(float(entry_price), 2),
                    'exit_price': round(float(exit_price), 2),
                    'pnl': round(float(pnl), 2),
                    'pnl_pct': round(float(pnl_pct), 2),
                    'is_win': bool(pnl > 0)
                })

        return trades

    def get_available_strategies(self) -> List[Dict]:
        """获取可用策略列表"""
        return [
            {
                'id': 'yang_yongxing',
                'name': '杨永兴尾盘战法',
                'desc': '尾盘买入法，筛选当日涨幅3%-5%、近30日有涨停、量比大于1的标的，次日冲高止盈'
            }
        ]
