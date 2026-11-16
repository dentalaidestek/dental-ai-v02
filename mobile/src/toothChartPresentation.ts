export type ToothChartPatientIdentity = {
  first_name?: string | null;
  last_name?: string | null;
  age?: number | null;
};

/** Mirrors the patient identity shown above the web tooth chart. */
export function toothChartPatientSummary(patient: ToothChartPatientIdentity): string {
  const name = [patient.first_name, patient.last_name]
    .map(value => typeof value === "string" ? value.trim() : "")
    .filter(Boolean)
    .join(" ") || "İsimsiz hasta";
  const age = typeof patient.age === "number" && Number.isInteger(patient.age) && patient.age >= 0
    ? `${patient.age} yaş`
    : "";
  return age ? `${name} · ${age}` : name;
}
