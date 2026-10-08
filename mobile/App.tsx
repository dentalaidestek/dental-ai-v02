import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { getDashboard, getPatient, getPatients, login, Patient, User } from "./src/api";

const navy = "#071B35";
const bg = "#F5F7FA";

function LoginScreen({ onLogin }: { onLogin: (token: string, user: User) => void }) {
  const [loginValue, setLoginValue] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true); setError("");
    try {
      const result = await login(loginValue, password);
      const me = await (await fetch("https://dentalai.tr/api/mobile/v1/me", {
        headers: { Authorization: "Bearer " + result.access_token },
      })).json();
      onLogin(result.access_token, me.user);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Giriş başarısız.");
    } finally { setBusy(false); }
  }

  return <SafeAreaView style={styles.login}>
    <View style={styles.logo}><Text style={styles.logoText}>🦷</Text></View>
    <Text style={styles.title}>DENTAL AI</Text>
    <Text style={styles.subtitle}>Diş hekimliği için akıllı çalışma alanı</Text>
    <TextInput style={styles.input} placeholder="Kullanıcı adı veya e-posta" autoCapitalize="none" value={loginValue} onChangeText={setLoginValue}/>
    <TextInput style={styles.input} placeholder="Şifre" secureTextEntry value={password} onChangeText={setPassword}/>
    {error ? <Text style={styles.error}>{error}</Text> : null}
    <Pressable style={styles.primary} onPress={submit} disabled={busy}>
      {busy ? <ActivityIndicator color="#fff"/> : <Text style={styles.primaryText}>Giriş Yap</Text>}
    </Pressable>
  </SafeAreaView>;
}

function Home({ token, user }: { token: string; user: User }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => { getDashboard(token).then(setData).catch(() => {}); }, [token]);
  return <SafeAreaView style={styles.screen}>
    <Text style={styles.greeting}>Merhaba, {user.display_name}</Text>
    <Text style={styles.sectionTitle}>Bugün</Text>
    <View style={styles.stats}>
      <Stat label="Hastalar" value={data?.stats?.patient_count ?? "—"}/>
      <Stat label="Analizler" value={data?.stats?.analysis_count ?? "—"}/>
      <Stat label="Program" value={data?.stats?.upcoming_event_count ?? "—"}/>
    </View>
    <Text style={styles.sectionTitle}>Hızlı İşlemler</Text>
    <View style={styles.card}><Text style={styles.cardTitle}>🦷 Dental AI Analizi</Text><Text style={styles.cardSub}>Yeni görüntü analizi başlat</Text></View>
    <View style={styles.card}><Text style={styles.cardTitle}>👤 Yeni Hasta</Text><Text style={styles.cardSub}>Hasta kaydını yönet</Text></View>
    <View style={styles.card}><Text style={styles.cardTitle}>📅 Programım</Text><Text style={styles.cardSub}>Yaklaşan randevu ve görevler</Text></View>
  </SafeAreaView>;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return <View style={styles.stat}><Text style={styles.statValue}>{value}</Text><Text style={styles.statLabel}>{label}</Text></View>;
}

function Patients({ token, navigation }: any) {
  const [items, setItems] = useState<Patient[]>([]);
  const [q, setQ] = useState("");
  async function load(value = q) { try { setItems((await getPatients(token, value)).items); } catch {} }
  useEffect(() => { load(""); }, []);
  return <SafeAreaView style={styles.screen}>
    <Text style={styles.pageTitle}>Hastalar</Text>
    <TextInput style={styles.search} placeholder="Hasta ara..." value={q} onChangeText={setQ} onSubmitEditing={() => load()}/>
    {items.map(p => <Pressable key={p.id} style={styles.patient} onPress={() => navigation.navigate("PatientDetail", { id: p.id })}>
      <View style={styles.avatar}><Text style={styles.avatarText}>{(p.first_name?.[0] || "?") + (p.last_name?.[0] || "")}</Text></View>
      <View style={{ flex: 1 }}><Text style={styles.patientName}>{p.first_name} {p.last_name}</Text><Text style={styles.cardSub}>{p.phone || p.anonymous_id || "Hasta kaydı"}</Text></View>
      <Text style={styles.chevron}>›</Text>
    </Pressable>)}
  </SafeAreaView>;
}

function PatientDetail({ token, route }: any) {
  const [data, setData] = useState<any>(null);
  useEffect(() => { getPatient(token, route.params.id).then(setData).catch(() => {}); }, [token, route.params.id]);
  if (!data) return <View style={styles.center}><ActivityIndicator/></View>;
  const p = data.patient;
  return <SafeAreaView style={styles.screen}>
    <Text style={styles.pageTitle}>{p.first_name} {p.last_name}</Text>
    <Text style={styles.cardSub}>{p.phone || "Telefon yok"} · {p.age ? p.age + " yaş" : "Yaş bilgisi yok"}</Text>
    <View style={styles.card}><Text style={styles.cardTitle}>Diş Şeması</Text><Text style={styles.cardSub}>{data.teeth.length} diş kaydı · {data.surfaces.length} yüzey kaydı</Text></View>
    <View style={styles.card}><Text style={styles.cardTitle}>Tedaviler</Text><Text style={styles.cardSub}>{data.treatments.length} kayıt</Text></View>
    <View style={styles.card}><Text style={styles.cardTitle}>Medya</Text><Text style={styles.cardSub}>{data.media.length} dosya</Text></View>
  </SafeAreaView>;
}

function Profile({ user, onLogout }: { user: User; onLogout: () => void }) {
  return <SafeAreaView style={styles.screen}>
    <Text style={styles.pageTitle}>Profilim</Text>
    <View style={styles.profile}><View style={styles.bigAvatar}><Text style={styles.bigAvatarText}>{user.display_name?.[0] || "D"}</Text></View><Text style={styles.profileName}>{user.display_name}</Text><Text style={styles.cardSub}>{user.professional_title || "Diş hekimliği kullanıcısı"}</Text></View>
    <View style={styles.card}><Text style={styles.cardTitle}>Hesap</Text><Text style={styles.cardSub}>{user.email}</Text></View>
    <Pressable style={styles.logout} onPress={onLogout}><Text style={styles.logoutText}>Çıkış Yap</Text></Pressable>
  </SafeAreaView>;
}

const Tabs = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

function PatientStack({ token }: { token: string }) {
  return <Stack.Navigator screenOptions={{ headerTintColor: navy, headerTitleStyle: { fontWeight: "700" } }}>
    <Stack.Screen name="PatientsList" options={{ title: "Hastalar" }}>{props => <Patients {...props} token={token}/>}</Stack.Screen>
    <Stack.Screen name="PatientDetail" options={{ title: "Hasta" }}>{props => <PatientDetail {...props} token={token}/>}</Stack.Screen>
  </Stack.Navigator>;
}

function MainApp({ token, user, onLogout }: { token: string; user: User; onLogout: () => void }) {
  return <NavigationContainer>
    <Tabs.Navigator screenOptions={{ tabBarActiveTintColor: navy, headerShown: false }}>
      <Tabs.Screen name="Home" options={{ title: "Anasayfa", tabBarLabel: "Anasayfa" }}>{() => <Home token={token} user={user}/>}</Tabs.Screen>
      <Tabs.Screen name="Patients" options={{ title: "Hastalar", tabBarLabel: "Hastalar" }}>{() => <PatientStack token={token}/>}</Tabs.Screen>
      <Tabs.Screen name="AI" options={{ title: "Dental AI", tabBarLabel: "AI" }}>{() => <SafeAreaView style={styles.center}><Text style={styles.pageTitle}>Dental AI</Text><Text style={styles.cardSub}>Görüntü analizi ekranı burada native olacak.</Text></SafeAreaView>}</Tabs.Screen>
      <Tabs.Screen name="Program" options={{ title: "Program", tabBarLabel: "Program" }}>{() => <SafeAreaView style={styles.center}><Text style={styles.pageTitle}>Programım</Text></SafeAreaView>}</Tabs.Screen>
      <Tabs.Screen name="Profile" options={{ title: "Profil", tabBarLabel: "Profil" }}>{() => <Profile user={user} onLogout={onLogout}/>}</Tabs.Screen>
    </Tabs.Navigator>
  </NavigationContainer>;
}

export default function App() {
  const [session, setSession] = useState<{ token: string; user: User } | null>(null);
  if (!session) return <LoginScreen onLogin={(token, user) => setSession({ token, user })}/>;
  return <MainApp token={session.token} user={session.user} onLogout={() => setSession(null)}/>;
}

const styles = StyleSheet.create({
  login: { flex: 1, backgroundColor: bg, padding: 24, justifyContent: "center" },
  logo: { width: 72, height: 72, borderRadius: 22, backgroundColor: navy, alignItems: "center", justifyContent: "center", alignSelf: "center", marginBottom: 14 },
  logoText: { fontSize: 36 }, title: { textAlign: "center", fontSize: 28, fontWeight: "800", color: navy }, subtitle: { textAlign: "center", color: "#687386", marginBottom: 28, marginTop: 6 },
  input: { backgroundColor: "#fff", borderRadius: 14, padding: 15, marginBottom: 12, borderWidth: 1, borderColor: "#E1E6ED" },
  primary: { backgroundColor: navy, borderRadius: 14, padding: 16, alignItems: "center", marginTop: 8 }, primaryText: { color: "#fff", fontWeight: "800", fontSize: 16 }, error: { color: "#B42318", marginBottom: 8 },
  screen: { flex: 1, backgroundColor: bg, padding: 18 }, greeting: { fontSize: 25, fontWeight: "800", color: navy, marginTop: 8 }, pageTitle: { fontSize: 28, fontWeight: "800", color: navy, marginBottom: 16 },
  sectionTitle: { fontSize: 17, fontWeight: "800", color: navy, marginTop: 24, marginBottom: 10 }, stats: { flexDirection: "row", gap: 10 }, stat: { flex: 1, backgroundColor: "#fff", borderRadius: 16, padding: 15 }, statValue: { fontSize: 25, fontWeight: "800", color: navy }, statLabel: { color: "#687386", marginTop: 3 },
  card: { backgroundColor: "#fff", borderRadius: 17, padding: 17, marginBottom: 11 }, cardTitle: { fontSize: 16, fontWeight: "800", color: navy }, cardSub: { color: "#687386", marginTop: 5 }, search: { backgroundColor: "#fff", borderRadius: 14, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#E1E6ED" },
  patient: { flexDirection: "row", alignItems: "center", backgroundColor: "#fff", borderRadius: 16, padding: 12, marginBottom: 9 }, avatar: { width: 46, height: 46, borderRadius: 23, backgroundColor: "#E9EEF5", alignItems: "center", justifyContent: "center", marginRight: 12 }, avatarText: { color: navy, fontWeight: "800" }, patientName: { fontSize: 16, fontWeight: "800", color: navy }, chevron: { fontSize: 28, color: "#9AA3B2" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: bg, padding: 24 }, profile: { alignItems: "center", marginBottom: 22 }, bigAvatar: { width: 82, height: 82, borderRadius: 41, backgroundColor: navy, alignItems: "center", justifyContent: "center", marginBottom: 10 }, bigAvatarText: { color: "#fff", fontSize: 32, fontWeight: "800" }, profileName: { color: navy, fontSize: 22, fontWeight: "800" }, logout: { borderRadius: 14, padding: 15, alignItems: "center", borderWidth: 1, borderColor: "#D6DCE5" }, logoutText: { color: "#B42318", fontWeight: "800" }
});
