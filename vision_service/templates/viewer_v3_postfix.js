// Final compatibility layer: normalize tooth labels after all viewer enhancements are loaded.
(function(){
  function normalizeFdi(v){
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

  const enhancedRenderJaw = renderJaw;
  renderJaw = async function(){
    if (result && Array.isArray(result.teeth)){
      for (const t of result.teeth){
        if (t) t.fdi = normalizeFdi(t.fdi);
      }
    }
    return enhancedRenderJaw();
  };
})();
