// ===== 量化选股平台 - 前端逻辑 =====

const API_BASE = '/api';
let equityChart = null;

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', function() {
    initTabs();
    loadStrategyInfo();
    initBacktestForm();
    setDefaultDates();
});

// ===== 标签页切换 =====
function initTabs() {
    const navBtns = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    navBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const tabId = this.dataset.tab;

            navBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(t => t.classList.remove('active'));

            this.classList.add('active');
            document.getElementById(tabId + '-tab').classList.add('active');

            if (tabId === 'backtest') {
                setDefaultDates();
            }
        });
    });
}

// ===== 加载策略信息 =====
function loadStrategyInfo() {
    fetch(`${API_BASE}/strategy/list`)
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data.length > 0) {
                const strategy = data.data[0];
                renderConditions(strategy.conditions);
            }
        })
        .catch(err => {
            console.error('加载策略信息失败:', err);
        });

    // 绑定选股按钮
    document.getElementById('start-screen-btn').addEventListener('click', startScreen);
}

// ===== 渲染筛选条件 =====
function renderConditions(conditions) {
    const grid = document.getElementById('conditions-grid');
    grid.innerHTML = conditions.map(c => `
        <div class="condition-item">
            <div class="condition-name">${c.name}</div>
            <div class="condition-value">${c.condition}</div>
            <div class="condition-desc">${c.desc}</div>
        </div>
    `).join('');
}

// ===== 开始选股 =====
let screenPollingInterval = null;

function startScreen() {
    const btn = document.getElementById('start-screen-btn');
    const progressCard = document.getElementById('screen-progress');
    const resultCard = document.getElementById('screen-result');

    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span>选股中...';
    progressCard.style.display = 'block';
    resultCard.style.display = 'none';

    updateProgress(0, 0, '正在初始化...', 'running');

    fetch(`${API_BASE}/screen/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy: 'yang_yongxing' })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            pollScreenStatus(data.task_id);
        } else {
            throw new Error(data.error || '选股失败');
        }
    })
    .catch(err => {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🚀</span>开始选股';
        updateProgress(0, 0, `选股失败: ${err.message}`, 'failed');
    });
}

// ===== 轮询选股进度 =====
function pollScreenStatus(taskId) {
    if (screenPollingInterval) {
        clearInterval(screenPollingInterval);
    }

    screenPollingInterval = setInterval(() => {
        fetch(`${API_BASE}/screen/status/${taskId}`)
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    const task = data.data;
                    const progress = task.total > 0 ? (task.progress / task.total * 100) : 0;

                    if (task.status === 'running') {
                        updateProgress(progress, task.total, task.message, 'running');
                    } else if (task.status === 'completed') {
                        clearInterval(screenPollingInterval);
                        updateProgress(100, task.total, task.message, 'completed');
                        renderScreenResult(task.result);
                        resetScreenButton();
                    } else if (task.status === 'failed') {
                        clearInterval(screenPollingInterval);
                        updateProgress(0, 0, task.message || task.error, 'failed');
                        resetScreenButton();
                    }
                }
            })
            .catch(err => {
                console.error('获取进度失败:', err);
            });
    }, 1000);
}

// ===== 更新进度显示 =====
function updateProgress(percent, total, message, status) {
    const progressBar = document.getElementById('progress-bar');
    const progressMsg = document.getElementById('progress-message');
    const statusBadge = document.getElementById('progress-status');

    progressBar.style.width = percent + '%';
    progressMsg.textContent = message;

    statusBadge.className = 'status-badge status-' + status;
    statusBadge.textContent = status === 'running' ? '运行中' :
                              status === 'completed' ? '已完成' :
                              status === 'failed' ? '失败' : '';
}

// ===== 重置选股按钮 =====
function resetScreenButton() {
    const btn = document.getElementById('start-screen-btn');
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">🔄</span>重新选股';
}

// ===== 渲染选股结果 =====
function renderScreenResult(stocks) {
    const resultCard = document.getElementById('screen-result');
    const resultCount = document.getElementById('result-count');
    const tbody = document.getElementById('stock-table-body');

    resultCount.textContent = `共找到 ${stocks.length} 只股票`;
    resultCard.style.display = 'block';

    if (stocks.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" style="text-align: center; padding: 40px; color: var(--text-muted);">
                    暂无符合条件的股票，请稍后重试或调整筛选条件
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = stocks.map(stock => `
        <tr>
            <td><strong>${stock.code}</strong></td>
            <td>${stock.name}</td>
            <td>${stock.price.toFixed(2)}</td>
            <td class="${stock.change_pct >= 0 ? 'text-up' : 'text-down'}">
                ${stock.change_pct >= 0 ? '+' : ''}${stock.change_pct.toFixed(2)}%
            </td>
            <td>${stock.turnover_rate.toFixed(2)}%</td>
            <td>${stock.volume_ratio.toFixed(2)}</td>
            <td>${stock.total_market_cap.toFixed(2)}</td>
            <td>${stock.limit_up_count_30d} 次</td>
            <td>
                <div class="match-score">
                    <div class="score-bar">
                        <div class="score-fill" style="width: ${stock.match_score}%"></div>
                    </div>
                    <span>${stock.match_score.toFixed(0)}</span>
                </div>
            </td>
            <td>
                <button class="btn btn-sm btn-outline" onclick="showStockDetail('${stock.code}')">
                    详情
                </button>
            </td>
        </tr>
    `).join('');
}

// ===== 显示股票详情 =====
function showStockDetail(code) {
    const modal = document.getElementById('stock-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');

    modal.style.display = 'flex';
    modalTitle.textContent = '加载中...';
    modalBody.innerHTML = '<div class="placeholder"><div class="placeholder-icon">⏳</div><p>正在加载股票详情...</p></div>';

    fetch(`${API_BASE}/signal/${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                renderStockDetail(data.data);
            } else {
                throw new Error(data.error || '加载失败');
            }
        })
        .catch(err => {
            modalBody.innerHTML = `<div class="placeholder"><div class="placeholder-icon">❌</div><p>加载失败: ${err.message}</p></div>`;
        });
}

// ===== 渲染股票详情 =====
function renderStockDetail(signal) {
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');

    modalTitle.textContent = `${signal.name} (${signal.code})`;

    const conditions = [
        { name: '当日涨幅 3%-5%', key: 'change_pct_ok', detail: `当前: ${signal.change_pct.toFixed(2)}%` },
        { name: '近30日有涨停', key: 'limit_up_ok', detail: `涨停次数: ${signal.limit_up_count_30d} 次` },
        { name: '总市值 < 200亿', key: 'market_cap_ok', detail: `当前: ${signal.total_market_cap.toFixed(2)} 亿` },
        { name: '量比 > 1', key: 'volume_ratio_ok', detail: `当前: ${signal.volume_ratio.toFixed(2)}` },
        { name: '换手率 5%-10%', key: 'turnover_ok', detail: `当前: ${signal.turnover_rate.toFixed(2)}%` },
        { name: '14:30后创新高', key: 'new_high_ok', detail: signal.new_high_ok ? '回踩不破' : '未满足' }
    ];

    modalBody.innerHTML = `
        <div class="signal-header">
            <div class="signal-stock-info">
                <h4>${signal.name}</h4>
                <div class="stock-code">${signal.code}</div>
            </div>
            <div class="signal-price">
                <div class="price">${signal.price.toFixed(2)}</div>
                <div class="change ${signal.change_pct >= 0 ? 'text-up' : 'text-down'}">
                    ${signal.change_pct >= 0 ? '+' : ''}${signal.change_pct.toFixed(2)}%
                </div>
            </div>
        </div>

        <div class="conditions-checklist">
            ${conditions.map(c => `
                <div class="condition-check-item">
                    <div class="condition-name">
                        <span class="condition-icon">${signal.conditions[c.key] ? '✅' : '❌'}</span>
                        <span>${c.name}</span>
                    </div>
                    <span class="condition-status ${signal.conditions[c.key] ? 'pass' : 'fail'}">
                        ${signal.conditions[c.key] ? '通过' : '未通过'} · ${c.detail}
                    </span>
                </div>
            `).join('')}
        </div>

        <div class="signal-suggestion">
            ${signal.suggestion}
        </div>
    `;
}

// ===== 关闭弹窗 =====
function closeModal() {
    document.getElementById('stock-modal').style.display = 'none';
}

// ESC 关闭弹窗
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});

// ===== 回测相关 =====
function initBacktestForm() {
    const form = document.getElementById('backtest-form');
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        runBacktest();
    });
}

function setDefaultDates() {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setFullYear(startDate.getFullYear() - 1);

    document.getElementById('bt-end').value = formatDate(endDate);
    document.getElementById('bt-start').value = formatDate(startDate);
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function runBacktest() {
    const code = document.getElementById('bt-code').value.trim();
    const strategy = document.getElementById('bt-strategy').value;
    const capital = parseFloat(document.getElementById('bt-capital').value);
    const commission = parseFloat(document.getElementById('bt-commission').value) / 100;
    const startDate = document.getElementById('bt-start').value;
    const endDate = document.getElementById('bt-end').value;

    if (!code) {
        alert('请输入股票代码');
        return;
    }

    const placeholder = document.getElementById('backtest-placeholder');
    const resultDiv = document.getElementById('backtest-result');
    const submitBtn = document.querySelector('#backtest-form button[type="submit"]');

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="btn-icon">⏳</span>回测中...';
    placeholder.style.display = 'flex';
    resultDiv.style.display = 'none';
    placeholder.innerHTML = '<div class="placeholder-icon">⏳</div><p>正在回测，请稍候...</p>';

    fetch(`${API_BASE}/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            code,
            strategy,
            initial_capital: capital,
            commission_rate: commission,
            start_date: startDate,
            end_date: endDate
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            renderBacktestResult(data.data);
        } else {
            throw new Error(data.error || '回测失败');
        }
    })
    .catch(err => {
        placeholder.innerHTML = `<div class="placeholder-icon">❌</div><p>回测失败: ${err.message}</p>`;
    })
    .finally(() => {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span class="btn-icon">📊</span>开始回测';
    });
}

function renderBacktestResult(result) {
    const placeholder = document.getElementById('backtest-placeholder');
    const resultDiv = document.getElementById('backtest-result');
    const perf = result.performance;

    placeholder.style.display = 'none';
    resultDiv.style.display = 'block';

    // 更新绩效指标
    document.getElementById('metric-total-return').textContent =
        (perf.total_return >= 0 ? '+' : '') + perf.total_return.toFixed(2) + '%';
    document.getElementById('metric-annual-return').textContent =
        (perf.annual_return >= 0 ? '+' : '') + perf.annual_return.toFixed(2) + '%';
    document.getElementById('metric-max-drawdown').textContent = perf.max_drawdown.toFixed(2) + '%';
    document.getElementById('metric-sharpe').textContent = perf.sharpe_ratio.toFixed(2);
    document.getElementById('metric-win-rate').textContent = perf.win_rate.toFixed(2) + '%';
    document.getElementById('metric-pl-ratio').textContent = perf.profit_loss_ratio.toFixed(2);

    // 更新交易统计
    document.getElementById('stat-total-trades').textContent = perf.total_trades + ' 次';
    document.getElementById('stat-win-trades').textContent = perf.winning_trades + ' 次';
    document.getElementById('stat-lose-trades').textContent = perf.losing_trades + ' 次';
    document.getElementById('stat-benchmark').textContent =
        (perf.benchmark_return >= 0 ? '+' : '') + perf.benchmark_return.toFixed(2) + '%';
    document.getElementById('stat-excess').textContent =
        (perf.excess_return >= 0 ? '+' : '') + perf.excess_return.toFixed(2) + '%';
    document.getElementById('stat-final-equity').textContent = '¥' + perf.final_equity.toLocaleString();

    // 绘制净值曲线
    renderEquityChart(result.equity_curve);

    // 渲染交易记录
    renderTradeRecords(result.trades);
}

function renderEquityChart(data) {
    const ctx = document.getElementById('equity-chart').getContext('2d');

    if (equityChart) {
        equityChart.destroy();
    }

    const labels = data.map(d => d.date);
    const equityData = data.map(d => d.equity);
    const benchmarkData = data.map(d => d.benchmark);

    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '策略净值',
                    data: equityData,
                    borderColor: '#2563eb',
                    backgroundColor: 'rgba(37, 99, 235, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 5
                },
                {
                    label: '基准收益',
                    data: benchmarkData,
                    borderColor: '#9ca3af',
                    backgroundColor: 'rgba(156, 163, 175, 0.05)',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 5
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    position: 'top',
                    align: 'end',
                    labels: {
                        usePointStyle: true,
                        padding: 20
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(31, 41, 55, 0.95)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: function(context) {
                            const value = context.parsed.y;
                            const initial = data[0] ? data[0].equity : 100000;
                            const pct = ((value - initial) / initial * 100).toFixed(2);
                            return `${context.dataset.label}: ¥${value.toLocaleString()} (${pct >= 0 ? '+' : ''}${pct}%)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxTicksLimit: 8,
                        color: '#6b7280'
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(229, 231, 235, 0.5)'
                    },
                    ticks: {
                        color: '#6b7280',
                        callback: function(value) {
                            return '¥' + (value / 10000).toFixed(1) + '万';
                        }
                    }
                }
            }
        }
    });
}

function renderTradeRecords(trades) {
    const tbody = document.getElementById('trade-table-body');

    if (trades.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 30px; color: var(--text-muted);">
                    暂无交易记录
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = trades.map(trade => `
        <tr>
            <td>${trade.entry_date}</td>
            <td>${trade.exit_date}</td>
            <td>${trade.entry_price.toFixed(2)}</td>
            <td>${trade.exit_price.toFixed(2)}</td>
            <td class="${trade.is_win ? 'text-up' : 'text-down'}">
                ${trade.is_win ? '+' : ''}${trade.pnl.toFixed(2)}
            </td>
            <td class="${trade.is_win ? 'text-up' : 'text-down'}">
                ${trade.is_win ? '+' : ''}${trade.pnl_pct.toFixed(2)}%
            </td>
        </tr>
    `).join('');
}
