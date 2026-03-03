export type Role = "admin" | "librarian" | "member";
export type BookStatus = "available" | "borrowed";

export interface Book {
  id: number;
  title: string;
  author: string;
  metadata: Record<string, unknown>;
  metadata_json?: Record<string, unknown>;
  status: BookStatus;
  created_at: string;
  updated_at: string;
}

export interface Loan {
  id: number;
  book_id: number;
  borrower_name: string;
  checked_out_by: string;
  checked_out_at: string;
  checked_in_at: string | null;
}

export interface ChatSearchSource {
  book_id: number;
  title: string;
  author: string;
  status: BookStatus;
  score: number;
  snippet: string;
}

export interface ChatSearchResponse {
  answer: string;
  sources: ChatSearchSource[];
  blocked: boolean;
  reason: string | null;
  retrieval_method: string;
  conversation_id: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  role: Role;
}
