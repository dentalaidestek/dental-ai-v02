export type PatientCreateValues = Readonly<{
  first_name?: unknown;
  last_name?: unknown;
  phone?: unknown;
}>;

/** Match the web new-patient form's required Turkish mobile-number field. */
export function normalizePatientCreatePhone(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\D/g, '').slice(0, 11) : '';
}

export function patientCreateValidationError(values: PatientCreateValues): string | null {
  const firstName = typeof values.first_name === 'string' ? values.first_name.trim() : '';
  const lastName = typeof values.last_name === 'string' ? values.last_name.trim() : '';
  const phone = typeof values.phone === 'string' ? values.phone.trim() : '';

  if (!firstName || !lastName) return 'Ad ve soyad zorunludur.';
  if (!phone) return 'Telefon numarası zorunludur.';
  if (!/^05\d{9}$/.test(phone)) {
    return 'Telefon numarası 05 ile başlamalı ve toplam 11 rakam olmalıdır.';
  }
  return null;
}
