const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{test}=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../src/NativeSocialAdmin.tsx'),'utf8');

test('native moderation grant stays in memory and closes on blur, background and expiry',()=>{
 assert.match(source,/grantRef\s*=\s*useRef<string\s*\|\s*null>/);
 assert.match(source,/useFocusEffect\(/);
 assert.match(source,/AppState\.addEventListener\("change"/);
 assert.match(source,/expiresAt\s*-\s*Date\.now\(\)/);
 assert.match(source,/revokeSocialAdminStepUp\(token, current\)/);
 assert.doesNotMatch(source,/SecureStore|AsyncStorage|setItemAsync|localStorage/);
});

test('native moderation is ADMIN-gated and decisions remain version-checked',()=>{
 assert.match(source,/String\(user\.role\s*\|\|\s*""\)\.toUpperCase\(\)\s*===\s*"ADMIN"/);
 assert.match(source,/getSocialAdminQueue\(token, grant, kind, status, before\)/);
 assert.match(source,/getSocialAdminReports\(token, grant/);
 assert.match(source,/getSocialAdminDetail\(token, grant, targetKind, id\)/);
 assert.match(source,/decideSocialAdminModeration\(/);
 assert.match(source,/item\?\.version/);
 assert.match(source,/decisionReason\.trim\(\)\.length\s*<\s*3/);
 assert.match(source,/socialImageSource\(row\.url, token\)/);
});
