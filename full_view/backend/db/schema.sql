PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patients (
  patient_id TEXT PRIMARY KEY CHECK (patient_id GLOB 'P-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'),
  name TEXT NOT NULL,
  gender TEXT DEFAULT 'unknown',
  age INTEGER,
  dob TEXT,
  contact TEXT,
  allergies_json TEXT NOT NULL DEFAULT '[]',
  chronic_conditions_json TEXT NOT NULL DEFAULT '[]',
  blood_type TEXT,
  status TEXT NOT NULL DEFAULT 'ARRIVED',
  current_department_id TEXT,
  current_room_id TEXT,
  current_bed_id TEXT,
  profile_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS encounters (
  encounter_id TEXT PRIMARY KEY CHECK (encounter_id GLOB 'E-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]'),
  patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  status TEXT NOT NULL DEFAULT 'OPEN',
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  reason TEXT,
  summary_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY,
  encounter_id TEXT NOT NULL REFERENCES encounters(encounter_id),
  patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  department_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  started_at TEXT NOT NULL,
  ended_at TEXT,
  department_payload_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE (encounter_id, department_id)
);

CREATE TABLE IF NOT EXISTS locations (
  room_id TEXT PRIMARY KEY CHECK (room_id GLOB 'R-*'),
  visual_room_id TEXT,
  department_id TEXT NOT NULL,
  floor INTEGER NOT NULL,
  kind TEXT NOT NULL,
  display_name TEXT NOT NULL,
  capacity_beds INTEGER NOT NULL DEFAULT 0,
  map_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS beds (
  bed_id TEXT PRIMARY KEY CHECK (bed_id GLOB 'B-*'),
  room_id TEXT NOT NULL REFERENCES locations(room_id),
  bed_index INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'available',
  patient_id TEXT REFERENCES patients(patient_id),
  updated_at TEXT NOT NULL,
  UNIQUE (room_id, bed_index)
);

CREATE TABLE IF NOT EXISTS bed_assignments (
  assignment_id TEXT PRIMARY KEY,
  bed_id TEXT NOT NULL REFERENCES beds(bed_id),
  room_id TEXT NOT NULL REFERENCES locations(room_id),
  patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  encounter_id TEXT REFERENCES encounters(encounter_id),
  assigned_at TEXT NOT NULL,
  released_at TEXT,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS location_history (
  history_id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  encounter_id TEXT REFERENCES encounters(encounter_id),
  from_room_id TEXT,
  to_room_id TEXT,
  event_seq INTEGER,
  moved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS department_requests (
  request_id TEXT PRIMARY KEY,
  department_id TEXT NOT NULL,
  request_type TEXT NOT NULL,
  idempotency_key TEXT,
  raw_payload_json TEXT NOT NULL,
  normalized_payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  core_response_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT,
  correlation_id TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hospital_events (
  event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  patient_id TEXT,
  encounter_id TEXT,
  source_department_id TEXT,
  target_department_id TEXT,
  correlation_id TEXT NOT NULL,
  producer TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  animation_plan_json TEXT NOT NULL DEFAULT '{}',
  accepted INTEGER NOT NULL DEFAULT 1,
  reason_code TEXT,
  occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_outbox (
  outbox_id TEXT PRIMARY KEY,
  event_seq INTEGER NOT NULL REFERENCES hospital_events(event_seq),
  channel TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  published_at TEXT
);

CREATE TABLE IF NOT EXISTS department_inbox (
  delivery_id TEXT PRIMARY KEY,
  department_id TEXT NOT NULL,
  event_seq INTEGER NOT NULL REFERENCES hospital_events(event_seq),
  event_type TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  acked_at TEXT,
  UNIQUE (department_id, event_seq, event_type)
);

CREATE TABLE IF NOT EXISTS department_outbox (
  outbox_id TEXT PRIMARY KEY,
  department_id TEXT NOT NULL,
  request_id TEXT REFERENCES department_requests(request_id),
  event_seq INTEGER REFERENCES hospital_events(event_seq),
  envelope_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS department_sync_cursor (
  department_id TEXT PRIMARY KEY,
  last_delivered_seq INTEGER NOT NULL DEFAULT 0,
  last_acked_seq INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  scope TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (scope, idempotency_key)
);
