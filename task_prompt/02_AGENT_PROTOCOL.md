# Coding Agent 执行协议

## 1. 你每次启动后的固定动作
每次开始工作时，严格执行以下顺序：

1. 读取 `00_PROJECT_BRIEF.md`
2. 读取 `00A_ENV_BOOTSTRAP.md`
3. 读取 `01_TASK_BOARD.md`
4. 读取 `04_STATUS.json`
5. 读取 `05_CHANGELOG.md`
6. 检查项目目录与 `outputs/` 已有文件
7. 判断当前应优先推进的任务包
8. 只执行一个主任务包，或一个主任务包中的一个可验证子任务

**不要依赖聊天上下文作为唯一信息源。工作空间文件才是事实来源。**

## 2. 环境优先规则
- 若 `Gate 0` 未完成，必须先执行 `E0 从零开始环境搭建`。
- 若已存在可用环境，也必须至少完成 E0 的探测、日志和 smoke test 子任务。
- 环境搭建优先使用非 root、本地、自包含方案。
- 若环境搭建需要 `sudo`、系统驱动、外网权限或大数据下载权限，而当前 agent 无法满足，必须立刻写入状态文件并上报。

## 3. 仿真平台选择规则
- 主路线仿真平台固定为 **Habitat-Lab / Habitat-Sim**。
- 主路线场景优先级固定为：**HM3D 小规模可用 split > 当前机器已有的 Habitat demo/test scene**。
- 若 Habitat 可跑通，则不得静默切换到 Isaac Sim、AI2-THOR、Gazebo 等其他平台。
- 只有在 Habitat 安装或场景依赖明确阻塞并已写入状态文件后，才允许切换到 **Plan B（离线 next-view ranking）**。

## 4. 完成任务后的固定动作
每完成一个可验证子任务，必须立刻：

1. 保存代码与结果文件
2. 更新 `01_TASK_BOARD.md` 中对应复选框
3. 更新 `04_STATUS.json`
4. 向 `05_CHANGELOG.md` 追加一条记录
5. 给出简短汇报

## 5. 汇报模板
每次汇报必须采用下面格式：

- 当前任务包：E0 / T?
- 当前子任务：E0.? / T?.?
- 完成情况：已完成 / 部分完成 / 阻塞
- 新增文件：...
- 关键结果：...
- 阻塞原因：...
- 下一步：...

## 6. 中断恢复规则
如果会话中断、网络断开或 agent 被重启，恢复时必须：

1. 忽略旧聊天上下文中的未落实描述
2. 重新读取控制文件
3. 以 `01_TASK_BOARD.md` 的打钩状态作为进度基准
4. 以 `04_STATUS.json` 的 `current_task` 和 `next_action` 作为优先动作
5. 若发现文件与聊天描述冲突，以文件为准

## 7. 阻塞处理规则
若任一子任务阻塞，执行下面策略：

- 阻塞 < 30 分钟：先自查和修复
- 阻塞 >= 30 分钟：更新 `04_STATUS.json` 的 `status=BLOCKED`
- 阻塞 >= 60 分钟：必须写出 fallback 方案并切到备选路径

对于环境阻塞，必须明确区分：
- 缺 Python/conda
- 缺网络
- 缺写权限
- 缺 root/sudo
- 缺 GPU/CUDA
- 缺场景数据

## 8. Plan B 启动条件
若 Habitat 或场景数据无法稳定跑通，立刻切换到离线 next-view ranking：

- 用一条已有轨迹或可生成轨迹
- 将前 t 帧作为当前记忆
- 从未来若干候选帧中选择下一眼
- 比较 random / frontier-like / task-aware
- 保留 object memory 和 memory-assisted 回答器

## 9. 设计原则
- 优先“跑通 + 出图 + 出表”
- 主链路优先于支线
- 小步提交，避免一次改太多
- 所有脚本可重复运行
- 所有结果写入 `outputs/`
- 所有假设写入 `outputs/final_summary.md`
