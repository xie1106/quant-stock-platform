"""
杨永兴尾盘战法策略
核心逻辑：
1. 当日涨幅锁定在3%-5%区间
2. 近30个交易日内至少出现一次涨停
3. 总市值严格小于200亿元
4. 当日量比大于1
5. 换手率控制在5%-10%
6. 分时图走势需在14:30后创日内新高，且回踩不破新高点
"""

import pandas as pd
from typing import List, Dict, Tuple
from datetime import datetime

from backend.data.stock_data import get_data_provider, norm_ticker


class YangYongxingStrategy:
    """杨永兴尾盘战法"""

    def __init__(self):
        self.data_provider = get_data_provider()
        self.strategy_name = "杨永兴尾盘战法"
        self.strategy_desc = "尾盘买入法，通过筛选当日涨幅3%-5%、近30日有涨停、市值小于200亿、量比大于1、换手率5%-10%、14:30后创新高且回踩不破的标的，博取次日冲高收益。"

    def get_filter_conditions(self) -> List[Dict]:
        """获取筛选条件说明"""
        return [
            {
                'name': '当日涨幅',
                'condition': '3% ~ 5%',
                'desc': '锁定温和上涨区间，避免追高'
            },
            {
                'name': '近30日涨停',
                'condition': '至少1次',
                'desc': '股性活跃，有涨停基因'
            },
            {
                'name': '总市值',
                'condition': '< 200亿',
                'desc': '小盘股弹性更大'
            },
            {
                'name': '量比',
                'condition': '> 1',
                'desc': '当日放量，资金关注'
            },
            {
                'name': '换手率',
                'condition': '5% ~ 10%',
                'desc': '活跃度适中，避免过高或过低'
            },
            {
                'name': '14:30后创新高',
                'condition': '回踩不破',
                'desc': '尾盘强势拉升，资金做多意愿强'
            }
        ]

    def screen_stocks(self, progress_callback=None) -> List[Dict]:
        """
        执行选股
        progress_callback: 进度回调函数，参数为 (当前, 总数, 消息)
        """
        results = []

        # 获取全市场股票列表
        if progress_callback:
            progress_callback(0, 100, "正在获取股票列表...")

        stock_list = self.data_provider.get_stock_list()
        if stock_list.empty:
            return results

        total_stocks = len(stock_list)
        if progress_callback:
            progress_callback(0, total_stocks, f"共获取 {total_stocks} 只股票，开始初筛...")

        # 第一步：基础条件筛选（涨幅、市值、量比、换手率）
        filtered = stock_list[
            (stock_list['change_pct'] >= 3) &
            (stock_list['change_pct'] <= 5) &
            (stock_list['total_market_cap'] < 200) &
            (stock_list['total_market_cap'] > 0) &
            (stock_list['volume_ratio'] > 1) &
            (stock_list['turnover_rate'] >= 5) &
            (stock_list['turnover_rate'] <= 10)
        ].copy()

        if progress_callback:
            progress_callback(len(filtered), total_stocks,
                            f"初筛完成，剩余 {len(filtered)} 只股票，开始深度筛选...")

        # 第二步：深度筛选（近30日涨停、14:30后创新高）
        candidates = []
        for idx, row in filtered.iterrows():
            code = row['code']

            if progress_callback:
                progress_callback(len(candidates) + 1, len(filtered),
                                f"正在分析 {code} {row['name']}...")

            try:
                # 检查近30日涨停
                limit_up_count = self.data_provider.get_limit_up_history(code, days=30)
                if limit_up_count < 1:
                    continue

                # 检查14:30后创新高且回踩不破
                has_new_high, day_high, pullback_low = self.data_provider.check_intraday_new_high_after_1430(code)
                if not has_new_high:
                    continue

                # 符合所有条件
                candidate = {
                    'code': code,
                    'name': row['name'],
                    'price': round(row['price'], 2),
                    'change_pct': round(row['change_pct'], 2),
                    'turnover_rate': round(row['turnover_rate'], 2),
                    'volume_ratio': round(row['volume_ratio'], 2),
                    'total_market_cap': round(row['total_market_cap'], 2),
                    'limit_up_count_30d': limit_up_count,
                    'day_high': round(day_high, 2),
                    'pullback_low': round(pullback_low, 2),
                    'pe': round(row.get('pe', 0), 2),
                    'pb': round(row.get('pb', 0), 2),
                    'match_score': self._calculate_score(row, limit_up_count, has_new_high)
                }
                candidates.append(candidate)

            except Exception as e:
                print(f"分析 {code} 失败: {e}")
                continue

        # 按匹配度排序
        candidates.sort(key=lambda x: x['match_score'], reverse=True)

        return candidates

    def _calculate_score(self, row: pd.Series, limit_up_count: int, has_new_high: bool) -> float:
        """计算匹配度分数（0-100）"""
        score = 0

        # 涨幅得分（越接近4%越好）
        change_pct = row['change_pct']
        if 3.5 <= change_pct <= 4.5:
            score += 20
        elif 3 <= change_pct <= 5:
            score += 15

        # 涨停次数得分
        if limit_up_count >= 3:
            score += 20
        elif limit_up_count >= 2:
            score += 15
        else:
            score += 10

        # 市值得分（越小越好）
        market_cap = row['total_market_cap']
        if market_cap < 50:
            score += 15
        elif market_cap < 100:
            score += 12
        elif market_cap < 150:
            score += 8
        else:
            score += 5

        # 量比得分（越大越好）
        volume_ratio = row['volume_ratio']
        if volume_ratio >= 2:
            score += 15
        elif volume_ratio >= 1.5:
            score += 12
        else:
            score += 8

        # 换手率得分（越接近7.5%越好）
        turnover = row['turnover_rate']
        if 6.5 <= turnover <= 8.5:
            score += 15
        elif 5 <= turnover <= 10:
            score += 10

        # 14:30创新高加分
        if has_new_high:
            score += 15

        return min(score, 100)

    def generate_buy_signal(self, code: str) -> Dict:
        """
        生成买入信号详情
        """
        code = norm_ticker(code)
        quote = self.data_provider.get_realtime_quote(code)
        limit_up_count = self.data_provider.get_limit_up_history(code, days=30)
        has_new_high, day_high, pullback_low = self.data_provider.check_intraday_new_high_after_1430(code)

        # 判断是否符合条件
        conditions = {
            'change_pct_ok': 3 <= quote['change_pct'] <= 5,
            'limit_up_ok': limit_up_count >= 1,
            'market_cap_ok': quote['total_market_cap'] < 200,
            'volume_ratio_ok': quote['volume_ratio'] > 1,
            'turnover_ok': 5 <= quote['turnover_rate'] <= 10,
            'new_high_ok': has_new_high
        }

        all_match = all(conditions.values())

        return {
            'code': code,
            'name': quote['name'],
            'price': quote['price'],
            'change_pct': quote['change_pct'],
            'conditions': conditions,
            'all_match': all_match,
            'limit_up_count_30d': limit_up_count,
            'day_high': day_high,
            'pullback_low': pullback_low,
            'total_market_cap': quote['total_market_cap'],
            'volume_ratio': quote['volume_ratio'],
            'turnover_rate': quote['turnover_rate'],
            'suggestion': self._generate_suggestion(all_match, conditions)
        }

    def _generate_suggestion(self, all_match: bool, conditions: Dict) -> str:
        """生成操作建议"""
        if all_match:
            return "✅ 符合杨永兴尾盘战法全部条件，可考虑在尾盘14:50左右介入，次日冲高止盈。"

        failed = []
        if not conditions['change_pct_ok']:
            failed.append('涨幅不在3%-5%区间')
        if not conditions['limit_up_ok']:
            failed.append('近30日无涨停')
        if not conditions['market_cap_ok']:
            failed.append('市值超过200亿')
        if not conditions['volume_ratio_ok']:
            failed.append('量比不足1')
        if not conditions['turnover_ok']:
            failed.append('换手率不在5%-10%区间')
        if not conditions['new_high_ok']:
            failed.append('14:30后未创新高或回踩破位')

        return f"⚠️ 未满足条件：{'; '.join(failed)}"
