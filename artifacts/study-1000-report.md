1000 senaryonun yerel niyet/bağlam testi

Sonuç: 663/1000 (%66.3); başarısız/inceleme gereken: 337.

Bu oran canlı retrieval/cevap doğruluğu değildir. SQL, gerçek chunk seçimi, kaynak yeterliliği, Gemini cevabı ve girişli /ask-stream doğrulanmadı.

| Kategori | Geçti | Toplam | % |
|---|---:|---:|---:|
| course_quiz | 0 | 50 | 0.0 |
| course_summary | 28 | 50 | 56.0 |
| course_teaching | 28 | 50 | 56.0 |
| depth_repair | 42 | 50 | 84.0 |
| exam_priorities | 25 | 50 | 50.0 |
| frustration | 36 | 50 | 72.0 |
| grouped_quiz_answers | 50 | 50 | 100.0 |
| multipart_request | 0 | 50 | 0.0 |
| named_definition | 49 | 50 | 98.0 |
| named_numeric_fact | 48 | 50 | 96.0 |
| named_procedure | 49 | 50 | 98.0 |
| ordinal_quiz_reference | 50 | 50 | 100.0 |
| outline_format | 42 | 50 | 84.0 |
| qualifier_replacement | 0 | 50 | 0.0 |
| return_previous_topic | 0 | 50 | 0.0 |
| single_quiz_answer | 50 | 50 | 100.0 |
| source_markings | 25 | 50 | 50.0 |
| topic_switch_during_quiz | 49 | 50 | 98.0 |
| unbound_reference | 42 | 50 | 84.0 |
| unknown_topic | 50 | 50 | 100.0 |

Başarısız kontrol türleri: {"course_scope": 119, "context_reference": 85, "qualifier": 50, "facets": 50, "task": 28, "visual_source": 25, "not_grading": 11, "conversation_repair": 14, "named_subject": 7, "unbound_clarification": 8, "no_stale_context": 1, "no_stale_qualifier": 1}

Beklentiler ölçüm öncesinde donduruldu. Bütün kontroller geçmeden senaryo başarılı sayılmadı. İşaretlenenler kök sebep/gold incelemesi gerektirir.

Farklı soru metni: 860; soru + geçmiş + beklenti bakımından farklı senaryo: 1000. Aynı kısa cevap/komutun farklı bağlamlarda davranışı da ölçüldü.

Canlı uçtan uca doğrulanan: 0/1000. Üretim doğruluk yüzdesi: ölçülmedi.
