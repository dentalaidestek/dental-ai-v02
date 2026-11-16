export type PatientProfileQuickActionKey = 'chart' | 'analysis' | 'appointment' | 'treatment';

export type PatientProfileQuickAction = Readonly<{
  key: PatientProfileQuickActionKey;
  label: string;
  description: string;
  icon: string;
  hint: string;
  primary?: boolean;
}>;

const QUICK_ACTIONS: readonly PatientProfileQuickAction[] = Object.freeze([
  {
    key: 'chart',
    label: 'Diş Şeması',
    description: 'FDI ve diş yüzeylerini kaydedin',
    icon: '🦷',
    hint: 'Hastanın FDI diş şemasını açar.',
    primary: true,
  },
  {
    key: 'analysis',
    label: 'AI Analiz',
    description: 'Klinik görüntü ve ön değerlendirme',
    icon: '✦',
    hint: 'Bu hasta için yeni klinik analiz başlatır.',
  },
  {
    key: 'appointment',
    label: 'Randevu',
    description: 'Hasta için randevu oluşturun',
    icon: '◷',
    hint: 'Bu hasta için randevu oluşturma ekranını açar.',
  },
  {
    key: 'treatment',
    label: 'Tedavi',
    description: 'Tedavi geçmişine kayıt ekleyin',
    icon: '＋',
    hint: 'Tedavi geçmişine yeni kayıt formunu açar.',
  },
]);

export function patientProfileQuickActions(): readonly PatientProfileQuickAction[] {
  return QUICK_ACTIONS;
}

export function patientProfileName(firstName?: string | null, lastName?: string | null): string {
  const name = [firstName, lastName]
    .map((value) => typeof value === 'string' ? value.trim() : '')
    .filter(Boolean)
    .join(' ');
  return name || 'İsimsiz Hasta';
}

export function patientProfileInitials(firstName?: string | null, lastName?: string | null): string {
  const first = typeof firstName === 'string' ? firstName.trim() : '';
  const last = typeof lastName === 'string' ? lastName.trim() : '';
  const initials = `${first.slice(0, 1)}${last.slice(0, 1)}`.toUpperCase();
  return initials || 'H';
}

export function patientProfileAgeLabel(age?: number | null): string {
  return age === null || age === undefined ? 'Hasta kaydı' : `${age} yaş`;
}

export type PatientProfileEditValues = Readonly<{
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
}>;

/** Match the native patient-edit form to the web form and canonical API contract. */
export function patientProfileEditError(values: PatientProfileEditValues): string | null {
  const firstName = typeof values.first_name === 'string' ? values.first_name.trim() : '';
  const lastName = typeof values.last_name === 'string' ? values.last_name.trim() : '';
  const phone = typeof values.phone === 'string' ? values.phone.trim() : '';

  if (!firstName || !lastName) return 'Ad ve soyad zorunludur.';
  if (phone && !/^05[0-9]{9}$/.test(phone)) {
    return 'Telefon numarası 05 ile başlamalı ve toplam 11 rakam olmalıdır.';
  }
  return null;
}
