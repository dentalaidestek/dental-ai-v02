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
  birth_date?: string | null;
  tc_kimlik_no?: string | null;
  address?: string | null;
  chief_complaint?: string | null;
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

export type PatientProfileDeleteGate = Readonly<{
  busy: boolean;
  uncertain: boolean;
  /** No unsaved or unresolved patient-profile edits may be discarded by deletion. */
  profileEditReady: boolean;
  treatmentIntentReady: boolean;
  treatmentIntentBlocked: boolean;
  hasPendingTreatment: boolean;
  deleteIntentReady: boolean;
  deleteIntentBlocked: boolean;
  hasPendingDelete: boolean;
}>;

/**
 * A patient can only start a new deletion after profile/treatment writes and
 * any prior delete intent have been restored and reconciled. A pending delete
 * is resolved with its original request key, never replaced with a new key.
 */
export function patientProfileCanDeletePatient(gate: PatientProfileDeleteGate): boolean {
  return gate.busy === false &&
    gate.uncertain === false &&
    gate.profileEditReady === true &&
    gate.treatmentIntentReady === true &&
    gate.treatmentIntentBlocked === false &&
    gate.hasPendingTreatment === false &&
    gate.deleteIntentReady === true &&
    gate.deleteIntentBlocked === false &&
    gate.hasPendingDelete === false;
}

/** Compare the exact editable patient fields after the backend's trim/null normalization. */
export function patientProfileEditMatches(
  draft: PatientProfileEditValues,
  current: PatientProfileEditValues,
): boolean {
  const normalized = (value: unknown) => typeof value === 'string' ? value.trim() : '';
  const fields: readonly (keyof PatientProfileEditValues)[] = [
    'first_name', 'last_name', 'phone', 'birth_date', 'tc_kimlik_no', 'address', 'chief_complaint',
  ];
  return fields.every((field) => normalized(draft[field]) === normalized(current[field]));
}


export type PatientProfileEditField = keyof PatientProfileEditValues;

export type PatientProfileEditFieldDefinition = Readonly<{
  key: PatientProfileEditField;
  label: string;
  control: 'text' | 'date';
  keyboardType?: 'phone-pad' | 'number-pad';
  maxLength?: number;
  multiline?: boolean;
}>;

/**
 * Ordered native edit controls mirror the fields in patient_detail.html.
 * Keep labels, order and input constraints in one testable contract.
 */
const PATIENT_PROFILE_EDIT_FIELDS: readonly PatientProfileEditFieldDefinition[] = Object.freeze([
  { key: 'first_name', label: 'Ad', control: 'text' },
  { key: 'last_name', label: 'Soyad', control: 'text' },
  { key: 'phone', label: 'Telefon', control: 'text', keyboardType: 'phone-pad', maxLength: 11 },
  { key: 'tc_kimlik_no', label: 'TC Kimlik No', control: 'text', keyboardType: 'number-pad', maxLength: 11 },
  { key: 'birth_date', label: 'Doğum Tarihi', control: 'date' },
  { key: 'address', label: 'Adres', control: 'text', multiline: true },
  { key: 'chief_complaint', label: 'Başvuru şikâyeti', control: 'text', multiline: true },
]);

export function patientProfileEditFields(): readonly PatientProfileEditFieldDefinition[] {
  return PATIENT_PROFILE_EDIT_FIELDS;
}

export type PatientProfileEditConflict = Readonly<{
  field: PatientProfileEditField;
  label: string;
  baseValue: string;
  draftValue: string;
  currentValue: string;
}>;

export type PatientProfileEditMerge = Readonly<{
  values: Readonly<Record<PatientProfileEditField, string>>;
  conflicts: readonly PatientProfileEditConflict[];
}>;

/**
 * Three-way merge after an optimistic-revision conflict.
 * Unchanged local fields take the latest server value; locally changed fields
 * stay in the draft. A field changed differently by both sessions is returned
 * as an explicit conflict and must be resolved by the clinician before saving.
 */
export function patientProfileMergeEditConflict(
  base: PatientProfileEditValues,
  draft: PatientProfileEditValues,
  current: PatientProfileEditValues,
): PatientProfileEditMerge {
  const fields: readonly Readonly<{ key: PatientProfileEditField; label: string }>[] = [
    { key: 'first_name', label: 'Ad' },
    { key: 'last_name', label: 'Soyad' },
    { key: 'phone', label: 'Telefon' },
    { key: 'birth_date', label: 'Doğum tarihi' },
    { key: 'tc_kimlik_no', label: 'TC kimlik numarası' },
    { key: 'address', label: 'Adres' },
    { key: 'chief_complaint', label: 'Başvuru şikâyeti' },
  ];
  const normalize = (value: unknown): string => typeof value === 'string' ? value.trim() : '';
  const asFormValue = (value: unknown): string => typeof value === 'string' ? value : '';
  const values = {} as Record<PatientProfileEditField, string>;
  const conflicts: PatientProfileEditConflict[] = [];

  for (const item of fields) {
    const baseValue = normalize(base[item.key]);
    const draftValue = normalize(draft[item.key]);
    const currentValue = normalize(current[item.key]);
    const draftChanged = draftValue !== baseValue;
    const currentChanged = currentValue !== baseValue;

    values[item.key] = draftChanged
      ? asFormValue(draft[item.key])
      : asFormValue(current[item.key]);

    if (draftChanged && currentChanged && draftValue !== currentValue) {
      conflicts.push({
        field: item.key,
        label: item.label,
        baseValue,
        draftValue: asFormValue(draft[item.key]),
        currentValue: asFormValue(current[item.key]),
      });
    }
  }

  return { values, conflicts };
}
