# 任务板（单一事实来源）

> 说明：coding agent 每次开始工作时，先读本文件，再读 `04_STATUS.json` 和 `05_CHANGELOG.md`。
> 完成一项就把对应方框打钩，并在备注里写输出路径。
> 若中断，下次恢复时以本文件的勾选状态为准，不依赖聊天历史。

## 总体状态
- 项目状态：`IN_PROGRESS`
- 当前推荐执行任务：`T3`
- 当前所处 Gate：`Gate 1`
- 仓库辅助：根目录 `.gitignore` 已生成，当前会忽略本地环境、下载数据、外部依赖克隆、生成输出、缓存和本地记录文档
- 推送辅助：`scripts/push_repo.sh` 已生成；首次可用 `--remote-url` 配置 `origin`，之后默认可一键 `add + commit + push`

---

## E0 从零开始环境搭建
目标：在当前工作空间内构建一个可重复、可记录、尽量不依赖 root 权限的最小实验环境，为 Habitat 主路线做准备。

### 子任务
- [x] E0.1 读取 `00A_ENV_BOOTSTRAP.md`
- [x] E0.2 探测宿主环境并生成 `outputs/logs/bootstrap_probe.md`
- [x] E0.3 选择环境方案（conda / venv / 本地 Miniforge）
- [x] E0.4 创建并激活项目环境
- [x] E0.5 创建项目目录结构
- [x] E0.6 安装基础依赖
- [x] E0.7 生成 `outputs/logs/bootstrap_env.md`
- [x] E0.8 生成 `outputs/logs/pip_freeze.txt`
- [x] E0.9 生成 `outputs/logs/bootstrap_smoketest.md`
- [x] E0.10 生成 `scripts/bootstrap_env.sh`（以及必要的激活脚本）

### 完成判定
- [x] 能进入可用 Python 环境
- [x] 基础依赖可 import
- [x] 关键目录已创建
- [x] 环境日志与 freeze 文件已落盘
- [x] 后续 T0 可直接开始

### 备注
- 采用方案：`conda`；当前主环境为 `opening_preexp`，`.venv` 保留为备用
- 环境路径：`/home/zyc/miniconda3/envs/opening_preexp`
- 关键依赖版本：当前 Habitat 兼容运行时为 `python 3.9.19`，`habitat-sim 0.3.3`，`habitat-lab 0.3.3`，`numpy 1.26.4`，`matplotlib 3.3.2`
- 阻塞情况：此前 `conda create` 的 SSL 异常仍记录在 `outputs/logs/bootstrap_env.md`，但当前已通过现成 `opening_preexp` 环境绕过；后续为兼容 Habitat 官方 `conda` 包已将该环境切换到 Python 3.9 运行时，`scripts/bootstrap_env.sh`、`scripts/activate_env.sh` 仍可直接激活；`pandas`、`open3d` 等早期基础依赖需要在后续按需补装

---

## T0 环境与数据可用性核验
目标：优先在 **Habitat-Lab / Habitat-Sim** 中确认能否在至少一个场景中获取 RGB、depth、pose、semantic，并跑一条最小轨迹。

默认优先级：
- 首选：HM3D 小规模可用 split（example / minival / 当前机器可获取的小体量版本）
- 次选：当前机器已有的 Habitat demo/test scene
- 若 Habitat 无法稳定跑通：按协议切换 Plan B，不自行改换其他仿真平台

### 子任务
- [x] T0.1 编写 `scripts/check_env.py`
- [x] T0.2 输出 `outputs/logs/env_report.md`
- [x] T0.3 在单个场景中跑 20~30 step 随机轨迹
- [x] T0.4 保存 RGB/depth/semantic 示例图
- [x] T0.5 保存一张 top-down 路径图 `outputs/figures/minimal_demo.png`

### 完成判定
- [x] 至少一个场景可稳定加载
- [x] 能获取 RGB、depth、semantic、pose
- [x] 能重复运行最小 demo

### 备注
- 使用的仿真平台：`Habitat-Lab / Habitat-Sim`
- 使用的场景/数据：`HM3D example full`；当前最小验证场景为 `data/versioned_data/hm3d-0.2/hm3d/example/00861-GLAQ4DNUx5U/GLAQ4DNUx5U.basis.glb`
- 输出路径：`scripts/check_env.py`, `outputs/logs/env_report.md`, `scripts/run_minimal_trajectory.py`, `outputs/runs/minimal_demo_trajectory.json`, `scripts/export_minimal_observations.py`, `outputs/figures/minimal_demo_rgb.png`, `outputs/figures/minimal_demo_depth.png`, `outputs/figures/minimal_demo_semantic.png`, `scripts/export_minimal_topdown_map.py`, `outputs/figures/minimal_demo.png`
- 阻塞情况：原有 Habitat 包与场景数据阻塞已解除；`outputs/logs/env_report.md` 当前结论为 `PLAN_A_READY`；`habitat_baselines` 尚未安装，但不影响 T0 最小轨迹验证

---

## T1 任务集生成
目标：生成至少 20 个简单任务，优先 room_exist / near_exist。

### 子任务
- [x] T1.1 编写 `scripts/generate_tasks.py`
- [x] T1.2 生成 `outputs/tasks/tasks.json`
- [x] T1.3 任务 yes/no 尽量平衡
- [x] T1.4 每个任务包含 GT answer

### 完成判定
- [x] 至少 20 个任务可用
- [x] 每条任务字段完整
- [x] 可被后续策略和回答器直接消费

### 备注
- 输出路径：`scripts/generate_tasks.py`, `scripts/validate_tasks.py`, `outputs/tasks/tasks.json`；验证预览：`outputs/runs/task_preview.json`；正式校验：`outputs/logs/task_validation.md`
- 任务模板：当前脚本同时支持 `room_exist` 与 `near_exist`。`room_exist` 使用 `region_object_keyword_heuristic` 从 region 内对象类别推断房间类别，`near_exist` 使用 `same_region_cooccurrence_heuristic`，以“同一 region 共现”作为最小近邻 GT。正式任务集当前共 `24` 条任务（`8` 条 `room_exist` + `16` 条 `near_exist`），yes/no 分布为 `12/12`，并已统一补充 `gt_answer_bool` 与 `task_spec` 字段，便于后续策略和回答器直接消费
- 人工核验辅助：`scripts/browse_scene.py` 可直接加载当前 HM3D 场景与 `outputs/tasks/tasks.json`，支持 `RGB/depth/semantic` 切换、任务切换、`H` 隐藏 HUD 与截图；当前默认浏览分辨率已提升到 `960x720`，HUD 改为更紧凑的左上角面板，已验证可导出更新后的预览图 `outputs/figures/scene_browser_preview.png`

---

## T2 最小空间记忆
目标：实现 occupancy / explored map 和 object memory table。

### 子任务
- [x] T2.1 实现 `src/memory/occupancy_map.py`
- [x] T2.2 实现 `src/memory/object_memory.py`
- [x] T2.3 导出 `outputs/runs/object_memory_dump.json`
- [x] T2.4 生成对象记忆可视化图

### 完成判定
- [x] 记忆可跨时间累积
- [x] occupancy map 可供 frontier 策略使用
- [x] object memory 可导出与复查

### 备注
- 输出路径：`src/memory/occupancy_map.py`, `src/memory/object_memory.py`, `scripts/export_object_memory_figure.py`, `outputs/runs/occupancy_map_summary.json`, `outputs/runs/object_memory_preview.json`, `outputs/runs/object_memory_dump.json`, `outputs/figures/object_memory_overview.png`
- 记忆字段：当前 `occupancy_map` 使用轨迹位置的 `x/z` 离散网格化，维护 `explored_cells / free_cells / occupied_cells / frontier_cells / visit_counts`；当前 `object_memory` 使用 HM3D GT semantic objects 的 `category / region_id / bbox center / bbox size`，并沿轨迹累计 `first_seen_step / last_seen_step / observation_count / observed_step_ids / min_distance_m`。当前正式 dump 已导出，包含 `25` 个 pose 更新、`37` 个累计观察到的对象、`21` 个对象类别；并已进一步生成 `outputs/figures/object_memory_overview.png`，在一张图里汇总 top-down 对象分布、类别计数和 first/last seen 时间线。当前对象记忆仍是基于对象中心与 FOV/radius 的几何可见性近似，不是逐像素语义融合

---

## T3 三种探索策略
目标：实现并跑通 random / frontier / task-aware。

### 子任务
- [x] T3.1 实现 `random_policy.py`
- [x] T3.2 实现 `frontier_policy.py`
- [x] T3.3 实现 `task_aware_policy.py`
- [x] T3.4 实现 `task_parser.py`
- [ ] T3.5 保存若干 episode rollout 与轨迹图

### 完成判定
- [ ] 三种策略使用统一接口
- [ ] 三种策略均可在同一任务集上批量跑通
- [ ] 日志可供评估脚本直接读取

### 备注
- 输出路径：`src/policies/__init__.py`, `src/policies/base_policy.py`, `src/policies/rollout_utils.py`, `src/policies/random_policy.py`, `src/policies/frontier_policy.py`, `src/policies/task_aware_policy.py`, `src/policies/task_parser.py`, `outputs/runs/random_policy_preview.json`, `outputs/runs/frontier_policy_preview.json`, `outputs/runs/task_aware_policy_preview.json`, `outputs/runs/task_parser_preview.json`
- 当前进展：已建立统一策略接口 `PolicyInput / PolicyDecision / BaseExplorationPolicy` 与 rollout 公共函数，并实现可直接运行的 `RandomPolicy`、`FrontierPolicy` 和 `TaskAwarePolicy`。同时已新增 `task_parser.py`，把原始任务标准化为统一的 `ParsedTask` 表示，显式输出 `relation / room_label / target_category / anchor_category / semantic_hints / room_keywords / hint_categories`；`task_aware_policy` 已改为消费该解析结果，而不是直接内联解析 `task_spec`。当前三条 smoke rollout 均复用首条正式任务与同一 HM3D scene：`random` 动作分布 `move_forward=11 / turn_left=9 / turn_right=4`、碰撞次数 `11`；`frontier` 动作分布 `move_forward=6 / turn_left=10 / turn_right=8`、碰撞次数 `6`；`task_aware` 动作分布 `move_forward=7 / turn_left=8 / turn_right=9`、碰撞次数进一步降为 `1`
- task-aware 打分形式：当前使用 `combined_score = observed_relevance_score + scene_prior_score - frontier_distance_penalty * frontier_distance`。其中 `observed_relevance_score` 来自已观察到的相关对象记忆，`scene_prior_score` 来自与 `task_spec` 关键词匹配的 GT semantic object 先验，最终仍沿用 `frontier` 的“对齐朝向 -> 前进 / 碰撞恢复”执行框架

---

## T4 两类回答器
目标：比较只看当前帧与使用历史记忆的效果。

### 子任务
- [ ] T4.1 实现 `current_frame_answerer.py`
- [ ] T4.2 实现 `memory_answerer.py`
- [ ] T4.3 保存每个任务的 predicted answer
- [ ] T4.4 保存回答证据摘要

### 完成判定
- [ ] 两类回答器接口统一
- [ ] 两类回答器可批量跑任务集
- [ ] 结果可直接统计准确率

### 备注
- 输出路径：
- 使用的回答规则：

---

## T5 评估、统计与作图
目标：生成开题可直接展示的图表与表格。

### 子任务
- [ ] T5.1 生成 `outputs/tables/table_policy_results.csv`
- [ ] T5.2 生成 `outputs/tables/table_memory_results.csv`
- [ ] T5.3 生成 `outputs/figures/fig_policy_comparison.png`
- [ ] T5.4 生成 `outputs/figures/fig_memory_comparison.png`
- [ ] T5.5 生成 `outputs/figures/fig_qualitative_paths.png`
- [ ] T5.6 生成 `outputs/figures/fig_failure_case.png`

### 完成判定
- [ ] 至少一个指标上 task-aware 优于 random
- [ ] 至少一个指标上 memory-assisted 优于 current-frame-only
- [ ] 图表可直接用于开题 PPT

### 备注
- 输出路径：
- 核心指标：

---

## T6 轻量三维重建演示（支线）
目标：用 RGB-D + pose 形成点云 / TSDF 可视化图。

### 子任务
- [ ] T6.1 编写 `scripts/build_pointcloud_demo.py`
- [ ] T6.2 导出 `outputs/runs/sceneX_recon.ply`
- [ ] T6.3 生成 `outputs/figures/fig_pointcloud_demo.png`

### 完成判定
- [ ] 至少一张清晰可展示的 3D 重建图
- [ ] 至少一个可复用的点云或 TSDF 文件

### 备注
- 输出路径：
- 使用工具：

---

## T7 收尾交付
目标：整理 README、总结与全部结果文件。

### 子任务
- [ ] T7.1 编写 `README.md`
- [ ] T7.2 编写 `outputs/final_summary.md`
- [ ] T7.3 检查所有图表是否齐全
- [ ] T7.4 检查所有表格是否齐全
- [ ] T7.5 检查可复现路径说明

### 完成判定
- [ ] 外部人员能按 README 跑主要实验
- [ ] 图、表、总结齐全
- [ ] 具备开题展示价值

### 备注
- 输出路径：
- 未完成项：

---

## Gate 状态
- [x] Gate 0：环境已可用（E0 完成）
- [ ] Gate 1：最小闭环跑通（T0 + T1 部分 + T2 + random 策略可从任务到回答跑通）
- [ ] Gate 2：探索策略对比跑通（T3 完成并有第一版对比表）
- [ ] Gate 3：记忆帮助对比跑通（T4 完成并有第一版对比表）
- [ ] Gate 4：开题交付包完成（T5 + T6 + T7 完成）
