# 开题级预实验项目说明（给 coding agent）

## 项目目标
论文方向：**面向具身智能的任务驱动主动三维重建与层次化空间记忆**。

本次只做**开题级预实验**，不是完整论文系统。预实验只验证三件事：

1. **任务驱动探索** 比随机探索、普通 frontier 探索更快获得任务相关证据。
2. **最小空间记忆** 比只看当前帧更有助于回答问题或目标搜索。
3. RGB-D 多视角观测能够形成一个**可展示的轻量三维重建结果**，作为后续论文系统可行性的证明。

## 范围边界
必须遵守：

- 不做完整在线 3DGS 优化。
- 不做 RL / PPO / A3C 等训练型策略。
- 不接外部闭源 API。
- 优先使用仿真器真值语义（GT semantic / instance）做感知。
- 探索只做启发式 task-aware heuristic。
- 三维重建只做轻量点云 / TSDF 演示，不进入闭环决策。


## 仿真平台选择（已明确）
本项目的仿真与数据优先级固定如下：

**Plan A（首选）**
- 仿真平台：`Habitat-Lab / Habitat-Sim`
- 场景数据：优先 `HM3D example / minival / 体量较小的可用 split`
- 感知来源：优先使用 Habitat 可直接提供的 `RGB / depth / semantic / instance / pose`

**Plan A-降级版（若 HM3D 当前不可用）**
- 仍使用 `Habitat-Lab / Habitat-Sim`
- 改用当前机器上最容易跑通的 Habitat 场景或 demo scene
- 目标是先打通“任务输入 → 探索 → 记忆 → 回答”的最小闭环，不死磕特定数据集

**Plan B（若 Habitat 本身或场景依赖卡住）**
- 切换为**离线 next-view ranking 预实验**
- 只保留轨迹、候选视角、object memory、回答器和轻量 3D 融合演示
- 依然要比较 `random / frontier-like / task-aware`

约束：
- coding agent 不得自行改用其他大型仿真框架（如 Isaac Sim、AI2-THOR、Gazebo）作为主路线，除非先明确记录阻塞并得到用户确认。
- 若 Habitat 可跑通，则默认继续沿 Habitat 主路线推进，不做平台漂移。

## 最终要产出的核心结论
最终需要用实验结果支撑下面这句话：

> 在小规模具身探索预实验中，任务驱动探索比随机/普通探索更快获得任务相关证据；基于历史观测构建的最小空间记忆比只看当前帧更有利于回答问题；同时，RGB-D 多视角观测可以形成可展示的轻量三维重建结果，为后续完整论文系统提供可行性验证。

## 最低验收标准
- 至少 5 个场景。
- 至少 20 个任务（总量）。
- 3 种探索策略都能跑：random / frontier / task-aware。
- 2 种回答器都能跑：current-frame-only / memory-assisted。
- 至少一个指标上 task-aware 优于 random。
- 至少一个指标上 memory-assisted 优于 current-frame-only。
- 至少一张轻量三维重建可视化图。

## 结果文件要求
必须最终生成：

- `outputs/figures/fig_policy_comparison.png`
- `outputs/figures/fig_memory_comparison.png`
- `outputs/figures/fig_qualitative_paths.png`
- `outputs/figures/fig_pointcloud_demo.png`
- `outputs/figures/fig_failure_case.png`
- `outputs/tables/table_policy_results.csv`
- `outputs/tables/table_memory_results.csv`
- `outputs/final_summary.md`

## 基本技术路线
主链路：

T0 环境与数据跑通  
→ T1 任务集生成  
→ T2 最小空间记忆  
→ T3 三种探索策略  
→ T4 两类回答器  
→ T5 评估与作图  
→ T7 收尾交付

支线：

T6 轻量三维重建演示

优先级规则：**主链路 > 支线**。
