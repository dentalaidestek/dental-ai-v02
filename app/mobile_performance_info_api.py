"""Native expert performance-info adapter (five-route parity port).

Web handler owns the canonical copy; this adapter only parses the shared
template with the same read/clean pattern. Ported from the mobile-parity
branch (handler + minimal deps). The parity branch nests this adapter under
the canonical mobile router; here it mounts with the same /api/mobile/v1
prefix so the URL contract is identical.
"""
import re
from html.parser import HTMLParser
from fastapi import APIRouter, Depends, HTTPException

from app.mobile_api import _mobile_access_token, _mobile_request, _mobile_user

router = APIRouter(prefix="/api/mobile/v1", tags=["mobile-performance-info"])


class PlainLegal(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'h1','h2','h3','p','li','br'}:self.parts.append('\n\n' if tag!='li' else '\n• ')
    def handle_data(self,data):self.parts.append(data)
    def text(self):return re.sub(r'[ \t]+',' ',''.join(self.parts)).strip()


def _account_user(token:str=Depends(_mobile_access_token),user=Depends(_mobile_user)):
    from app import main as web
    if user.role=='ADMIN' and web.get_current_user(_mobile_request(token,'GET')) is None:
        raise HTTPException(status_code=403,detail='Yönetici oturumu için güvenlik doğrulaması gerekiyor.')
    return user


@router.get('/experts/performance-info')
def performance_info(token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    """Web /expert-support/performance-info metninin mobil karşılığı; uzman kurallarıyla aynı okuma/temizleme deseni.

    Native client (professionalApi.ts ExpertPerformanceInfo) reads title/body/sections;
    content stays for clients released before the parity fix.
    """
    import re
    from app import main as web
    source=web.templates.env.loader.get_source(web.templates.env,'expert_performance_info.html')[0]
    heading=re.search(r'<h1>(.*?)</h1>',source,re.S)
    parts=re.findall(r'<section class="expert-rule-card">(.*?)</section>',source,re.S)
    if not heading or not parts:raise HTTPException(status_code=503,detail='Performans açıklaması alınamıyor.')
    title_parser=PlainLegal();title_parser.feed(heading.group(1))
    plain=PlainLegal();plain.feed('\n'.join(parts))
    sections=[]
    for part in parts:
        section_title=re.search(r'<h2>(.*?)</h2>',part,re.S)
        section_body=re.sub(r'<h2>.*?</h2>','',part,flags=re.S)
        title_text=PlainLegal();body_text=PlainLegal()
        if section_title:title_text.feed(section_title.group(1))
        body_text.feed(section_body)
        sections.append({'title':title_text.text(),'body':body_text.text()})
    return {'ok':True,'title':title_parser.text(),'body':plain.text(),'sections':sections,'content':plain.text()}
