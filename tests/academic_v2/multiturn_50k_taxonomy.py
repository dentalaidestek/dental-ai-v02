"""Taxonomy for the 50k Academic AI multi-turn continuity benchmark.

Keep this file data-only. The generator composes these axes instead of
hard-coding 50k near-duplicate sentences.
"""
TAXONOMY_VERSION="2026-10-04.1"
INTERACTION=[
"recollection_near","recollection_far","expansion","refinement","followup",
"topic_switch_explicit","topic_switch_implicit","return_to_old_topic",
"same_task_new_topic","same_topic_new_task","goal_switch","format_switch",
"scope_narrow","scope_expand","regenerate","correction","negation_override",
"comparison_add_target","comparison_replace_target","abandon_previous",
]
REFERENCE=[
"pronoun_bu","pronoun_o","previous_answer","previous_user_turn","ordinal_item",
"ordinal_question","relative_previous","relative_before_previous","named_topic",
"implicit_subject","multi_hop","ambiguous_antecedent","missing_antecedent",
"assistant_list_item","assistant_prose_forbidden_subject",
]
STATE=[
"inherit_topic","inherit_task","inherit_goal","inherit_format","inherit_count",
"replace_topic","replace_task","replace_goal","replace_format","replace_count",
"clear_topic","clear_task","clear_goal","clear_count","qualifier_add",
"qualifier_replace","qualifier_remove","stale_state_trap","error_propagation_trap",
]
LANGUAGE=[
"clean","typo_light","typo_heavy","missing_diacritics","phonetic_spelling",
"missing_spaces","extra_spaces","no_punctuation","fragment","ellipsis",
"colloquial","slang","anger","polite","telegraphic","mixed_turkish_latin",
"abbreviation","case_noise","repeated_letters","self_correction_mid_sentence",
]
DISTRACTOR=[
"none","assistant_dental_terms","assistant_wrong_topic","user_side_comment",
"irrelevant_turn","two_candidate_topics","same_term_different_context",
"old_count","old_format","old_goal","old_qualifier","quoted_old_question",
]
DISTANCE=[1,2,3,4,5,6,7,8]
TURN_LENGTH=[2,3,4,5,6,7,8,9,10]
EXPECTED_FIELDS=("topic","task","goal","format","count","length","reference","qualifiers")
FAILURE_LABELS=(
"wrong_topic","stale_topic","task_loss","wrong_task","goal_loss","wrong_goal",
"format_loss","wrong_format","count_loss","wrong_count","qualifier_leak",
"reference_miss","wrong_reference","assistant_prose_leak","error_propagation",
"unresolved_but_should_resolve","resolved_but_should_abstain","exception",
)
