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
  fromHistory: boolean;
  notice: string;
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
      ? "Önceki hekim onaylı alan değeri"
      : "Bu muayenedeki konuşma dayanağı",
    // Older drafts may contain the approved value in quote; it is not a verbatim quote.
    quote: fromHistory ? "" : quote,
    hasEvidence: !fromHistory && quote.length > 0,
    edited: value?.edited === true,
    fromHistory,
    notice: fromHistory
      ? "Bu değer önceki hekim onaylı kayıttan alınmıştır. Özgün konuşma alıntısı hasta dosyasında saklanmıyor; güncelliğini hastayla doğrulayın."
      : quote.length > 0
        ? ""
        : "Bu muayene alanı için konuşma dayanağı sunulmadı; kaydetmeden önce ayrıca doğrulayın.",
  };
}
