import {useCallback,useEffect,useRef,useState} from 'react';
export type Page<T>={items:T[];next_before:number|null};
export function mergeRecords<T extends {id:number}>(existing:T[],incoming:T[],ascending=false):T[]{
 const byId=new Map(existing.map(item=>[item.id,item]));incoming.forEach(item=>byId.set(item.id,item));const incomingIds=new Set(incoming.map(item=>item.id));
 return ascending?Array.from(byId.values()).sort((a,b)=>a.id-b.id):[...incoming,...existing.filter(item=>!incomingIds.has(item.id))];
}
export function validInitialCursor<T extends {id:number}>(page:Page<T>,cursorMode:"id"|"offset"="id",offsetBase=0):number|null{
 const cursor=page.next_before;
 if(cursor===null||!Number.isSafeInteger(cursor)||cursor<0||!Array.isArray(page.items)||page.items.length===0)return null;
 const ids=page.items.map(item=>item?.id);
 if(ids.some(id=>!Number.isSafeInteger(id)||id<0))return null;
 return cursorMode==="offset"?(cursor===offsetBase+page.items.length?cursor:null):(ids.includes(cursor)?cursor:null);
}
export function usePagedRecords<T extends {id:number}>(scope:string,fetchPage:(before?:number)=>Promise<Page<T>>,ascending=false,replaceOnRefresh=false,cursorMode:"id"|"offset"="id"){
 const [items,setItems]=useState<T[]>([]),[next,setNext]=useState<number|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const fetchRef=useRef(fetchPage);fetchRef.current=fetchPage;
 const generation=useRef(0),more=useRef(false),pending=useRef<number|null>(null),knownIds=useRef(new Set<number>()),seenCursors=useRef(new Set<number>());
 const refresh=useCallback(async()=>{
  const request=++generation.current;seenCursors.current.clear();setBusy(true);setError('');
  try{const page=await fetchRef.current();if(request!==generation.current)return;
   if(!Array.isArray(page?.items)||page.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0)||new Set(page.items.map(item=>item.id)).size!==page.items.length||!(page.next_before===null||(Number.isSafeInteger(page.next_before)&&page.next_before>=0)))throw Error("Geçersiz sayfa yanıtı.");
   // Do not silently truncate the first page when the server advertises an unusable cursor.
   // Preserve the last verified clinical rows so a corrected response can be retried.
   const initialCursor=validInitialCursor(page,cursorMode);
   if(page.next_before!==null&&initialCursor===null)throw Error("Geçersiz sayfalama imleci. Tekrar deneyin.");
   if(replaceOnRefresh){knownIds.current=new Set(page.items.map(item=>item.id));more.current=false;setItems(page.items);setNext(initialCursor);return;}
   const overlaps=page.items.some(item=>knownIds.current.has(item.id));
   if(!page.items.length){knownIds.current.clear();more.current=false;setItems([]);setNext(null);return;}
   if(!overlaps)more.current=false;
   page.items.forEach(item=>knownIds.current.add(item.id));
   setItems(old=>mergeRecords(old,page.items,ascending));if(!more.current)setNext(validInitialCursor(page,cursorMode));
  }catch(e){if(request===generation.current)setError(e instanceof Error?e.message:'Yüklenemedi. Tekrar deneyin.');}
  finally{if(request===generation.current)setBusy(false);}
 },[scope,ascending,replaceOnRefresh,cursorMode]);
 const loadMore=async()=>{
  if(next===null||pending.current===generation.current||busy)return;const request=generation.current;pending.current=request;setBusy(true);setError('');
  try{const page=await fetchRef.current(next);if(request!==generation.current)return;
   if(!Array.isArray(page?.items)||page.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0)||new Set(page.items.map(item=>item.id)).size!==page.items.length||!(page.next_before===null||(Number.isSafeInteger(page.next_before)&&page.next_before>=0)))throw Error("Geçersiz sayfa yanıtı.");
   // Distinguish a non-advancing/skipping offset from a malformed ID cursor.
   // Validate before mutating clinical records so the same page can be retried.
   if(cursorMode==="offset"&&page.next_before!==null&&page.items.length>0&&page.next_before!==next+page.items.length)
    throw Error("Geçersiz sayfalama ilerlemesi. Tekrar deneyin.");
   const nextCursor=validInitialCursor(page,cursorMode,cursorMode==="offset"?next:0);
   // A nonterminal page must supply a usable cursor and at least one record.
   // Otherwise preserve the current records/cursor and surface a retryable error.
   if(page.next_before!==null&&nextCursor===null)
    throw Error("Geçersiz sayfalama imleci. Tekrar deneyin.");
   // An offset that does not advance can silently skip or repeat patient records.
   // Reject the entire page and retain the cursor so the user can retry safely.
   if(cursorMode==="offset"&&nextCursor!==null&&nextCursor!==next+page.items.length)
    throw Error("Geçersiz sayfalama ilerlemesi. Tekrar deneyin.");
   // Reject a cursor cycle before committing page data. A retry must remain possible
   // after the server fixes its response, rather than silently ending pagination.
   if(nextCursor!==null&&(nextCursor===next||seenCursors.current.has(nextCursor)))
    throw Error("Geçersiz sayfalama döngüsü. Tekrar deneyin.");
   // A server page that repeats an existing patient without advancing its offset
   // must not silently replace the currently displayed clinical record.
   if(cursorMode==="offset"&&page.items.some(item=>knownIds.current.has(item.id)))
    throw Error("Tekrarlanan hasta sayfası. Tekrar deneyin.");
   page.items.forEach(item=>knownIds.current.add(item.id));
   setItems(old=>{if(ascending)return mergeRecords(old,page.items,true);const existingIds=new Set(old.map(item=>item.id));return [...old,...page.items.filter(item=>!existingIds.has(item.id))];});
   // A broken backend cursor must not trigger an endless request for the same page.
   seenCursors.current.add(next);
   setNext(nextCursor!==null&&!seenCursors.current.has(nextCursor)?nextCursor:null);more.current=true;
  }catch(e){if(request===generation.current)setError(e instanceof Error?e.message:'Yüklenemedi. Tekrar deneyin.');}
  finally{if(pending.current===request)pending.current=null;if(request===generation.current)setBusy(false);}
 };
 useEffect(()=>{generation.current++;pending.current=null;more.current=false;knownIds.current.clear();seenCursors.current.clear();setItems([]);setNext(null);refresh();return()=>{generation.current++;};},[refresh]);
 return {items,setItems,refresh,loadMore,hasMore:next!==null,busy,error};
}

