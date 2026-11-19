export type VoiceAudioMime="audio/mpeg"|"audio/wav"|"audio/webm"|"audio/ogg"|"audio/mp4";

export const VOICE_AUDIO_MIN_BYTES=100;
export const VOICE_AUDIO_MAX_BYTES=8*1024*1024;
export const VOICE_AUDIO_MAX_SECONDS=90.5;

const MIME_EXTENSIONS:Record<VoiceAudioMime,string>={
 "audio/mpeg":"mp3",
 "audio/wav":"wav",
 "audio/webm":"webm",
 "audio/ogg":"ogg",
 "audio/mp4":"m4a"
};
const EXTENSION_MIMES:Record<string,VoiceAudioMime>={
 mp3:"audio/mpeg",
 wav:"audio/wav",
 webm:"audio/webm",
 ogg:"audio/ogg",
 m4a:"audio/mp4",
 mp4:"audio/mp4"
};
const MIME_ALIASES:Record<string,VoiceAudioMime>={
 "audio/x-wav":"audio/wav",
 "audio/wave":"audio/wav",
 "audio/vnd.wave":"audio/wav",
 "audio/x-m4a":"audio/mp4",
 "audio/m4a":"audio/mp4"
};

export function normalizeVoiceAudioMime(value:unknown):VoiceAudioMime|null{
 if(typeof value!=="string")return null;
 const raw=value.split(";")[0].trim().toLowerCase();
 if(raw in MIME_ALIASES)return MIME_ALIASES[raw];
 if(raw==="audio/mpeg"||raw==="audio/wav"||raw==="audio/webm"||raw==="audio/ogg"||raw==="audio/mp4")return raw;
 return null;
}

export function isSupportedVoiceAudioMime(value:unknown):value is VoiceAudioMime{
 return normalizeVoiceAudioMime(value)!==null;
}

export function isVoiceAudioExtensionForMime(extension:unknown,mime:unknown):boolean{
 if(typeof extension!=="string")return false;
 const normalized=normalizeVoiceAudioMime(mime);
 if(!normalized)return false;
 return EXTENSION_MIMES[extension.replace(/^\\./,"").toLowerCase()]===normalized;
}

export function resolveVoiceAudioAsset(mimeType:unknown,filename:unknown):{mime:VoiceAudioMime;extension:string}{
 const name=typeof filename==="string"?filename.trim():"";
 const match=/\\.([A-Za-z0-9]{1,8})$/.exec(name);
 const extensionMime=match?EXTENSION_MIMES[match[1].toLowerCase()]:undefined;
 const supplied=normalizeVoiceAudioMime(mimeType);
 const raw=typeof mimeType==="string"?mimeType.split(";")[0].trim().toLowerCase():"";
 const generic=!raw||raw==="application/octet-stream"||raw==="binary/octet-stream";
 if(raw&&!supplied&&!generic)throw Error("MP3, WAV, WebM, OGG veya M4A ses dosyası seçin.");
 if(supplied&&extensionMime&&supplied!==extensionMime)throw Error("Ses dosyasının MIME türü ile uzantısı eşleşmiyor.");
 const mime=supplied||extensionMime;
 if(!mime)throw Error("Ses dosyasının biçimi doğrulanamadı.");
 return {mime,extension:MIME_EXTENSIONS[mime]};
}

export function validateVoiceAudioBytes(size:unknown):number{
 if(typeof size!=="number"||!Number.isFinite(size)||size<VOICE_AUDIO_MIN_BYTES||size>VOICE_AUDIO_MAX_BYTES)
  throw Error("Ses dosyası 100 bayttan büyük ve en fazla 8 MB olmalıdır.");
 return size;
}

export function validateVoiceAudioDuration(seconds:unknown):number{
 if(typeof seconds!=="number"||!Number.isFinite(seconds)||seconds<=0||seconds>VOICE_AUDIO_MAX_SECONDS)
  throw Error("Ses dosyası en fazla 90 saniye olmalı. Daha kısa bir bölüm seçin.");
 return seconds;
}
