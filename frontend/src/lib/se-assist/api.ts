const BASE = "/api/se_assist";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    credentials: "include",
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// Emails
export const listEmails = (skip = 0, limit = 20, uploadedBy?: number) => {
  let url = `/emails/?skip=${skip}&limit=${limit}`;
  if (uploadedBy) url += `&uploaded_by=${uploadedBy}`;
  return request<EmailListResponse>(url);
};
export const getEmail = (emailId: number) => request<EmailResponse>(`/emails/${emailId}`);
export const deleteEmail = (emailId: number) =>
  request<{ message: string }>(`/emails/${emailId}`, { method: "DELETE" });
export const seedDemo = () =>
  request<{ message: string; email_id: number }>("/emails/seed-demo", { method: "POST" });
export const listUploaders = () =>
  request<Uploader[]>(`/emails/uploaders`);

export async function uploadEml(file: File): Promise<{ message: string; email_id: number }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE}/emails/upload`, {
    method: "POST",
    body: formData,
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

// Analysis
export const runAnalysis = (emailId: number) =>
  request<AnalysisResponse>(`/analysis/${emailId}`, { method: "POST" });
export const getAnalysis = (emailId: number) =>
  request<AnalysisResponse>(`/analysis/${emailId}`);
export const updateAnalysis = (analysisId: number, data: Partial<AnalysisUpdate>) =>
  request<AnalysisResponse>(`/analysis/${analysisId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
export const rerunAnalysis = (emailId: number) =>
  request<AnalysisResponse>(`/analysis/${emailId}/rerun`, { method: "POST" });

// Transcripts
export const listTranscripts = (skip = 0, limit = 20, uploadedBy?: number) => {
  let url = `/transcripts/?skip=${skip}&limit=${limit}`;
  if (uploadedBy) url += `&uploaded_by=${uploadedBy}`;
  return request<TranscriptListResponse>(url);
};
export const getTranscript = (id: number) => request<TranscriptResponse>(`/transcripts/${id}`);
export const createTranscript = (data: { company_name: string; call_date?: string; transcript_text: string }) =>
  request<TranscriptResponse>(`/transcripts/`, { method: "POST", body: JSON.stringify(data) });
export const deleteTranscript = (id: number) =>
  request<{ message: string }>(`/transcripts/${id}`, { method: "DELETE" });
export const listTranscriptUploaders = () =>
  request<Uploader[]>(`/transcripts/uploaders`);
export const runTranscriptAnalysis = (transcriptId: number) =>
  request<TranscriptAnalysisResponse>(`/transcripts/${transcriptId}/analyze`, { method: "POST" });
export const getTranscriptAnalysis = (transcriptId: number) =>
  request<TranscriptAnalysisResponse>(`/transcripts/${transcriptId}/analysis`);
export const updateTranscriptAnalysis = (analysisId: number, data: Partial<AnalysisUpdate>) =>
  request<TranscriptAnalysisResponse>(`/transcripts/analysis/${analysisId}`, { method: "PUT", body: JSON.stringify(data) });
export const rerunTranscriptAnalysis = (transcriptId: number) =>
  request<TranscriptAnalysisResponse>(`/transcripts/${transcriptId}/rerun`, { method: "POST" });

// Types
export interface Uploader { id: number; name: string; }

export interface ParsedEmailData {
  company_name: string;
  call_date: string | null;
  duration: string | null;
  key_points: string[];
  next_steps: string[];
  twilio_participants: { name: string; title: string | null }[];
  customer_participants: { name: string; title: string | null }[];
  associated_deals: { name: string; amount: string | null; stage: string | null; close_date: string | null }[];
}

export interface EmailResponse {
  id: number;
  gmail_message_id: string;
  subject: string;
  company_name: string | null;
  call_date: string | null;
  duration: string | null;
  parsed_data: ParsedEmailData;
  status: string;
  received_at: string;
  created_at: string;
  uploaded_by_name: string | null;
  user_id: number | null;
}

export interface EmailListResponse { emails: EmailResponse[]; total: number; }

export interface AnalysisResponse {
  id: number;
  gong_email_id: number;
  use_case_category: string | null;
  presales_stage: string | null;
  sfdc_use_case_description: string | null;
  sfdc_solutions_notes: string | null;
  sfdc_technical_risks: string | null;
  raw_response: Record<string, unknown>;
  model_used: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface AnalysisUpdate {
  use_case_category: string;
  presales_stage: string;
  sfdc_use_case_description: string;
  sfdc_solutions_notes: string;
  sfdc_technical_risks: string;
}

export interface TranscriptResponse {
  id: number;
  company_name: string;
  call_date: string | null;
  duration: string | null;
  transcript_text: string;
  status: string;
  created_at: string;
  uploaded_by_name: string | null;
  user_id: number | null;
}

export interface TranscriptListResponse { transcripts: TranscriptResponse[]; total: number; }

export interface TranscriptAnalysisResponse {
  id: number;
  transcript_id: number;
  use_case_category: string | null;
  presales_stage: string | null;
  sfdc_use_case_description: string | null;
  sfdc_solutions_notes: string | null;
  sfdc_technical_risks: string | null;
  raw_response: Record<string, unknown>;
  model_used: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  created_at: string;
}
