# 我的量化选股平台

A股量化选股与回测平台，内置「杨永兴尾盘战法」策略。

## 功能特性

### 智能选股
基于杨永兴尾盘战法，六大核心筛选条件：
- 当日涨幅锁定在 3%-5% 区间
- 近 30 个交易日内至少出现一次涨停
- 总市值严格小于 200 亿元
- 当日量比大于 1
- 换手率控制在 5%-10%
- 分时图 14:30 后创日内新高且回踩不破

### 策略回测
- 支持自定义股票代码、本金、手续费率、时间区间
- 完整绩效报告：总收益率、年化收益率、最大回撤、夏普比率、胜率、盈亏比
- 净值曲线图（策略 vs 基准对比）
- 详细交易记录

## 技术栈

| 模块 | 技术 |
|------|------|
| 数据源 | mootdx (通达信) + 腾讯财经 + 东方财富 |
| 后端 | Flask + Pandas + NumPy |
| 前端 | HTML / CSS / JavaScript + Chart.js |
| 图表 | Chart.js 净值曲线可视化 |

## 项目结构

```
├── backend/
│   ├── app.py                # Flask 后端主应用
│   ├── data/
│   │   └── stock_data.py     # A股数据提供层
│   ├── strategies/
│   │   └── yang_yongxing.py  # 杨永兴尾盘战法策略
│   └── backtest/
│       └── engine.py         # 回测引擎
├── frontend/
│   ├── index.html            # 主页面
│   ├── css/style.css         # 样式
│   └── js/app.js             # 前端逻辑
├── .gitignore
└── README.md
```

## 快速开始

### 安装依赖

```bash
pip install mootdx requests pandas stockstats flask flask-cors
```

### 启动服务

```bash
python backend/app.py
```

访问 http://localhost:5000 即可使用。

## 免责声明

本项目仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。
