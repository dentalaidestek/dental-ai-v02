"""Deterministic product-specific corpus for Academic AI retrieval planning.

This is training-data infrastructure, not a benchmark and not a live parser.
Families are split by semantic construction so surface paraphrases of the same
template cannot leak across train/validation/test.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import random
from typing import Iterable

from app.academic_retrieval_plan import AcademicRetrievalPlan, ComparisonRequirement, RetrievalNeed


@dataclass(frozen=True)
class TrainingExample:
    example_id: str
    family: str
    split: str
    utterance: str
    plan: AcademicRetrievalPlan

    def to_json(self) -> str:
        payload = asdict(self)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_SUBJECTS = (
    ("pulpitis", "pulpitis"),
    ("pulp_necrosis", "pulpa nekrozu"),
    ("caries", "dental çürük"),
    ("third_molar", "üçüncü molar"),
    ("working_length", "çalışma boyu"),
    ("probing_depth", "sondalama derinliği"),
    ("sna", "SNA"),
    ("snb", "SNB"),
)
_FACETS = (
    ("diagnosis", "tanısını"),
    ("treatment", "tedavisini"),
    ("complication", "komplikasyonlarını"),
    ("classification", "sınıflamasını"),
    ("measurement", "nasıl ölçüldüğünü"),
    ("value", "normal değerini"),
)


_FAMILY_SPLITS = {
    # Split by semantic construction, never by individual paraphrase.
    "single_subject_multi_facet": "train",
    "two_subject_asymmetric_facets": "train",
    "symmetric_comparison": "validation",
    "past_question_to_note_dependency": "test",
}


def _split_for_family(family: str) -> str:
    try:
        return _FAMILY_SPLITS[family]
    except KeyError as exc:
        raise ValueError(f"semantic family has no explicit split: {family}") from exc


def _example_id(family: str, utterance: str) -> str:
    digest = hashlib.sha256((family + "\0" + utterance).encode("utf-8")).hexdigest()[:16]
    return f"{family}:{digest}"


def _need(need_id: str, subject_id: str, subject: str, facet: str, **kwargs) -> RetrievalNeed:
    return RetrievalNeed(
        need_id=need_id,
        subject_ids=(subject_id,),
        subject_terms=(subject,),
        facet=facet,
        **kwargs,
    )


def _single_subject_examples() -> Iterable[TrainingExample]:
    family = "single_subject_multi_facet"
    split = _split_for_family(family)
    forms = (
        "{subject} için {left} ve {right} nottan anlat",
        "{subject} {left}; ayrıca {right} çıkar",
        "{subject} konusunda {left} ile {right} lazım",
    )
    for subject_id, subject in _SUBJECTS[:4]:
        for (left_facet, left), (right_facet, right) in zip(_FACETS, _FACETS[1:]):
            for form in forms:
                utterance = form.format(subject=subject, left=left, right=right)
                plan = AcademicRetrievalPlan(
                    original_query=utterance,
                    needs=(
                        _need("n1", subject_id, subject, left_facet),
                        _need("n2", subject_id, subject, right_facet),
                    ),
                )
                yield TrainingExample(_example_id(family, utterance), family, split, utterance, plan)


def _asymmetric_examples() -> Iterable[TrainingExample]:
    family = "two_subject_asymmetric_facets"
    split = _split_for_family(family)
    forms = (
        "{a} {fa}, {b} ise {fb} anlat",
        "{a} için {fa}; ama {b} için {fb} lazım",
        "{a} {fa} ile {b} {fb} nottan çıkar",
    )
    subject_pairs = zip(_SUBJECTS[::2], _SUBJECTS[1::2])
    facet_pairs = (("diagnosis", "tanısını", "treatment", "tedavisini"),
                   ("value", "normal değerini", "measurement", "nasıl ölçüldüğünü"))
    for (aid, a), (bid, b) in subject_pairs:
        for af, fa, bf, fb in facet_pairs:
            for form in forms:
                utterance = form.format(a=a, b=b, fa=fa, fb=fb)
                plan = AcademicRetrievalPlan(
                    original_query=utterance,
                    needs=(_need("a", aid, a, af), _need("b", bid, b, bf)),
                )
                yield TrainingExample(_example_id(family, utterance), family, split, utterance, plan)


def _comparison_examples() -> Iterable[TrainingExample]:
    family = "symmetric_comparison"
    split = _split_for_family(family)
    forms = (
        "{a} ile {b} {dimension} karşılaştır",
        "{a} ve {b} arasında {dimension} farkını nottan çıkar",
    )
    for (aid, a), (bid, b) in ((("sna", "SNA"), ("snb", "SNB")),
                               (("pulpitis", "pulpitis"), ("pulp_necrosis", "pulpa nekrozu"))):
        for facet, dimension in (("value", "normal değer"), ("diagnosis", "tanısal bulgu")):
            for form in forms:
                utterance = form.format(a=a, b=b, dimension=dimension)
                plan = AcademicRetrievalPlan(
                    original_query=utterance,
                    answer_operation="compare",
                    needs=(_need("a", aid, a, facet), _need("b", bid, b, facet)),
                    comparisons=(ComparisonRequirement(("a", "b"), (facet,)),),
                )
                yield TrainingExample(_example_id(family, utterance), family, split, utterance, plan)


def _historical_dependency_examples() -> Iterable[TrainingExample]:
    family = "past_question_to_note_dependency"
    split = _split_for_family(family)
    forms = (
        "Geçmiş sorularda {subject} için neyin yoklandığını bul, sonra nottan o yerleri özetle",
        "Hocanın {subject} sorularında ölçtüğü kavramları çıkar ve nottaki karşılıklarını çalıştır",
        "Çıkmış {subject} sorularından test edilen noktaları belirle; kanıtı ders notundan getir",
    )
    for subject_id, subject in _SUBJECTS[:6]:
        for form in forms:
            utterance = form.format(subject=subject)
            plan = AcademicRetrievalPlan(
                original_query=utterance,
                answer_operation="summarize",
                needs=(
                    _need("history", subject_id, subject, "tested_concept", sources=("past_questions",)),
                    _need(
                        "notes", subject_id, subject, "study_evidence",
                        sources=("notes",), depends_on=("history",),
                    ),
                ),
                metadata=(("student_marking_is_truth", "false"),),
            )
            yield TrainingExample(_example_id(family, utterance), family, split, utterance, plan)


def build_training_examples(seed: int = 20261004) -> tuple[TrainingExample, ...]:
    examples = [
        *_single_subject_examples(),
        *_asymmetric_examples(),
        *_comparison_examples(),
        *_historical_dependency_examples(),
    ]
    random.Random(seed).shuffle(examples)
    ids = [item.example_id for item in examples]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate training example id")
    utterances = [item.utterance.casefold() for item in examples]
    if len(utterances) != len(set(utterances)):
        raise ValueError("duplicate training utterance")
    return tuple(examples)


def corpus_report(examples: Iterable[TrainingExample]) -> dict[str, object]:
    rows = tuple(examples)
    by_split = {split: sum(item.split == split for item in rows) for split in ("train", "validation", "test")}
    families = sorted({item.family for item in rows})
    leakage = [
        family for family in families
        if len({item.split for item in rows if item.family == family}) != 1
    ]
    return {
        "count": len(rows),
        "families": len(families),
        "by_split": by_split,
        "family_split_leakage": tuple(leakage),
    }


if __name__ == "__main__":
    examples = build_training_examples()
    print(json.dumps(corpus_report(examples), ensure_ascii=False, sort_keys=True))
    for example in examples:
        print(example.to_json())
