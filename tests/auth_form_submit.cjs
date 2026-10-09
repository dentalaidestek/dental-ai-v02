const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const html=fs.readFileSync('app/templates/login.html','utf8');const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
for(const action of ['/login','/verify-email'])test(action+' blocks duplicate submission and recovers after navigation',()=>{
 const handlers={},windowHandlers={};let valid=true,prevented=0;
 const button={disabled:false,classList:{add(){},remove(){}},setAttribute(){},removeAttribute(){}};
 const form={querySelector:()=>button,checkValidity:()=>valid,addEventListener:(name,f)=>handlers[name]=f};
 vm.runInNewContext(script,{document:{querySelector:selector=>selector.includes(action)?form:null},window:{addEventListener:(name,f)=>windowHandlers[name]=f}});
 valid=false;handlers.submit({preventDefault(){prevented++}});assert.equal(button.disabled,false);
 valid=true;handlers.submit({preventDefault(){prevented++}});assert.equal(button.disabled,true);
 handlers.submit({preventDefault(){prevented++}});assert.equal(prevented,1);
 windowHandlers.pageshow();assert.equal(button.disabled,false);
});
