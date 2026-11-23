export const EXTRACTED_TOOTH_FILTER_ID = "tooth-extracted-grayscale";
export const EXTRACTED_TOOTH_FILTER_URL = `url(#${EXTRACTED_TOOTH_FILTER_ID})`;

// CSS reference: grayscale(1) brightness(.7). Each RGB row uses the same
// Rec. 709 luminance coefficients scaled to 70%; alpha is preserved.
export const EXTRACTED_TOOTH_FILTER_MATRIX =
  "0.14882 0.50064 0.05054 0 0 " +
  "0.14882 0.50064 0.05054 0 0 " +
  "0.14882 0.50064 0.05054 0 0 " +
  "0 0 0 1 0";

export function toothVisualFilter(status: string): string | undefined {
  return status === "EXTRACTED" ? EXTRACTED_TOOTH_FILTER_URL : undefined;
}

export function toothVisualModel(number:string){
 if(!/^(?:[1-4][1-8]|[5-8][1-5])$/.test(number))throw Error('Geçersiz FDI diş numarası.');
 const position=Number(number[1]),quadrant=Number(number[0]),primary=quadrant>=5;
 return {column:primary?(position>=4?0:position===3?2:3):(position>=6?0:position>=4?1:position===3?2:3),lower:[3,4,7,8].includes(quadrant)};
}
