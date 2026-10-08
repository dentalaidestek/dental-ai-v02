const API_BASE = "https://dentalai.tr/api/mobile/v1";

export type User = {
  id: number;
  username: string;
  email: string;
  display_name: string;
  role: string;
  professional_title?: string | null;
  specialty?: string | null;
  university?: string | null;
};

export type Patient = {
  id: number;
  anonymous_id?: string | null;
  first_name: string;
  last_name: string;
  phone?: string | null;
  birth_date?: string | null;
  age?: number | null;
  chief_complaint?: string | null;
  created_at?: string | null;
};

export async function login(loginValue: string, password: string) {
  const response = await fetch(API_BASE + "/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login: loginValue, password }),
  });
  if (!response.ok) throw new Error("Giriş başarısız.");
  return response.json() as Promise<{ access_token: string; expires_at: string }>;
}

async function request<T>(path: string, token: string): Promise<T> {
  const response = await fetch(API_BASE + path, {
    headers: { Authorization: "Bearer " + token },
  });
  if (!response.ok) throw new Error("İstek başarısız.");
  return response.json();
}

export const getMe = (token: string) => request<{ user: User }>("/me", token);
export const getDashboard = (token: string) =>
  request<{
    user: User;
    stats: { patient_count: number; analysis_count: number; upcoming_event_count: number };
    recent_patients: Patient[];
    upcoming_events: Array<{ id: number; title: string; start_at: string; patient_id?: number | null }>;
  }>("/dashboard", token);

export const getPatients = (token: string, q = "") =>
  request<{ items: Patient[]; total: number }>(
    "/patients?limit=50" + (q ? "&q=" + encodeURIComponent(q) : ""),
    token,
  );

export const getPatient = (token: string, id: number) =>
  request<{
    patient: Patient;
    teeth: unknown[];
    surfaces: unknown[];
    treatments: unknown[];
    media: unknown[];
  }>("/patients/" + id, token);
