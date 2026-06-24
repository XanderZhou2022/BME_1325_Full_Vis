# Fullview 变更请求格式规范

本文档用于规范各 department 向 Fullview 核心系统提交变更请求的格式。适用场景包括：

- 新增、删除、重命名或调整房间。
- 新增、减少或调整病床、桌椅、设备等房间资源。
- 新增、修改或删除患者移动规则。
- 新增跨 department 流程，例如门诊转 ICU、急诊转住院、ICU 去检查、住院患者出院。

核心原则：department 不直接修改 Fullview 的 `map-config.json` 或 `event-rules/*.json`。各组先按本文档提交标准化 request，由 Fullview 维护者审核后统一更新地图、规则和后端数据。

## 1. 提交方式

推荐提交为 GitHub Issue、飞书/腾讯文档表单或 Markdown 文档。每个 request 应该只描述一个清晰变更。如果一个业务流程同时需要新增房间和新增规则，可以放在同一个 request 中，但必须分成 `Room Change` 和 `Rule Change` 两部分。

推荐文件名或标题格式：

```text
[Fullview Request] {department_id} - {short_summary}
```

示例：

```text
[Fullview Request] outpatient - 新增呼吸内科诊室与门诊分诊规则
```

## 2. 统一字段

所有 request 都必须包含以下基础信息。

| 字段 | 必填 | 说明 | 示例 |
|---|---|---|---|
| `request_id` | 是 | 请求唯一 ID，由提交方生成 | `REQ-OP-20260612-001` |
| `request_type` | 是 | 请求类型 | `room_update` / `rule_update` / `room_and_rule_update` |
| `department_id` | 是 | 提交 department | `outpatient` |
| `requested_by` | 是 | 提交人或小组 | `门诊组` |
| `contact` | 是 | 联系方式 | `name@example.com` |
| `priority` | 是 | 优先级 | `low` / `normal` / `high` |
| `reason` | 是 | 为什么需要这个变更 | `新增呼吸方向患者流转` |
| `expected_behavior` | 是 | 变更后系统应该如何表现 | `患者分诊后可进入呼吸内科诊室` |
| `affected_departments` | 是 | 受影响 department | `["outpatient", "lab"]` |
| `breaking_change` | 是 | 是否会影响现有流程 | `false` |

## 3. Request 总模板

复制以下模板填写。

````markdown
## Basic Info

- request_id:
- request_type:
- department_id:
- requested_by:
- contact:
- priority:
- reason:
- expected_behavior:
- affected_departments:
- breaking_change:

## Current Problem

请描述当前 Fullview 中缺少什么、哪里不符合 department 业务。

## Room Change

如果没有房间变更，填写 `N/A`。

### Room Change List

```json
[
  {
    "action": "add | update | delete",
    "floor_id": 2,
    "room_id": "existing_room_id_or_empty_for_new_room",
    "proposed_room_id": "respiratory_consult_2",
    "display_name": "Respiratory Consult",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "desk",
        "count": 1
      }
    ],
    "migration": {
      "current_patients_action": "none | move_to_room | discharge_required",
      "target_room_id": null
    },
    "notes": ""
  }
]
```

## Rule Change

如果没有规则变更，填写 `N/A`。

### Rule Change List

```json
[
  {
    "action": "add | update | delete",
    "category": "outpatient",
    "event_id": "OP_TRIAGE_TO_RESP_CONSULT",
    "name": "门诊分诊后前往呼吸内科诊室",
    "description": "门诊患者完成分诊后进入呼吸内科诊室",
    "movement": {
      "schema": "patient-move",
      "from": "triage_2",
      "to": "respiratory_consult_2",
      "via": [],
      "transport": "walking",
      "patientFormDuringMove": "walking",
      "finalForm": "consultation",
      "escortRequired": false,
      "escortRoles": [],
      "equipment": [],
      "resourcePolicy": {
        "retainSourceBed": false,
        "releaseSourceBed": false
      },
      "queuePolicy": {
        "whenTargetBusy": "queue",
        "queueRoomId": "outpatient_waiting"
      }
    },
    "allowed_sources": ["triage_2", "outpatient_waiting"],
    "allowed_targets": ["respiratory_consult_2"],
    "reject_conditions": [
      "target consultation room already occupied and queue is disabled"
    ],
    "notes": ""
  }
]
```

## Test Cases

请至少提供 1 个 accepted case 和 1 个 rejected case。

### Accepted

```json
{
  "event_id": "OP_TRIAGE_TO_RESP_CONSULT",
  "patient_id": "P-OP-001",
  "from_room_id": "triage_2",
  "to_room_id": "respiratory_consult_2",
  "expected": "accepted"
}
```

### Rejected

```json
{
  "event_id": "OP_TRIAGE_TO_RESP_CONSULT",
  "patient_id": "P-OP-001",
  "from_room_id": "pharmacy_2",
  "to_room_id": "respiratory_consult_2",
  "expected": "rejected",
  "reason_code": "SOURCE_NOT_ALLOWED"
}
```

## Reviewer Notes

由 Fullview 维护者填写：

- reviewed_by:
- decision: `accepted | rejected | need_more_info`
- implementation_notes:
- files_to_update:
- validation_result:
````

## 4. 房间变更规范

### 4.1 房间 action

| action | 用途 |
|---|---|
| `add` | 新增房间 |
| `update` | 修改房间名称、布局、容量、家具、保护状态 |
| `delete` | 删除房间 |

### 4.2 房间 ID

新增房间可以由提交方提供 `proposed_room_id`，但最终 ID 由 Fullview 维护者确认，必须满足：

- 全院唯一。
- 使用 lowercase slug。
- 不使用空格和中文。
- 语义稳定，不要包含临时序号或个人姓名。

推荐：

```text
respiratory_consult_2
icu_stepdown_beds
ward_resp_isolation
```

不推荐：

```text
room_new
张三诊室
test_room_1
```

### 4.3 `kind` 标准

`kind` 用来决定房间业务类型和渲染样式。

| kind | 说明 |
|---|---|
| `entrance` | 入口 |
| `registration` | 登记/挂号 |
| `triage` | 分诊 |
| `waiting` | 等候区 |
| `consultation` | 普通诊室 |
| `internal_medicine` | 内科诊室 |
| `surgery` | 外科诊室 |
| `pediatrics` | 儿科诊室 |
| `fever` | 发热门诊 |
| `obgyn` | 妇产科 |
| `lab` | 检验/检查 |
| `pharmacy` | 药房 |
| `icu` | ICU 床位房 |
| `ward` | 住院病房 |
| `nurse_station` | 护士站 |
| `doctor_office` | 医生办公室 |
| `elevator` | 电梯 |
| `mdt` | MDT 会诊相关房间 |

如果需要新 `kind`，必须在 request 中说明：

```json
{
  "new_kind": "respiratory_consult",
  "reason": "门诊需要呼吸专科诊室颜色和统计分类",
  "fallback_kind": "consultation"
}
```

### 4.4 布局字段

`layout` 使用地图网格坐标，不使用屏幕像素。

```json
{
  "x": 45,
  "y": 17,
  "w": 11,
  "h": 8
}
```

如果提交方不知道具体位置，可以写：

```json
{
  "placement": "auto",
  "preferred_area": "near outpatient waiting",
  "w": 11,
  "h": 8
}
```

Fullview 维护者会在地图编辑器中安排实际位置。

### 4.5 床位字段

有床房间必须写明：

```json
{
  "capacity": {
    "beds": 4,
    "max_beds": 4
  }
}
```

床位 ID 由 Fullview 自动生成：

```text
{room_id}-bed-{nn}
```

例如：

```text
icu_beds_a-bed-01
resp_ward-bed-03
```

注意：ICU 和住院部患者临时去检查时，原床位必须保留，不能被其他患者占用。

### 4.6 保护房间

以下房间原则上不能删除或随意移动：

- 电梯。
- 入口。
- 核心登记/分诊节点。
- 已被多条 rule 使用的关键路径房间。

如果必须修改，request 必须写明影响范围：

```json
{
  "protected_change_reason": "需要调整电梯附近路径避免地图重叠",
  "affected_rules": ["ED_TO_ICU_MOVE", "OP_TO_WARD_MOVE"],
  "migration_plan": "保持 room_id 不变，仅调整 layout"
}
```

## 5. Rule 变更规范

### 5.1 Rule action

| action | 用途 |
|---|---|
| `add` | 新增移动规则 |
| `update` | 修改已有规则的来源、目标、运输方式、资源要求 |
| `delete` | 删除规则 |

### 5.2 `event_id` 标准

`event_id` 必须：

- 全院唯一。
- 使用大写 snake case。
- 清楚表达来源和目标。
- 一旦被 department 使用，不应频繁改名。

推荐格式：

```text
{SOURCE}_{ACTION}_{TARGET}
```

示例：

```text
OP_TRIAGE_TO_CONSULT_ROOM
ED_TO_ICU_MOVE
ICU_TO_WARD_MOVE
WARD_TO_DIAGNOSTIC_MOVE
WARD_PATIENT_EXIT_HOSPITAL
```

### 5.3 `movement` 字段

每条患者移动规则必须包含 `movement`。

```json
{
  "schema": "patient-move",
  "from": "current_op_room",
  "to": "target_ward_room",
  "via": ["elevator_2", "elevator_5"],
  "transport": "stretcher",
  "patientFormDuringMove": "stretcher",
  "finalForm": "bed",
  "escortRequired": true,
  "escortRoles": ["porter"],
  "equipment": ["transport_bed"],
  "resourcePolicy": {
    "retainSourceBed": false,
    "releaseSourceBed": true
  }
}
```

### 5.4 来源与目标

`from` 和 `to` 可以使用具体 `room_id`，也可以使用 symbolic source/target。

常用 symbolic 字段：

| 字段 | 含义 |
|---|---|
| `current_room` | 患者当前房间 |
| `current_ed_room` | 当前急诊房间 |
| `current_op_room` | 当前门诊房间 |
| `current_consult_room` | 当前诊室 |
| `current_icu_bed_room` | 当前 ICU 床位房 |
| `current_ward_room` | 当前住院病房 |
| `source_icu_bed_room` | 患者已分配的 ICU 床位房 |
| `source_ward_room` | 患者已分配的住院床位房 |
| `target_ward_room` | 任意可用住院病房 |

如果 request 使用新的 symbolic 字段，必须说明它的判定逻辑。

### 5.5 运输方式

| transport | 使用场景 |
|---|---|
| `walking` | 患者自己走，常用于门诊普通移动 |
| `wheelchair` | 需要轮椅转运 |
| `stretcher` | 躺床或推床转运 |

标准约束：

- 门诊普通候诊、分诊、缴费、药房可以 `walking`。
- 急诊转 ICU/住院原则上使用 `stretcher` 或 `wheelchair`，不能让患者自己走。
- ICU/住院患者去检查或干预，如果不是出院，原则上使用 `stretcher` 或 `wheelchair`。
- 只要 `transport` 不是 `walking`，一般需要 `escortRoles` 包含 `porter`。

### 5.6 最终显示形态

| finalForm | 前端展示 |
|---|---|
| `walking` | 站立/行走患者 |
| `waiting` | 等候患者 |
| `consultation` | 患者与医生问诊 |
| `stretcher` | 推床/担架患者 |
| `bed` | 躺在 ICU/病房床上 |
| `hidden` | 离院或不在地图显示 |

### 5.7 队列策略

如果目标房间是诊室或资源有限房间，应明确队列策略。

```json
{
  "queuePolicy": {
    "whenTargetBusy": "queue",
    "queueRoomId": "outpatient_waiting",
    "maxQueueLength": null,
    "autoAdvance": true
  }
}
```

推荐标准：

- 诊室已有患者时，不允许直接进入。
- 后端把患者放入该诊室队列。
- 前一个患者离开后，队列第一位自动进入诊室。

### 5.8 资源策略

涉及床位时必须写 `resourcePolicy`。

```json
{
  "resourcePolicy": {
    "retainSourceBed": true,
    "releaseSourceBed": false,
    "reserveTargetBed": false
  }
}
```

常见场景：

| 场景 | retainSourceBed | releaseSourceBed | finalForm |
|---|---:|---:|---|
| ICU 患者去检查 | true | false | `stretcher` 或返回 `bed` |
| 住院患者去检查 | true | false | `stretcher` 或返回 `bed` |
| 急诊转 ICU | false | true | `bed` |
| 门诊转住院 | false | true | `bed` |
| 住院患者出院 | false | true | `hidden` |

## 6. Accepted / Rejected 标准

每条 rule request 必须给出测试用例。

### 6.1 Accepted case

必须说明为什么应该通过：

```json
{
  "case_id": "ACCEPT-001",
  "event_id": "ED_TO_ICU_MOVE",
  "patient_id": "P-ER-001",
  "from_room_id": "ed_red_resus",
  "to_room_id": "icu_admission",
  "expected": "accepted",
  "reason": "患者在急诊抢救室，目标 ICU 有空床，规则允许急诊转 ICU"
}
```

### 6.2 Rejected case

必须说明应拒绝原因：

```json
{
  "case_id": "REJECT-001",
  "event_id": "ED_TO_ICU_MOVE",
  "patient_id": "P-ER-001",
  "from_room_id": "pharmacy_2",
  "to_room_id": "icu_admission",
  "expected": "rejected",
  "reason_code": "SOURCE_NOT_ALLOWED",
  "reason": "患者不在急诊区域，不能使用急诊转 ICU 规则"
}
```

## 7. 完整示例

下面是一个完整 request 示例。

````markdown
## Basic Info

- request_id: REQ-OP-20260612-001
- request_type: room_and_rule_update
- department_id: outpatient
- requested_by: 门诊组
- contact: outpatient-team@example.com
- priority: normal
- reason: 需要新增呼吸内科诊室，支持慢性咳嗽患者进入专科问诊
- expected_behavior: 门诊患者完成分诊后，如果分配到呼吸方向，可以从 triage_2 或 outpatient_waiting 移动到 Respiratory Consult
- affected_departments: ["outpatient"]
- breaking_change: false

## Current Problem

当前 2F 门诊只有普通 Consultation A/B、Internal Med、Surgery、Pediatrics、Fever、OB-GYN，缺少呼吸专科诊室。门诊组希望新增一个房间，并增加分诊到呼吸诊室的移动规则。

## Room Change

```json
[
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "respiratory_consult_2",
    "display_name": "Respiratory Consult",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "placement": "auto",
      "preferred_area": "near Consultation A/B",
      "w": 11,
      "h": 8
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "desk",
        "count": 1
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "需要支持问诊患者和医生同屏显示"
  }
]
```

## Rule Change

```json
[
  {
    "action": "add",
    "category": "outpatient",
    "event_id": "OP_TRIAGE_TO_RESP_CONSULT",
    "name": "门诊分诊后前往呼吸内科诊室",
    "description": "慢性咳嗽或呼吸相关患者完成分诊后进入呼吸内科诊室",
    "movement": {
      "schema": "patient-move",
      "from": ["triage_2", "outpatient_waiting"],
      "to": "respiratory_consult_2",
      "via": [],
      "transport": "walking",
      "patientFormDuringMove": "walking",
      "finalForm": "consultation",
      "escortRequired": false,
      "escortRoles": [],
      "equipment": [],
      "resourcePolicy": {
        "retainSourceBed": false,
        "releaseSourceBed": false
      },
      "queuePolicy": {
        "whenTargetBusy": "queue",
        "queueRoomId": "outpatient_waiting",
        "autoAdvance": true
      }
    },
    "allowed_sources": ["triage_2", "outpatient_waiting"],
    "allowed_targets": ["respiratory_consult_2"],
    "reject_conditions": [
      "patient is not in triage_2 or outpatient_waiting",
      "target room id does not exist"
    ],
    "notes": ""
  }
]
```

## Test Cases

### Accepted

```json
{
  "case_id": "ACCEPT-001",
  "event_id": "OP_TRIAGE_TO_RESP_CONSULT",
  "patient_id": "P-OP-001",
  "from_room_id": "triage_2",
  "to_room_id": "respiratory_consult_2",
  "expected": "accepted"
}
```

### Rejected

```json
{
  "case_id": "REJECT-001",
  "event_id": "OP_TRIAGE_TO_RESP_CONSULT",
  "patient_id": "P-OP-001",
  "from_room_id": "pharmacy_2",
  "to_room_id": "respiratory_consult_2",
  "expected": "rejected",
  "reason_code": "SOURCE_NOT_ALLOWED"
}
```
````

## 8. Fullview 维护者审核清单

维护者收到 request 后，按以下清单审核。

### 8.1 房间审核

- `room_id` 是否全院唯一。
- `floor_id` 是否符合医院楼层设计。
- `department_id` 是否存在。
- `kind` 是否已支持，或是否提供 fallback。
- 房间是否会覆盖电梯、走廊关键点或其他房间。
- 如果删除房间，是否仍有患者、医生、护士、床位或 rule 引用。
- 如果新增床位，`bed_id` 是否能稳定生成。

### 8.2 Rule 审核

- `event_id` 是否全院唯一。
- `from` 和 `to` 是否引用有效房间或已支持 symbolic 字段。
- `transport` 是否符合临床场景。
- 非 walking 转运是否配置 `porter`。
- ICU/住院患者临时外出是否保留床位。
- 诊室/有限资源房间是否配置队列策略。
- 是否提供 accepted/rejected 测试用例。

### 8.3 更新文件

根据 request 类型，可能更新：

```text
full_view/map-config.json
full_view/event-rules/*.json
rules/event-rules/*.json
full_view/backend-data/room-state.json
full_view/HOSPITAL_CORE_STANDARD.md
rules/README.md
```

如果新增字段或新 `kind`，必须同步更新规范文档。

## 9. 不接受的 request

以下 request 通常会被退回：

- 只写“帮我们加一个房间”，没有 floor、department、用途。
- 只写“患者从 A 到 B”，没有 event_id、transport、finalForm。
- 直接要求 department 修改 Fullview JSON，而没有说明业务场景。
- 新规则绕过床位、护工、诊室占用等已有资源约束。
- 删除保护房间或关键路径房间，但没有迁移计划。
- 使用不稳定 ID，例如 `room1`、`new_test`、`doctor_wang_room`。

## 10. 最小可提交版本

如果时间紧，至少提交以下内容：

```markdown
## Basic Info

- request_id:
- request_type:
- department_id:
- requested_by:
- reason:
- expected_behavior:

## Change

要新增/修改/删除的房间或 rule 是什么？

## Required Fields

- floor_id:
- room_id / proposed_room_id:
- event_id:
- from_room_id:
- to_room_id:
- transport:
- finalForm:

## Test

- accepted case:
- rejected case:
```

信息不完整时，Fullview 维护者可以先标记为 `need_more_info`，不直接修改核心系统。
