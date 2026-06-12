# 住院部 Fullview 医护移动接口说明

本文只说明住院部后端已经提供的 Fullview 事件接口，供 UI 协作者在 `BME_1325_Full_Vis-main` 中补动画规则和前端渲染。住院部侧不直接修改 Fullview 前端仓库。

## 1. 事件读取入口

Fullview 继续轮询：

```text
GET /api/hospital/events?after=<eventSeq>
```

事件均来自：

```text
visual_logs/fullview_event_log.json
```

现有患者移动仍使用 `animationPlan`。新增医护移动使用 `staffMovePlan`，旧前端不识别该字段时仍可通过 `snapshotRefresh` 刷新位置。

## 2. 患者去检查中心

触发点：护士提交辅助检查申请。

```json
{
  "accepted": true,
  "eventId": "WARD_TO_DIAGNOSTIC_MOVE",
  "patientId": "PATIENT_xxx",
  "animationPlan": {
    "kind": "patient-move",
    "transport": "stretcher",
    "fromRoomId": "card_ward",
    "toRoomId": "diagnostic_center",
    "viaRoomIds": [],
    "finalForm": "stretcher",
    "patientFormDuringMove": "stretcher",
    "porterId": "NURSE_CARD_01",
    "porterReturn": {
      "roomId": "diagnostic_center",
      "floor": 5,
      "x": 0,
      "y": 0,
      "tileX": 0,
      "tileY": 0
    }
  }
}
```

语义：护士带患者从所属病房去 `diagnostic_center`。检查期间原床位不应释放。

## 3. 检查后返回病房

触发点：护士收到 `DIAGNOSTIC_RESULT` 或 `DIAGNOSTIC_RESULT_NOTICE`。

```json
{
  "accepted": true,
  "eventId": "WARD_DIAGNOSTIC_RETURN",
  "patientId": "PATIENT_xxx",
  "animationPlan": {
    "kind": "patient-move",
    "transport": "stretcher",
    "fromRoomId": "diagnostic_center",
    "toRoomId": "card_ward",
    "viaRoomIds": [],
    "finalForm": "bed",
    "patientFormDuringMove": "stretcher",
    "porterId": "NURSE_CARD_01",
    "porterReturn": {
      "roomId": "nurse_station",
      "floor": 5,
      "x": 0,
      "y": 0,
      "tileX": 0,
      "tileY": 0
    }
  }
}
```

语义：患者从检查中心回原病房床位，护士最终回护士站。

## 4. 护士执行医嘱去病房

触发点：护士执行 `EXECUTE_IMMEDIATE`，或查询患者记录 / 护理任务。

```json
{
  "accepted": true,
  "eventId": "WARD_NURSE_ORDER_VISIT",
  "patientId": "PATIENT_xxx",
  "staffId": "NURSE_CARD_01",
  "snapshotRefresh": true,
  "staffMovePlan": {
    "kind": "staff-visit",
    "staffId": "NURSE_CARD_01",
    "fromRoomId": "nurse_station",
    "toRoomId": "card_ward",
    "returnRoomId": "nurse_station",
    "patientId": "PATIENT_xxx",
    "durationSeconds": 8,
    "reason": "nurse execute_immediate"
  }
}
```

期望 UI 行为：护士从 `nurse_station` 移动到患者所属 ward room，停留短时间，完成后回 `nurse_station`。如果暂不做路径动画，也可以先根据 snapshot 显示护士短暂出现在病房。

## 5. 医生查房去病房

触发点：医生向患者发送查房问诊消息，或医生工具触发患者相关医嘱。

```json
{
  "accepted": true,
  "eventId": "WARD_DOCTOR_ROUND_VISIT",
  "patientId": "PATIENT_xxx",
  "staffId": "DOCTOR_CARD_01",
  "snapshotRefresh": true,
  "staffMovePlan": {
    "kind": "staff-visit",
    "staffId": "DOCTOR_CARD_01",
    "fromRoomId": "doctor_office",
    "toRoomId": "card_ward",
    "returnRoomId": "doctor_office",
    "patientId": "PATIENT_xxx",
    "durationSeconds": 9,
    "reason": "doctor ward round"
  }
}
```

期望 UI 行为：医生从 `doctor_office` 移动到患者所属 ward room，查房后回办公室。

## 6. 房间约定

住院部患者病房目前是科室聚合房间：

```text
RESP -> resp_ward
CARD -> card_ward
GASTRO -> gastro_ward
NEURO -> neuro_ward
ENDO -> endo_ward
GENSURG -> gensurg_ward
ORTHO -> ortho_ward
OBGYN -> obgyn_ward
PED -> peds_ward
```

固定医护房间：

```text
护士默认位置: nurse_station
医生默认位置: doctor_office
检查中心: diagnostic_center
```

## 7. 建议新增规则

UI 侧可新增两类规则：

- `WARD_NURSE_ORDER_VISIT`：staff-visit，护士站到患者病房再回护士站。
- `WARD_DOCTOR_ROUND_VISIT`：staff-visit，医生办公室到患者病房再回医生办公室。

患者带检可以复用已有：

- `WARD_TO_DIAGNOSTIC_MOVE`
- `WARD_DIAGNOSTIC_RETURN`

但建议 UI 侧识别 `animationPlan.porterId`，让指定护士作为 escort/porter 参与患者移动，并根据 `porterReturn` 返回目标位置。
