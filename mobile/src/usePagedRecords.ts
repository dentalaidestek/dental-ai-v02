import {useCallback,useEffect,useRef,useState} from 'react';
export type Page<T>={items:T[];next_before:number|null};
export function mergeRecords<T extends {id:number}>(existing:T[],incoming:T[],ascending=false):T[]{
 const byId=new Map(existing.map(item=>[item.id,item]));incoming.forEach(item=>byId.set(item.id,item));const incomingIds=new Set(incoming.map(item=>item.id));
 return ascending?Array.from(byId.values()).sort((a,b)=>a.id-b.id):[...incoming,...existing.filter(item=>!incomingIds.has(item.id))];
}
export function validInitialCursor<T extends {id:number}>(page:Page<T>,cursorMode:"id"|"offset"="id"):number|null{
 const cursor=page.next_before;
 if(cursor===null||!Number.isSafeInteger(cursor)||cursor<0||!Array.isArray(page.items)||page.items.length===0)return null;
 const ids=page.items.map(item=>item?.id);
 if(ids.some(id=>!Number.isSafeInteger(id)||id<0))return null;
 return cursorMode==="offset"?(cursor>0?cursor:null):(ids.includes(cursor)?cursor:null);
}
export function usePagedRecords<T extends {id:number}>(scope:string,fetchPage:(before?:number)=>Promise<Page<T>>,ascending=false,replaceOnRefresh=false,cursorMode:"id"|"offset"="id"){
 const [items,setItems]=useState<T[]>([]),[next,setNext]=useState<number|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const fetchRef=useRef(fetchPage);fetchRef.current=fetchPage;
 const generation=useRef(0),more=useRef(false),pending=useRef<number|null>(null),knownIds=useRef(new Set<number>()),seenCursors=useRef(new Set<number>());
 const refresh=useCallback(async()=>{
  const request=++generation.current;seenCursors.current.clear();setBusy(true);setError('');
  try{const page=await fetchRef.current();if(request!==generation.current)return;
   if(!Array.isArray(page?.items)||page.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0)||new Set(page.items.map(item=>item.id)).size!==page.items.length)throw Error("Geçersiz sayfa yanıtı.");
   if(replaceOnRefresh){knownIds.current=new Set(page.items.map(item=>item.id));more.current=false;setItems(page.items);setNext(validInitialCursor(page,cursorMode));return;}
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
   if(!Array.isArray(page?.items)||page.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0)||new Set(page.items.map(item=>item.id)).size!==page.items.length)throw Error("Geçersiz sayfa yanıtı.");
   const nextCursor=validInitialCursor(page,cursorMode);
   // Preserve a valid page but close pagination when an offset repeats or regresses.
   const stalledOffset=cursorMode==="offset"&&nextCursor!==null&&nextCursor<=next;
   page.items.forEach(item=>knownIds.current.add(item.id));
   setItems(old=>{if(ascending)return mergeRecords(old,page.items,true);const existingIds=new Set(old.map(item=>item.id));return [...old,...page.items.filter(item=>!existingIds.has(item.id))];});
   // A broken backend cursor must not trigger an endless request for the same page.
   seenCursors.current.add(next);
   setNext(!stalledOffset&&nextCursor!==null&&!seenCursors.current.has(nextCursor)?nextCursor:null);more.current=true;
  }catch(e){if(request===generation.current)setError(e instanceof Error?e.message:'Yüklenemedi. Tekrar deneyin.');}
  finally{if(pending.current===request)pending.current=null;if(request===generation.current)setBusy(false);}
 };
 useEffect(()=>{generation.current++;pending.current=null;more.current=false;knownIds.current.clear();seenCursors.current.clear();setItems([]);setNext(null);refresh();return()=>{generation.current++;};},[refresh]);
 return {items,setItems,refresh,loadMore,hasMore:next!==null,busy,error};
}

