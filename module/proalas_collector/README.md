# ProalasCollector

Alas Scheduler 定时采集资源快照，写入 **`./config/{config_name}.json` → `ProalasData.GameResource`**（及 `ResourceHistory` 时序）。

**TimerPlan bundle** 在 AI 规划前串行调用本任务（`skip_task_delay`）。

## 配置项

| 项 | 说明 |
|----|------|
| ReadOilCoin | 从 Alas 日志读取石油/物资/钻石 |
| ReadEventPt | OCR 活动 PT |
| ReadBuildCube | 建造页 OCR 魔方 |
| ReadBoatDock | **主动进船坞** OCR 占用/上限 → `BoatDock` / `BoatMax` |
| ReadBoatRate | 收藏率（内部 `ProalasBoatMessage`，应在 ReadBoatDock 之后） |
| WriteUserData | 写入 `ProalasData.GameResource` |

## 已收拢 / 隐藏

| 原独立任务 | 现状 |
|------------|------|
| `ProalasBoatMessage`（采集收藏率） | 并入 `ReadBoatRate`；Scheduler 关闭；侧栏隐藏 |
| `ProalasGetExpUseExp`（经验书） | 侧栏隐藏、Scheduler 关闭；属 S4 执行，**不**并入采集 |

`UserDataPath` 已废弃并从 WebUI 隐藏。
