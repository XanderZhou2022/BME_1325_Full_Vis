# [Fullview Request] ward - 住院部床位扩容与初始医护人员配置

## Basic Info

- request_id: REQ-WARD-20260612-001
- request_type: room_update
- department_id: ward
- requested_by: 住院部组 / Group 2
- contact: 住院部组联调同学
- priority: high
- reason: 住院部联调时需要让远端 Fullview 与住院部后端资源配置一致；当前远端床位容量和初始住院部医护显示不符合住院部后端配置。
- expected_behavior: 5F 住院部每个专科只有 1 个病房；每个病房 10 张床；每个病房 1 名医生、2 名护士；两名护士分别负责前 5 张床和后 5 张床；页面初始状态能看到前台登记护士、护士长、护士站空闲护士和医生办公室医生。
- affected_departments: ["ward"]
- breaking_change: false

## Current Problem

远端 Fullview 页面里住院部床位数量不足，且初始页面没有按住院部后端配置展示住院部真实医生、护士、入院登记护士和护士长。

住院部后端会继续通过现有 API 发送患者、移动、查房、护士带检、转 ICU 等事件；但床位容量和初始医护人员需要 Fullview 端先在配置/seed 数据中存在。

## Submission Note

这份 request 是提交给 Fullview / UI 协作者的配置变更请求，不是住院部后端运行时直接发送的事件请求。

原因：

- 床位数量属于 `map-config.json`、房间资源、`room-state` 或服务器 seed database 的配置变更。
- 初始医生护士属于 `backend-data/staff.json` 或服务器 seed database 的人员数据变更。
- 当前 Fullview department API 支持 `patient_upsert`、`movement_request`、`transfer_request`、`discharge_request`、`clinical_event`，但没有开放 `staff_upsert` 或 `room_update`。

因此请 Fullview 维护者将本 request 中的 Room Change 和 Seed Staff Change 合入远端 Fullview 服务器配置/种子数据，并重新加载或重启 Fullview 后端。

## Backend Source Of Truth

请按住院部后端配置文件同步：

```text
F:\大学\大二下\模拟医院-2\config\ward_config.json
```

当前住院部后端配置已经调整为：

```json
{
  "default_beds_per_room": 10,
  "per_ward": {
    "room_count": 1,
    "beds_per_room": 10,
    "doctor_count": 2,
    "nurse_count": 4
  }
}
```

每个专科仍使用原有 ward code 和对应 Fullview 房间：

| ward code | dept | Fullview room_id | source room number |
|---|---|---|---:|
| RESP | 呼吸内科 | R-WARD-RESP | 101 |
| CARD | 心血管内科 | R-WARD-CARD | 111 |
| GASTRO | 消化内科 | R-WARD-GASTRO | 121 |
| NEURO | 神经内科 | R-WARD-NEURO | 131 |
| ENDO | 内分泌科 | R-WARD-ENDO | 141 |
| GENSURG | 普通外科 | R-WARD-GENSURG | 201 |
| ORTHO | 骨科 | R-WARD-ORTHO | 211 |
| OBGYN | 妇产科 | R-WARD-OBGYN | 221 |
| PED | 儿科 | R-WARD-PEDS | 231 |

## Room Change

请将以下 5F 住院部 9 个专科病房都调整为 10 张床。保持现有 `room_id`、位置、房间名称、科室、kind 和移动规则引用不变，仅更新容量、床位渲染资源和后端床位资源状态。

实现要求：

- 每个专科只有 1 个病房。
- 每个病房显示 10 张床，即使暂时没有患者占用。
- 床位 ID 按 Fullview 规范稳定生成：`{room_id}-bed-{nn}`。
- 示例：`R-WARD-RESP-bed-01` 到 `R-WARD-RESP-bed-10`，或保持现有系统同等命名规则。
- `GET /api/hospital/rooms` 中每个住院病房的 `beds` / `bedAssignments` / `bedIds` 应能反映 10 张床。
- 现有住院部移动规则不应因为扩容而改变。

### Room Change List

```json
[
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-RESP",
    "proposed_room_id": null,
    "display_name": "呼吸内科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "呼吸内科唯一病房；source room number 101。床位 ID：R-WARD-RESP-bed-01 到 R-WARD-RESP-bed-10。"
  },
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-CARD",
    "proposed_room_id": null,
    "display_name": "心血管内科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "心血管内科唯一病房；source room number 111。床位 ID：R-WARD-CARD-bed-01 到 R-WARD-CARD-bed-10。"
  },
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-GASTRO",
    "proposed_room_id": null,
    "display_name": "消化内科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "消化内科唯一病房；source room number 121。床位 ID：R-WARD-GASTRO-bed-01 到 R-WARD-GASTRO-bed-10。"
  },
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-NEURO",
    "proposed_room_id": null,
    "display_name": "神经内科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "神经内科唯一病房；source room number 131。床位 ID：R-WARD-NEURO-bed-01 到 R-WARD-NEURO-bed-10。"
  },
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-ENDO",
    "proposed_room_id": null,
    "display_name": "内分泌科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "内分泌科唯一病房；source room number 141。床位 ID：R-WARD-ENDO-bed-01 到 R-WARD-ENDO-bed-10。"
  },
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-GENSURG",
    "proposed_room_id": null,
    "display_name": "普通外科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "普通外科唯一病房；source room number 201。床位 ID：R-WARD-GENSURG-bed-01 到 R-WARD-GENSURG-bed-10。"
  },
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-ORTHO",
    "proposed_room_id": null,
    "display_name": "骨科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "骨科唯一病房；source room number 211。床位 ID：R-WARD-ORTHO-bed-01 到 R-WARD-ORTHO-bed-10。"
  },
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-OBGYN",
    "proposed_room_id": null,
    "display_name": "妇产科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "妇产科唯一病房；source room number 221。床位 ID：R-WARD-OBGYN-bed-01 到 R-WARD-OBGYN-bed-10。"
  },
  {
    "action": "update",
    "floor_id": 5,
    "room_id": "R-WARD-PEDS",
    "proposed_room_id": null,
    "display_name": "儿科病房",
    "department_id": "ward",
    "kind": "ward",
    "protected": false,
    "layout": {
      "placement": "keep_existing"
    },
    "capacity": {
      "beds": 10,
      "max_beds": 10
    },
    "items": [
      {
        "type": "bed",
        "count": 10
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "儿科唯一病房；source room number 231。床位 ID：R-WARD-PEDS-bed-01 到 R-WARD-PEDS-bed-10。"
  }
]
```

## Seed Staff Change

当前公开 department request 类型不包含 `staff_upsert`。请 Fullview 维护者在 `full_view/backend-data/staff.json` 或远端服务器 seed database 中确认/补充住院部 seed staff。若已存在相同 `employeeId` / `staff_id`，请按下面规则更新，不要生成重复人员。

生成规则必须与住院部后端一致：

```text
医生 staff_id / employeeId: DOCTOR_{code}_01
医生 name: {dept}医生{index:02d}
每个专科 index: 01

护士 staff_id / employeeId: NURSE_{code}_{index:02d}
护士 name: {dept}护士{index:02d}
每个专科 index: 01..02
```

总量：

- 普通病区医生：9 个专科 * 1 = 9 名
- 普通病区护士：9 个专科 * 2 = 18 名
- 入院登记护士：1 名，`NURSE_01`
- 护士长：1 名，`CHARGE_NURSE_01`

医护初始位置：

- `NURSE_01`：`R-WARD-WARD-ADMISSION`
- `CHARGE_NURSE_01`：`R-WARD-NURSE-STATION`
- 所有 `NURSE_{code}_{01..02}`：`R-WARD-NURSE-STATION`
- 所有 `DOCTOR_{code}_01`：`R-WARD-DOCTOR-OFFICE`

护士床位责任映射：

- `NURSE_{code}_01` 负责该专科唯一病房的 01-05 床。
- `NURSE_{code}_02` 负责该专科唯一病房的 06-10 床。
- 示例：`NURSE_RESP_01` 负责 `R-WARD-RESP` 的 01-05 床；`NURSE_RESP_02` 负责 `R-WARD-RESP` 的 06-10 床。
- 责任映射需要与住院部后端 `ward_config.json` 生成结果一致。

示例：

```json
[
  {
    "action": "add_or_update",
    "employeeId": "NURSE_01",
    "staff_id": "NURSE_01",
    "type": "nurse",
    "role": "nurse",
    "name": "医院前台登记护士",
    "department": "住院部入院登记",
    "department_id": "ward",
    "roomId": "R-WARD-WARD-ADMISSION",
    "room_id": "R-WARD-WARD-ADMISSION",
    "pose": "standing",
    "available": true
  },
  {
    "action": "add_or_update",
    "employeeId": "CHARGE_NURSE_01",
    "staff_id": "CHARGE_NURSE_01",
    "type": "nurse",
    "role": "nurse",
    "name": "病区护士长",
    "department": "住院部",
    "department_id": "ward",
    "roomId": "R-WARD-NURSE-STATION",
    "room_id": "R-WARD-NURSE-STATION",
    "pose": "standing",
    "available": true
  },
  {
    "action": "add_or_update",
    "employeeId": "DOCTOR_RESP_01",
    "staff_id": "DOCTOR_RESP_01",
    "type": "doctor",
    "role": "doctor",
    "name": "呼吸内科医生01",
    "department": "呼吸内科",
    "department_id": "ward",
    "ward_code": "RESP",
    "roomId": "R-WARD-DOCTOR-OFFICE",
    "room_id": "R-WARD-DOCTOR-OFFICE",
    "pose": "standing",
    "available": true
  },
  {
    "action": "add_or_update",
    "employeeId": "NURSE_RESP_01",
    "staff_id": "NURSE_RESP_01",
    "type": "nurse",
    "role": "nurse",
    "name": "呼吸内科护士01",
    "department": "呼吸内科",
    "department_id": "ward",
    "ward_code": "RESP",
    "roomId": "R-WARD-NURSE-STATION",
    "room_id": "R-WARD-NURSE-STATION",
    "pose": "standing",
    "available": true
  }
]
```

请按同样规则为 9 个专科全部生成，不要只创建示例人员。

### 完整 Staff ID 列表

#### 入院登记与护士长

| employeeId | staff_id | name | type | roomId | notes |
|---|---|---|---|---|---|
| NURSE_01 | NURSE_01 | 医院前台登记护士 | nurse | R-WARD-WARD-ADMISSION | 入院登记护士 |
| CHARGE_NURSE_01 | CHARGE_NURSE_01 | 病区护士长 | nurse | R-WARD-NURSE-STATION | 护士长 |

#### 各专科医生 (每个专科 1 名)

| employeeId | staff_id | name | type | roomId | ward_code |
|---|---|---|---|---|---|
| DOCTOR_RESP_01 | DOCTOR_RESP_01 | 呼吸内科医生01 | doctor | R-WARD-DOCTOR-OFFICE | RESP |
| DOCTOR_CARD_01 | DOCTOR_CARD_01 | 心血管内科医生01 | doctor | R-WARD-DOCTOR-OFFICE | CARD |
| DOCTOR_GASTRO_01 | DOCTOR_GASTRO_01 | 消化内科医生01 | doctor | R-WARD-DOCTOR-OFFICE | GASTRO |
| DOCTOR_NEURO_01 | DOCTOR_NEURO_01 | 神经内科医生01 | doctor | R-WARD-DOCTOR-OFFICE | NEURO |
| DOCTOR_ENDO_01 | DOCTOR_ENDO_01 | 内分泌科医生01 | doctor | R-WARD-DOCTOR-OFFICE | ENDO |
| DOCTOR_GENSURG_01 | DOCTOR_GENSURG_01 | 普通外科医生01 | doctor | R-WARD-DOCTOR-OFFICE | GENSURG |
| DOCTOR_ORTHO_01 | DOCTOR_ORTHO_01 | 骨科医生01 | doctor | R-WARD-DOCTOR-OFFICE | ORTHO |
| DOCTOR_OBGYN_01 | DOCTOR_OBGYN_01 | 妇产科医生01 | doctor | R-WARD-DOCTOR-OFFICE | OBGYN |
| DOCTOR_PED_01 | DOCTOR_PED_01 | 儿科医生01 | doctor | R-WARD-DOCTOR-OFFICE | PED |

#### 各专科护士 (每个专科 2 名)

| employeeId | staff_id | name | type | roomId | ward_code | 负责床位 |
|---|---|---|---|---|---|---|
| NURSE_RESP_01 | NURSE_RESP_01 | 呼吸内科护士01 | nurse | R-WARD-NURSE-STATION | RESP | 01-05 |
| NURSE_RESP_02 | NURSE_RESP_02 | 呼吸内科护士02 | nurse | R-WARD-NURSE-STATION | RESP | 06-10 |
| NURSE_CARD_01 | NURSE_CARD_01 | 心血管内科护士01 | nurse | R-WARD-NURSE-STATION | CARD | 01-05 |
| NURSE_CARD_02 | NURSE_CARD_02 | 心血管内科护士02 | nurse | R-WARD-NURSE-STATION | CARD | 06-10 |
| NURSE_GASTRO_01 | NURSE_GASTRO_01 | 消化内科护士01 | nurse | R-WARD-NURSE-STATION | GASTRO | 01-05 |
| NURSE_GASTRO_02 | NURSE_GASTRO_02 | 消化内科护士02 | nurse | R-WARD-NURSE-STATION | GASTRO | 06-10 |
| NURSE_NEURO_01 | NURSE_NEURO_01 | 神经内科护士01 | nurse | R-WARD-NURSE-STATION | NEURO | 01-05 |
| NURSE_NEURO_02 | NURSE_NEURO_02 | 神经内科护士02 | nurse | R-WARD-NURSE-STATION | NEURO | 06-10 |
| NURSE_ENDO_01 | NURSE_ENDO_01 | 内分泌科护士01 | nurse | R-WARD-NURSE-STATION | ENDO | 01-05 |
| NURSE_ENDO_02 | NURSE_ENDO_02 | 内分泌科护士02 | nurse | R-WARD-NURSE-STATION | ENDO | 06-10 |
| NURSE_GENSURG_01 | NURSE_GENSURG_01 | 普通外科护士01 | nurse | R-WARD-NURSE-STATION | GENSURG | 01-05 |
| NURSE_GENSURG_02 | NURSE_GENSURG_02 | 普通外科护士02 | nurse | R-WARD-NURSE-STATION | GENSURG | 06-10 |
| NURSE_ORTHO_01 | NURSE_ORTHO_01 | 骨科护士01 | nurse | R-WARD-NURSE-STATION | ORTHO | 01-05 |
| NURSE_ORTHO_02 | NURSE_ORTHO_02 | 骨科护士02 | nurse | R-WARD-NURSE-STATION | ORTHO | 06-10 |
| NURSE_OBGYN_01 | NURSE_OBGYN_01 | 妇产科护士01 | nurse | R-WARD-NURSE-STATION | OBGYN | 01-05 |
| NURSE_OBGYN_02 | NURSE_OBGYN_02 | 妇产科护士02 | nurse | R-WARD-NURSE-STATION | OBGYN | 06-10 |
| NURSE_PED_01 | NURSE_PED_01 | 儿科护士01 | nurse | R-WARD-NURSE-STATION | PED | 01-05 |
| NURSE_PED_02 | NURSE_PED_02 | 儿科护士02 | nurse | R-WARD-NURSE-STATION | PED | 06-10 |

## Staff ID Mapping Requirement

住院部后端会在远程事件中直接发送真实 Agent ID：

- 医生查房：例如 `DOCTOR_RESP_01`
- 护士执行医嘱/带检：例如 `NURSE_RESP_01`
- 入院登记护士：`NURSE_01`
- 护士长：`CHARGE_NURSE_01`

请 Fullview 服务器能够识别这些 ID。不要只支持 `N-WD-001` / `D-WD-001` 这类占位 ID。如果 Fullview Core 内部仍需要短标准 ID，请在服务器侧添加兼容映射，但不要要求住院部后端替换真实 Agent ID。

## Rule Change

N/A

本次不新增或删除 rule。住院部继续使用现有规则：

- `WARD_ADMISSION_TO_BED`
- `WARD_TO_DIAGNOSTIC_MOVE`
- `WARD_DIAGNOSTIC_RETURN`
- `WARD_NURSE_ORDER_VISIT`
- `WARD_DOCTOR_ROUND_VISIT`
- `TRANSFER_WARD_TO_ICU`

## Test Cases

### Accepted

```json
{
  "case_id": "ACCEPT-001",
  "event_id": "WARD_ADMISSION_TO_BED",
  "patient_id": "P-1234abcd",
  "from_room_id": "R-WARD-WARD-ADMISSION",
  "to_room_id": "R-WARD-RESP",
  "expected": "accepted",
  "reason": "R-WARD-RESP has 10 available beds after the room capacity update."
}
```

```json
{
  "case_id": "ACCEPT-002",
  "event_id": "WARD_NURSE_ORDER_VISIT",
  "patient_id": "P-1234abcd",
  "staff_id": "NURSE_RESP_01",
  "from_room_id": "R-WARD-NURSE-STATION",
  "to_room_id": "R-WARD-RESP",
  "return_room_id": "R-WARD-NURSE-STATION",
  "expected": "accepted",
  "reason": "NURSE_RESP_01 exists in staff seed data and is a ward nurse."
}
```

```json
{
  "case_id": "ACCEPT-003",
  "event_id": "WARD_DOCTOR_ROUND_VISIT",
  "patient_id": "P-1234abcd",
  "staff_id": "DOCTOR_RESP_01",
  "from_room_id": "R-WARD-DOCTOR-OFFICE",
  "to_room_id": "R-WARD-RESP",
  "return_room_id": "R-WARD-DOCTOR-OFFICE",
  "expected": "accepted",
  "reason": "DOCTOR_RESP_01 exists in staff seed data and is a ward doctor."
}
```

### Rejected

```json
{
  "case_id": "REJECT-001",
  "event_id": "WARD_ADMISSION_TO_BED",
  "patient_id": "P-1234abcd",
  "from_room_id": "R-WARD-WARD-ADMISSION",
  "to_room_id": "R-WARD-NOT-EXIST",
  "expected": "rejected",
  "reason_code": "TARGET_ROOM_NOT_FOUND",
  "reason": "目标病房不存在。"
}
```

```json
{
  "case_id": "REJECT-002",
  "event_id": "WARD_NURSE_ORDER_VISIT",
  "patient_id": "P-1234abcd",
  "staff_id": "DOCTOR_RESP_01",
  "from_room_id": "R-WARD-DOCTOR-OFFICE",
  "to_room_id": "R-WARD-RESP",
  "expected": "rejected",
  "reason_code": "STAFF_ROLE_MISMATCH",
  "reason": "WARD_NURSE_ORDER_VISIT 必须使用护士 staff。"
}
```

## Reviewer Notes

由 Fullview 维护者填写：

- reviewed_by:
- decision: `accepted | rejected | need_more_info`
- implementation_notes:
- files_to_update:
  - `full_view/map-config.json`
  - `full_view/backend-data/room-state.json`
  - `full_view/backend-data/staff.json`
  - any server-side seed database / deployed backend data used by the remote Fullview server
- validation_result:
