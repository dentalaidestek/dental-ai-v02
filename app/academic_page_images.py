"""Bounded local page rendering for reading photographed exam questions."""
import io
import threading

_PDFIUM_LOCK = threading.Lock()  # PDFium is not safe for concurrent calls.
_MAX_BYTES = 12 * 1024 * 1024


def question_page_attachments(attachments, *, top_detail=False):
    """Preserve source labels and page geometry; no OCR or provider call."""
    result=[]
    remaining=_MAX_BYTES-sum(len(item.get('data',b'')) for item in attachments)
    for item in attachments:
        data=item.get('data')
        converted=None
        if item.get('mime_type')=='application/pdf' and isinstance(data,bytes):
            try:
                import pypdfium2 as pdfium
                with _PDFIUM_LOCK:
                    document=pdfium.PdfDocument(data)
                    try:
                        if len(document)==1:
                            page=document[0]
                            try:
                                width,height=page.get_size()
                                bitmap=page.render(scale=min(3,3200/max(width,height)))
                                try:
                                    image=bitmap.to_pil().convert('RGB')
                                    try:
                                        output=io.BytesIO()
                                        image.save(output,format='JPEG',quality=92)
                                        converted=output.getvalue()
                                    finally:
                                        image.close()
                                finally:
                                    bitmap.close()
                            finally:
                                page.close()
                    finally:
                        document.close()
            except Exception:
                # The original stays available if a local decoder cannot read
                # it. Never drop a source page or claim its contents were read.
                converted=None
        if converted and len(converted)<=remaining+len(data):
            remaining+=len(data)-len(converted)
            item={**item,'data':converted,'mime_type':'image/jpeg'}
        result.append({**item,'media_resolution':'MEDIA_RESOLUTION_HIGH'})
    if top_detail:
        from PIL import Image
        for item in list(result):
            if item.get('mime_type')!='image/jpeg':
                continue
            try:
                with Image.open(io.BytesIO(item['data'])) as image:
                    crop=image.crop((0,0,image.width,max(1,image.height//4)))
                    try:
                        output=io.BytesIO();crop.save(output,format='JPEG',quality=92)
                        data=output.getvalue()
                    finally:
                        crop.close()
                if len(data)<=remaining:
                    remaining-=len(data)
                    result.append({**item,'data':data,'label':item.get('label','')+
                        ' (aynı sayfanın üst bölümü, yakın görünüm; basılı şık harflerini koru)'})
            except Exception:
                continue  # The full original page remains in the request.
    return result
