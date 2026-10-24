"""Owned per-file indexing status; never expose raw worker exceptions."""
from sqlalchemy import text


def failure_reason(error):
    value = str(error or '').lower()
    rules = [
        ('pdf_page_limit', 'PDF_PAGE_LIMIT', 'PDF, indeksleme sayfa sınırını aşıyor.'),
        ('no_chunks_for_page', 'NO_CHUNKS_FOR_PAGE', 'Bir sayfadan kullanılabilir metin parçası oluşturulamadı.'),
        ('tessdata', 'OCR_CONFIGURATION', 'OCR dil dosyaları yapılandırılmamış.'),
        ('tesseract', 'OCR_CONFIGURATION', 'OCR motoru yapılandırması tamamlanamadı.'),
        ('no module named', 'DEPENDENCY_MISSING', 'İndeksleme çalışanında gerekli bir yazılım bileşeni eksik.'),
        ('does not exist', 'SCHEMA_MISMATCH', 'İndeksleme çalışanı ile veritabanı şeması uyuşmuyor.'),
        ('index_artifact_mismatch', 'INDEX_ARTIFACT_MISMATCH', 'Kaydedilmiş indeks parçaları doğrulanamadı.'),
        ('build_incomplete', 'BUILD_INCOMPLETE', 'Dosyanın tüm indeksleme adımları tamamlanamadı.'),
        ('unsupported_ocr_provider', 'OCR_CONFIGURATION', 'OCR sağlayıcısı yapılandırması desteklenmiyor.'),
        ('unsupported_v2_mime', 'UNSUPPORTED_FILE', 'Bu dosya türü indekslenemiyor.'),
        ('429', 'PROVIDER_RATE_LIMIT', 'İşleme sağlayıcısının kullanım sınırına ulaşıldı.'),
        ('quota', 'PROVIDER_QUOTA', 'İşleme sağlayıcısının kotası doldu.'),
        ('api key', 'PROVIDER_CONFIGURATION', 'İşleme sağlayıcısının erişim ayarı eksik veya geçersiz.'),
        ('timeout', 'PROCESSING_TIMEOUT', 'İndeksleme işlemi zaman aşımına uğradı.'),
        ('timed out', 'PROCESSING_TIMEOUT', 'İndeksleme işlemi zaman aşımına uğradı.'),
        ('no such file', 'SOURCE_MISSING', 'İndeksleme çalışanı kaynak dosyaya ulaşamadı.'),
        ('not found', 'SOURCE_MISSING', 'Kaynak veya işleme hizmeti bulunamadı.'),
        ('provider:', 'PROVIDER_FAILED', 'İşleme sağlayıcısı dosyayı tamamlayamadı.'),
    ]
    return next(((code, message) for token, code, message in rules if token in value),
                ('INDEX_FAILED', 'Dosyanın indekslenmesi tamamlanamadı.'))


def owned_material_status(session, *, owner_user_id, course_id):
    rows = session.execute(text('''
        SELECT m.id,m.display_name,m.original_filename,m.index_status,
               m.active_index_version,m.building_index_version,m.index_error,
               j.id AS job_id,j.status AS job_status,j.stage,j.last_error
        FROM studymaterial m LEFT JOIN studyindexjob j
          ON j.owner_user_id=m.owner_user_id AND j.course_id=m.course_id
         AND j.material_id=m.id
         AND j.index_version=COALESCE(m.building_index_version,m.active_index_version)
        WHERE m.owner_user_id=:owner AND m.course_id=:course AND m.deleted_at IS NULL
        ORDER BY m.id
    '''), {'owner': owner_user_id, 'course': course_id}).mappings().all()
    files = []
    for row in rows:
        usable = row['index_status'] == 'READY' and bool(row['active_index_version'])
        orphan = bool(row['building_index_version']) and row['job_id'] is None
        failed = row['job_status'] in ('FAILED', 'CANCELLED') or row['index_status'] == 'FAILED' or orphan
        code, message = (None, None)
        if failed:
            if orphan:
                code, message = 'INDEX_JOB_MISSING', 'Bu dosyanın bekleyen indeksleme işi bulunamadı.'
            elif row['job_status'] == 'CANCELLED':
                code, message = 'INDEX_CANCELLED', 'Bu dosyanın indeksleme işi iptal edilmiş.'
            else:
                code, message = failure_reason(row['last_error'] or row['index_error'])
        state = ('update_failed' if failed else 'updating' if row['building_index_version'] else 'ready') if usable else 'failed' if failed else 'preparing'
        files.append(dict(id=row['id'], filename=row['display_name'] or row['original_filename'],
            state=state, usable=usable, stage=row['stage'], error_code=code, message=message))
    usable_count = sum(item['usable'] for item in files)
    complete = bool(files) and all(item['state'] == 'ready' for item in files)
    return dict(ready=usable_count > 0, complete=complete, completed=usable_count,
                total=len(files), state='ready' if complete else 'partial' if usable_count else
                'failed' if any(item['state'] == 'failed' for item in files) else 'preparing', files=files)
