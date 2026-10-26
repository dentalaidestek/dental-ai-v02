/* Private in-page transcript. Never writes browser storage or sends a request itself. */
((scope)=>{
  const bytes=text=>new TextEncoder().encode(text).length;
  function splitTranscript(text){
    const chunks=[];let offset=0;
    while(offset<text.length){
      let end=Math.min(offset+12000,text.length);
      if(end<text.length&&/[\uD800-\uDBFF]/.test(text[end-1]))end--;
      while(bytes(text.slice(offset,end))>36000)end--;
      if(end<text.length){const candidate=text.slice(offset,end),boundary=Math.max(candidate.lastIndexOf('\n'),candidate.lastIndexOf('. '),candidate.lastIndexOf(' '));if(boundary>candidate.length/2)end=offset+boundary+1;}
      chunks.push(text.slice(offset,end));offset=end;
    }
    return chunks;
  }
  class FinishDraft{
    constructor(){this.text='';this.cursor=0;this.version=0;this.running=false;}
    set(text){
      if(typeof text!=='string'||text.length>72000||bytes(text)>216000)throw Error('Görüşme metni sınırına ulaşıldı (72.000 karakter / 216 KB). Metin korunuyor; kısaltıp yeniden deneyin.');
      if(text!==this.text){this.text=text;this.cursor=0;this.version++;}
    }
    clear(){this.text='';this.cursor=0;this.version++;}
    async process(extract){
      if(this.running)throw Error('Görüşme zaten işleniyor.');
      this.running=true;const version=this.version,chunks=splitTranscript(this.text);
      try{while(this.cursor<chunks.length){await extract(chunks[this.cursor],this.cursor,chunks.length);if(version!==this.version)throw Error('Görüşme değişti; yeniden değerlendirin.');this.cursor++;}}
      finally{this.running=false;}
    }
  }
  const api={FinishDraft,splitTranscript};scope.VoiceFinishDraft=api;
  if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
