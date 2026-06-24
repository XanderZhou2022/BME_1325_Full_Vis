# 门诊诊室瞬移修复说明

## 基准

本次以 `frontend/fullview_ref/fullview/full_view` 作为标准前端基准。

以下共享逻辑保持与标准前端一致：

- `main.js`
- `pathfinding.js`
- `runtime.js`
- `hospital-api.js`
- Fullview 公共事件规则和事件序列化逻辑

此前添加的门诊 `durationSeconds`、患者动态限速和动画起点重建方案均已撤回。

## 根因

标准地图中的门诊队列与诊室紧贴。多数队列宽度覆盖整个诊室出口，同时队列只有朝向诊室的入口，座椅还占用了出口通道。

患者离开部分诊室前往缴费处时，标准 `createRoomPath()` 返回 `null`。标准前端随后执行快照回退，因此患者直接出现在后端目标房间，表现为瞬移。

## 前端必要改动

仅修改 `full_view/map-config.json`：

- 将 12 个专科门口队列宽度由 `12.2` 缩短至 `7.2`。
- 为这些队列增加右侧出口。
- 移除堵住出口的第二张椅子。
- 将诊断中心队列移出诊断中心门口，避免阻断 payment → lab 和 lab → 专科队列。
- 将外科处置室 desk 从底部门口移至房间上方，恢复队列 → 手术床及手术床 → 专科队列路径。

未修改动画速度、事件监听、快照处理或寻路算法。

## 门诊后端调整

`FULLVIEW_VISUAL_COOLDOWN_MULTIPLIER` 默认值和本地配置由 `2.0` 恢复为 `1.0`。

串行 outbox、Fullview accepted gate 和基础事件冷却仍保留，避免同一患者的事件无序发送。

## 自动测试

测试文件：

`full_view/tests/outpatient-path-regression.mjs`

测试直接加载标准前端使用的：

- `map.js`
- `runtime.js`
- `pathfinding.js`
- `map-config.json`

它验证 14 个门诊诊室及 payment、pharmacy、lab、外科处置流程满足：

1. 对应门口队列可以进入诊室。
2. 诊室可以寻路到缴费处。
3. 诊室可以寻路到 pharmacy 和外科处置队列。
4. payment 可以进入 lab，lab 可以返回所有专科队列。
5. 外科队列可以进入每张手术床，手术床可以返回所有专科队列。
6. 不会进入 `No route found` 的快照瞬移分支。

运行：

```powershell
& '<node.exe>' frontend/fullview/full_view/tests/outpatient-path-regression.mjs
```

验证结果：

- `fullview_ref`：失败，可复现 `R-OP-SURGERY -> R-OP-PAYMENT` 不可达。
- 修复后：通过，14 个诊室及 67 条 payment/pharmacy/procedure 路径均可达。
