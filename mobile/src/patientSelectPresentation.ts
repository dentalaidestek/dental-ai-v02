import {
  normalizePatientDirectorySearch,
  patientDirectoryDetails,
  type PatientDirectoryFields,
} from './patientDirectoryPresentation';

export const PATIENT_SELECT_QUERY_MAX_LENGTH = 100;

export function normalizePatientSelectQuery(value: string): string {
  if (typeof value !== 'string') {
    throw new Error('Hasta araması geçersiz.');
  }
  const normalized = normalizePatientDirectorySearch(value);
  if (normalized.length > PATIENT_SELECT_QUERY_MAX_LENGTH) {
    throw new Error('Hasta araması en fazla 100 karakter olabilir.');
  }
  return normalized;
}

export function patientSelectEmptyState(
  query: string,
  busy: boolean,
  error?: string,
): string {
  if (busy) return 'Hastalar yükleniyor…';
  if (error) return 'Hasta listesi alınamadı.';
  return query ? 'Eşleşen hasta bulunamadı.' : 'Henüz hasta bulunmuyor.';
}

export function patientSelectRowDetails(
  patient: PatientDirectoryFields,
): string[] {
  return patientDirectoryDetails(patient);
}
