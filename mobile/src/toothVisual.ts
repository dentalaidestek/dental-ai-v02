export function toothVisualModel(number:string){
 if(!/^(?:[1-4][1-8]|[5-8][1-5])$/.test(number))throw Error('Geçersiz FDI diş numarası.');
 const position=Number(number[1]),quadrant=Number(number[0]),primary=quadrant>=5;
 return {column:primary?(position>=4?0:position===3?2:3):(position>=6?0:position>=4?1:position===3?2:3),lower:[3,4,7,8].includes(quadrant)};
}
