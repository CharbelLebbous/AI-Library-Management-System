import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

import App from "./App";

vi.mock("./lib/auth", () => ({
  isAuthEnabled: vi.fn().mockReturnValue(false),
  getToken: vi.fn().mockReturnValue("admin:admin@example.com"),
  setDevToken: vi.fn()
}));

vi.mock("./api", () => ({
  setAuthTokenResolver: vi.fn(),
  getCurrentUser: vi.fn().mockResolvedValue({ id: "u1", email: "u1@example.com", role: "admin" }),
  listBooks: vi.fn().mockResolvedValue([
    {
      id: 1,
      title: "Rich Dad Poor Dad",
      author: "Robert Kiyosaki",
      metadata: { description: "Money management basics." },
      status: "available",
      created_at: "2026-03-03T00:00:00Z",
      updated_at: "2026-03-03T00:00:00Z"
    }
  ]),
  createBook: vi.fn(),
  deleteBook: vi.fn(),
  checkoutBook: vi.fn(),
  checkinBook: vi.fn(),
  chatSearch: vi.fn()
}));


describe("App", () => {
  it("renders title and book description", async () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>
    );

    expect(screen.getByText(/Aspire Library AI/i)).toBeInTheDocument();
    expect(await screen.findByText(/Money management basics\./i)).toBeInTheDocument();
  });
});
