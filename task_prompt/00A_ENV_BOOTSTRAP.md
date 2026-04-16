# E0 从零开始环境搭建说明（给 coding agent）

> 目标：在工作空间内构建一个可重复、可记录、尽量不依赖 root 权限的最小实验环境。
> 只有 E0 完成后，才进入 T0 及后续任务。

## E0 总原则
- 先检查，再安装；先最小化，再扩展。
- 优先使用现有工具链：`python3` / `pip` / `conda`。
- 若没有 `conda` 但有 `python3`，优先使用 `venv`。
- 若两者都没有，但允许联网安装，则本地安装 Miniforge 到工作空间。
- 若缺少系统权限、外网权限或 GPU 驱动，必须写入状态文件并上报。

## E0 推荐执行顺序

### E0.1 宿主机探测
必须记录：
- 操作系统与版本
- shell 类型
- `python3 --version`
- `pip --version`
- `conda --version`（如果有）
- `git --version`
- `nvidia-smi`（如果有 GPU）
- 当前目录可写性
- 当前是否可联网（最小测试即可）

输出：
- `outputs/logs/bootstrap_probe.md`

### E0.2 选择环境方案
按优先顺序选择：
1. 若已有可用 conda：创建 `opening_preexp` 环境
2. 否则若已有 `python3`：创建 `.venv`
3. 否则若允许联网：本地安装 Miniforge 到 `.tools/miniforge3`
4. 若以上都不满足：标记 BLOCKED，并写出用户需要补齐的最小条件

必须在 `outputs/logs/bootstrap_env.md` 中记录选用方案与理由。

### E0.3 建立项目目录
若项目目录不存在，创建以下最小结构：
- `configs/`
- `scripts/`
- `src/`
- `outputs/logs/`
- `outputs/figures/`
- `outputs/tables/`
- `outputs/runs/`
- `outputs/tasks/`

### E0.4 安装基础依赖
优先安装最小基础依赖：
- `pip`
- `setuptools`
- `wheel`
- `pyyaml`
- `numpy`
- `pandas`
- `matplotlib`
- `pillow`
- `tqdm`

若成功，再安装可选依赖：
- `open3d`
- `opencv-python`

仿真依赖（Habitat 等）不要在 E0 一开始强装；先完成基础环境和最小 smoke test，再按 T0 需要逐步安装。

### E0.5 导出依赖文件
生成并保存：
- `requirements.txt`（若还没有则创建）
- `outputs/logs/pip_freeze.txt`
- 如使用 conda，额外保存 `outputs/logs/conda_env_export.yml`

### E0.6 环境冒烟测试
至少测试以下 import：
- `python`
- `yaml`
- `numpy`
- `pandas`
- `matplotlib`
- `PIL`
- `open3d`（若已安装）

输出：
- `outputs/logs/bootstrap_smoketest.md`

### E0.7 生成启动脚本
至少生成一个可重复使用的环境启动脚本：
- `scripts/bootstrap_env.sh`
- 若使用 venv，补充 `scripts/activate_env.sh`
- 若使用 conda，补充环境激活说明

### E0.8 完成判定
只有满足以下条件，E0 才算完成：
- 能进入可用 Python 环境
- 能运行基础 import
- 关键目录已创建
- 环境日志、freeze 文件、启动脚本都已落盘
- 后续 T0 可在此基础上继续推进

## 阻塞与 fallback
若 E0 阻塞，必须区分阻塞类型：
1. **无 Python/conda**
2. **无网络，无法下载依赖**
3. **无写权限**
4. **需要 root/sudo 才能安装系统包**
5. **GPU 驱动或 CUDA 不可用**

若属于 1~4 且当前 agent 无法自行解决，必须：
- 更新 `04_STATUS.json`
- 在 `05_CHANGELOG.md` 记录阻塞
- 明确告诉用户最小补齐动作

## 推荐最小安装策略
### 方案 A：已有 python3
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install pyyaml numpy pandas matplotlib pillow tqdm
pip install open3d opencv-python
```

### 方案 B：已有 conda
```bash
conda create -y -n opening_preexp python=3.10
conda activate opening_preexp
python -m pip install --upgrade pip setuptools wheel
pip install pyyaml numpy pandas matplotlib pillow tqdm
pip install open3d opencv-python
```

### 方案 C：本地 Miniforge（仅在允许联网时）
在工作空间本地安装，不写系统路径，并在日志中记录安装目录与激活方式。

## E0 完成后必须更新
- `01_TASK_BOARD.md`：勾选 E0 完成项
- `04_STATUS.json`：推进到 T0
- `05_CHANGELOG.md`：追加一条环境搭建完成记录
