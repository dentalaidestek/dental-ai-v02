(function(root,factory){
  var getOptions=factory();
  if(typeof module==="object"&&module.exports)module.exports=getOptions;
  if(root){
    root.toothChartSurfaceOptions=getOptions;
    root.toothChartIsLowerJawTooth=getOptions.isLowerJawTooth;
  }
})(typeof window!=="undefined"?window:null,function(){
  "use strict";
  var FDI=/^(?:[1-4][1-8]|[5-8][1-5])$/;
  function isLowerJawTooth(toothNumber){
    if(typeof toothNumber!=="string"||!FDI.test(toothNumber))return false;
    var quadrant=Number(toothNumber[0]);
    return quadrant===3||quadrant===4||quadrant===7||quadrant===8;
  }
  function toothChartSurfaceOptions(toothNumber){
    if(typeof toothNumber!=="string"||!FDI.test(toothNumber))return [];
    var first=Number(toothNumber[1])<=3?"INCISAL":"OCCLUSAL";
    return [first,"MESIAL","DISTAL","BUCCAL","LINGUAL"];
  }
  toothChartSurfaceOptions.isLowerJawTooth=isLowerJawTooth;
  return toothChartSurfaceOptions;
});
