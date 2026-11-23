export function clinicalDate(year:number,month:number,day:number){return `${String(year).padStart(4,'0')}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;}
export function parseClinicalDate(value:string){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
 const [year,month,day]=value.split('-').map(Number),date=new Date(year,month-1,day);
 return year>=1900&&year<=2200&&date.getFullYear()===year&&date.getMonth()===month-1&&date.getDate()===day?date:null;
}
export function calendarDays(year:number,month:number):Array<number|null>{
 const first=(new Date(year,month,1).getDay()+6)%7,count=new Date(year,month+1,0).getDate();
 return [...Array(first).fill(null),...Array.from({length:count},(_,i)=>i+1)];
}
