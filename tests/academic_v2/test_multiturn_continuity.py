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

def test_large_requested_count_is_not_an_ordinal_reference():
    h=[u(FLOR),a("..."),u("10 soru yap."),a("...")]
    q=resolve_followup_query("500 soru yap.",h)
    # Resolution preserves the user's request. Execution budgets belong to
    # generation orchestration; deleting the number silently changes intent.
    assert "500 soru" in q and "flor" in low(q)

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
    # Rejecting the generated questions is not an instruction to drop the
    # selected topic. The former assertion rewarded the lost-topic bug.
    assert "20" in q4 and "periodontal cep" in low(q4)
    h += [u("Yok bu sorular iyi değil ya baştan 20 soru hazırla"),a(_qlist(20))]
    q5=resolve_followup_query("Şimdi o anlattığın konuyu bu sorular arasında bul hangileri ile ilişkili",h[-8:])
    assert "periodontal cep" in low(q5) and ("ilişkili" in low(q5) or "eşleştir" in low(q5))


def test_ordinal_reference_reads_only_explicit_assistant_list_item():
    history=[
        u("Flor konusunda 20 soru hazırla"),
        a("\n".join(f"{i}. Flor ile ilgili klinik soru {i}\nA) a\nB) b\nC) c\nD) d" for i in range(1,21))),
    ]
    resolved=resolve_followup_query("13. sorunun konusunu anlat",history)
    assert "flor" in resolved.casefold()
    assert "klinik soru 13" in resolved.casefold()


def test_multi_hop_reuses_assistant_subject_only_after_explicit_reference():
    history=[
        u("Flor konusunda 20 soru hazırla"),
        a("\n".join(f"{i}. Flor ile ilgili klinik soru {i}\nA) a\nB) b\nC) c\nD) d" for i in range(1,21))),
        u("13. sorunun konusunu anlat"),
        a("Flor klinik soru 13 açıklaması"),
    ]
    resolved=resolve_followup_query("sadece bu konudan 10 soru hazırla",history)
    assert "flor" in resolved.casefold()
    assert "10 soru" in resolved.casefold()


def test_unreferenced_assistant_prose_never_becomes_subject():
    history=[u("Flor anlat"),a("Flor açıklaması. İmplant ve ameloblastoma ayrıca örnek olabilir.")]
    resolved=resolve_followup_query("bunu biraz daha anlat",history)
    assert "flor" in resolved.casefold()
    assert "implant" not in resolved.casefold()
    assert "ameloblastoma" not in resolved.casefold()


def test_axis_specific_inheritance_does_not_copy_stale_count():
    history=[u("Flor için 10 soru hazırla"),a("hazırlandı")]
    resolved=resolve_followup_query("aynı konuyu normal anlat",history)
    assert "flor" in resolved.casefold()
    assert "10 soru" not in resolved.casefold()


def test_count_and_ordinal_have_different_ownership():
    history = [u("Flor için soru hazırla"), a("1. Pulpitis sorusu\n2. SNB sorusu")]
    generated = low(resolve_followup_query("2 soru hazırla", history))
    selected = low(resolve_followup_query("2. sorunun konusunu anlat", history))
    assert "flor" in generated and "snb" not in generated
    assert "snb" in selected and "flor" not in selected


def test_selected_item_survives_chained_operations_and_acknowledgements():
    for number in (2, 9, 17):
        for acknowledgment in ("tamam sağ ol", "bu arada yarın sınav var", "önceden 40 soru demiştim"):
            history = [u("Soru hazırla"), a(f"{number}. Gingivitis tanısı\nA) Pulpitis\nB) Amalgam"),
                       u(f"{number}. sorunun konusunu anlat"), a("İmplant da örnek olabilir."),
                       u("sadece bu konudan soru hazırla"), a("hazırlandı"), u(acknowledgment)]
            result = low(resolve_followup_query("aynı konudan devam et", history))
            assert "gingivitis" in result
            assert all(x not in result for x in ("pulpitis", "amalgam", "implant", "40 soru"))


def test_explicit_new_subject_overrides_previously_selected_item():
    history = [u("Soru hazırla"), a("2. Gingivitis tanısı"),
               u("2. sorunun konusunu anlat"), a("..."), u("SNB nedir?"), a("...")]
    result = low(resolve_followup_query("bu konudan devam et", history))
    assert "snb" in result and "gingivitis" not in result


def test_unknown_user_noun_phrase_is_not_replaced_by_operator_words():
    history = [u("Mukogingival cerrahi hakkında anlat"), a("..."),
               u("sadece tanımı anlat"), a("..."), u("10 soru hazırla"), a("...")]
    result = low(resolve_followup_query("bunun komplikasyonları?", history))
    assert "mukogingival cerrahi" in result
    assert "sadece tanımı" not in result and "10 soru" not in result


def test_unavailable_selected_item_does_not_fall_back_to_old_topic():
    history = [u("Pulpitis anlat"), a("1. SNB sorusu")]
    query = "9. sorunun konusunu anlat"
    assert resolve_followup_query(query, history) == query


def test_qualifier_replacement_persists_without_old_qualifier():
    history = [u("Çocuklarda flor kullanımını anlat"), a("..."),
               u("Hayır çocuk değil erişkin açısından anlat"), a("...")]
    result = low(resolve_followup_query("aynı konudan devam et", history))
    assert "flor" in result and "erişkin" in result and "çocuk" not in result


def test_count_inheritance_ignores_reported_old_request():
    history = [u("Flor için 11 soru hazırla"), a("..."),
               u("önceden 40 soru demiştim"), a("...")]
    result = low(resolve_followup_query("aynı sayıda soru hazırla", history))
    assert "11 soru" in result and "40" not in result


def test_multiple_subject_pronoun_does_not_choose_one():
    history = [u("SNA ve SNB anlat"), a("...")]
    query = "bunu biraz daha anlat"
    assert resolve_followup_query(query, history) == query


def test_gold_audit_reports_contradictions_without_mutating_cases():
    from copy import deepcopy
    from scripts.audit_multiturn_continuity import defects
    case = {"history": [("user", "Pulpitis anlat")], "query": "devam et",
            "must": ["pulpitis"], "must_not": ["PULPITIS"]}
    before = deepcopy(case)
    assert defects(case) == {"required_and_forbidden_same_term": ["pulpitis"]}
    assert case == before
    case["must_not"] = []
    assert defects(case) == {}
    case["must"] = ["SNB"]
    assert defects(case) == {"required_term_not_visible_anywhere": ["snb"]}


def test_count_override_keeps_topic_without_selecting_a_list_item():
    history = [u("Gingivitis için 12 soru hazırla"), a("12. Amalgam sorusu")]
    resolved = low(resolve_followup_query("yok 12 soru olsun", history))
    assert "gingivitis" in resolved and "12 soru" in resolved
    assert "amalgam" not in resolved


def test_unqualified_continue_resumes_active_task_but_new_topic_resets_slots():
    history = [u("Flor için sınav amaçlı 11 soru hazırla"), a("...")]
    resumed = low(resolve_followup_query("aynı konudan devam et", history))
    assert "flor" in resumed and "11 soru" in resumed and "sınav" in resumed
    history += [u("SNB nedir?"), a("...")]
    resumed = low(resolve_followup_query("aynı konudan devam et", history))
    assert "snb" in resumed
    assert all(x not in resumed for x in ("flor", "11 soru", "sınav"))


def test_benchmark_normalization_folds_turkish_dotless_i():
    from scripts.benchmark_multiturn_continuity_50k import n
    folded = n("sınav kısa ayrıntılı")
    assert "sinav" in folded
    assert "kisa" in folded
    assert "ayrintili" in folded


def test_goal_inheritance_uses_active_state_not_any_old_exam_mention():
    active = [
        {"role":"user","content":"apeksifikasyon anlat"},
        {"role":"assistant","content":"açıklama"},
        {"role":"user","content":"sınav için anlat"},
        {"role":"assistant","content":"sınav özeti"},
    ]
    out = resolve_followup_query("aynı amaçla devam et", active)
    assert "sınav için" in out

    switched = active + [
        {"role":"user","content":"Spee eğrisi anlat"},
        {"role":"assistant","content":"açıklama"},
    ]
    out = resolve_followup_query("aynı amaçla devam et", switched)
    assert "sınav için" not in out


def test_exam_goal_recovers_bounded_typo_variants_without_fuzzy_topic_guessing():
    history = [
        {"role":"user","content":"pulpotomi anlat"},
        {"role":"assistant","content":"açıklama"},
    ]
    for query in ("yok sıav için nlat", "yok sııınav için anlat", "yok sına içi anlat", "yok sav için anlat"):
        out = resolve_followup_query(query, history)
        assert "sınav için" in out
        assert "pulpotomi" in out


def test_same_topic_continuation_survives_bounded_control_word_typos():
    history=[
        {"role":"user","content":"cam iyonomer siman anlat"},
        {"role":"assistant","content":"cam iyonomer siman açıklaması"},
        {"role":"user","content":"bu arada yarın sınav var"},
        {"role":"assistant","content":"anladım"},
    ]
    resolved=resolve_followup_query("aynı onudan devamet",history)
    assert "cam iyonomer" in resolved.casefold()


def test_independent_explain_turn_clears_old_question_task_before_same_way():
    history=[
        {"role":"user","content":"pulpektomi için test hazırla"},
        {"role":"assistant","content":"test"},
        {"role":"user","content":"pulpektomi anlat"},
    ]
    resolved=resolve_followup_query("aynı şekilde devam et",history)
    assert "soru hazırla" not in resolved.casefold()


def test_repeated_letter_ordinal_still_selects_explicit_assistant_item():
    assistant="\n".join(f"{i}. irreversible pulpitis ile ilgili klinik soru {i}" for i in range(1,21))
    history=[{"role":"user","content":"irreversible pulpitis konusunda 20 soru hazırla"},{"role":"assistant","content":assistant}]
    resolved=resolve_followup_query("13. sooruuunun konusunu anlat",history)
    assert "irreversible pulpitis" in resolved.casefold()
    assert "klinik soru 13" in resolved.casefold()


def test_same_way_task_continuation_survives_bounded_control_word_typos():
    history=[
        {"role":"user","content":"sefalometrik analiz için test hazırla"},
        {"role":"assistant","content":"test"},
        {"role":"user","content":"tamam sağ ol"},
        {"role":"assistant","content":"rica ederim"},
    ]
    resolved=resolve_followup_query("ayı şekilde devamet",history)
    assert "sefalometrik" in resolved.casefold()
    assert "soru hazırla" in resolved.casefold()


def test_relative_previous_selects_previous_distinct_user_topic():
    history=[
        {"role":"user","content":"bruksizm anlat"},
        {"role":"assistant","content":"bruksizm açıklaması"},
        {"role":"user","content":"apikal periodontitis anlat"},
        {"role":"assistant","content":"apikal periodontitis açıklaması"},
    ]
    resolved=resolve_followup_query("bir önceki konuya dön",history)
    assert "bruksizm" in resolved.casefold()
    assert "apikal periodontitis" not in resolved.casefold().split("—",1)[0]


def test_relative_before_previous_selects_middle_of_three_topics():
    history=[
        {"role":"user","content":"bruksizm anlat"},
        {"role":"assistant","content":"a"},
        {"role":"user","content":"apikal periodontitis anlat"},
        {"role":"assistant","content":"b"},
        {"role":"user","content":"rejeneratif endodonti anlat"},
        {"role":"assistant","content":"c"},
    ]
    resolved=resolve_followup_query("ondan bir önceki konuya dön",history)
    assert "apikal periodontitis" in resolved.casefold()


def test_ambiguous_generator_inherit_topic_remains_abstention():
    from tests.academic_v2.multiturn_50k_generator import build
    case = build(220)
    assert case.axes["reference"] == "ambiguous_antecedent"
    assert case.axes["state"] == "inherit_topic"
    assert case.expected.get("should_abstain") is True
    assert case.must == ()


def test_structured_reference_gold_uses_selected_item_topic_terms():
    from tests.academic_v2.multiturn_50k_generator import TOPICS, build
    case = build(99)
    assert case.axes["reference"] == "ordinal_item"
    assert case.axes["state"] == "inherit_topic"
    assert case.expected.get("reference") == "assistant_item_13"
    topic_terms = next(terms for topic, terms in TOPICS if topic == case.expected["topic"])
    assert case.must == topic_terms


def test_noisy_ordinal_reference_resolves_selected_item_without_count_confusion():
    history=[
        {"role":"user","content":"pulpektomi konusunda 20 soru hazırla"},
        {"role":"assistant","content":"12. başka konu\n13. pulpektomi klinik soru 13\n14. başka konu"},
    ]
    typo=resolve_followup_query("13. orunu konusunu anlat",history)
    mixed=resolve_followup_query("13. questionnun konusunu anlat",history)
    count=resolve_followup_query("20 soru hazırla",history)
    assert "pulpektomi" in typo.casefold()
    assert "pulpektomi" in mixed.casefold()
    assert "klinik soru 13" not in count.casefold()


def test_generator_inherit_topic_replays_final_active_user_topic():
    from tests.academic_v2.multiturn_50k_generator import TOPICS, build
    case = build(120)
    assert case.axes["reference"] == "relative_previous"
    assert case.axes["state"] == "inherit_topic"
    assert "aynı konudan" in case.expected["_semantic_query_pre_noise"].casefold()
    active = None
    for role, text in case.expected["_semantic_history_pre_noise"]:
        if role != "user" or text.casefold().startswith(("önceden", "eski sorum", "bu arada")) or "aklımda" in text.casefold():
            continue
        for topic, terms in TOPICS:
            if topic.casefold() in text.casefold() or all(term.casefold() in text.casefold() for term in terms):
                active = topic
    assert active is not None
    assert case.expected["topic"] == active


def test_relative_generator_gold_tracks_final_ordered_chain():
    from tests.academic_v2.multiturn_50k_generator import build
    previous = build(7)
    before_previous = build(8)
    assert previous.axes["reference"] == "relative_previous"
    assert previous.expected["topic"] in previous.history[-4][1]
    assert previous.expected["topic"] not in previous.history[-2][1]
    assert before_previous.axes["reference"] == "relative_before_previous"
    assert before_previous.expected["topic"] in before_previous.history[-4][1]
    assert before_previous.expected["topic"] not in before_previous.history[-2][1]


def test_before_previous_and_heavy_noisy_continue_are_bounded_regressions():
    history=[
        u("bruksizm anlat"),a("a"),
        u("apikal periodontitis anlat"),a("b"),
        u("rejeneratif endodonti anlat"),a("c"),
    ]
    out=low(resolve_followup_query("ondan bir önceki konuya dön",history))
    assert "bruksizm" in out
    assert "rejeneratif endodonti" not in out.split("—",1)[0]

    task_history=[u("internal rezorpsiyon için test hazırla"),a("test")]
    noisy=low(resolve_followup_query("ayı şekilde evam et",task_history))
    assert "internal rezorpsiyon" in noisy
    assert "soru hazırla" in noisy
