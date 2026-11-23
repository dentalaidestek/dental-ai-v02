import type {ToothSurfaceCode} from './api';
import {toothSurfaceOptionsForTooth} from './toothSurfaceOptions';

/** Map the web preview's fixed occlusal pin to the anatomically correct FDI surface. */
export function toothChartSurfaceForTooth(toothNumber:string,pinSurface:ToothSurfaceCode):ToothSurfaceCode|null{
 const options=toothSurfaceOptionsForTooth(toothNumber);
 if(options.some(([code])=>code===pinSurface))return pinSurface;
 if(pinSurface==='OCCLUSAL'&&options.some(([code])=>code==='INCISAL'))return 'INCISAL';
 return null;
}

/** Web setSurface(v) always selects v; tapping the active surface does not clear it. */
export function toothChartSurfaceSelection(surface:ToothSurfaceCode):ToothSurfaceCode[]{
 return [surface];
}
