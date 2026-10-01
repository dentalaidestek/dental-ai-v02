"""Behavior checks for zero-provider Dental Academic scope routing."""
from app.dental_academic_scope import classify_academic_question_scope

assert classify_academic_question_scope("ANB açısı kaç derecedir?") == "DENTAL"
assert classify_academic_question_scope("48 numaralı diş mandibular kanala yakın mı?") == "DENTAL"
assert classify_academic_question_scope("bu notu özetle") == "STUDY_ACTION"
assert classify_academic_question_scope(
    "bunu biraz daha açıkla",
    recent_history=[{"role": "assistant", "content": "ANB açısı..."}],
) == "FOLLOWUP"
assert classify_academic_question_scope("programlama algoritması anlat") == "NON_DENTAL"
assert classify_academic_question_scope("ceza hukuku nedir?") == "NON_DENTAL"

# Unseen biomedical/dental vocabulary must not be falsely rejected. Retrieval
# evidence is the second gate for UNKNOWN.
assert classify_academic_question_scope("pterygomandibular raphe nerede?") == "UNKNOWN"
assert classify_academic_question_scope("Nance holding arch endikasyonu") == "UNKNOWN"

print("Dental Academic scope routing: OK")
