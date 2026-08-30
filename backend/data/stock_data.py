"""
A股数据提供层 - 基于a-stock-data架构封装
数据源优先级: mootdx(通达信) > 腾讯财经 > 东方财富
"""

import re
import time
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple


def norm_ticker(ticker: str) -> str:
    """标准化股票代码，提取6位数字"""
    m = re.search(r'(\d{6})', str(ticker))
    if not m:
        raise ValueError(f"无法解析股票代码: {ticker}")
    return m.group(1)


def get_market_prefix(code: str) -> str:
    """根据股票代码判断市场前缀"""
    code = norm_ticker(code)
    if code.startswith(('60', '68', '900')):
        return 'sh'  # 上海
    elif code.startswith(('00', '30', '200')):
        return 'sz'  # 深圳
    elif code.startswith(('43', '83', '87', '92')):
        return 'bj'  # 北京
    return 'sh'


class StockDataProvider:
    """A股数据提供者 - 封装多数据源"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self._tdx_client = None

    def _get_tdx_client(self):
        """获取通达信客户端"""
        if self._tdx_client is None:
            try:
                from mootdx.quotes import Quotes
                self._tdx_client = Quotes.factory(market='std')
            except Exception as e:
                print(f"mootdx初始化失败: {e}")
                self._tdx_client = None
        return self._tdx_client

    def get_kline(self, code: str, period: str = 'daily', count: int = 100) -> pd.DataFrame:
        """
        获取K线数据
        period: daily(日线), weekly(周线), monthly(月线), 1min(1分钟), 5min(5分钟), 15min(15分钟), 30min(30分钟), 60min(60分钟)
        """
        code = norm_ticker(code)

        # 优先使用mootdx
        client = self._get_tdx_client()
        if client is not None:
            try:
                market = 1 if code.startswith(('60', '68')) else 0
                period_map = {
                    'daily': 9, 'weekly': 5, 'monthly': 6,
                    '1min': 0, '5min': 1, '15min': 2, '30min': 3, '60min': 4
                }
                category = period_map.get(period, 9)

                data = client.bars(symbol=code, market=market, category=category, count=count)
                if data is not None and len(data) > 0:
                    df = pd.DataFrame(data)
                    # 处理日期列
                    if 'datetime' in df.columns:
                        df.insert(0, 'date', pd.to_datetime(df['datetime']))
                    elif 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                    # 处理成交量列：vol -> volume
                    if 'vol' in df.columns and 'volume' not in df.columns:
                        df = df.rename(columns={'vol': 'volume'})
                    elif 'vol' in df.columns and 'volume' in df.columns:
                        # 两列都存在时，删除 volume 列，保留 vol 并重命名
                        df = df.drop(columns=['volume'])
                        df = df.rename(columns={'vol': 'volume'})
                    # 去除重复列名
                    df = df.loc[:, ~df.columns.duplicated()]
                    # 只保留需要的列（按顺序）
                    result = pd.DataFrame()
                    for col in ['date', 'open', 'high', 'low', 'close', 'volume']:
                        if col in df.columns:
                            result[col] = df[col].values
                    result = result.sort_values('date').reset_index(drop=True)
                    return result
            except Exception as e:
                print(f"mootdx获取K线失败: {e}")

        # 备用: 百度K线
        try:
            return self._get_kline_baidu(code, period, count)
        except Exception as e:
            print(f"百度K线失败: {e}")

        raise Exception(f"获取K线数据失败: {code}")

    def _get_kline_baidu(self, code: str, period: str = 'daily', count: int = 100) -> pd.DataFrame:
        """从百度获取K线数据"""
        market = get_market_prefix(code)
        period_map = {'daily': 'day', 'weekly': 'week', 'monthly': 'month'}
        baidu_period = period_map.get(period, 'day')

        url = f'https://gushitong.baidu.com/opendata?resource_id=5351&query={market}{code}&code={market}{code}&market={market}&type={baidu_period}&count={count}'

        resp = self.session.get(url, timeout=10)
        data = resp.json()

        if data.get('ResultNum', 0) > 0:
            result = data['Result'][0]
            if 'DisplayData' in result:
                display_data = json.loads(result['DisplayData']['resultData'])
                kline_data = display_data.get('state', {}).get('kLine', {}).get('data', [])

                if kline_data:
                    df = pd.DataFrame(kline_data)
                    df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']
                    df['date'] = pd.to_datetime(df['date'])
                    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
                    df['volume'] = df['volume'].astype(float)
                    df = df.sort_values('date').reset_index(drop=True)
                    return df.tail(count)

        raise Exception("百度K线数据获取失败")

    def get_realtime_quote(self, code: str) -> Dict:
        """
        获取实时行情（腾讯财经）
        返回: 价格、涨跌幅、PE、PB、市值、换手率、量比等
        """
        code = norm_ticker(code)
        market = get_market_prefix(code)

        url = f'https://qt.gtimg.cn/q={market}{code}'
        resp = self.session.get(url, timeout=10)
        resp.encoding = 'gbk'

        if resp.text and 'pv_none' not in resp.text:
            parts = resp.text.split('~')
            if len(parts) > 45:
                return {
                    'code': code,
                    'name': parts[1],
                    'price': float(parts[3]) if parts[3] else 0,
                    'pre_close': float(parts[4]) if parts[4] else 0,
                    'open': float(parts[5]) if parts[5] else 0,
                    'high': float(parts[33]) if parts[33] else 0,
                    'low': float(parts[34]) if parts[34] else 0,
                    'volume': float(parts[6]) if parts[6] else 0,
                    'amount': float(parts[37]) if parts[37] else 0,
                    'change_pct': float(parts[32]) if parts[32] else 0,
                    'turnover_rate': float(parts[38]) if parts[38] else 0,
                    'pe': float(parts[39]) if parts[39] else 0,
                    'pb': float(parts[46]) if len(parts) > 46 and parts[46] else 0,
                    'total_market_cap': float(parts[45]) if len(parts) > 45 and parts[45] else 0,  # 总市值(亿)
                    'circulating_market_cap': float(parts[44]) if len(parts) > 44 and parts[44] else 0,  # 流通市值(亿)
                    'volume_ratio': float(parts[49]) if len(parts) > 49 and parts[49] else 0,  # 量比
                }

        raise Exception(f"获取实时行情失败: {code}")

    def get_stock_list(self) -> pd.DataFrame:
        """获取A股股票列表"""
        try:
            # 从东方财富获取股票列表
            url = 'http://80.push2.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1,
                'pz': 6000,
                'po': 1,
                'np': 1,
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',
                'fields': 'f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21,f23'
            }

            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()

            if data.get('data') and data['data'].get('diff'):
                stocks = data['data']['diff']
                df = pd.DataFrame(stocks)
                df = df.rename(columns={
                    'f12': 'code',
                    'f14': 'name',
                    'f2': 'price',
                    'f3': 'change_pct',
                    'f4': 'change',
                    'f5': 'volume',
                    'f6': 'amount',
                    'f7': 'amplitude',
                    'f8': 'turnover_rate',
                    'f9': 'pe',
                    'f10': 'volume_ratio',
                    'f15': 'high',
                    'f16': 'low',
                    'f17': 'open',
                    'f18': 'pre_close',
                    'f20': 'total_market_cap',  # 总市值(元)
                    'f21': 'circulating_market_cap',  # 流通市值(元)
                    'f23': 'pb'
                })
                # 市值转为亿元
                df['total_market_cap'] = df['total_market_cap'] / 1e8
                df['circulating_market_cap'] = df['circulating_market_cap'] / 1e8
                return df

        except Exception as e:
            print(f"获取股票列表失败: {e}")

        # 备用: 返回空DataFrame
        return pd.DataFrame(columns=['code', 'name', 'price', 'change_pct', 'turnover_rate',
                                      'volume_ratio', 'total_market_cap', 'pe', 'pb'])

    def get_minute_data(self, code: str, date: Optional[str] = None) -> pd.DataFrame:
        """
        获取分时数据
        date: 日期字符串，如 '2024-01-15'，默认为今天
        """
        code = norm_ticker(code)
        market = 1 if code.startswith(('60', '68')) else 0

        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        # 尝试使用mootdx
        client = self._get_tdx_client()
        if client is not None:
            try:
                data = client.minute(symbol=code, market=market)
                if data is not None and len(data) > 0:
                    df = pd.DataFrame(data)
                    if 'datetime' in df.columns:
                        df['time'] = pd.to_datetime(df['datetime'])
                    df = df.rename(columns={'price': 'price', 'vol': 'volume'})
                    if 'time' in df.columns and 'price' in df.columns:
                        return df[['time', 'price', 'volume']].copy()
            except Exception as e:
                print(f"mootdx分时数据失败: {e}")

        # 备用: 新浪分时
        try:
            prefix = 'sh' if market == 1 else 'sz'
            url = f'https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_{prefix}{code}_{int(time.time()*1000)}/CN_MarketDataService.getKLineData?symbol={prefix}{code}&scale=1&ma=no&datalen=242'
            resp = self.session.get(url, timeout=10)
            text = resp.text

            import re
            json_match = re.search(r'\((.*)\)', text)
            if json_match:
                data = json.loads(json_match.group(1))
                if data:
                    df = pd.DataFrame(data)
                    df['time'] = pd.to_datetime(df['day'])
                    df['price'] = df['close'].astype(float)
                    df['volume'] = df['volume'].astype(float)
                    return df[['time', 'price', 'volume']].copy()
        except Exception as e:
            print(f"新浪分时数据失败: {e}")

        raise Exception(f"获取分时数据失败: {code}")

    def get_limit_up_history(self, code: str, days: int = 30) -> int:
        """
        检查近N个交易日内是否有涨停
        返回: 涨停次数
        """
        try:
            df = self.get_kline(code, count=days + 10)
            if df.empty or len(df) < 2:
                return 0

            limit_up_count = 0
            for i in range(1, min(len(df), days + 1)):
                pre_close = df.iloc[i - 1]['close']
                close = df.iloc[i]['close']
                if pre_close > 0:
                    change_pct = (close - pre_close) / pre_close * 100
                    # 主板涨停10%，创业板/科创板20%，ST股5%
                    limit_pct = 9.8  # 用9.8作为阈值，考虑四舍五入
                    if change_pct >= limit_pct:
                        limit_up_count += 1

            return limit_up_count
        except Exception as e:
            print(f"检查涨停历史失败: {e}")
            return 0

    def check_intraday_new_high_after_1430(self, code: str) -> Tuple[bool, float, float]:
        """
        检查14:30后是否创日内新高且回踩不破
        返回: (是否符合条件, 日内新高价, 回踩最低价)
        """
        try:
            df = self.get_minute_data(code)
            if df.empty:
                return False, 0, 0

            # 筛选14:30之后的数据
            df['time_str'] = df['time'].dt.strftime('%H:%M')
            after_1430 = df[df['time_str'] >= '14:30'].copy()

            if after_1430.empty:
                return False, 0, 0

            # 日内最高价
            day_high = df['price'].max()

            # 14:30后的最高价
            high_after_1430 = after_1430['price'].max()

            # 检查14:30后是否创了新高（或接近新高）
            if high_after_1430 < day_high * 0.998:
                return False, day_high, 0

            # 找到创新高的时间点
            high_idx = after_1430['price'].idxmax()
            high_time = after_1430.loc[high_idx, 'time']

            # 新高之后的回踩
            after_high = df[df['time'] > high_time].copy()

            if after_high.empty:
                return True, day_high, high_after_1430

            # 回踩最低价
            pullback_low = after_high['price'].min()

            # 回踩是否破了新高点（允许0.5%的误差）
            if pullback_low >= high_after_1430 * 0.995:
                return True, day_high, pullback_low
            else:
                return False, day_high, pullback_low

        except Exception as e:
            print(f"检查日内新高失败: {e}")
            return False, 0, 0


# 单例实例
_data_provider = None


def get_data_provider() -> StockDataProvider:
    global _data_provider
    if _data_provider is None:
        _data_provider = StockDataProvider()
    return _data_provider
