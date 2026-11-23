export type SupportPendingIntentKind = "CREATE" | "REPLY";

function validId(value:number):boolean{
 return Number.isSafeInteger(value)&&value>0;
}

export function supportCreateIntentStorageKey(userId:number):string{
 if(!validId(userId))throw new Error("Geçersiz hesap kimliği.");
 return "dai.support.create.pending.v2."+userId;
}

export function supportReplyIntentStorageKey(userId:number,ticketId:number):string{
 if(!validId(userId)||!validId(ticketId))throw new Error("Geçersiz hesap veya destek talebi kimliği.");
 return "dai.support.reply.pending.v2."+userId+"."+ticketId;
}

export function isSupportPendingIntentForUser(
 value:unknown,userId:number,kind:SupportPendingIntentKind,ticketId?:number
):value is {version:2;user_id:number;kind:SupportPendingIntentKind;ticket_id?:number;key:string;subject?:string;message:string;case_id?:number|null}{
 if(!validId(userId)||!value||typeof value!=="object")return false;
 const item=value as Record<string,unknown>;
 if(item.version!==2||item.user_id!==userId||item.kind!==kind||
    typeof item.key!=="string"||!/^support_[a-z0-9]{1,24}_[a-z0-9]{8,24}$/.test(item.key)||
    typeof item.message!=="string"||item.message.length>4000)return false;
 if(kind==="CREATE"){
  return typeof item.subject==="string"&&item.subject.trim().length>0&&item.subject.length<=160&&
   (item.case_id===null||(Number.isSafeInteger(item.case_id)&&Number(item.case_id)>0));
 }
 return validId(ticketId||0)&&item.ticket_id===ticketId;
}
