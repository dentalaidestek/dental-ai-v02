import io
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject
from app.academic_page_images import question_page_attachments


def test_exam_page_image_preserves_orientation_source_and_readable_dimensions():
    writer=PdfWriter()
    page=writer.add_blank_page(width=200,height=300)
    content=DecodedStreamObject()
    content.set_data(b'1 0 0 rg 0 280 20 20 re f')
    page[NameObject('/Contents')]=writer._add_object(content)
    output=io.BytesIO();writer.write(output)
    source={'mime_type':'application/pdf','data':output.getvalue(),
            'material_id':26,'page_number':4,'label':'Owned file, page 4'}
    converted=question_page_attachments([source])[0]
    assert converted['material_id']==26 and converted['page_number']==4
    assert converted['label']==source['label'] and source['mime_type']=='application/pdf'
    assert converted['mime_type']=='image/jpeg'
    with Image.open(io.BytesIO(converted['data'])) as image:
        assert image.size==(600,900)
        red,green,blue=image.getpixel((15,15))
        assert red>240 and green<20 and blue<20
    assert len(converted['data'])<=12*1024*1024
    detailed=question_page_attachments([source],top_detail=True)
    assert len(detailed)==2 and detailed[1]['page_number']==4
    with Image.open(io.BytesIO(detailed[1]['data'])) as image:
        assert image.size==(600,225)
        red,green,blue=image.getpixel((15,15))
        assert red>240 and green<20 and blue<20


def test_unreadable_pdf_is_retained_instead_of_dropping_the_source():
    source={'mime_type':'application/pdf','data':b'not a valid PDF','page_number':7}
    converted=question_page_attachments([source])[0]
    assert converted['data']==source['data'] and converted['page_number']==7
    assert converted['mime_type']=='application/pdf'
