(function(root,factory){
  var getOptions=factory();
  if(typeof module==="object"&&module.exports)module.exports=getOptions;
  if(root)root.toothChartSurfaceOptions=getOptions;
})(typeof window!=="undefined"?window:null,function(){
  "use strict";
  return function toothChartSurfaceOptions(toothNumber){
    if(typeof toothNumber!=="string"||!/^(?:[1-4][1-8]|[5-8][1-5])$/.test(toothNumber))return [];
    var first=Number(toothNumber[1])<=3?"INCISAL":"OCCLUSAL";
    return [first,"MESIAL","DISTAL","BUCCAL","LINGUAL"];
  };
});
