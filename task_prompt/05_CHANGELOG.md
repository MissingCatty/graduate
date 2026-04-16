# 变更日志

> 规则：每完成一个可验证子任务，追加一条记录。
> 格式建议：时间 / 任务 / 做了什么 / 新增文件 / 下一步

## 初始化
- 时间：待填写
- 任务：项目初始化
- 内容：创建控制文件、任务板、状态文件、交接提示。
- 新增文件：00_PROJECT_BRIEF.md, 00A_ENV_BOOTSTRAP.md, 01_TASK_BOARD.md, 02_AGENT_PROTOCOL.md, 03_HANDOFF_PROMPT.txt, 04_STATUS.json, 05_CHANGELOG.md
- 下一步：执行 E0 从零开始环境搭建

## 2026-04-16
- 时间：2026-04-16T18:22:20+08:00
- 任务：E0.1-E0.2
- 内容：读取环境搭建说明，完成宿主机探测，并生成首份环境探测日志。
- 新增文件：outputs/logs/bootstrap_probe.md
- 下一步：执行 E0.3，基于已探测到的 `conda`/`python3` 能力选择环境方案并创建项目环境

- 时间：2026-04-16T18:25:04+08:00
- 任务：E0.3
- 内容：核对 `conda` 可用性与现有环境后，确定采用 `conda + Python 3.10` 方案，并记录环境选择依据。
- 新增文件：outputs/logs/bootstrap_env.md
- 下一步：执行 E0.4，创建并激活 `opening_preexp` 环境

- 时间：2026-04-16T18:28:46+08:00
- 任务：E0.4
- 内容：尝试创建 `conda` 环境时遭遇 Anaconda 仓库 `SSL EOF` 错误，离线重试仍失败；随后回退到工作空间本地 `.venv`，并完成激活验证。
- 新增文件：无；更新 outputs/logs/bootstrap_env.md
- 下一步：执行 E0.5，创建项目目录结构

- 时间：2026-04-16T18:49:55+08:00
- 任务：E0.6
- 内容：检测到现成 `opening_preexp` conda 环境后，切回 conda 主路线；在该环境中安装了基础依赖与 `open3d`、`opencv-python`，并完成 import 验证。
- 新增文件：无；更新 outputs/logs/bootstrap_env.md
- 下一步：执行 E0.5，创建项目目录结构

- 时间：2026-04-16T18:53:45+08:00
- 任务：E0.5
- 内容：创建项目最小目录骨架，补齐 `configs/`、`scripts/`、`src/` 以及 `outputs` 下的 figures/tables/runs/tasks 子目录。
- 新增文件：无；新增目录 `configs/`, `scripts/`, `src/`, `outputs/figures/`, `outputs/tables/`, `outputs/runs/`, `outputs/tasks/`
- 下一步：执行 E0.7，确认并收口 `outputs/logs/bootstrap_env.md`

- 时间：2026-04-16T18:56:24+08:00
- 任务：E0.7
- 内容：复核并收口 `outputs/logs/bootstrap_env.md`，将其定稿为当前 conda 主路线的环境日志，并补充最终核对信息。
- 新增文件：无；更新 outputs/logs/bootstrap_env.md
- 下一步：执行 E0.8，导出 `pip freeze` 与 conda 环境快照

- 时间：2026-04-16T18:59:59+08:00
- 任务：E0.8
- 内容：导出依赖快照，生成 `requirements.txt`、`outputs/logs/pip_freeze.txt` 和 `outputs/logs/conda_env_export.yml`。
- 新增文件：requirements.txt, outputs/logs/pip_freeze.txt, outputs/logs/conda_env_export.yml
- 下一步：执行 E0.9，生成 `outputs/logs/bootstrap_smoketest.md`

- 时间：2026-04-16T19:01:48+08:00
- 任务：E0.9
- 内容：在 `opening_preexp` 环境中完成基础 import smoke test，并记录 Python 可执行路径与关键包版本。
- 新增文件：outputs/logs/bootstrap_smoketest.md
- 下一步：执行 E0.10，生成环境启动脚本

- 时间：2026-04-16T19:04:58+08:00
- 任务：E0.10
- 内容：生成可重复使用的 conda 环境启动脚本并完成激活验证；至此 E0 完成，Gate 0 完成，后续转入 T0。
- 新增文件：scripts/bootstrap_env.sh, scripts/activate_env.sh
- 下一步：执行 T0.1，编写 `scripts/check_env.py`

- 时间：2026-04-16T19:26:56+08:00
- 任务：T0.1
- 内容：编写 `scripts/check_env.py`，用于探测 Habitat-Lab / Habitat-Sim 模块与常见 HM3D / Habitat scene 数据路径；dry-run 当前显示 Habitat 包缺失且未发现本地场景数据。
- 新增文件：scripts/check_env.py
- 下一步：执行 T0.2，生成 `outputs/logs/env_report.md`

- 时间：2026-04-16T19:29:14+08:00
- 任务：T0.2
- 内容：运行 `scripts/check_env.py` 并生成正式环境报告；报告当前结论为 `BLOCKED_ON_HABITAT_PACKAGES`，且未发现本地 HM3D 或 Habitat demo/test scene。
- 新增文件：outputs/logs/env_report.md
- 下一步：先解除 Habitat 包阻塞，再继续推进 T0.3

- 时间：2026-04-16T19:49:03+08:00
- 任务：T0.3
- 内容：将 `opening_preexp` 运行时切换到 Habitat 官方兼容的 Python 3.9，安装 `habitat-sim 0.3.3` 与 `habitat-lab 0.3.3`，下载 `HM3D example full`，刷新 `outputs/logs/env_report.md` 为 `PLAN_A_READY`，并在单个 HM3D example 场景中跑通 24-step 随机轨迹，成功获取 RGB/depth/semantic 与 pose。
- 新增文件：scripts/run_minimal_trajectory.py, outputs/runs/minimal_demo_trajectory.json；更新 outputs/logs/env_report.md
- 下一步：执行 T0.4，保存 RGB/depth/semantic 示例图

- 时间：2026-04-16T19:57:04+08:00
- 任务：T0.4
- 内容：新增 `scripts/export_minimal_observations.py`，复用 `T0.3` 的最小轨迹结果和初始位姿，导出 HM3D example 场景的 RGB、归一化 depth 与伪彩色 semantic 示例图。
- 新增文件：scripts/export_minimal_observations.py, outputs/figures/minimal_demo_rgb.png, outputs/figures/minimal_demo_depth.png, outputs/figures/minimal_demo_semantic.png
- 下一步：执行 T0.5，生成 top-down 路径图 `outputs/figures/minimal_demo.png`

- 时间：2026-04-16T20:17:57+08:00
- 任务：T0.5
- 内容：新增 `scripts/export_minimal_topdown_map.py`，复用 `T0.3` 的最小轨迹和 HM3D example 场景，生成 top-down 路径图并标注起点、终点与随机轨迹。
- 新增文件：scripts/export_minimal_topdown_map.py, outputs/figures/minimal_demo.png
- 下一步：执行 T1.1，编写 `scripts/generate_tasks.py`

- 时间：2026-04-16T20:25:27+08:00
- 任务：T1.1
- 内容：新增 `scripts/generate_tasks.py`，基于当前可用 HM3D semantic GT 编写第一版任务生成器。脚本支持 `room_exist` 与 `near_exist` 两类 yes-no 任务，并把 GT 来源显式写入元数据；其中 `room_exist` 使用 region-object keyword heuristic，`near_exist` 使用 same-region co-occurrence heuristic。验证预览当前可生成 `24` 条任务。
- 新增文件：scripts/generate_tasks.py, outputs/runs/task_preview.json
- 下一步：执行 T1.2，生成 `outputs/tasks/tasks.json`

- 时间：2026-04-16T20:29:12+08:00
- 任务：T1.2
- 内容：运行 `scripts/generate_tasks.py` 生成正式任务文件 `outputs/tasks/tasks.json`。当前正式任务集包含 `24` 条任务，字段完整性检查通过，类型分布为 `room_exist=6`、`near_exist=18`，标签分布为 `yes=15`、`no=9`。
- 新增文件：outputs/tasks/tasks.json
- 下一步：执行 T1.3，调整 yes/no 分布并尽量保持任务类型覆盖

- 时间：2026-04-16T20:37:10+08:00
- 任务：T1.3
- 内容：更新 `scripts/generate_tasks.py` 的平衡采样逻辑，扩展房间候选类别，并刷新预览与正式任务文件。当前正式任务集仍为 `24` 条任务，但已调整为 `room_exist=8`、`near_exist=16`，标签分布达到 `yes=12`、`no=12`。
- 新增文件：无；更新 scripts/generate_tasks.py, outputs/runs/task_preview.json, outputs/tasks/tasks.json
- 下一步：执行 T1.4，确认每条任务都包含显式 `gt_answer` 与后续消费所需字段

- 时间：2026-04-16T20:44:18+08:00
- 任务：T1.4
- 内容：为任务生成器补充统一的 `task_spec` 与 `gt_answer_bool` 字段，刷新预览与正式任务文件，并新增 `scripts/validate_tasks.py` 对任务结构做正式校验。当前 `outputs/logs/task_validation.md` 结论为 `PASS`，`24` 条任务全部包含显式 GT answer，且可被后续策略和回答器直接消费。
- 新增文件：scripts/validate_tasks.py, outputs/logs/task_validation.md；更新 scripts/generate_tasks.py, outputs/runs/task_preview.json, outputs/tasks/tasks.json
- 下一步：执行 T2.1，实现 `src/memory/occupancy_map.py`

- 时间：2026-04-16T21:03:03+08:00
- 任务：T2.1
- 内容：新增 `src/memory/occupancy_map.py`，实现最小二维空间记忆，支持把 Habitat 轨迹位置离散到 `x/z` 网格并累计 `explored/free/occupied/frontier` 与 `visit_counts`。使用现有 `outputs/runs/minimal_demo_trajectory.json` 完成 smoke 验证，并导出 `outputs/runs/occupancy_map_summary.json`；当前摘要结果为 `25` 个位置、`43` 个 free cells、`20` 个 frontier cells。
- 新增文件：src/memory/occupancy_map.py, outputs/runs/occupancy_map_summary.json
- 下一步：执行 T2.2，实现 `src/memory/object_memory.py`

- 时间：2026-04-16T21:19:09+08:00
- 任务：T2.2
- 内容：新增 `src/memory/object_memory.py`，基于 HM3D GT semantic objects 和现有轨迹位姿实现最小对象记忆。该模块当前会过滤结构类对象，并按几何可见性近似累计 `category / region_id / bbox center / bbox size / first_seen_step / last_seen_step / observation_count / observed_step_ids / min_distance_m`。已导出预览 `outputs/runs/object_memory_preview.json`，当前结果包含 `37` 个累计观察到的对象、`21` 个对象类别。
- 新增文件：src/memory/object_memory.py, outputs/runs/object_memory_preview.json
- 下一步：执行 T2.3，导出正式 `outputs/runs/object_memory_dump.json`

- 时间：2026-04-16T21:25:34+08:00
- 任务：Support
- 内容：新增 `scripts/browse_scene.py` 作为人工核验当前 HM3D 场景任务答案的浏览工具。该脚本可加载 `00861-GLAQ4DNUx5U` 场景与 `outputs/tasks/tasks.json`，支持 `RGB/depth/semantic` 切换、任务切换、重置与截图；并已通过 `--snapshot-output` 模式导出预览图 `outputs/figures/scene_browser_preview.png`。
- 新增文件：scripts/browse_scene.py, outputs/figures/scene_browser_preview.png
- 下一步：恢复主线，继续执行 T2.3，导出正式 `outputs/runs/object_memory_dump.json`

- 时间：2026-04-16T21:33:40+08:00
- 任务：Support
- 内容：根据人工试用反馈优化 `scripts/browse_scene.py`。当前浏览器默认渲染分辨率提高到 `960x720`，不再只是放大低分辨率图像；同时将原先覆盖大面积顶部/底部的文字说明改为更紧凑的左上 HUD 和底部细提示条，并新增 `H` 键隐藏 HUD，减少对场景的遮挡。已重新生成更新后的预览图 `outputs/figures/scene_browser_preview.png`。
- 新增文件：无；更新 scripts/browse_scene.py, outputs/figures/scene_browser_preview.png
- 下一步：恢复主线，继续执行 T2.3，导出正式 `outputs/runs/object_memory_dump.json`

- 时间：2026-04-16T21:42:33+08:00
- 任务：Support
- 内容：新增根目录 `.gitignore`，按当前仓库实际情况忽略本地虚拟环境、下载数据、外部依赖克隆、`outputs/` 生成物、Python 缓存、编辑器临时文件以及本地记录文档，同时保留 `scripts/`、`src/`、`task_prompt/` 和 `requirements.txt` 等源码与控制文件可被跟踪。
- 新增文件：.gitignore
- 下一步：恢复主线，继续执行 T2.3，导出正式 `outputs/runs/object_memory_dump.json`

- 时间：2026-04-16T21:46:07+08:00
- 任务：Support
- 内容：新增仓库推送脚本 `scripts/push_repo.sh`。该脚本支持首次通过 `--remote-url` 配置 `origin`，后续默认执行一键 `git add -A`、按给定或自动生成的 message 提交，并推送当前分支；同时提供 `--skip-commit` 和 `--dry-run` 以便更安全地使用。已通过 `--help` 和 `--dry-run` 做无副作用验证。
- 新增文件：scripts/push_repo.sh
- 下一步：恢复主线，继续执行 T2.3，导出正式 `outputs/runs/object_memory_dump.json`

- 时间：2026-04-16T21:54:10+08:00
- 任务：T2.3
- 内容：使用现有 `src/memory/object_memory.py` 导出正式对象记忆文件 `outputs/runs/object_memory_dump.json`，并完成结构核对。当前正式 dump 包含 `37` 条对象记忆条目、`21` 个观察到的对象类别，以及 `25` 个 pose 更新；条目字段覆盖 `category / region_id / bbox / first_seen_step / last_seen_step / observation_count / observed_step_ids / min_distance_m`。
- 新增文件：outputs/runs/object_memory_dump.json
- 下一步：执行 T2.4，生成对象记忆可视化图

- 时间：2026-04-16T21:58:34+08:00
- 任务：T2.4
- 内容：新增 `scripts/export_object_memory_figure.py`，基于正式对象记忆 dump 和现有最小轨迹生成 `outputs/figures/object_memory_overview.png`。当前可视化图在单张画布中汇总了对象 top-down 分布、类别计数、以及对象的 first/last seen 时间线，便于人工复查对象记忆是否跨时间正确累积。至此 T2 完成。
- 新增文件：scripts/export_object_memory_figure.py, outputs/figures/object_memory_overview.png
- 下一步：执行 T3.1，实现 `random_policy.py`
