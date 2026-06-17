# [Fullview Request] outpatient - 重构 2F 门诊房间设计并改为门口排队模式

## Basic Info

- request_id: REQ-FV-20260617-001
- request_type: room_and_rule_update
- department_id: outpatient
- requested_by: hospital runtime / frontend integration
- contact: jangb
- priority: high
- reason: 当前 Fullview 2F 门诊层缺少多个专科诊室，现有设计也不适合表达“一个大科室下面有多个接诊位置”和“所有排队都在目标房间门口等待”的模式。另外，检验区域命名希望统一为 `diagnostic_center`，外科还需要一个独立的门诊手术室。
- expected_behavior: 2F Outpatient 取消统一总候诊区的活跃规则角色；所有科室和检查房都使用各自门口排队锚点；需要双医生接诊的科室提供两个接诊位置；外科新增一个带 2 个床位的门诊手术室；原 `lab_2` 按 5F `diagnostic_center` 的设计命名和风格重做为 `diagnostic_center_2`。
- affected_departments: ["outpatient", "internal", "surgery", "obgyn", "pediatrics", "fever", "ophthalmology", "ent", "dentistry", "dermatology", "psychiatry", "rehabilitation", "pain"]
- breaking_change: false

## Current Problem

当前 Fullview 2F 已包含以下门诊相关房间：

- `registration_2`
- `payment_2`
- `triage_2`
- `consultation_a_2`
- `consultation_b_2`
- `internal_2`
- `surgery_2`
- `pediatrics_2`
- `fever_2`
- `obgyn_2`
- `lab_2`
- `pharmacy_2`
- `doctor_entry_2`
- `outpatient_waiting`
- `elevator_2`

当前前端与业务需求之间存在以下问题：

- `ophthalmology`、`ent`、`dentistry`、`dermatology`、`psychiatry`、`rehabilitation`、`pain` 没有对应专科诊室。
- 当前房间设计更接近“一间房只表达一个接诊点”，不适合表达大科室下的多个接诊位置。
- `internal` 和 `surgery` 需要双医生并行接诊，因此都应有 2 个可独立占用的接诊位置。
- `surgery` 还需要一个独立门诊手术室，靠近外科诊室，并包含 2 个床位。
- 当前 `outpatient_waiting` 是统一总候诊区，但本次希望取消统一总候诊区的排队逻辑；任何原因导致的等待，都应放在目标房间或目标科室门口。
- 当前 `lab_2` 的命名和视觉表达不符合本次期望，应该改成 `diagnostic_center_2`，并参考 5F `diagnostic_center` 的设计。

## Room Change

### Room Change List

```json
[
  {
    "action": "delete",
    "floor_id": 2,
    "room_id": "outpatient_waiting",
    "proposed_room_id": null,
    "display_name": "OP Waiting",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "remove_from_active_flow"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "取消统一总候诊区，不再作为门诊排队或候诊规则节点使用。"
  },
  {
    "action": "update",
    "floor_id": 2,
    "room_id": "lab_2",
    "proposed_room_id": "diagnostic_center_2",
    "display_name": "Diagnostic Center",
    "department_id": "outpatient",
    "kind": "lab",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "keep_current",
      "preferred_area": "same footprint as current lab_2"
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
    "notes": "将 2F 检验/检查房统一命名为 diagnostic center；设计可参考 5F 的 diagnostic_center。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "ophthalmology_consult_2",
    "display_name": "Ophthalmology",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "near existing 2F specialty consultation rooms"
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
    "notes": "新增眼科接诊房间。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "ent_consult_2",
    "display_name": "Otolaryngology",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "near existing 2F specialty consultation rooms"
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
    "notes": "新增耳鼻喉科接诊房间。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "dentistry_consult_2",
    "display_name": "Dentistry",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "near existing 2F specialty consultation rooms"
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
    "notes": "新增口腔科接诊房间。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "dermatology_consult_2",
    "display_name": "Dermatology",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "near existing 2F specialty consultation rooms"
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
    "notes": "新增皮肤科接诊房间。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "psychiatry_consult_2",
    "display_name": "Psychiatry",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "quiet side of 2F outpatient if possible"
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
    "notes": "新增精神科接诊房间，尽量放在更安静的位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "rehabilitation_consult_2",
    "display_name": "Rehabilitation Medicine",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "near outpatient circulation path with easy access"
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
    "notes": "新增康复医学科接诊房间。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "pain_consult_2",
    "display_name": "Pain Management",
    "department_id": "outpatient",
    "kind": "consultation",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "near existing 2F specialty consultation rooms"
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
    "notes": "新增疼痛科接诊房间。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "internal_consult_b_2",
    "display_name": "Internal Medicine B",
    "department_id": "outpatient",
    "kind": "internal_medicine",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "near internal_2"
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
    "notes": "内科需要 2 个接诊位置；这是其中一个位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "surgery_consult_b_2",
    "display_name": "Surgery B",
    "department_id": "outpatient",
    "kind": "surgery",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "near surgery_2"
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
    "notes": "外科需要 2 个接诊位置；这是其中一个位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "surgery_procedure_2",
    "display_name": "Surgery Procedure Room",
    "department_id": "outpatient",
    "kind": "surgery",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "auto",
      "preferred_area": "adjacent to surgery_2 and surgery_consult_b_2"
    },
    "capacity": {
      "beds": 2,
      "max_beds": 2
    },
    "items": [
      {
        "type": "bed",
        "count": 2
      },
      {
        "type": "desk",
        "count": 1
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "新增外科门诊手术室，靠近外科诊室，包含 2 个床位。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "internal_queue_2",
    "display_name": "Internal Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside internal_2 and internal_consult_b_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "内科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "surgery_queue_2",
    "display_name": "Surgery Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside surgery_2, surgery_consult_b_2, and surgery_procedure_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "外科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "pediatrics_queue_2",
    "display_name": "Pediatrics Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside pediatrics_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "儿科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "fever_queue_2",
    "display_name": "Fever Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside fever_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "发热门诊门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "obgyn_queue_2",
    "display_name": "OB-GYN Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside obgyn_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "妇产科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "ophthalmology_queue_2",
    "display_name": "Ophthalmology Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside ophthalmology_consult_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "眼科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "ent_queue_2",
    "display_name": "ENT Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside ent_consult_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "耳鼻喉科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "dentistry_queue_2",
    "display_name": "Dentistry Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside dentistry_consult_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "口腔科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "dermatology_queue_2",
    "display_name": "Dermatology Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside dermatology_consult_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "皮肤科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "psychiatry_queue_2",
    "display_name": "Psychiatry Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside psychiatry_consult_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "精神科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "rehabilitation_queue_2",
    "display_name": "Rehabilitation Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside rehabilitation_consult_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "康复医学科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "pain_queue_2",
    "display_name": "Pain Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside pain_consult_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "疼痛科门口排队位置。"
  },
  {
    "action": "add",
    "floor_id": 2,
    "room_id": null,
    "proposed_room_id": "diagnostic_center_queue_2",
    "display_name": "Diagnostic Queue",
    "department_id": "outpatient",
    "kind": "waiting",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 7,
      "h": 4,
      "placement": "auto",
      "preferred_area": "immediately outside diagnostic_center_2"
    },
    "capacity": {
      "beds": 0,
      "max_beds": 0
    },
    "items": [
      {
        "type": "chair",
        "count": 2
      }
    ],
    "migration": {
      "current_patients_action": "none",
      "target_room_id": null
    },
    "notes": "检查中心门口排队位置。"
  },
  {
    "action": "update",
    "floor_id": 2,
    "room_id": "internal_2",
    "proposed_room_id": "internal_2",
    "display_name": "Internal Medicine A",
    "department_id": "outpatient",
    "kind": "internal_medicine",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "keep_current"
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
    "notes": "内科需要 2 个接诊位置；这是其中一个位置。"
  },
  {
    "action": "update",
    "floor_id": 2,
    "room_id": "surgery_2",
    "proposed_room_id": "surgery_2",
    "display_name": "Surgery A",
    "department_id": "outpatient",
    "kind": "surgery",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "keep_current"
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
    "notes": "外科需要 2 个接诊位置；这是其中一个位置。"
  },
  {
    "action": "update",
    "floor_id": 2,
    "room_id": "pediatrics_2",
    "proposed_room_id": "pediatrics_2",
    "display_name": "Pediatrics",
    "department_id": "outpatient",
    "kind": "pediatrics",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "keep_current"
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
    "notes": "保留现有房间，并在门口增加排队位置。"
  },
  {
    "action": "update",
    "floor_id": 2,
    "room_id": "obgyn_2",
    "proposed_room_id": "obgyn_2",
    "display_name": "OB-GYN",
    "department_id": "outpatient",
    "kind": "obgyn",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "keep_current"
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
    "notes": "保留现有房间，并在门口增加排队位置。"
  },
  {
    "action": "update",
    "floor_id": 2,
    "room_id": "fever_2",
    "proposed_room_id": "fever_2",
    "display_name": "Fever Clinic",
    "department_id": "outpatient",
    "kind": "fever",
    "protected": false,
    "layout": {
      "x": null,
      "y": null,
      "w": 11,
      "h": 8,
      "placement": "keep_current"
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
    "notes": "保留现有房间，并在门口增加排队位置。"
  }
]
```

## Rule Change

### Rule Change List

```json
[
  {
    "action": "add",
    "category": "outpatient",
    "event_id": "OP_TRIAGE_TO_SPECIALTY_CONSULT",
    "name": "门诊分诊后进入目标诊室",
    "description": "当目标科室或目标房间仍有可用接诊位置时，患者从 triage_2 直接进入目标诊室。",
    "movement": {
      "schema": "patient-move",
      "from": "triage_2",
      "to": [
        "internal_2",
        "internal_consult_b_2",
        "surgery_2",
        "surgery_consult_b_2",
        "surgery_procedure_2",
        "pediatrics_2",
        "fever_2",
        "obgyn_2",
        "ophthalmology_consult_2",
        "ent_consult_2",
        "dentistry_consult_2",
        "dermatology_consult_2",
        "psychiatry_consult_2",
        "rehabilitation_consult_2",
        "pain_consult_2",
        "diagnostic_center_2"
      ],
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
      }
    },
    "allowed_sources": ["triage_2"],
    "allowed_targets": [
      "internal_2",
      "internal_consult_b_2",
      "surgery_2",
      "surgery_consult_b_2",
      "surgery_procedure_2",
      "pediatrics_2",
      "fever_2",
      "obgyn_2",
      "ophthalmology_consult_2",
      "ent_consult_2",
      "dentistry_consult_2",
      "dermatology_consult_2",
      "psychiatry_consult_2",
      "rehabilitation_consult_2",
      "pain_consult_2",
      "diagnostic_center_2"
    ],
    "reject_conditions": [
      "target room has no free slot or no free bed",
      "target room does not exist"
    ],
    "notes": "适用于首次分诊后的目标房间进入。"
  },
  {
    "action": "add",
    "category": "outpatient",
    "event_id": "OP_CURRENT_TO_TARGET_DOOR_QUEUE",
    "name": "任何等待都去目标房间门口排队",
    "description": "无论是初诊、复诊、检查前等待还是诊室已满，只要目标房间当前不可进入，患者都移动到目标房间对应的门口排队位置。",
    "movement": {
      "schema": "patient-move",
      "from": "current_room",
      "to": [
        "internal_queue_2",
        "surgery_queue_2",
        "pediatrics_queue_2",
        "fever_queue_2",
        "obgyn_queue_2",
        "ophthalmology_queue_2",
        "ent_queue_2",
        "dentistry_queue_2",
        "dermatology_queue_2",
        "psychiatry_queue_2",
        "rehabilitation_queue_2",
        "pain_queue_2",
        "diagnostic_center_queue_2"
      ],
      "via": [],
      "transport": "walking",
      "patientFormDuringMove": "walking",
      "finalForm": "waiting",
      "escortRequired": false,
      "escortRoles": [],
      "equipment": [],
      "resourcePolicy": {
        "retainSourceBed": false,
        "releaseSourceBed": false
      }
    },
    "allowed_sources": ["current_room"],
    "allowed_targets": [
      "internal_queue_2",
      "surgery_queue_2",
      "pediatrics_queue_2",
      "fever_queue_2",
      "obgyn_queue_2",
      "ophthalmology_queue_2",
      "ent_queue_2",
      "dentistry_queue_2",
      "dermatology_queue_2",
      "psychiatry_queue_2",
      "rehabilitation_queue_2",
      "pain_queue_2",
      "diagnostic_center_queue_2"
    ],
    "reject_conditions": [
      "target room still has a free slot or a free bed",
      "matching door queue anchor does not exist"
    ],
    "notes": "不再使用统一总候诊区；所有等待都去目标房间门口。"
  },
  {
    "action": "add",
    "category": "outpatient",
    "event_id": "OP_TARGET_DOOR_QUEUE_ADVANCE",
    "name": "门口排队患者进入目标房间",
    "description": "当目标房间释放出接诊位置或床位后，门口排队区中的患者进入目标房间。",
    "movement": {
      "schema": "patient-move",
      "from": [
        "internal_queue_2",
        "surgery_queue_2",
        "pediatrics_queue_2",
        "fever_queue_2",
        "obgyn_queue_2",
        "ophthalmology_queue_2",
        "ent_queue_2",
        "dentistry_queue_2",
        "dermatology_queue_2",
        "psychiatry_queue_2",
        "rehabilitation_queue_2",
        "pain_queue_2",
        "diagnostic_center_queue_2"
      ],
      "to": [
        "internal_2",
        "internal_consult_b_2",
        "surgery_2",
        "surgery_consult_b_2",
        "surgery_procedure_2",
        "pediatrics_2",
        "fever_2",
        "obgyn_2",
        "ophthalmology_consult_2",
        "ent_consult_2",
        "dentistry_consult_2",
        "dermatology_consult_2",
        "psychiatry_consult_2",
        "rehabilitation_consult_2",
        "pain_consult_2",
        "diagnostic_center_2"
      ],
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
      }
    },
    "allowed_sources": [
      "internal_queue_2",
      "surgery_queue_2",
      "pediatrics_queue_2",
      "fever_queue_2",
      "obgyn_queue_2",
      "ophthalmology_queue_2",
      "ent_queue_2",
      "dentistry_queue_2",
      "dermatology_queue_2",
      "psychiatry_queue_2",
      "rehabilitation_queue_2",
      "pain_queue_2",
      "diagnostic_center_queue_2"
    ],
    "allowed_targets": [
      "internal_2",
      "internal_consult_b_2",
      "surgery_2",
      "surgery_consult_b_2",
      "surgery_procedure_2",
      "pediatrics_2",
      "fever_2",
      "obgyn_2",
      "ophthalmology_consult_2",
      "ent_consult_2",
      "dentistry_consult_2",
      "dermatology_consult_2",
      "psychiatry_consult_2",
      "rehabilitation_consult_2",
      "pain_consult_2",
      "diagnostic_center_2"
    ],
    "reject_conditions": [
      "target room still has no free slot or no free bed",
      "patient is not in the matching door queue"
    ],
    "notes": "当目标房间空出位置时，对应门口队列前进。"
  }
]
```

## Test Cases

### Accepted

```json
{
  "case_id": "ACCEPT-001",
  "event_id": "OP_CURRENT_TO_TARGET_DOOR_QUEUE",
  "patient_id": "P-OP-001",
  "from_room_id": "triage_2",
  "to_room_id": "internal_queue_2",
  "expected": "accepted",
  "reason": "患者已分配到内科，但内科两个接诊位置都已占用，因此患者应在内科门口等待，而不是进入统一总候诊区。"
}
```

### Rejected

```json
{
  "case_id": "REJECT-001",
  "event_id": "OP_CURRENT_TO_TARGET_DOOR_QUEUE",
  "patient_id": "P-OP-001",
  "from_room_id": "pharmacy_2",
  "to_room_id": "outpatient_waiting",
  "expected": "rejected",
  "reason_code": "TARGET_NOT_ALLOWED",
  "reason": "本次设计中不再允许患者进入统一总候诊区等待；等待目标必须是某个具体房间对应的门口排队位置。"
}
```

## Reviewer Notes

由 Fullview 维护者填写：

- reviewed_by:
- decision: `accepted | rejected | need_more_info`
- implementation_notes:
- files_to_update:
- validation_result:
