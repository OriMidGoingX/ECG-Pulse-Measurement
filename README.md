# 心电脉搏测量系统 💓

[![Python](https://img.shields.io/badge/Python-3.6%2B-blue)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/PyQt5-5.15%2B-green)](https://riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一款基于 **PyQt5** 开发的实时心电脉搏监测软件，支持 **串口数据采集、波形可视化、心率计算与数据导出**，适用于心电信号或脉搏信号的实时监测场景。


<img width="3199" height="1888" alt="屏幕截图 2025-10-28 121754" src="https://github.com/user-attachments/assets/2bece32a-f1bb-4bd6-be94-7cd14376924a" />

---

## ✨ 功能特性

### 🔌 串口通信管理
- 自动扫描可用串口，支持多种波特率（9600~460800）
- 实时显示连接状态、采样率等信息
- 快速连接/断开串口与端口刷新功能

### 📊 波形实时可视化
- 高刷新率波形绘制，支持抗锯齿显示
- 自定义显示窗口（5~20秒）
- 自动标记 R 波峰值（绿色圆点）
- 支持波形垂直平移、缩放及居中重置

### ❤️ 心率计算功能
- 内置轻量级无滤波 R 波检测算法
- 实时计算心率（BPM），峰值检测可调参数：
  - 阈值比例 `r_threshold_ratio`
  - 最小R波间隔 `min_r_interval`
- 异常值过滤，保证稳定显示

### 💾 数据管理
- 原始数据查看（HEX/TEXT 两种模式）
- CSV 数据导出，包含时间戳、ADC原始值、电压值
- 缓冲区保护（最多 200,000 点），防止内存溢出

### ⚙️ 灵活参数配置
- 可调采样率（1~20000Hz）、ADC位数（1~32位）、参考电压（0.1~10V）
- 心率算法阈值和最小间隔可调节，适配不同信号

---

## 🚀 快速开始

### 环境依赖

| 依赖库       | 版本要求  | 说明                     |
|--------------|-----------|--------------------------|
| Python       | ≥3.6      | 运行环境                 |
| PyQt5        | ≥5.15     | GUI界面框架              |
| pyqtgraph    | ≥0.12     | 高性能波形绘制           |
| numpy        | ≥1.19     | 数值计算支持             |
| pyserial     | ≥3.5      | 串口通信支持             |

### 安装与运行

1. 克隆仓库
   ```bash
   git clone https://github.com/OriMidGoingX/ECG-Pulse-Measurement.git
   cd ECG-Pulse-Measurement
