/**
 * 我的量化选股平台 - 前端逻辑
 */

const API_BASE = '';
let equityChart = null;
let screenTaskId = null;
let pollTimer = null;

// ===== Tab 切换 =====
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`${tab}-tab`).classList.add('active');
    });
});

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', () => {
    loadStrategyConditions();
    initBacktestDates();
});

function initBacktestDates() {
    const now = new Date();
    const oneYearAgo = new Date(now);
    oneYearAgo.setFullYear(now.getFullYear() - 1);

    document.getElementById('bt-start').value = formatDate(oneYearAgo);
    document.getElementById('bt-end').value = formatDate(now);
}

function formatDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

// ===== 策略条件加载 =====
async function loadStrategyConditions() {
    try {
        const resp = await fetch(`${API_BASE}/api/strategy/conditions`);
        const data = await resp.json();
        const grid = document.getElementById('conditions-grid');
        if (data.conditions) {
            grid.innerHTML = data.conditions.map(c => `
                <div class="condition-item">
                    <div class="condition-name">${c.name}</div>
                    <div class="condition-value">${c.condition}</div>
                    <div class="condition-desc">${c.desc}</div>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error('加载策略条件失败:', e);
    }
}

// ===== 选股 =====
document.getElementById('start-screen-btn').addEventListener('click', startScreening);

async function startScreening() {
    const btn = document.getElementById('start-screen-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span><span>正在选股...</span>';

    document.getElementById('screen-progress').style.display = 'block';
    document.getElementById('screen-result').style.display = 'none';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-status').textContent = '运行中';
    document.getElementById('progress-status').className = 'status-badge status-running';

    try {
        const resp = await fetch(`${API_BASE}/api/screen`, { method: 'POST' });
        const data = await resp.json();

        if (data.task_id) {
            screenTaskId = data.task_id;
            pollScreenProgress();
        }
    } catch (e) {
        showScreenError('选股启动失败：' + e.message);
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🚀</span><span>一键选股</span>';
    }
}

function pollScreenProgress() {
    pollTimer = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/api/screen/status/${screenTaskId}`);
            const data = await resp.json();

            if (data.status === 'running' || data.status === 'pending') {
                const pct = data.total > 0 ? Math.round(data.current / data.total * 100) : 0;
                document.getElementById('progress-bar').style.width = pct + '%';
                document.getElementById('progress-message').textContent = data.message || '处理中...';
            } else if (data.status === 'completed') {
                clearInterval(pollTimer);
                document.getElementById('progress-bar').style.width = '100%';
                document.getElementById('progress-status').textContent = '完成';
                document.getElementById('progress-status').className = 'status-badge status-completed';
                document.getElementById('progress-message').textContent = `选股完成，共筛选出 ${data.results.length} 只股票`;

                renderScreenResults(data.results);

                const btn = document.getElementById('start-screen-btn');
                btn.disabled = false;
                btn.innerHTML = '<span class="btn-icon">🔄</span><span>重新选股</span>';
            } else if (data.status === 'failed') {
                clearInterval(pollTimer);
                showScreenError(data.message || '选股失败');
            }
        } catch (e) {
            console.error('轮询失败:', e);
        }
    }, 1000);
}

function showScreenError(msg) {
    document.getElementById('progress-status').textContent = '失败';
    document.getElementById('progress-status').className = 'status-badge status-failed';
    document.getElementById('progress-message').textContent = msg;
    const btn = document.getElementById('start-screen-btn');
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">🚀</span><span>一键选股</span>';
}

function renderScreenResults(stocks) {
    const tbody = document.getElementById('stock-table-body');
    document.getElementById('screen-result').style.display = 'block';
    document.getElementById('result-count').textContent = `共 ${stocks.length} 只`;

    if (stocks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:40px; color:#9ca3af;">今日无符合条件股票，换个交易日再来看看</td></tr>';
        return;
    }

    tbody.innerHTML = stocks.map(s => {
        const ratingClass = s.rating === '推荐' ? 'badge-recommend' :
                            s.rating === '关注' ? 'badge-watch' :
                            s.rating === '谨慎' ? 'badge-caution' : 'badge-unmatch';

        const changeClass = s.change_pct > 0 ? 'text-up' : 'text-down';
        const changeSign = s.change_pct > 0 ? '+' : '';

        return `
            <tr>
                <td><span class="badge ${ratingClass}">${s.rating}</span></td>
                <td>${s.code}</td>
                <td><strong>${s.name}</strong></td>
                <td>${s.price}</td>
                <td class="${changeClass}">${changeSign}${s.change_pct}%</td>
                <td><span style="font-size:13px; color:#6b7280;">${s.simple_explain || '--'}</span></td>
                <td>
                    <div class="match-score">
                        <span>${s.match_score}</span>
                        <div class="score-bar"><div class="score-fill" style="width:${s.match_score}%"></div></div>
                    </div>
                </td>
                <td><button class="btn btn-sm btn-outline" onclick="showStockDetail('${s.code}')">详情</button></td>
            </tr>
        `;
    }).join('');
}

// ===== 股票详情 =====
async function showStockDetail(code) {
    const modal = document.getElementById('stock-modal');
    const body = document.getElementById('modal-body');
    const title = document.getElementById('modal-title');

    title.textContent = '股票详情';
    body.innerHTML = '<div style="text-align:center; padding:40px;">加载中...</div>';
    modal.style.display = 'flex';

    try {
        const resp = await fetch(`${API_BASE}/api/stock/${code}/signal`);
        const data = await resp.json();

        title.textContent = `${data.name} (${data.code})`;

        const conditions = [
            { name: '当日涨幅 3%-5%', icon: '📊', ok: data.conditions.change_pct_ok,
              passText: `${data.change_pct}% 在范围内`, failText: `${data.change_pct}% 不在3%-5%` },
            { name: '近30日有涨停', icon: '🔥', ok: data.conditions.limit_up_ok,
              passText: `近30日涨停${data.limit_up_count_30d}次`, failText: '近30日无涨停' },
            { name: '总市值 < 200亿', icon: '💰', ok: data.conditions.market_cap_ok,
              passText: `${data.total_market_cap.toFixed(0)}亿 符合`, failText: `${data.total_market_cap.toFixed(0)}亿 超标` },
            { name: '量比 > 1', icon: '📈', ok: data.conditions.volume_ratio_ok,
              passText: `量比${data.volume_ratio} 放量`, failText: `量比${data.volume_ratio} 不足` },
            { name: '换手率 5%-10%', icon: '🔄', ok: data.conditions.turnover_ok,
              passText: `换手${data.turnover_rate}% 正常`, failText: `换手${data.turnover_rate}% 异常` },
            { name: '14:30后创新高', icon: '⏰', ok: data.conditions.new_high_ok,
              passText: '尾盘创新高且站稳', failText: '尾盘未创新高或破位' }
        ];

        const ratingClass = data.rating === '推荐' ? 'badge-recommend' :
                            data.rating === '关注' ? 'badge-watch' :
                            data.rating === '谨慎' ? 'badge-caution' : 'badge-unmatch';

        body.innerHTML = `
            <div class="signal-header">
                <div class="signal-stock-info">
                    <h4>${data.name} <span class="badge ${ratingClass}">${data.rating}</span></h4>
                    <div class="stock-code">代码：${data.code} | ${data.rating_desc}</div>
                </div>
                <div class="signal-price">
                    <div class="price">${data.price}</div>
                    <div class="change ${data.change_pct > 0 ? 'text-up' : 'text-down'}">
                        ${data.change_pct > 0 ? '+' : ''}${data.change_pct}%
                    </div>
                </div>
            </div>

            <div class="conditions-checklist">
                ${conditions.map(c => `
                    <div class="condition-check-item">
                        <div class="condition-name">
                            <span class="condition-icon">${c.icon}</span>
                            ${c.name}
                        </div>
                        <span class="condition-status ${c.ok ? 'pass' : 'fail'}">
                            ${c.ok ? '✅ ' + c.passText : '❌ ' + c.failText}
                        </span>
                    </div>
                `).join('')}
            </div>

            <div class="signal-suggestion">
                <strong>💡 操作建议：</strong>${data.suggestion}
            </div>
        `;
    } catch (e) {
        body.innerHTML = `<div style="text-align:center; padding:40px; color:#ef4444;">加载失败：${e.message}</div>`;
    }
}

function closeModal() {
    document.getElementById('stock-modal').style.display = 'none';
}

// ===== 回测 =====
document.getElementById('backtest-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const code = document.getElementById('bt-code').value.trim();
    if (!code) {
        alert('请输入股票代码');
        return;
    }

    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="btn-icon">⏳</span>正在回测...';

    document.getElementById('backtest-placeholder').style.display = 'none';
    document.getElementById('backtest-result').style.display = 'block';

    // 显示加载中
    document.getElementById('overall-verdict').innerHTML = '<div style="text-align:center; padding:30px; color:#6b7280;">正在计算中...</div>';
    document.querySelectorAll('.metric-value').forEach(el => el.textContent = '--');

    try {
        const params = new URLSearchParams({
            code: code,
            capital: document.getElementById('bt-capital').value || 100000,
            commission: document.getElementById('bt-commission').value || 0.1,
            start: document.getElementById('bt-start').value,
            end: document.getElementById('bt-end').value
        });

        const resp = await fetch(`${API_BASE}/api/backtest?${params}`);
        const data = await resp.json();

        if (!resp.ok) {
            throw new Error(data.error || '回测失败');
        }

        renderBacktestResult(data);
    } catch (e) {
        document.getElementById('overall-verdict').innerHTML =
            `<div style="text-align:center; padding:30px; color:#ef4444;">回测失败：${e.message}</div>`;
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span class="btn-icon">📊</span>开始回测';
    }
});

function renderBacktestResult(data) {
    const perf = data.performance;

    // ===== 总体评价 =====
    const totalReturn = perf.total_return;
    const totalTrades = perf.total_trades;
    let verdictClass, verdictTitle, verdictDesc;

    if (totalTrades === 0) {
        verdictClass = 'verdict-neutral';
        verdictTitle = '😐 没有产生交易';
        verdictDesc = `这只股票在所选时间段内没有触发买入信号（可能市值超过200亿或不满足策略条件），换一只小盘股试试`;
    } else if (totalReturn > 20) {
        verdictClass = 'verdict-good';
        verdictTitle = '🎉 表现优秀';
        verdictDesc = `这个策略在 ${data.code} 上表现很好，赚了 ${totalReturn}%，比一直持有多赚 ${perf.excess_return}%`;
    } else if (totalReturn > 0) {
        verdictClass = 'verdict-neutral';
        verdictTitle = '📈 赚钱了';
        verdictDesc = `策略赚了 ${totalReturn}%，不过赚得不多，可以看看其他股票或者调整参数`;
    } else {
        verdictClass = 'verdict-bad';
        verdictTitle = '📉 亏钱了';
        verdictDesc = `策略亏了 ${Math.abs(totalReturn)}%，这个策略在 ${data.code} 上效果不好，换一只股票试试`;
    }

    document.getElementById('overall-verdict').className = `verdict-card ${verdictClass}`;
    document.getElementById('overall-verdict').innerHTML = `
        <h4>${verdictTitle}</h4>
        <p>${verdictDesc}</p>
    `;

    // ===== 核心指标 =====
    const returnClass = totalReturn >= 0 ? 'text-up' : 'text-down';
    const returnSign = totalReturn >= 0 ? '+' : '';
    document.getElementById('metric-total-return').textContent = `${returnSign}${totalReturn}%`;
    document.getElementById('metric-total-return').className = `metric-value ${returnClass}`;
    document.getElementById('hint-total-return').textContent = `本金${data.initial_capital}元 → ${perf.final_equity}元`;

    document.getElementById('metric-max-drawdown').textContent = `${perf.max_drawdown}%`;
    document.getElementById('metric-max-drawdown').className = `metric-value ${perf.max_drawdown < -15 ? 'text-down' : ''}`;

    document.getElementById('metric-win-rate').textContent = `${perf.win_rate}%`;
    document.getElementById('metric-annual-return').textContent = `${perf.annual_return > 0 ? '+' : ''}${perf.annual_return}%`;

    // ===== 交易统计 =====
    document.getElementById('stat-total-trades').textContent = perf.total_trades;
    document.getElementById('stat-win-trades').textContent = perf.winning_trades;
    document.getElementById('stat-lose-trades').textContent = perf.losing_trades;
    document.getElementById('stat-final-equity').textContent = `${perf.final_equity}元`;

    // ===== 净值曲线 =====
    renderEquityChart(data.equity_curve, data.initial_capital);

    // ===== 交易记录 =====
    const tradeBody = document.getElementById('trade-table-body');
    if (data.trades && data.trades.length > 0) {
        tradeBody.innerHTML = data.trades.map(t => {
            const resultClass = t.is_win ? 'text-up' : 'text-down';
            const resultText = t.is_win ? `赚${t.pnl_pct}%` : `亏${Math.abs(t.pnl_pct)}%`;
            return `
                <tr>
                    <td>${t.entry_date}</td>
                    <td>${t.exit_date}</td>
                    <td>${t.entry_price}</td>
                    <td>${t.exit_price}</td>
                    <td class="${resultClass}">${resultText}</td>
                </tr>
            `;
        }).join('');
    } else {
        tradeBody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:#9ca3af;">没有产生交易</td></tr>';
    }
}

function renderEquityChart(curveData, initialCapital) {
    const ctx = document.getElementById('equity-chart').getContext('2d');

    if (equityChart) {
        equityChart.destroy();
    }

    const labels = curveData.map(d => d.date);
    const equity = curveData.map(d => d.equity);
    const benchmark = curveData.map(d => d.benchmark);

    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '策略收益',
                    data: equity,
                    borderColor: '#2563eb',
                    backgroundColor: 'rgba(37, 99, 235, 0.05)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: '#2563eb'
                },
                {
                    label: '一直持有(对比)',
                    data: benchmark,
                    borderColor: '#9ca3af',
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.3,
                    pointRadius: 0,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: { font: { size: 12 } }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const val = ctx.parsed.y;
                            const pct = ((val - initialCapital) / initialCapital * 100).toFixed(1);
                            return `${ctx.dataset.label}: ${val.toFixed(0)}元 (${pct}%)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { maxTicksLimit: 8, font: { size: 11 } },
                    grid: { display: false }
                },
                y: {
                    ticks: {
                        callback: v => v.toFixed(0),
                        font: { size: 11 }
                    },
                    grid: { color: '#f3f4f6' }
                }
            }
        }
    });
}
