# Fullview 远程服务器访问指南

本文档说明各 department 如何通过局域网或 VPN 访问本仓库部署的 **SIM Hospital Fullview** 服务器，以及如何发送 API 请求接入全院状态与事件系统。

> 服务器由 Fullview 组维护。若无法连接，请先联系维护同学确认服务是否在运行、IP 是否变更。

---

## 1. 服务器地址

| 网络环境 | Base URL | 适用对象 |
|----------|----------|----------|
| 校园网 / 同一局域网 | `http://10.19.125.229:8000` | 与服务器在同一校园网的同学 |
| VPN（Tailscale 等） | `http://100.79.195.68:8000` | 已加入同一 VPN 的同学 |

下文以校园网地址为例，VPN 用户把 `10.19.125.229` 换成 `100.79.195.68` 即可。

**端口**：`8000`

**不要使用 `localhost` 或 `127.0.0.1`** —— 那只能访问你自己电脑，无法连到 Fullview 服务器。

---

## 2. 打开前端页面

在浏览器中访问：

| 页面 | URL |
|------|-----|
| 全院地图 | http://10.19.125.229:8000/ |
| Operations Console | http://10.19.125.229:8000/console.html |
| Department Dashboard | http://10.19.125.229:8000/department-dashboard.html |

地图页会轮询后端事件并播放患者移动动画；控制台可手动发送移动请求做联调。

---

## 3. 连通性检查

先确认服务器在线：

```bash
curl http://10.19.125.229:8000/api/health
```

期望返回：

```json
{
  "ok": true,
  "service": "fullview-core",
  "database": "..."
}
```

再拉取全院快照：

```bash
curl http://10.19.125.229:8000/api/hospital/snapshot
```

---

## 4. 接入原则

1. **Fullview 后端是权威**：患者位置、床位占用、事件是否批准，由服务器判断。
2. **不要直接改地图前端**：各组通过 HTTP API 发请求，不要在前端自行移动患者。
3. **使用统一 ID**：`patient_id`、`room_id`、`bed_id`、`event_id` 须符合 [接入手册](fullview-integration-manual.md) 中的约定。
4. **移动必须对应规则**：`event_id` 须在服务器 `event-rules` 中有定义，否则会被拒绝。
5. **请求字段**：推荐 snake_case（`request_id`、`patient_id`）；也兼容 camelCase（`requestId`、`patientId`）。

---

## 5. 常用只读 API

将 `{BASE}` 替换为 `http://10.19.125.229:8000`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `{BASE}/api/health` | 健康检查 |
| GET | `{BASE}/api/hospital/snapshot` | 全院状态（患者、医护、房间、事件序号） |
| GET | `{BASE}/api/hospital/rooms` | 房间与床位占用 |
| GET | `{BASE}/api/hospital/people` | 所有患者与医护 |
| GET | `{BASE}/api/hospital/events?after=0` | 事件日志（`after` 为上次读到的 `event_seq`） |
| GET | `{BASE}/api/v1/departments` | 已注册科室列表 |
| GET | `{BASE}/api/v1/departments/{department_id}/capabilities` | 某科室支持的请求类型 |
| GET | `{BASE}/api/event-rules` | 移动规则索引 |

### 轮询事件示例

```bash
curl "http://10.19.125.229:8000/api/hospital/events?after=12"
```

---

## 6. 写入 API（核心）

### 6.1 患者移动 — `POST /api/hospital/events/move`

最常用的接入接口。后端校验规则与资源后，返回是否 `accepted` 及 `animation_plan`。

**请求**

```http
POST http://10.19.125.229:8000/api/hospital/events/move
Content-Type: application/json
```

```json
{
  "request_id": "icu-req-20260612-001",
  "source": "icu",
  "operator_id": "ICU-Agent-001",
  "event_id": "TRANSFER_ED_TO_ICU",
  "patient_id": "P-ER-001",
  "from_room_id": "ed_red_resus",
  "to_room_id": "icu_admission",
  "context": {
    "reason": "needs ICU monitoring"
  }
}
```

**成功响应（节选）**

```json
{
  "accepted": true,
  "event_seq": 12,
  "event_id": "TRANSFER_ED_TO_ICU",
  "patient_id": "P-ER-001",
  "animation_plan": {
    "kind": "patient-move",
    "transport": "stretcher",
    "from_room_id": "ed_red_resus",
    "to_room_id": "icu_admission",
    "via_room_ids": ["ed_handoff", "elevator_1", "elevator_3"],
    "final_form": "bed"
  }
}
```

**失败响应（节选）**

```json
{
  "accepted": false,
  "event_seq": 13,
  "reason_code": "TARGET_NOT_ALLOWED",
  "message": "Target room is not allowed by the selected movement rule."
}
```

失败时患者**不会移动**；请根据 `reason_code` / `message` 处理（等待床位、换目标房间等）。

---

### 6.2 新患者入院 — `POST /api/hospital/patients/admit`

从急诊或门诊入口创建患者并触发分诊规则。

```json
{
  "request_id": "ed-intake-001",
  "source": "emergency",
  "operator_id": "ED-Agent-001",
  "department": "emergency",
  "context": {
    "reason": "walk-in chest tightness"
  }
}
```

`department` 可选 `"emergency"` 或 `"outpatient"`。

---

### 6.3 科室统一请求 — `POST /api/v1/departments/{department_id}/requests/{request_type}`

推荐各组用此接口提交结构化请求（患者 upsert、转运、出院等）。支持幂等键：

```http
POST http://10.19.125.229:8000/api/v1/departments/icu/requests/movement_request
Content-Type: application/json
Idempotency-Key: icu-move-P-ICU-001-001
```

```json
{
  "patient_id": "P-ICU-001",
  "encounter_id": "ENC-ICU-001",
  "event_id": "ICU_TO_EXAM_OR_INTERVENTION",
  "from_room_id": "icu_beds_a",
  "to_room_id": "diagnostic_center",
  "reason": "scheduled CT"
}
```

常见 `request_type`：

| request_type | 用途 |
|--------------|------|
| `patient_upsert` | 创建/更新患者 |
| `movement_request` | 科室内或规则内移动 |
| `transfer_request` | 跨科室转运（如急诊 → ICU） |
| `discharge_request` | 出院 |
| `clinical_event` | 临床事件（不改变位置） |

可用 `GET /api/v1/departments/{department_id}/schemas` 查看各类型 JSON Schema。

---

## 7. 代码示例

### 7.1 Python

```python
import requests

BASE = "http://10.19.125.229:8000"

r = requests.get(f"{BASE}/api/health", timeout=10)
r.raise_for_status()
print(r.json())

payload = {
    "request_id": "icu-req-001",
    "source": "icu",
    "operator_id": "ICU-Agent-001",
    "event_id": "TRANSFER_ED_TO_ICU",
    "patient_id": "P-ER-001",
    "from_room_id": "ed_red_resus",
    "to_room_id": "icu_admission",
    "context": {"reason": "needs ICU monitoring"},
}
r = requests.post(f"{BASE}/api/hospital/events/move", json=payload, timeout=30)
result = r.json()
if result.get("accepted"):
    print("移动已批准, event_seq =", result["event_seq"])
else:
    print("被拒绝:", result.get("reason_code"), result.get("message"))
```

### 7.2 JavaScript / Node.js

```javascript
const BASE = "http://10.19.125.229:8000";

async function movePatient() {
  const res = await fetch(`${BASE}/api/hospital/events/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      request_id: "icu-req-001",
      source: "icu",
      operator_id: "ICU-Agent-001",
      event_id: "TRANSFER_ED_TO_ICU",
      patient_id: "P-ER-001",
      from_room_id: "ed_red_resus",
      to_room_id: "icu_admission",
      context: { reason: "needs ICU monitoring" },
    }),
  });
  const data = await res.json();
  console.log(data.accepted ? "accepted" : data.message);
}

movePatient();
```

### 7.3 curl

```bash
curl -X POST "http://10.19.125.229:8000/api/hospital/events/move" \
  -H "Content-Type: application/json" \
  -d "{\"request_id\":\"icu-req-001\",\"source\":\"icu\",\"operator_id\":\"ICU-Agent-001\",\"event_id\":\"TRANSFER_ED_TO_ICU\",\"patient_id\":\"P-ER-001\",\"from_room_id\":\"ed_red_resus\",\"to_room_id\":\"icu_admission\",\"context\":{\"reason\":\"needs ICU monitoring\"}}"
```

---

## 8. 各组推荐配置

在各自项目的环境变量或配置文件中设置：

```env
FULLVIEW_BASE_URL=http://10.19.125.229:8000
FULLVIEW_DEPARTMENT_ID=icu
```

| 科室 | department_id 示例 |
|------|-------------------|
| 急诊 | `emergency` |
| 门诊 | `outpatient` |
| ICU | `icu` |
| 住院部 | `ward` |
| MDT | `mdt` |

---

## 9. 联调建议

1. 浏览器打开地图页，观察患者是否按 `animation_plan` 移动。
2. 用 Console 手动发一次相同 `event_id`，确认规则存在且参数正确。
3. 用 `GET /api/hospital/snapshot` 核对 `patient_id` 当前 `room_id` 与 `from_room_id` 一致。
4. ICU/住院患者临时去检查时，原床位会保留；不要用错误的 `event_id` 导致床位被误释放。
5. 需要新增房间或移动规则时，请按 [变更请求格式](fullview-change-request-format.md) 提交，不要直接改服务器文件。

---

## 10. 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 连接超时 | 不在同一网络 / 服务未启动 | 确认校园网或 VPN；联系维护同学 |
| `connection refused` | 端口未监听或防火墙拦截 | 确认 8000 端口；维护同学检查防火墙 |
| `accepted: false` | 规则、床位、房间不匹配 | 查 `reason_code`；对照 snapshot 与 event-rules |
| 地图无动画 | 未轮询 events | 刷新地图页；确认 `accepted: true` 且含 `animation_plan` |
| CORS 报错 | 浏览器跨域 | 服务器已开启 CORS；建议后端服务发请求 |

---

## 11. 更多文档

- [Fullview 接入手册](fullview-integration-manual.md) — ID 标准、数据格式、完整接入流程
- [API 详细说明](../full_view/API.md) — 请求/响应字段
- [核心数据标准](../full_view/HOSPITAL_CORE_STANDARD.md) — 字段命名与结构
- [事件规则说明](../rules/README.md) — 移动规则设计

---

## 12. 维护者：启动服务器

在服务器上执行：

```powershell
cd full_view
python dev-server.py 8000
```

默认监听 `0.0.0.0:8000`，局域网与 VPN 均可访问。IP 变更时请同步更新本文档第 1 节。