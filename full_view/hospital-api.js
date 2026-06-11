export async function fetchHospitalSnapshot() {
  return fetchJson("./api/hospital/snapshot", "hospital snapshot");
}

export async function fetchHospitalPeople() {
  return fetchJson("./api/hospital/people", "hospital people");
}

export async function fetchHospitalRooms() {
  return fetchJson("./api/hospital/rooms", "hospital rooms");
}

export async function fetchHospitalEvents(after = 0) {
  return fetchJson(`./api/hospital/events?after=${encodeURIComponent(after)}`, "hospital events");
}

export async function requestPatientMove(payload) {
  const response = await fetch("./api/hospital/events/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Unable to request patient move: ${response.status}`);
  return response.json();
}

export async function fetchEventRuleIndex() {
  return fetchJson("./api/event-rules", "event rule index");
}

export async function fetchEventRuleCategory(file) {
  return fetchJson(`./api/event-rules/${encodeURIComponent(file)}`, file);
}

export async function fetchPersonProfile(id) {
  const people = await fetchHospitalPeople();
  const patient = people.patients.find((item) => item.id === id || item.patientId === id);
  if (patient) {
    return {
      type: "patient",
      patientId: patient.patientId,
      department: patient.department,
      name: patient.name,
      symptoms: patient.symptoms,
      status: patient.status,
      roomId: patient.roomId,
    };
  }
  const staff = people.staff.find((item) => item.id === id || item.employeeId === id);
  if (staff) {
    return {
      type: staff.role || staff.type,
      employeeId: staff.employeeId,
      department: staff.department,
      name: staff.name,
      roomId: staff.roomId,
    };
  }
  return null;
}

async function fetchJson(url, label) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Unable to load ${label}: ${response.status}`);
  return response.json();
}
