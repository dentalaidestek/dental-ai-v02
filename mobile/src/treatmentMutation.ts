export type TreatmentPayload = {
  treatment_name: string;
  tooth_number: string;
  treatment_date: string;
  material: string;
  doctor_note: string;
  result: string;
};

export type TreatmentMutationIntent = {
  userId: number;
  patientId: number;
  operation: "CREATE" | "UPDATE";
  treatmentId: number | null;
  requestKey: string;
  expectedRevision: string | null;
  payload: TreatmentPayload;
};

const keyPattern = /^[A-Za-z0-9_-]{16,80}$/;
const revisionPattern = /^[a-f0-9]{64}$/;
const validTooth = (value: string) =>
  /^(?:[1-4][1-8]|[5-8][1-5])$/.test(value);

function validDate(value: string) {
  if (!value) return true;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
  if (year < 1 || month < 1 || month > 12 || day < 1) return false;
  const date = new Date(Date.UTC(year, month, 0));
  return day <= date.getUTCDate();
}

export function treatmentMutationStorageKey(userId: number, patientId: number) {
  if (!Number.isSafeInteger(userId) || userId < 1 ||
      !Number.isSafeInteger(patientId) || patientId < 1)
    throw new Error("Geçersiz tedavi taslak kapsamı.");
  return `dai.treatment.${userId}.${patientId}`;
}

export function parseTreatmentMutationIntent(
  raw: string,
  userId: number,
  patientId: number,
): TreatmentMutationIntent {
  let value: any;
  try { value = JSON.parse(raw); }
  catch { throw new Error("Bekleyen tedavi kaydı okunamadı."); }
  if (!value || value.userId !== userId || value.patientId !== patientId ||
      !Number.isSafeInteger(userId) || userId < 1 ||
      !Number.isSafeInteger(patientId) || patientId < 1 ||
      !["CREATE", "UPDATE"].includes(value.operation) ||
      typeof value.requestKey !== "string" || !keyPattern.test(value.requestKey) ||
      !value.payload || typeof value.payload !== "object" || Array.isArray(value.payload))
    throw new Error("Bekleyen tedavi kaydı bu hasta veya hesap için doğrulanamadı.");

  const treatmentId = value.treatmentId ?? null;
  const expectedRevision = value.expectedRevision ?? null;
  if (value.operation === "CREATE") {
    if (treatmentId !== null || expectedRevision !== null)
      throw new Error("Yeni tedavi taslağının kapsamı geçersiz.");
  } else if (!Number.isSafeInteger(treatmentId) || treatmentId < 1 ||
             typeof expectedRevision !== "string" || !revisionPattern.test(expectedRevision)) {
    throw new Error("Düzenlenecek tedavinin sürümü doğrulanamadı.");
  }

  const p = value.payload;
  const payload: TreatmentPayload = {
    treatment_name: typeof p.treatment_name === "string" ? p.treatment_name.trim() : "",
    tooth_number: typeof p.tooth_number === "string" ? p.tooth_number.trim() : "",
    treatment_date: typeof p.treatment_date === "string" ? p.treatment_date : "",
    material: typeof p.material === "string" ? p.material : "",
    doctor_note: typeof p.doctor_note === "string" ? p.doctor_note : "",
    result: typeof p.result === "string" ? p.result : "",
  };
  if (!payload.treatment_name || payload.treatment_name.length > 200 ||
      (payload.tooth_number && !validTooth(payload.tooth_number)) ||
      !validDate(payload.treatment_date) ||
      payload.material.length > 500 || payload.doctor_note.length > 4000 ||
      payload.result.length > 1000)
    throw new Error("Bekleyen tedavi alanları doğrulanamadı.");

  return {
    userId, patientId, operation: value.operation, treatmentId,
    requestKey: value.requestKey, expectedRevision, payload,
  };
}
