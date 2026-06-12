## Basic Info

- request_id: REQ-MDT-20260612-001
- request_type: rule_update
- department_id: mdt
- requested_by: MDT group
- contact: TBD
- priority: high
- reason: ICU patients may need an MDT consultation, and FullVis should be able to display the patient or case moving from ICU to the 4F MDT floor.
- expected_behavior: After ICU requests MDT consultation, a backend service can call FullVis `/api/hospital/events/move` with `ICU_TO_MDT_CONSULT_MOVE`, and FullVis will animate the patient from the current ICU bed room to `mdt_call` or `mdt_meeting`.
- affected_departments: ["icu", "mdt"]
- breaking_change: false

## Current Problem

FullVis already has the 4F MDT floor and rooms such as `mdt_call`, `head_doctor`, `mdt_meeting`, and `elevator_4`.
However, the current executable movement rule files do not include an ICU-to-MDT movement rule. When ICU requests MDT consultation, MDT can process the consultation, but FullVis cannot yet animate the patient or case moving to the MDT floor through `/api/hospital/events/move`.

## Room Change

N/A

## Rule Change

```json
[
  {
    "action": "add",
    "category": "transfer",
    "event_id": "ICU_TO_MDT_CONSULT_MOVE",
    "name": "ICU patient moves to MDT consultation",
    "description": "When ICU requests MDT consultation, the patient or case is moved from the ICU bed area to the 4F MDT consultation entry room.",
    "movement": {
      "schema": "patient-move",
      "from": "current_icu_bed_room",
      "to": ["mdt_call", "mdt_meeting"],
      "via": ["icu_transfer", "elevator_3", "elevator_4"],
      "transport": "stretcher",
      "patientFormDuringMove": "stretcher",
      "finalForm": "consultation",
      "escortRequired": true,
      "escortRoles": ["porter", "icu_nurse"],
      "equipment": ["portable_monitor", "oxygen", "transport_bag"],
      "resourcePolicy": {
        "retainSourceBed": true,
        "releaseSourceBed": false
      },
      "queuePolicy": {
        "whenTargetBusy": "queue",
        "queueRoomId": "mdt_lounge",
        "autoAdvance": true
      }
    },
    "allowed_sources": ["icu_beds_a", "icu_beds_b", "icu_isolation"],
    "allowed_targets": ["mdt_call", "mdt_meeting"],
    "reject_conditions": [
      "patient is not currently in an ICU bed room",
      "target MDT room does not exist",
      "required ICU nurse or porter is unavailable"
    ],
    "notes": "The ICU source bed should be retained because MDT consultation is not an ICU discharge or transfer of care. If FullVis prefers to visualize only a case token rather than the physical patient, please keep the same event_id and route but adjust finalForm or visual representation accordingly."
  }
]
```

## Test Cases

### Accepted

```json
{
  "case_id": "ACCEPT-001",
  "event_id": "ICU_TO_MDT_CONSULT_MOVE",
  "patient_id": "P-ICU-001",
  "from_room_id": "icu_beds_a",
  "to_room_id": "mdt_call",
  "expected": "accepted",
  "reason": "The patient is currently in an ICU bed room and the target MDT room exists."
}
```

### Rejected

```json
{
  "case_id": "REJECT-001",
  "event_id": "ICU_TO_MDT_CONSULT_MOVE",
  "patient_id": "P-ICU-001",
  "from_room_id": "pharmacy_2",
  "to_room_id": "mdt_call",
  "expected": "rejected",
  "reason_code": "SOURCE_NOT_ALLOWED",
  "reason": "The patient is not in an ICU bed room, so the ICU-to-MDT consultation movement rule should not be used."
}
```

## Reviewer Notes

- reviewed_by:
- decision: `accepted | rejected | need_more_info`
- implementation_notes:
- files_to_update:
- validation_result:
