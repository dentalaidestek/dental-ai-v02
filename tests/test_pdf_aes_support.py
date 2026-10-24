from pypdf import PdfReader, PdfWriter
from pypdf.errors import FileNotDecryptedError
import pytest
from app.academic_material_status import failure_reason


def encrypted_pdf(path, password):
    writer = PdfWriter()
    writer.add_blank_page(width=596, height=865)
    writer.encrypt(password, owner_password='test-owner-only', algorithm='AES-128')
    writer.write(path)


def test_reader_opens_empty_password_aes_pdf_without_source_rewrite(tmp_path):
    path = tmp_path / 'aes.pdf'
    encrypted_pdf(path, '')
    original = path.read_bytes()
    reader = PdfReader(path)
    assert reader.is_encrypted
    assert len(reader.pages) == 1
    assert path.read_bytes() == original


def test_reader_still_rejects_a_real_password_requirement(tmp_path):
    path = tmp_path / 'password.pdf'
    encrypted_pdf(path, 'required-password')
    with pytest.raises(FileNotDecryptedError):
        len(PdfReader(path).pages)


def test_missing_aes_dependency_has_safe_actionable_status():
    code, message = failure_reason('cryptography>=3.1 is required for AES algorithm')
    assert code == 'PDF_AES_SUPPORT_MISSING'
    assert 'eksik' in message
