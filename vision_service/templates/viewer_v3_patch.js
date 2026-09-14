// Dental AI 3D viewer compatibility patch: normalize FDI labels before the 3D filter.
(function(){
  function normalizeFdiValue(v){
    const s=String(v ?? '').trim();
    if (/^[1-4][1-8]$/.test(s)) return Number(s);
    const m=s.match(/(?:^|\D)([1-4][1-8])(?:\D|$)/);
    if (m) return Number(m[1]);
    const digits=s.replace(/\D/g,'');
    if (digits.length>=2){
      const tail=digits.slice(-2);
      if (/^[1-4][1-8]$/.test(tail)) return Number(tail);
    }
    return v;
  }

  if (typeof renderJaw !== 'function') return;
  const originalRenderJaw = renderJaw;
  renderJaw = async function(){
    if (result && Array.isArray(result.teeth)){
      for (const t of result.teeth){
        if (t) t.fdi = normalizeFdiValue(t.fdi);
      }
      const rawCount = result.teeth.length;
      const validCount = result.teeth.filter(t=>t?.bbox && /^[1-4][1-8]$/.test(String(t.fdi))).length;
      console.log('[3D_FDI_BRIDGE]', {rawCount, validCount, labels: result.teeth.slice(0,12).map(t=>t?.fdi)});
      if (rawCount>0 && validCount===0){
        throw new Error('Dişler bulundu ancak FDI etiketleri 3D katmanına çevrilemedi');
      }
    }
    return originalRenderJaw();
  };
})();
