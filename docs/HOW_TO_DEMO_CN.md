# org.system 现场使用说明（中文操作卡）

## 1. 启动

打开 PowerShell，逐行执行：

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
python -m pip install -r requirements.txt
$env:ORG_SYSTEM_LLM_MODE="mock"
python -m uvicorn app.main:app --reload --port 8000
```

浏览器打开：`http://127.0.0.1:8000`

也可以直接双击项目根目录的 `START_DEMO.cmd`，结束时双击 `STOP_DEMO.cmd`。

## 2. 上台前 30 秒

1. 点击右上角 **Reset demo**。
2. 确认左上角状态显示 **Team memory online**。
3. 确认人员下拉框顺序为 Tom、Sarah、Mei，当前选择 Sarah。
4. 建议比赛现场使用 mock 模式：语言有兜底，但检索、存储、验证、权限、回放和统计仍然真实执行。

## 3. 2 分 55 秒完整获奖演示

### A. Sarah 沉淀失败经验

人员选择 **Sarah**，在输入框粘贴并发送：

```text
We embedded 8 TB of Kubernetes logs for semantic incident search. The completed run consumed 148 GPU-hours but improved accuracy by only 3%. The better path is to sample 5%, cluster recurring log fingerprints, and set a go/no-go quality gate before scaling.
```

讲解重点：没有“保存知识”按钮。任务结果通过自然语言进入系统，后端真实蒸馏、验证并写入团队经验。

### B. Tom 用不同说法提出相似创新

人员切换为 **Tom**，粘贴并发送：

```text
I want to vectorize a month of cluster diagnostics using our accelerator capacity. Should I run it at full scale?
```

讲解重点：这句话没有照抄 Sarah 的关键词。右侧 receipt 会显示混合匹配分数和 **Semantic vector cosine**，并保留 Sarah 的署名、验证结论与 SHA-256 receipt。

### C. 真实回放证据

点击右侧 **Replay evidence in isolated process**。

必须看到：

```text
[SUCCESS] prior result reproduced in an isolated process
```

这不是终端动画。后端启动独立 Python 进程，重新生成指标并逐项比较；缺指标会失败关闭。

### D. Tom 提出没有历史数据的新实验

Tom 继续输入：

```text
I want to test content-addressed dependency caching in our CI pipeline. Has the team tried this before?
```

系统应显示 **No verified prior data**，并允许 Tom 开展带基线、成功指标和测试门槛的小规模实验。

### E. Tom 完成实验后记录正向结果

```text
We completed the CI cache experiment. Content-addressed dependency layer caching improved build time from 18 minutes to 7 minutes, and all tests passed. Restore the cache before compilation.
```

系统应自动沉淀 Tom 的成功经验，并记录节省 11 分钟及 tests passed。

### F. Mei 后来命中 Tom 的经验

切换 Mei，输入：

```text
I want to speed up CI builds by caching dependency layers. Should I implement it from scratch?
```

右侧 receipt 的 Origin 应为 **Tom**，指标显示 18 min → 7 min，避免重复实施 11 min。

### G. 证明这是组织系统，不是聊天机器人

依次点击顶部：

1. **My value**：个人贡献与知识来源归因。
2. **Team map**：谁知道什么、真实复用次数、拦截任务和 148 GPUh；Tom 的 CI receipt 另显示避免重复实施 11 min。
3. **Trust center**：验证状态、复验队列、审计事件、权限策略和 Codex 接入。

## 4. 在 Codex 中证明真实接入

项目已经包含 `.codex/config.toml` 和 `AGENTS.md`。把 `C:\Users\BitAltas\Documents\GitHub\Org_system` 作为可信项目重新打开/重启 Codex，然后输入一个资源消耗很大的工作计划。Codex 会按照项目规则优先调用 `avoid_duplicate_work`。

也可在终端确认：

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system
codex mcp list
```

如果项目级配置没有被当前会话重新加载，执行：

```powershell
codex mcp add org-system -- python C:\Users\BitAltas\Documents\GitHub\Org_system\backend\mcp_stdio.py
```

## 5. 最终自检

后端测试：

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
python -m unittest discover -s tests -v
```

保持服务运行，另开终端执行：

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-test.ps1
```

## 6. 仍必须由你本人完成的提交动作

- 在本次主要 Codex 任务里运行 `/feedback`，保存真实 Session ID。
- 录制并公开不超过三分钟的视频。
- 填入真实仓库 URL 和视频 URL。
- 在比赛允许时间内提交最终 Git commit。

这些证据不能由代码伪造；缺少它们会让完成度很高的产品失去参赛资格或可信度。
