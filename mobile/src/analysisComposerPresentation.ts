import {ANALYSIS_MAX_BATCH_BYTES,ANALYSIS_MAX_FILE_BYTES,ANALYSIS_MAX_IMAGES,MIB} from './uploadLimits';

export type AnalysisComposerStepKey='tooth'|'clinical'|'images';
export type AnalysisComposerStep={
 number:1|2|3;
 key:AnalysisComposerStepKey;
 title:string;
 label:string;
 placeholder:string;
 helper?:string;
 accessibilityLabel:string;
};

const nonNegativeCount=(value:number)=>Number.isSafeInteger(value)&&value>0?value:0;
const mibLabel=(bytes:number)=>`${Math.round(bytes/MIB)} MiB`;

export function analysisComposerImageHelp(hasSavedMedia:boolean):string{
 const perFile=mibLabel(ANALYSIS_MAX_FILE_BYTES);
 const batch=mibLabel(ANALYSIS_MAX_BATCH_BYTES);
 return hasSavedMedia
  ?`Kayıtlı görüntüler dahil toplam en fazla ${ANALYSIS_MAX_IMAGES} görüntü kullanılabilir. Yeni dosya başına ${perFile}, yeni dosyaların toplamı ${batch} sınırı vardır.`
  :`En fazla ${ANALYSIS_MAX_IMAGES} görüntü yükleyebilirsiniz. Dosya başına ${perFile}, toplam yeni dosya boyutu ${batch} ile sınırlıdır.`;
}

export function analysisComposerImageCountLabel(savedMediaCount:number,newImageCount:number):string{
 const saved=nonNegativeCount(savedMediaCount),added=nonNegativeCount(newImageCount);
 const parts=[`${saved+added} / ${ANALYSIS_MAX_IMAGES} görüntü seçildi`];
 if(saved)parts.push(`${saved} kayıtlı`);
 if(added)parts.push(`${added} yeni`);
 return parts.join(' · ');
}

export function analysisComposerSteps(savedMediaCount:number):AnalysisComposerStep[]{
 const hasSavedMedia=nonNegativeCount(savedMediaCount)>0;
 return[
  {number:1,key:'tooth',title:'Diş',label:'Diş numarası',placeholder:'Örn: 36 veya 36,46',accessibilityLabel:'Analiz FDI diş numaraları'},
  {number:2,key:'clinical',title:'Kısa klinik bilgi',label:'Hekim notu',placeholder:'Örn: Soğukta ağrı, çiğnemede hassasiyet, eski dolgu...',helper:'Görüntü olmadan da klinik bilgiyle analiz başlatabilirsiniz.',accessibilityLabel:'Analiz klinik bilgileri'},
  {number:3,key:'images',title:hasSavedMedia?'Ek görünt':'Fotoğraf / Röntgen',label:'Görüntü yükle',placeholder:'',helper:analysisComposerImageHelp(hasSavedMedia),accessibilityLabel:'Analiz görüntüleri'},
 ];
}

export const ANALYSIS_COMPOSER_SAFETY_NOTE='AI mevcut klinik bilgi ve görüntüyü birlikte değerlendirir; kritik bilgi eksikse yalnızca gerekli soruları gösterir.';
