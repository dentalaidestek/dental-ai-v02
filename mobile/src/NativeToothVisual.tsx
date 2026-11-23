import React from 'react';
import {View} from 'react-native';
import Svg,{ClipPath,Defs,FeColorMatrix,Filter,G,Image as SvgImage,LinearGradient,Path,Rect,Stop,SvgXml} from 'react-native-svg';
import {ToothStatusCode,ToothSurfaceCode} from './api';
import {
  EXTRACTED_TOOTH_FILTER_ID,
  EXTRACTED_TOOTH_FILTER_MATRIX,
  toothVisualFilter,
  toothVisualModel
} from './toothVisual';

// The same four-column enamel atlas, implant SVG and status paths as tooth_chart.html.
// The atlas is bundled with the app; this visual never requests a remote image.
const atlas=require('../assets/enamel-atlas-v2.webp');
const implant='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 220"><defs><linearGradient id="m" x1="0" x2="1"><stop stop-color="#6e7680"/><stop offset=".35" stop-color="#d9dde1"/><stop offset=".65" stop-color="#9aa1a9"/><stop offset="1" stop-color="#59616a"/></linearGradient></defs><path fill="#f2eee5" stroke="#cdbf9f" stroke-width="2" d="M27 20c10-14 56-14 66 0 7 10 4 34-2 49H29c-6-15-9-39-2-49Z"/><path fill="url(#m)" stroke="#59616a" stroke-width="2" d="M42 66h36v18H42zM47 84h26l-4 95-9 20-9-20Z"/><path fill="none" stroke="#626a73" stroke-width="2" d="M47 96h25M47 108h24M48 120h23M48 132h22M49 144h21M50 156h19M51 168h17"/></svg>';
const mark='M17 27c4-7 10-5 13-2 5-5 12-4 14 3l-4 14c-6 5-10-1-14 2-5 3-8-4-9-17Z';
const surfaceTransform:Partial<Record<ToothSurfaceCode,string>>={
  MESIAL:'translate(-10 6) translate(30 50) scale(.85) translate(-30 -50)',
  DISTAL:'translate(10 6) translate(30 50) scale(.85) translate(-30 -50)',
  LINGUAL:'translate(0 10)',
  BUCCAL:'translate(0 5)',
  OCCLUSAL:'translate(0 -9)',
  INCISAL:'translate(0 -9)'
};

export default function NativeToothVisual({number,status='HEALTHY',height=37,surface}:{
  number:string;
  status?:ToothStatusCode;
  height?:number;
  surface?:ToothSurfaceCode
}){
  const model=toothVisualModel(number);
  const filter=toothVisualFilter(status);
  return <View style={{height,alignSelf:'stretch',overflow:'hidden',transform:[{rotate:model.lower?'180deg':'0deg'}]}}>
    {status==='IMPLANT'
      ? <SvgXml xml={implant} width="100%" height="100%"/>
      : <Svg width="100%" height="100%" viewBox="0 0 60 100" preserveAspectRatio="none">
          <Defs>
            <ClipPath id="tooth-atlas-clip">
              <Rect x="5.4" y="5" width="49.2" height="90"/>
            </ClipPath>
            {filter&&<Filter id={EXTRACTED_TOOTH_FILTER_ID}>
              <FeColorMatrix type="matrix" values={EXTRACTED_TOOTH_FILTER_MATRIX}/>
            </Filter>}
            <LinearGradient id="caries" x2="0" y2="1">
              <Stop stopColor="#ff8d7c"/><Stop offset=".5" stopColor="#e92c25"/><Stop offset="1" stopColor="#ab131b"/>
            </LinearGradient>
            <LinearGradient id="filling" x2="0" y2="1">
              <Stop stopColor="#77dcff"/><Stop offset=".5" stopColor="#178cef"/><Stop offset="1" stopColor="#075ebc"/>
            </LinearGradient>
            <LinearGradient id="crown">
              <Stop stopColor="#eee0ff"/><Stop offset=".4" stopColor="#b26aea"/><Stop offset="1" stopColor="#8738b9"/>
            </LinearGradient>
          </Defs>
          <G filter={filter}>
            <SvgImage
              href={atlas}
              x={-model.column*60}
              y={0}
              width={240}
              height={100}
              preserveAspectRatio="none"
              clipPath="url(#tooth-atlas-clip)"
            />
            {['CARIES','FILLING','OTHER','ROOT_CANAL'].includes(status)&&<Path
              d={mark}
              transform={surface?surfaceTransform[surface]:undefined}
              fill={status==='CARIES'?'url(#caries)':status==='FILLING'?'url(#filling)':status==='OTHER'?'#ffc42c':'#ff8a1d'}
              opacity={status==='ROOT_CANAL'?.28:1}
              stroke="#fff"
              strokeWidth={.6}
            />}
            {status==='CROWN'&&<Path
              d="M12 9c6-7 12-2 18-2s12-5 18 2c4 5 4 12 2 20-10 7-30 7-40 0-2-8-2-15 2-20Z"
              fill="url(#crown)"
              opacity={.95}
              stroke="#f2dfff"
              strokeWidth={.8}
            />}
            {status==='ROOT_CANAL'&&<Path
              d="M24 34c1 13 0 29-5 44M36 34c-1 13 0 29 5 44M30 34v48"
              fill="none"
              stroke="#ff920e"
              strokeWidth={4}
              strokeLinecap="round"
            />}
            {status==='EXTRACTED'&&<Path
              d="M20 35l20 24M40 35L20 59"
              fill="none"
              stroke="#343a40"
              strokeWidth={4}
              strokeLinecap="round"
            />}
          </G>
        </Svg>}
  </View>;
}
