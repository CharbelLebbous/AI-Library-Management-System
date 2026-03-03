import axios from "axios";
import type { Book, ChatSearchResponse, CurrentUser, Loan } from "./types";
import { getToken } from "./lib/auth";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  timeout: 15000
});

let authTokenResolver: (() => Promise<string | null>) | null = null;

export function setAuthTokenResolver(resolver: (() => Promise<string | null>) | null) {
  authTokenResolver = resolver;
}

api.interceptors.request.use((config) => {
  return Promise.resolve().then(async () => {
    let token = "";
    let authResolverError: unknown = null;
    if (authTokenResolver) {
      try {
        token = (await authTokenResolver()) ?? "";
      } catch (error) {
        authResolverError = error;
        token = "";
      }
    }
    if (!token) {
      token = getToken();
    }
    if (!token && authResolverError) {
      if (authResolverError instanceof Error) {
        throw authResolverError;
      }
      throw new Error("Unable to get access token from Auth0.");
    }
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });
});

export async function listBooks(params: { query?: string; author?: string; status?: string }) {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== "")
  );
  const response = await api.get<Book[]>("/api/books", { params: cleanParams });
  return response.data.map((book) => ({
    ...book,
    metadata: (book.metadata ?? book.metadata_json ?? {}) as Record<string, unknown>
  }));
}

export async function getCurrentUser() {
  const response = await api.get<CurrentUser>("/api/me");
  return response.data;
}

export async function createBook(payload: { title: string; author: string; metadata: Record<string, unknown> }) {
  const response = await api.post<Book>("/api/books", payload);
  return response.data;
}

export async function checkoutBook(bookId: number, borrowerName: string) {
  const response = await api.post<Loan>(`/api/books/${bookId}/checkout`, { borrower_name: borrowerName });
  return response.data;
}

export async function checkinBook(bookId: number) {
  const response = await api.post<Loan>(`/api/books/${bookId}/checkin`);
  return response.data;
}

export async function deleteBook(bookId: number) {
  await api.delete(`/api/books/${bookId}`);
}

export async function chatSearch(payload: { question: string; conversationId?: string; reset?: boolean }) {
  const body = {
    question: payload.question,
    conversation_id: payload.conversationId,
    reset: payload.reset ?? false
  };
  const response = await api.post<ChatSearchResponse>("/api/ai/books/chat-search", body);
  return response.data;
}
