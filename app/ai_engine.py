import json


SYSTEM_PROMPT = """
Sen yalnızca DİŞ HEKİMLİĞİ alanında çalışan bir klinik karar destek yapay zekasısın.

TEMEL AMAÇ:
Hekime, mevcut klinik bilgiler, yüklenen dental görüntü ve Dental AI RAG kanıtları
üzerinden kısa, yapılandırılmış, kanıta dayalı ve klinik olarak uygulanabilir karar desteği ver.

KANIT VE GÖRÜNTÜ ÖNCELİĞİ:
1. Görüntüde gerçekten gözlenen bulgular.
2. Hekimin klinik muayene/not bilgileri ve diş numarası.
3. Hekimin ek cevapları.
4. Router tarafından seçilmiş branş kaynakları.
Kaynakta geçen bir durum sırf kaynakta bulunduğu için hastada var kabul edilmez.

GÖRÜNTÜ:
Görüntü verildiyse gerçekten incele. Yalnız desteklenen bulguları yaz.
Görülemeyen, görüntü kalitesi nedeniyle değerlendirilemeyen veya klinik test gerektiren
bir bulguyu görüntüde varmış gibi uydurma. Görüntü yoksa radyografik bulgu yazma.

KLİNİK ÇIKTI:
- En olası klinik durumu kısa gerekçeyle belirt.
- Önemli görüntü/klinik bulguları belirt.
- Tedavi seçeneklerini klinik öncelik sırasına göre sırala.
- Tedaviye bağlı dikkat edilecekleri yalnız vaka-özel, gerçekten ilgili komplikasyon/risk
  olarak yaz; genel komplikasyon listesi dökme.
- Mevcut bilgilerle önerilen yaklaşımı belirt.
- "differential" alanını yalnız EN SONDA gösterilecek "Diğer Olası Tanılar" için kullan.

TEDAVİ ÖNCELİĞİ:
Tedavi seçenekleri rastgele alternatifler değildir.
1. madde mevcut kanıta göre en uygun/öncelikli yaklaşım olmalı.
2. ve 3. madde yalnız klinik olarak makul alternatiflerse yer almalı.
Görüntü/klinik destek olmadan agresif tedaviyi yalnız ihtimal diye ekleme.
Bir tedavinin uygulanabilirliği restorabilite, periodontal destek, kök maturasyonu,
anatomik komşuluk, hasta yaşı/iş birliği veya benzeri bir kritik koşula bağlıysa bunu hesaba kat.

HEKİME SORU KARAR KURALI:
Ön analizde soru üretmeden önce tedavi seçeneklerini ve tedaviye bağlı riskleri düşün.
Bir soru SADECE aşağıdakilerden en az birini gerçekten değiştirecekse sor:
1. 1., 2. veya 3. tedavinin sırasını değiştirmek,
2. seçilen tedavinin uygulanabilir olup olmadığını değiştirmek,
3. vaka-özel önemli bir tedavi komplikasyon/riskini anlamlı biçimde değiştirmek.

Bunların hiçbirini değiştirmiyorsa soru SORMA.
Verilmiş bilgiyi tekrar sorma. Aynı bilgiyi başka cümleyle tekrar sorma.
Sırf merak, rutin anamnez veya kaynakta geçtiği için soru sorma.
Maksimum 3 soru; 0 soru tamamen geçerlidir.
Tüm sorular kısa serbest metin cevabı istemeli ve type daima "TEXT" olmalıdır.
Soruyu mümkünse hangi test/bulgu gerektiğini açık söyleyecek şekilde yaz
(örn. "Soğuk testine yanıtın süresi nedir?" veya "Sondlamada izole derin cep var mı?").
VAR/YOK butonu, 1-10 ölçek, sayısal input veya seçenekli soru üretme.

KOMPLİKASYON / DİKKAT:
"treatment_cautions" alanı tedavi sırasında veya sonrasında klinik önemi olan,
vakadaki görüntü/klinik bulguyla bağlantılı riskleri içerir.
Örn. açık apeks, ince kök duvarı, sinüs/kanal yakınlığı, ileri kemik kaybı,
kök rezorpsiyonu, gömülü diş komşuluğu, antirezorptif kullanımı, zor hava yolu gibi.
Kanıt yoksa genel/teorik risk uydurma; boş liste dönebilir.

KLİNİK SINIR:
Bu sistem hekimin muayenesinin yerini almaz. Hasta hakkında verilmemiş bilgi uydurma.
Belirsizliği açıkla ama görüntü analizinden veya klinik karar desteğinden kaçınma.
"""


def _clean(text):
    if not text:
        return ""
    return str(text).strip()


def build_preliminary_prompt(
    tooth_number,
    clinical_notes,
    image_path=None,
    knowledge_context=""
):
    return f"""
{SYSTEM_PROMPT}

DENTAL VAKA ÖN ANALİZİ YAP.

Diş: {_clean(tooth_number)}

Klinik bilgi:
{_clean(clinical_notes)}

Görüntü:
{
    "Görüntüyü gerçekten incele; yalnız görüntüde desteklenen bulguları kullan."
    if image_path
    else
    "Görüntü yok. Radyografik/görsel bulgu uydurma."
}

Router tarafından seçilen kanıt bağlamı:
{knowledge_context}

ÖNCE içinden şu karar kontrolünü yap:
- En olası durum nedir?
- En uygun 1-3 tedavi hangileridir ve sıraları nedir?
- Bu tedavilerde vaka-özel hangi komplikasyon/dikkat noktaları vardır?
- Eksik bir bilgi tedavi sırasını, uygulanabilirliğini veya bu riski gerçekten değiştirir mi?
Yalnız son sorunun cevabı EVET ise soru üret.

SADECE GEÇERLİ JSON DÖNDÜR. Markdown kullanma.
JSON:

{{
  "status": "ANALYSIS_COMPLETE",
  "most_likely": "En olası durum ve kısa gerekçe.",
  "findings": ["Önemli bulgu 1", "Önemli bulgu 2"],
  "treatment_options": [
    "En öncelikli tedavi",
    "Klinik olarak makul ikinci seçenek",
    "Varsa üçüncü seçenek"
  ],
  "treatment_cautions": [
    "Seçilen tedaviyle doğrudan ilişkili vaka-özel dikkat/komplikasyon noktası"
  ],
  "preferred_approach": "Mevcut bilgilerle önerilen kısa yaklaşım.",
  "differential": ["Diğer olası tanı 1", "Diğer olası tanı 2"],
  "recommended_evaluation": ["Soru gerektirmeyen ama hekimce doğrulanması uygun değerlendirme"],
  "questions": [
    {{
      "question": "Tedavi kararını gerçekten değiştiren kısa klinik soru",
      "type": "TEXT"
    }}
  ],
  "uncertainty": "Kısa belirsizlik/hekimin doğrulaması gereken nokta."
}}

KURALLAR:
- Her liste kısa olsun.
- findings en fazla 3.
- treatment_options en fazla 3 ve önem sırasına göre.
- treatment_cautions en fazla 3; yalnız vaka-özel.
- differential en fazla 2 ve sonuç ekranında en sonda kullanılacak.
- questions 0-3; type yalnız TEXT.
- Soru yalnız tedavi sırası, uygulanabilirliği veya tedavi komplikasyon riskini değiştiriyorsa sor.
- Tedaviyi değiştirmeyecek test/bilgi için soru üretme.
- Görüntüde olmayan bulgu uydurma.
- JSON'u tamamen kapat.
"""


def build_final_prompt(
    tooth_number,
    clinical_notes,
    answers,
    image_path=None,
    knowledge_context=""
):
    return f"""
{SYSTEM_PROMPT}

DENTAL VAKA NİHAİ ANALİZİ YAP.

Diş:
{_clean(tooth_number)}

İlk klinik bilgi:
{_clean(clinical_notes)}

Hekimin yeni cevapları:
{json.dumps(answers, ensure_ascii=False)}

Görüntü:
{
    "Görüntüyü gerçekten incele; yalnız desteklenen objektif bulguları kullan."
    if image_path
    else
    "Görüntü yok. Radyografik/görsel bulgu uydurma."
}

Router tarafından seçilen kanıt bağlamı:
{knowledge_context}

Hekimin yeni cevaplarını kullanarak tedavi sırasını, uygulanabilirliği ve
tedaviye bağlı dikkat/komplikasyonları YENİDEN değerlendir.
Ön analizdeki tedaviyi körü körüne koruma; cevap gerçekten kararı değiştiriyorsa güncelle.

SADECE GEÇERLİ JSON DÖNDÜR. Markdown kullanma.
JSON:

{{
  "status": "FINAL",
  "most_likely": "En olası durum ve kısa gerekçe.",
  "findings": ["Önemli bulgu 1", "Önemli bulgu 2"],
  "treatment_options": [
    "En öncelikli tedavi",
    "Klinik olarak makul ikinci seçenek",
    "Varsa üçüncü seçenek"
  ],
  "treatment_cautions": [
    "Tedaviyle doğrudan ilişkili vaka-özel dikkat/komplikasyon noktası"
  ],
  "preferred_approach": "Yeni cevaplarla önerilen kısa yaklaşım.",
  "differential": ["Diğer olası tanı 1", "Diğer olası tanı 2"]
}}

KURALLAR:
- findings en fazla 3.
- treatment_options en fazla 3 ve önem sırasına göre.
- treatment_cautions en fazla 3; yalnız vaka-özel.
- differential en fazla 2 ve en sonda.
- Görüntüde olmayan bulgu uydurma.
- Klinik bilgiyi görüntü bulgusu gibi gösterme.
- Final aşamada soru sorma.
- JSON'u tamamen kapat.
"""

def parse_ai_result(text):
    """
    AI çıktısını güvenli şekilde JSON'a çevirir.
    Markdown json çitlerini kaldırır ve geçerli JSON
    bulunamazsa RAW döndürür.
    """

    if not text:
        return {
            "status": "AI_INVALID",
            "error": "AI boş cevap döndürdü."
        }

    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

    try:
        result = json.loads(cleaned)

        if isinstance(result, dict):
            status = result.get("status")

            if status == "ANALYSIS_COMPLETE":
                result["status"] = "INITIAL"

            return result

    except json.JSONDecodeError:
        pass

    # Cevabın içinde JSON nesnesi varsa bulmayı dene.
    first = cleaned.find("{")
    last = cleaned.rfind("}")

    if first != -1 and last > first:
        candidate = cleaned[first:last + 1]

        try:
            result = json.loads(candidate)

            if isinstance(result, dict):
                if result.get("status") == "ANALYSIS_COMPLETE":
                    result["status"] = "INITIAL"

                return result

        except json.JSONDecodeError:
            pass

    return {
        "status": "RAW",
        "text": text
    }



# Gemini generateContent structured-output şemaları.
# Bunlar yalnızca çıktı biçimini sabitler; klinik içerik kuralları promptta kalır.
PRELIMINARY_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "status": {"type": "STRING", "enum": ["ANALYSIS_COMPLETE"]},
        "most_likely": {"type": "STRING"},
        "findings": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 3},
        "treatment_options": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 3},
        "treatment_cautions": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 3},
        "preferred_approach": {"type": "STRING"},
        "differential": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "recommended_evaluation": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "questions": {
            "type": "ARRAY",
            "maxItems": 3,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "question": {"type": "STRING"},
                    "type": {"type": "STRING", "enum": ["TEXT"]},
                },
                "required": ["question", "type"],
            },
        },
        "uncertainty": {"type": "STRING"},
    },
    "required": [
        "status",
        "most_likely",
        "findings",
        "treatment_options",
        "treatment_cautions",
        "preferred_approach",
        "differential",
        "recommended_evaluation",
        "questions",
        "uncertainty",
    ],
}

FINAL_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "status": {"type": "STRING", "enum": ["FINAL"]},
        "most_likely": {"type": "STRING"},
        "findings": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 3},
        "treatment_options": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 3},
        "treatment_cautions": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 3},
        "preferred_approach": {"type": "STRING"},
        "differential": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
    },
    "required": [
        "status",
        "most_likely",
        "findings",
        "treatment_options",
        "treatment_cautions",
        "preferred_approach",
        "differential",
    ],
}


_ALLOWED_QUESTION_TYPES = {"TEXT"}


def _invalid_result(message):
    return {
        "status": "AI_INVALID",
        "error": message,
    }


def _valid_text(value):
    return isinstance(value, str) and bool(value.strip())


def _valid_string_list(value):
    return isinstance(value, list) and all(_valid_text(item) for item in value)


def validate_preliminary_result(result):
    """Ön analiz JSON'unu template'e verilmeden önce doğrular ve normalize eder."""
    if not isinstance(result, dict):
        return _invalid_result("AI beklenen klinik sonuç formatını oluşturamadı.")

    if result.get("status") not in {"ANALYSIS_COMPLETE", "INITIAL"}:
        return _invalid_result("AI beklenen ön analiz durumunu üretmedi.")

    for field in ("most_likely", "preferred_approach", "uncertainty"):
        if not _valid_text(result.get(field)):
            return _invalid_result(f"AI ön analizinde '{field}' alanı eksik veya geçersiz.")

    for field in (
        "differential",
        "findings",
        "treatment_options",
        "treatment_cautions",
        "recommended_evaluation",
    ):
        if not _valid_string_list(result.get(field)):
            return _invalid_result(f"AI ön analizinde '{field}' alanı eksik veya geçersiz.")
        limit = 3 if field in {"findings", "treatment_options", "treatment_cautions"} else 2
        result[field] = result[field][:limit]

    questions = result.get("questions")
    if not isinstance(questions, list):
        return _invalid_result("AI ön analizindeki soru listesi geçersiz.")

    clean_questions = []
    for item in questions[:3]:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        question_type = item.get("type")
        if not _valid_text(question) or question_type not in _ALLOWED_QUESTION_TYPES:
            continue
        clean_questions.append({
            "question": question.strip(),
            "type": question_type,
        })

    # Boş soru listesi geçerlidir; yeterli bilgi varsa model soru sormayabilir.
    result["questions"] = clean_questions
    result["status"] = "INITIAL"
    return result


def validate_final_result(result):
    """Nihai analiz JSON'unu doğrular ve yalnız geçerli ise FINAL kabul eder."""
    if not isinstance(result, dict):
        return _invalid_result("AI beklenen final sonuç formatını oluşturamadı.")

    if result.get("status") != "FINAL":
        return _invalid_result("AI beklenen final analiz durumunu üretmedi.")

    for field in ("most_likely", "preferred_approach"):
        if not _valid_text(result.get(field)):
            return _invalid_result(f"AI final analizinde '{field}' alanı eksik veya geçersiz.")

    for field in ("differential", "findings", "treatment_options", "treatment_cautions"):
        if not _valid_string_list(result.get(field)):
            return _invalid_result(f"AI final analizinde '{field}' alanı eksik veya geçersiz.")
        limit = 3 if field in {"findings", "treatment_options", "treatment_cautions"} else 2
        result[field] = result[field][:limit]

    result["status"] = "FINAL"
    return result
