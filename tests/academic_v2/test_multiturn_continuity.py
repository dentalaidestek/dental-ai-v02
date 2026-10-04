"""Academic V2 deterministic multi-turn continuity benchmark."""
from app.study_retrieval_v2 import resolve_followup_query

def u(x): return {"role":"user", "content":x}
def a(x): return {"role":"assistant", "content":x}
def low(x): return x.replace("İ","i").replace("I","ı").lower()

FLOR="Çocuklarda flor kullanımını anlat."

def test_exam_test_count_chain():
    h=[u(FLOR),a("Flor çürük önlemede etkilidir.")]
    q=resolve_followup_query("Sınav için en önemli yerleri?",h)
    assert "flor" in low(q) and "çocuk" in low(q)
    h += [u("Sınav için en önemli yerleri?"),a("...")]
    q=resolve_followup_query("Bunu test şeklinde yap.",h)
    assert "flor" in low(q) and "test" in low(q)
    h += [u("Bunu test şeklinde yap."),a("1) ...")]
    q=resolve_followup_query("10 soru yap.",h)
    assert "flor" in low(q) and "10" in q

def test_explicit_topic_switch_drops_stale_context():
    h=[u(FLOR),a("...")]
    q=resolve_followup_query("Peki SNB nedir?",h)
    assert "snb" in low(q) and "flor" not in low(q) and "çocuk" not in low(q)

def test_correction_then_switch_does_not_leak_qualifier():
    h=[u(FLOR),a("..."),u("Hayır çocuk değil erişkin."),a("...")]
    q=resolve_followup_query("SNB nedir?",h)
    assert "snb" in low(q) and "çocuk" not in low(q) and "erişkin" not in low(q)

def test_assistant_distractors_never_seed_subject():
    h=[u(FLOR),a("periodontitis amalgam pulpitis kanal tedavisi")]
    q=low(resolve_followup_query("Sınav için en önemli yerleri?",h))
    assert "flor" in q
    assert all(x not in q for x in ("periodontitis","amalgam","pulpitis","kanal"))

def test_history_window_is_bounded_to_eight():
    h=[u(FLOR),a("...")]+[a("x")]*8
    assert "flor" not in low(resolve_followup_query("Daha kısa yap.",h))

def test_invalid_large_count_is_not_silently_accepted():
    h=[u(FLOR),a("..."),u("10 soru yap."),a("...")]
    q=resolve_followup_query("500 soru yap.",h)
    assert "500" not in q

def _qlist(n=20):
    rows=[]
    for i in range(1,n+1):
        body=("Periodontal cep derinliği 5 mm olan hastada kök yüzeyi düzleştirme sonrası hangi bulgu beklenir?"
              if i==13 else f"Konu {i}. maddesine ilişkin aşağıdakilerden hangisi doğrudur?")
        rows += [f"{i}. {body}","A) a","B) b","C) c","D) d",""]
    return "\n".join(rows)

def test_real_five_turn_reference_chain():
    h=[u("Çıkmış soru hazırla"),a(_qlist())]
    q2=resolve_followup_query("Bu sorulardan 13. sorunun konusunu anlat",h)
    assert "periodontal cep" in low(q2)
    h += [u("Bu sorulardan 13. sorunun konusunu anlat"),a("Kök yüzeyi düzleştirme ve cep derinliği.")]
    q3=resolve_followup_query("Sadece bu konudan soru hazırla",h[-8:])
    assert "periodontal cep" in low(q3) and "soru" in low(q3)
    h += [u("Sadece bu konudan soru hazırla"),a(_qlist(10))]
    q4=resolve_followup_query("Yok bu sorular iyi değil ya baştan 20 soru hazırla",h[-8:])
    assert "20" in q4 and "periodontal" not in low(q4)
    h += [u("Yok bu sorular iyi değil ya baştan 20 soru hazırla"),a(_qlist(20))]
    q5=resolve_followup_query("Şimdi o anlattığın konuyu bu sorular arasında bul hangileri ile ilişkili",h[-8:])
    assert "periodontal cep" in low(q5) and ("ilişkili" in low(q5) or "eşleştir" in low(q5))
