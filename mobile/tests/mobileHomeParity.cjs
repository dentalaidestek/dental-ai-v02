const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const src=f=>fs.readFileSync(require.resolve('../src/'+f),'utf8');
const app=()=>fs.readFileSync(require.resolve('../App.tsx'),'utf8');
test('home shows the voice exam card even when an older backend omits voice_exam_enabled',()=>{
 const source=app();
 // New backend sends voice_exam_enabled:false only when the user disables it.
 // Older live builds omit the field entirely; ===true hid the card there.
 assert.ok(source.includes('d?.voice_exam_enabled!==false'),'voice card must be visible unless the backend explicitly disables it');
 assert.ok(!source.includes('d?.voice_exam_enabled===true'),'the strict ===true gate that hid the card on old backends must be gone');
});
test('home header carries the web Uzman Profilim entry and opens expert management',()=>{
 const source=app();
 // Web base.html renders the expert-header-entry for eligible experts; native
 // proxies eligibility with the DOCTOR/ADMIN role check.
 assert.ok(source.includes('accessibilityLabel="Uzman Profilim"'),'header entry must expose the web label');
 assert.ok(source.includes('onPress={()=>nav.navigate("ExpertManagement")}'),'entry must reach the expert management screen');
 assert.ok(source.includes('["DOCTOR","ADMIN"].includes(String(user.role||"").toUpperCase())&&<Pressable accessibilityRole="button" accessibilityLabel="Uzman Profilim"'),'entry is gated to expert roles');
});
test('home menu button mirrors the web workspace menu with native screens',()=>{
 const source=app();
 // Web base.html: menu-toggle button (aria "Tüm menüyü aç") opens #mainMenu.
 assert.ok(source.includes('accessibilityLabel="Tüm menüyü aç"'),'menu toggle must expose the web aria-label');
 assert.ok(source.includes('["Hesabım (Profil)",()=>nav.navigate("Profile")]'),'menu maps Hesabım to the profile tab like web /account');
 assert.ok(source.includes('["Programım",()=>nav.navigate("Program")]'),'menu maps Programım like web /program');
 assert.ok(source.includes('["Dental Akış",()=>nav.navigate("DentalFlow")]'),'menu maps Dental Akış like web /dental-akis');
 assert.ok(source.includes('["Diş Şemaları",()=>nav.navigate("Patients",{screen:"ToothChartBrowser"})]'),'menu maps Diş Şemaları like web /tooth-charts');
 assert.ok(source.includes('["Analiz Geçmişi",()=>nav.navigate("AnalysisHistory")]'),'menu maps analizler to the history screen');
 assert.ok(source.includes('["Destek Taleplerim",()=>nav.navigate("SupportRequests")]'),'menu maps support like web /support-request');
 assert.ok(source.includes('["Dental Akış Yönetimi",()=>nav.navigate("SocialAdmin")]'),'ADMIN menu extra matches the web admin entry');
 assert.ok(source.includes('menuOpen&&<View style={{position:"absolute"'),'the menu sheet renders above the scroll view');
});
test('native account exposes every web profile update action',()=>{
 const auth=src('authApi.ts'),account=src('NativeAccount.tsx'),professional=src('professionalApi.ts');
 // Live probe 2026-11-21: GET /api/mobile/v1/account -> 404 on dentalai.tr while
 // /api/mobile/v1/dashboard -> 401: the deployed mobile router predates the
 // account adapter, so the UI works in code but needs a backend deploy to fire.
 for(const action of ['display-name','username','password','email','email/confirm','profile-photo','delete']){
  assert.ok(auth.includes("'"+action+"'"),'authApi must delegate the web '+action+' action');
 }
 assert.ok(account.includes("perform('display-name',{display_name:name})"),'display name form is wired');
 assert.ok(account.includes("perform('username',{username})"),'username form is wired');
 assert.ok(account.includes('current_password:currentPassword,new_password:password,new_password_confirm:confirmation'),'password form sends the web contract fields');
 assert.ok(account.includes("perform('email',{new_email:email,password:currentPassword})"),'email change with password confirmation is wired');
 assert.ok(account.includes('email/confirm'),'email verification code step is wired');
 assert.ok(account.includes("perform('profile-photo',"),'profile photo upload is wired');
 assert.ok(professional.includes('changeProfessionalTitle'),'professional title update is delegated');
 assert.ok(account.includes('Sonraki değişiklik'),'username change throttling notice is shown like web next_username_change_at');
});
