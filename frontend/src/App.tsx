import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { useAuth0 } from "@auth0/auth0-react";

import {
  chatSearch,
  checkinBook,
  checkoutBook,
  createBook,
  deleteBook,
  getCurrentUser,
  listBooks,
  setAuthTokenResolver
} from "./api";
import { AuthControls } from "./components/AuthControls";
import { DevTokenBar } from "./components/DevTokenBar";
import { isAuthEnabled } from "./lib/auth";
import type { Book, ChatSearchResponse, Role } from "./types";

export default function App() {
  const queryClient = useQueryClient();
  const authEnabled = isAuthEnabled();
  const auth0 = authEnabled ? useAuth0() : null;
  const authIsLoading = auth0?.isLoading ?? false;
  const authIsAuthenticated = auth0?.isAuthenticated ?? false;
  const authGetAccessTokenSilently = auth0?.getAccessTokenSilently;
  const [authApiReady, setAuthApiReady] = useState(!authEnabled);

  const [query, setQuery] = useState("");
  const [author, setAuthor] = useState("");
  const [status, setStatus] = useState("");

  const [title, setTitle] = useState("");
  const [bookAuthor, setBookAuthor] = useState("");
  const [bookDescription, setBookDescription] = useState("");
  const [borrowerNames, setBorrowerNames] = useState<Record<number, string>>({});

  const [chatQuestion, setChatQuestion] = useState("");
  const [chatResult, setChatResult] = useState<ChatSearchResponse | null>(null);
  const [conversationId, setConversationId] = useState(() => localStorage.getItem("library_ai_chat_conversation_id") ?? "");
  const [chatLoading, setChatLoading] = useState(false);
  const [uiError, setUiError] = useState("");
  const [uiInfo, setUiInfo] = useState("");

  const formatError = (error: unknown) => {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail;
      if (typeof detail === "string") {
        return detail;
      }
      return error.message;
    }
    if (error instanceof Error) {
      return error.message;
    }
    return "Unexpected error";
  };

  const filters = useMemo(() => ({ query, author, status }), [query, author, status]);
  const canLoadBooks = !authEnabled || (!authIsLoading && authIsAuthenticated);
  const canQueryApi = canLoadBooks && authApiReady;

  useEffect(() => {
    let cancelled = false;

    const bootstrapAuth = async () => {
      if (!authEnabled) {
        setAuthTokenResolver(null);
        setAuthApiReady(true);
        return;
      }

      if (!authIsAuthenticated || !authGetAccessTokenSilently) {
        localStorage.removeItem("library_ai_auth_token");
        setAuthTokenResolver(async () => "");
        setAuthApiReady(false);
        return;
      }

      try {
        const token = await authGetAccessTokenSilently();
        if (cancelled) return;
        localStorage.setItem("library_ai_auth_token", token);
        setAuthTokenResolver(async () => {
          const latestToken = await authGetAccessTokenSilently();
          localStorage.setItem("library_ai_auth_token", latestToken);
          return latestToken;
        });
        setAuthApiReady(true);
      } catch {
        if (cancelled) return;
        setAuthApiReady(false);
      }
    };

    void bootstrapAuth();

    return () => {
      cancelled = true;
    };
  }, [authEnabled, authGetAccessTokenSilently, authIsAuthenticated]);

  const booksQuery = useQuery({
    queryKey: ["books", filters],
    queryFn: () => listBooks(filters),
    retry: false,
    enabled: canQueryApi
  });

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: getCurrentUser,
    retry: 1,
    enabled: canQueryApi
  });

  const userRole: Role | null = meQuery.data?.role ?? null;
  const canManageCatalog = userRole === "admin" || userRole === "librarian";
  const canDeleteBooks = userRole === "admin";
  const canHandleCirculation = userRole === "admin" || userRole === "librarian";

  const books = booksQuery.data ?? [];
  const totalBooks = books.length;
  const availableBooks = books.filter((book) => book.status === "available").length;
  const borrowedBooks = books.filter((book) => book.status === "borrowed").length;

  const createMutation = useMutation({
    mutationFn: createBook,
    onSuccess: async () => {
      setUiError("");
      setUiInfo("Book created successfully.");
      await queryClient.invalidateQueries({ queryKey: ["books"] });
    },
    onError: (error) => {
      setUiInfo("");
      setUiError(`Create failed: ${formatError(error)}`);
    }
  });

  const checkoutMutation = useMutation({
    mutationFn: ({ bookId, borrower }: { bookId: number; borrower: string }) => checkoutBook(bookId, borrower),
    onSuccess: async () => {
      setUiError("");
      setUiInfo("Checkout successful.");
      await queryClient.invalidateQueries({ queryKey: ["books"] });
    },
    onError: (error) => {
      setUiInfo("");
      setUiError(`Checkout failed: ${formatError(error)}`);
    }
  });

  const checkinMutation = useMutation({
    mutationFn: checkinBook,
    onSuccess: async () => {
      setUiError("");
      setUiInfo("Checkin successful.");
      await queryClient.invalidateQueries({ queryKey: ["books"] });
    },
    onError: (error) => {
      setUiInfo("");
      setUiError(`Checkin failed: ${formatError(error)}`);
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBook,
    onSuccess: async () => {
      setUiError("");
      setUiInfo("Book deleted successfully.");
      await queryClient.invalidateQueries({ queryKey: ["books"] });
    },
    onError: (error) => {
      setUiInfo("");
      setUiError(`Delete failed: ${formatError(error)}`);
    }
  });

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!canManageCatalog) {
      setUiInfo("");
      setUiError("Only admin/librarian can create books.");
      return;
    }
    if (!title || !bookAuthor) {
      setUiInfo("");
      setUiError("Title and author are required.");
      return;
    }
    try {
      await createMutation.mutateAsync({
        title,
        author: bookAuthor,
        metadata: bookDescription.trim() ? { description: bookDescription.trim() } : {}
      });
      setTitle("");
      setBookAuthor("");
      setBookDescription("");
    } catch {
      // Error handled in mutation onError.
    }
  };

  const runChatSearch = async () => {
    if (!chatQuestion.trim()) {
      setUiInfo("");
      setUiError("Ask a question about books in your catalog.");
      return;
    }
    setChatLoading(true);
    try {
      const result = await chatSearch({ question: chatQuestion.trim(), conversationId: conversationId || undefined });
      setChatResult(result);
      setConversationId(result.conversation_id);
      localStorage.setItem("library_ai_chat_conversation_id", result.conversation_id);
      setUiError("");
      if (result.blocked) {
        setUiInfo("I could not answer that. Please ask a library-related question.");
      } else {
        setUiInfo("AI answer is ready.");
      }
    } catch (error) {
      setUiInfo("");
      setUiError(`AI chat search failed: ${formatError(error)}`);
    } finally {
      setChatLoading(false);
    }
  };

  const startNewChat = () => {
    setConversationId("");
    setChatQuestion("");
    setChatResult(null);
    localStorage.removeItem("library_ai_chat_conversation_id");
    setUiError("");
    setUiInfo("Started a new chat.");
  };

  const clearFilters = () => {
    setQuery("");
    setAuthor("");
    setStatus("");
    setUiInfo("Filters cleared.");
    setUiError("");
  };

  const setBorrowerName = (bookId: number, value: string) => {
    setBorrowerNames((prev) => ({ ...prev, [bookId]: value }));
  };

  const getBookDescription = (book: Book): string => {
    const value = book.metadata?.description;
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
    return "No description provided.";
  };

  return (
    <div className="app-shell">
      <main className="app-layout">
        <header className="card hero reveal">
          <div className="hero-kicker">AI-FIRST LIBRARY OPERATIONS</div>
          <h1 className="hero-title">AI Library Management System</h1>
          <p className="hero-subtitle">
            Production-style catalog management with role-aware access, secure SSO, and conversational semantic RAG.
          </p>
          <div className="hero-stats">
            <div className="stat-pill">
              <span className="stat-label">Total</span>
              <strong>{totalBooks}</strong>
            </div>
            <div className="stat-pill">
              <span className="stat-label">Available</span>
              <strong>{availableBooks}</strong>
            </div>
            <div className="stat-pill">
              <span className="stat-label">Borrowed</span>
              <strong>{borrowedBooks}</strong>
            </div>
          </div>
        </header>

        <section className="card reveal delay-1">
          {authEnabled && <AuthControls />}
          <DevTokenBar />
          {authEnabled && canLoadBooks && !authApiReady && (
            <p className="meta-text">Finalizing secure session...</p>
          )}
          {canQueryApi && meQuery.isError && (
            <div className="alert alert-error">Unable to load your permissions right now.</div>
          )}
          {userRole && (
            <div className={`role-banner role-${userRole}`}>
              {userRole === "admin" && <strong>Full access enabled.</strong>}
              {userRole === "librarian" && <strong>Catalog and circulation access enabled.</strong>}
              {userRole === "member" && <strong>Read-only access enabled.</strong>}
            </div>
          )}
        </section>

        <section className="workspace-grid">
          <article className="card reveal delay-2">
            <h2 className="section-title">Search Catalog</h2>
            <p className="section-description">
              Filter by title, author, and availability.
            </p>
            <div className="field-grid">
              <input
                className="input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="title or author text"
              />
              <input
                className="input"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder="author"
              />
              <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">any status</option>
                <option value="available">available</option>
                <option value="borrowed">borrowed</option>
              </select>
            </div>
            <div className="button-row">
              <button className="button button-secondary" onClick={clearFilters}>
                Clear Filters
              </button>
            </div>
          </article>

          <article className="card reveal delay-3">
            <h2 className="section-title">Add Book</h2>
            <p className="section-description">
              Add structured descriptions to improve semantic retrieval quality.
            </p>
            {canManageCatalog ? (
              <form onSubmit={submitCreate} className="field-grid">
                <input
                  className="input"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="title"
                />
                <input
                  className="input"
                  value={bookAuthor}
                  onChange={(e) => setBookAuthor(e.target.value)}
                  placeholder="author"
                />
                <textarea
                  className="textarea span-2"
                  value={bookDescription}
                  onChange={(e) => setBookDescription(e.target.value)}
                  placeholder="description (recommended for semantic RAG search)"
                />
                <button className="button button-primary span-2" type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? "Creating..." : "Create"}
                </button>
              </form>
            ) : (
              <div className="empty-note">Your account cannot add or edit books.</div>
            )}
          </article>
        </section>

        <section className="card reveal delay-4">
          <div className="section-head">
            <h2 className="section-title">Ask Library AI</h2>
            <span className="tag">Semantic RAG</span>
          </div>
          <p className="section-description">
            Ask in natural language about titles, authors, descriptions, status, or metadata.
          </p>
          <div className="chat-grid">
            <textarea
              className="textarea"
              value={chatQuestion}
              onChange={(e) => setChatQuestion(e.target.value)}
              placeholder="Example: Which books are about value investing and are currently available?"
            />
            <div className="chat-actions">
              <button className="button button-primary" onClick={runChatSearch} disabled={chatLoading}>
                {chatLoading ? "Thinking..." : "Ask AI"}
              </button>
              <button className="button button-secondary" onClick={startNewChat} disabled={chatLoading}>
                New Chat
              </button>
            </div>
          </div>
          {chatResult && (
            <div className="chat-result">
              <p className="chat-answer">
                <strong>Answer:</strong> {chatResult.answer}
              </p>
              {chatResult.sources.length > 0 && (
                <div>
                  <p className="source-title">Related books</p>
                  <ul className="source-list">
                    {chatResult.sources.map((src) => (
                      <li key={src.book_id}>
                        {src.title} by {src.author} <span className={`status-pill status-${src.status}`}>{src.status}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>

        <section className="card reveal delay-5">
          <h2 className="section-title">Books</h2>
          {uiError && <div className="alert alert-error">{uiError}</div>}
          {uiInfo && !uiError && <div className="alert alert-success">{uiInfo}</div>}
          {authEnabled && !canLoadBooks && <div className="empty-note">Sign in with SSO to load books.</div>}
          {canQueryApi && booksQuery.isLoading && <div className="loading-note">Loading books...</div>}
          {booksQuery.isError && (
            <div className="alert alert-error">
              Failed to load books: {formatError(booksQuery.error)}
            </div>
          )}
          {!booksQuery.isLoading && !booksQuery.isError && books.length === 0 && (
            <div className="empty-note">No books found for current filters.</div>
          )}
          <div className="book-grid">
            {books.map((book: Book) => (
              <article key={book.id} className="book-card">
                <div className="book-header">
                  <h3>{book.title}</h3>
                  <span className={`status-pill status-${book.status}`}>{book.status}</span>
                </div>
                <p className="book-author">{book.author}</p>
                <p className="book-description">
                  <strong>Description:</strong> {getBookDescription(book)}
                </p>
                <div className="book-actions">
                  {canHandleCirculation ? (
                    <>
                      <input
                        className="input borrower-input"
                        value={borrowerNames[book.id] ?? ""}
                        onChange={(e) => setBorrowerName(book.id, e.target.value)}
                        placeholder="borrower name"
                      />
                      <button
                        className="button button-secondary"
                        onClick={() => {
                          const borrower = borrowerNames[book.id]?.trim() || "Borrower";
                          checkoutMutation.mutate({ bookId: book.id, borrower });
                        }}
                        disabled={book.status === "borrowed"}
                      >
                        Checkout
                      </button>
                      <button
                        className="button button-secondary"
                        onClick={() => checkinMutation.mutate(book.id)}
                        disabled={book.status === "available"}
                      >
                        Checkin
                      </button>
                    </>
                  ) : (
                    <span className="empty-note">Read-only access</span>
                  )}
                  {canDeleteBooks && (
                    <button
                      className="button button-danger"
                      onClick={() => {
                        const confirmed = window.confirm(`Delete "${book.title}"? This cannot be undone.`);
                        if (confirmed) {
                          deleteMutation.mutate(book.id);
                        }
                      }}
                      disabled={deleteMutation.isPending}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
