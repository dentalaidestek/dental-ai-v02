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

export type ToothChartMutationGate = Readonly<{
  treatmentIntentReady: boolean;
  treatmentIntentBlocked: boolean;
  treatmentUncertain: boolean;
  hasPendingTreatment: boolean;
}>;

/** Do not permit tooth/surface writes until the durable treatment intent is known and settled. */
export function toothChartClinicalMutationBlocked(gate: ToothChartMutationGate): boolean {
  return gate.treatmentIntentReady !== true ||
    gate.treatmentIntentBlocked === true ||
    gate.treatmentUncertain === true ||
    gate.hasPendingTreatment === true;
}
