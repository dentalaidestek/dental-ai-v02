export type VoiceEvidenceLike = {
  quote?: unknown;
  origin?: unknown;
  edited?: unknown;
};

export type VoiceEvidencePresentation = {
  label: string;
  quote: string;
  hasEvidence: boolean;
  edited: boolean;
};

const MAX_EVIDENCE_CHARS = 3000;

/**
 * Presents the provenance of a voice-exam field without changing its clinical meaning.
 * History values are explicitly labelled as prior approved records, not current facts.
 */
export function voiceEvidencePresentation(value: VoiceEvidenceLike): VoiceEvidencePresentation {
  const quote = typeof value?.quote === "string" ? value.quote.trim().slice(0, MAX_EVIDENCE_CHARS) : "";
  const fromHistory = value?.origin === "history";

  return {
    label: fromHistory
      ? "Önceki hekim onaylı kayıttaki dayanak"
      : "Bu muayenedeki konuşma dayanağı",
    quote,
    hasEvidence: quote.length > 0,
    edited: value?.edited === true,
  };
}
