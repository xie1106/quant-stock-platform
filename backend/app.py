"""
量化选股平台 - Flask后端应用
"""

import sys
import os
import threading
import time
import atexit
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from backend.data.stock_data import get_data_provider, norm_ticker
from backend.strategies.yang_yongxing import YangYongxingStrategy
from backend.backtest.engine import BacktestEngine

FRONTEND_DIR = os.path.join(PROJECT_ROOT, 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
CORS(app)

# 初始化
strategy = YangYongxingStrategy()
backtest_engine = BacktestEngine()
data_provider = get_data_provider()

# 选股任务状态
screen_tasks = {}

# ===== 保活机制 =====
KEEP_ALIVE_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
_last_health_ping = 0

def _keep_alive_loop():
    """后台定时自访问，防止 Render 免费版休眠"""
    import requests
    while True:
        time.sleep(600)  # 每10分钟
        if KEEP_ALIVE_URL:
            try:
                requests.get(f"{KEEP_ALIVE_URL}/api/ping", timeout=10)
                print(f"[保活] ping成功 {time.strftime('%H:%M:%S')}")
            except Exception as e:
                print(f"[保活] ping失败: {e}")

def _start_keep_alive():
    """启动保活线程（仅在 Render 环境下）"""
    if KEEP_ALIVE_URL:
        t = threading.Thread(target=_keep_alive_loop, daemon=True)
        t.start()
        print(f"[保活] 已启动，每10分钟自访问 {KEEP_ALIVE_URL}")

@atexit.register
def _cleanup():
    pass


@app.route('/')
def index():
    """首页"""
    return send_from_directory(FRONTEND_DIR, 'index.html')


# ===== 静态文件 =====
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'css'), filename)


@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'js'), filename)


# ===== 策略条件（通俗版） =====
@app.route('/api/strategy/conditions')
def get_strategy_conditions():
    """获取策略筛选条件说明"""
    return jsonify({
        'conditions': strategy.get_filter_conditions()
    })


# ===== 一键选股 =====
@app.route('/api/screen', methods=['POST'])
def start_screen():
    """开始选股（一键模式）"""
    task_id = str(int(time.time() * 1000))

    def run_screen():
        screen_tasks[task_id] = {
            'status': 'running',
            'current': 0,
            'total': 0,
            'message': '初始化中...',
            'results': []
        }

        def progress_callback(current, total, message):
            screen_tasks[task_id]['current'] = current
            screen_tasks[task_id]['total'] = total
            screen_tasks[task_id]['message'] = message

        try:
            result = strategy.screen_stocks(progress_callback)
            screen_tasks[task_id]['status'] = 'completed'
            screen_tasks[task_id]['results'] = result
            screen_tasks[task_id]['message'] = f'选股完成，共找到 {len(result)} 只股票'
        except Exception as e:
            screen_tasks[task_id]['status'] = 'failed'
            screen_tasks[task_id]['message'] = f'选股失败: {str(e)}'

    thread = threading.Thread(target=run_screen)
    thread.daemon = True
    thread.start()

    return jsonify({'task_id': task_id})


@app.route('/api/screen/status/<task_id>')
def get_screen_status(task_id):
    """获取选股进度"""
    if task_id not in screen_tasks:
        return jsonify({'status': 'not_found', 'message': '任务不存在'}), 404

    task = screen_tasks[task_id]
    return jsonify({
        'status': task['status'],
        'current': task.get('current', 0),
        'total': task.get('total', 0),
        'message': task.get('message', ''),
        'results': task.get('results', [])
    })


# ===== 个股信号 =====
@app.route('/api/stock/<code>/signal')
def get_stock_signal(code):
    """获取个股买入信号详情"""
    try:
        signal = strategy.generate_buy_signal(code)
        return jsonify(signal)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== 回测（GET 简化版） =====
@app.route('/api/backtest')
def run_backtest():
    """执行回测 - GET方式，参数通过query传递"""
    try:
        code = request.args.get('code', '')
        capital = float(request.args.get('capital', 100000))
        commission_pct = float(request.args.get('commission', 0.1))
        start_date = request.args.get('start', '')
        end_date = request.args.get('end', '')

        if not code:
            return jsonify({'error': '请输入股票代码'}), 400

        # 手续费率：用户输入百分比，转为小数
        commission_rate = commission_pct / 100

        result = backtest_engine.run_backtest(
            code=code,
            strategy='yang_yongxing',
            initial_capital=capital,
            commission_rate=commission_rate,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None
        )

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== 健康检查 / 保活 =====
@app.route('/api/health')
def health_check():
    """健康检查"""
    return jsonify({
        'success': True,
        'status': 'ok',
        'timestamp': time.time()
    })


@app.route('/api/ping')
def ping():
    """保活接口 - 供 UptimeRobot 或自唤醒调用"""
    return jsonify({'status': 'pong', 'time': time.time()})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    print("=" * 60)
    print("  我的量化选股平台 - 启动中...")
    print("=" * 60)
    print(f"  访问地址: http://localhost:{port}")
    print(f"  云平台URL: {KEEP_ALIVE_URL or '未设置(本地运行)'}")
    print("=" * 60)
    _start_keep_alive()
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
