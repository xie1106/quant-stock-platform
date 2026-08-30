"""
量化选股平台 - Flask后端应用
"""

import sys
import os
import threading
import time
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.data.stock_data import get_data_provider, norm_ticker
from backend.strategies.yang_yongxing import YangYongxingStrategy
from backend.backtest.engine import BacktestEngine

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# 初始化
strategy = YangYongxingStrategy()
backtest_engine = BacktestEngine()
data_provider = get_data_provider()

# 选股任务状态
screen_tasks = {}


@app.route('/')
def index():
    """首页"""
    return send_from_directory('../frontend', 'index.html')


@app.route('/api/stock/list')
def get_stock_list():
    """获取股票列表"""
    try:
        df = data_provider.get_stock_list()
        stocks = df.to_dict('records')
        return jsonify({
            'success': True,
            'data': stocks,
            'total': len(stocks)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stock/quote/<code>')
def get_stock_quote(code):
    """获取股票实时行情"""
    try:
        quote = data_provider.get_realtime_quote(code)
        return jsonify({
            'success': True,
            'data': quote
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stock/kline/<code>')
def get_stock_kline(code):
    """获取K线数据"""
    try:
        period = request.args.get('period', 'daily')
        count = int(request.args.get('count', 100))

        df = data_provider.get_kline(code, period=period, count=count)
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        data = df.to_dict('records')

        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/strategy/list')
def get_strategy_list():
    """获取策略列表"""
    strategies = [
        {
            'id': 'yang_yongxing',
            'name': strategy.strategy_name,
            'desc': strategy.strategy_desc,
            'conditions': strategy.get_filter_conditions()
        }
    ]
    return jsonify({
        'success': True,
        'data': strategies
    })


@app.route('/api/screen/start', methods=['POST'])
def start_screen():
    """开始选股"""
    try:
        strategy_id = request.json.get('strategy', 'yang_yongxing')

        if strategy_id != 'yang_yongxing':
            return jsonify({
                'success': False,
                'error': f'不支持的策略: {strategy_id}'
            }), 400

        task_id = str(int(time.time()))

        # 启动选股任务
        def run_screen():
            screen_tasks[task_id] = {
                'status': 'running',
                'progress': 0,
                'total': 0,
                'message': '初始化...',
                'result': []
            }

            def progress_callback(current, total, message):
                screen_tasks[task_id]['progress'] = current
                screen_tasks[task_id]['total'] = total
                screen_tasks[task_id]['message'] = message

            try:
                result = strategy.screen_stocks(progress_callback)
                screen_tasks[task_id]['status'] = 'completed'
                screen_tasks[task_id]['result'] = result
                screen_tasks[task_id]['message'] = f'选股完成，共找到 {len(result)} 只符合条件的股票'
            except Exception as e:
                screen_tasks[task_id]['status'] = 'failed'
                screen_tasks[task_id]['error'] = str(e)
                screen_tasks[task_id]['message'] = f'选股失败: {str(e)}'

        thread = threading.Thread(target=run_screen)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/screen/status/<task_id>')
def get_screen_status(task_id):
    """获取选股进度"""
    if task_id not in screen_tasks:
        return jsonify({
            'success': False,
            'error': '任务不存在'
        }), 404

    task = screen_tasks[task_id]
    return jsonify({
        'success': True,
        'data': task
    })


@app.route('/api/signal/<code>')
def get_buy_signal(code):
    """获取个股买入信号"""
    try:
        signal = strategy.generate_buy_signal(code)
        return jsonify({
            'success': True,
            'data': signal
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/backtest/run', methods=['POST'])
def run_backtest():
    """执行回测"""
    try:
        data = request.json
        code = data.get('code')
        strategy_id = data.get('strategy', 'yang_yongxing')
        initial_capital = float(data.get('initial_capital', 100000))
        commission_rate = float(data.get('commission_rate', 0.001))
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        if not code:
            return jsonify({
                'success': False,
                'error': '请输入股票代码'
            }), 400

        result = backtest_engine.run_backtest(
            code=code,
            strategy=strategy_id,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            start_date=start_date,
            end_date=end_date
        )

        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/backtest/strategies')
def get_backtest_strategies():
    """获取回测策略列表"""
    strategies = backtest_engine.get_available_strategies()
    return jsonify({
        'success': True,
        'data': strategies
    })


@app.route('/api/health')
def health_check():
    """健康检查"""
    return jsonify({
        'success': True,
        'status': 'ok',
        'timestamp': time.time()
    })


if __name__ == '__main__':
    print("=" * 60)
    print("  我的量化选股平台 - 启动中...")
    print("=" * 60)
    print("  访问地址: http://localhost:5000")
    print("  API文档: http://localhost:5000/api/health")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
