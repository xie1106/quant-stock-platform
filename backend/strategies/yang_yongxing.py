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

from backend.data.stock_data import get_data_provider, norm_ticker, get_limit_up_threshold


class YangYongxingStrategy:
    """杨永兴尾盘战法"""

    def __init__(self):
        self.data_provider = get_data_provider()
        self.strategy_name = "杨永兴尾盘战法"
        self.strategy_desc = "尾盘买入法，通过筛选当日涨幅3%-5%、近30日有涨停、市值小于200亿、量比大于1、换手率5%-10%、14:30后创新高且回踩不破的标的，博取次日冲高收益。"

    def get_filter_conditions(self) -> List[Dict]:
        """获取筛选条件说明（通俗版）"""
        return [
            {
                'name': '当日涨幅',
                'condition': '3% ~ 5%',
                'desc': '涨得不多不少刚刚好，说明有人关注但没涨过头',
                'simple': '涨得温和，不追高'
            },
            {
                'name': '近30日涨停',
                'condition': '至少1次',
                'desc': '最近一个月内涨停过，说明这只股票"有脾气"，容易被资金拉升',
                'simple': '近期强势过，股性活跃'
            },
            {
                'name': '总市值',
                'condition': '< 200亿',
                'desc': '盘子不太大，资金容易撬动，涨起来快',
                'simple': '盘子小，容易拉'
            },
            {
                'name': '量比',
                'condition': '> 1',
                'desc': '今天成交量比平时大，说明有资金在买卖',
                'simple': '放量了，有资金来'
            },
            {
                'name': '换手率',
                'condition': '5% ~ 10%',
                'desc': '交易活跃度适中，既不太冷也不太热',
                'simple': '活跃度刚刚好'
            },
            {
                'name': '14:30后创新高',
                'condition': '回踩不破',
                'desc': '快收盘时还在往上冲，而且没有跌回来，说明资金信心足',
                'simple': '尾盘强势，资金看好'
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
            progress_callback(0, total_stocks, f"共 {total_stocks} 只股票，开始初筛...")

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
                            f"初筛完成，{len(filtered)} 只进入深度筛选...")

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

                # 计算匹配度
                match_score = self._calculate_score(row, limit_up_count, has_new_high)
                rating, rating_desc = self._get_rating(match_score, row, limit_up_count)

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
                    'match_score': round(match_score, 0),
                    'rating': rating,
                    'rating_desc': rating_desc,
                    'simple_explain': self._simple_explain(row, limit_up_count, match_score)
                }
                candidates.append(candidate)

            except Exception as e:
                print(f"分析 {code} 失败: {e}")
                continue

        # 按匹配度排序
        candidates.sort(key=lambda x: x['match_score'], reverse=True)

        return candidates

    def _get_rating(self, match_score: float, row: pd.Series, limit_up_count: int) -> Tuple[str, str]:
        """根据匹配度生成通俗评级"""
        if match_score >= 80:
            return '推荐', '各项条件优秀，尾盘可重点关注'
        elif match_score >= 65:
            return '关注', '基本符合条件，可加入自选观察'
        else:
            return '谨慎', '部分条件偏弱，建议多看少动'

    def _simple_explain(self, row: pd.Series, limit_up_count: int, score: float) -> str:
        """生成一句话通俗解读"""
        parts = []

        # 涨幅
        change = row['change_pct']
        if 3.5 <= change <= 4.5:
            parts.append('涨幅适中')
        else:
            parts.append('涨幅在范围内')

        # 市值
        cap = row['total_market_cap']
        if cap < 50:
            parts.append('小盘股弹性大')
        elif cap < 100:
            parts.append('中小盘')
        else:
            parts.append('偏中大市值')

        # 涨停
        if limit_up_count >= 3:
            parts.append(f'近30日{limit_up_count}次涨停股性很活')
        elif limit_up_count >= 2:
            parts.append(f'近30日涨停{limit_up_count}次')
        else:
            parts.append('近30日有涨停')

        # 量比
        vr = row['volume_ratio']
        if vr >= 2:
            parts.append('明显放量')
        else:
            parts.append('温和放量')

        return '，'.join(parts)

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
        match_score = sum([20 if v else 0 for v in conditions.values()]) + 20
        rating, rating_desc = self._get_rating(match_score, pd.Series(quote), limit_up_count) if all_match else ('不符合', '当前不满足杨永兴尾盘战法条件')

        return {
            'code': code,
            'name': quote['name'],
            'price': quote['price'],
            'change_pct': quote['change_pct'],
            'conditions': conditions,
            'all_match': all_match,
            'rating': rating,
            'rating_desc': rating_desc,
            'limit_up_count_30d': limit_up_count,
            'day_high': day_high,
            'pullback_low': pullback_low,
            'total_market_cap': quote['total_market_cap'],
            'volume_ratio': quote['volume_ratio'],
            'turnover_rate': quote['turnover_rate'],
            'suggestion': self._generate_suggestion(all_match, conditions)
        }

    def _generate_suggestion(self, all_match: bool, conditions: Dict) -> str:
        """生成操作建议（通俗版）"""
        if all_match:
            return "符合全部条件！建议下午2:50左右关注，如果尾盘走势依然强势，可考虑小仓位介入，第二天冲高就卖出获利。"

        failed = []
        if not conditions['change_pct_ok']:
            failed.append('涨幅不在3%-5%')
        if not conditions['limit_up_ok']:
            failed.append('近30日没有涨停过')
        if not conditions['market_cap_ok']:
            failed.append('市值超过200亿(太大了)')
        if not conditions['volume_ratio_ok']:
            failed.append('量比不够(资金没怎么来)')
        if not conditions['turnover_ok']:
            failed.append('换手率不合适')
        if not conditions['new_high_ok']:
            failed.append('尾盘没有创新高或回踩破了')

        return "暂时不符合条件：" + "；".join(failed) + "。可以继续观察，等条件满足再考虑。"
