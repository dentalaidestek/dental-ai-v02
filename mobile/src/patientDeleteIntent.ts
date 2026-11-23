export type PatientDeleteIntent = Readonly<{
  version: 1;
  userId: number;
  patientId: number;
  requestKey: string;
}>;

const REQUEST_KEY = /^[A-Za-z0-9_-]{16,96}$/;

export function patientDeleteIntentStorageKey(userId: number, patientId: number): string {
  if (!Number.isSafeInteger(userId) || userId <= 0 ||
      !Number.isSafeInteger(patientId) || patientId <= 0) {
    throw new Error("Hasta silme kapsamı geçersiz.");
  }
  return "dai.patient-delete.v1." + userId + "." + patientId;
}

export function createPatientDeleteIntent(
  userId: number,
  patientId: number,
  requestKey: string,
): PatientDeleteIntent {
  return parsePatientDeleteIntent(JSON.stringify({
    version: 1,
    userId,
    patientId,
    requestKey,
  }), userId, patientId);
}

export function parsePatientDeleteIntent(
  raw: string,
  expectedUserId: number,
  expectedPatientId: number,
): PatientDeleteIntent {
  if (typeof raw !== "string" || raw.length > 1024) {
    throw new Error("Bekleyen hasta silme kaydı geçersiz.");
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("Bekleyen hasta silme kaydı okunamadı.");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Bekleyen hasta silme kaydı geçersiz.");
  }
  const candidate = value as Record<string, unknown>;
  if (candidate.version !== 1 ||
      candidate.userId !== expectedUserId ||
      candidate.patientId !== expectedPatientId ||
      !Number.isSafeInteger(candidate.userId) ||
      !Number.isSafeInteger(candidate.patientId) ||
      typeof candidate.requestKey !== "string" ||
      !REQUEST_KEY.test(candidate.requestKey)) {
    throw new Error("Bekleyen hasta silme kaydı bu hesap veya hastayla eşleşmiyor.");
  }
  return Object.freeze({
    version: 1,
    userId: expectedUserId,
    patientId: expectedPatientId,
    requestKey: candidate.requestKey,
  });
}
