export type ChatFile={uri:string;name:string;type:string;size?:number;owned?:boolean};
export type ChatFileKind="IMAGE"|"FILE"|"VOICE";
const formats:Record<string,{kind:ChatFileKind;mime:string;aliases:string[]}>= {
 jpg:{kind:"IMAGE",mime:"image/jpeg",aliases:["image/jpeg"]},jpeg:{kind:"IMAGE",mime:"image/jpeg",aliases:["image/jpeg"]},
 png:{kind:"IMAGE",mime:"image/png",aliases:["image/png"]},webp:{kind:"IMAGE",mime:"image/webp",aliases:["image/webp"]},
 pdf:{kind:"FILE",mime:"application/pdf",aliases:["application/pdf"]},
 mp3:{kind:"VOICE",mime:"audio/mpeg",aliases:["audio/mpeg","audio/mp3"]},
 m4a:{kind:"VOICE",mime:"audio/mp4",aliases:["audio/mp4","audio/m4a","audio/x-m4a"]},
 wav:{kind:"VOICE",mime:"audio/wav",aliases:["audio/wav","audio/x-wav","audio/wave"]},
 ogg:{kind:"VOICE",mime:"audio/ogg",aliases:["audio/ogg","application/ogg"]},
};
export function validateChatFile(file:ChatFile):ChatFile&{kind:ChatFileKind}{
 const extension=file?.name?.split(".").pop()?.toLowerCase()||"",format=formats[extension];
 if(!file||!/^(?:file|content):\/\//.test(file.uri)||!format||
    file.type!=="application/octet-stream"&&!format.aliases.includes(file.type)||
    file.size!==undefined&&(!Number.isFinite(file.size)||file.size<=0||file.size>(format.kind==="IMAGE"?15:25)*1024*1024))
  throw Error("JPG/PNG/WEBP (15 MB), PDF veya M4A/MP3/WAV/OGG (25 MB) seçin.");
 return {...file,type:format.mime,kind:format.kind};
}
export function fitChatImage(naturalWidth:number,naturalHeight:number,maxWidth:number,maxHeight:number){
 if([naturalWidth,naturalHeight,maxWidth,maxHeight].some(n=>!Number.isFinite(n)||n<=0))throw Error("Görüntü boyutu geçersiz.");
 const scale=Math.min(maxWidth/naturalWidth,maxHeight/naturalHeight),exportScale=Math.min(1,1600/Math.max(naturalWidth,naturalHeight));
 return {width:naturalWidth*scale,height:naturalHeight*scale,exportWidth:Math.round(naturalWidth*exportScale),exportHeight:Math.round(naturalHeight*exportScale)};
}
export function clampChatPoint(x:number,y:number,width:number,height:number):[number,number]{
 return [Math.max(0,Math.min(width,x)),Math.max(0,Math.min(height,y))];
}
