import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MessageSquare, Plus, Search, Trash2, X } from "lucide-react";
import { useConversations, useDeleteConversation } from "@/hooks/queries";
import { parseUtc } from "@/lib/format";
import { Button } from "@/components/ui/Button";

export function ConversationsPage() {
  const query = useConversations(100);
  const deleteConversation = useDeleteConversation();
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  const conversations = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return query.data ?? [];
    return (query.data ?? []).filter((item) =>
      `${item.title ?? ""} ${item.summary ?? ""}`.toLowerCase().includes(q),
    );
  }, [query.data, search]);

  const handleDelete = async (e: React.MouseEvent, id: number, title?: string | null) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm(`Delete "${title || "Untitled conversation"}"?`)) return;
    await deleteConversation.mutateAsync(id);
  };

  return (
    <section className="mx-auto w-full max-w-4xl space-y-6 pb-12">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold tracking-tight text-ink">Conversations</h1>
          <p className="mt-1 text-sm text-ink-dim">
            Browse previous dialogues, search history, or start a fresh thread with IRIS.
          </p>
        </div>
        <Button onClick={() => navigate("/")} className="gap-2">
          <Plus size={16} />
          <span>New conversation</span>
        </Button>
      </header>

      {/* Search Input */}
      <div className="relative">
        <label className="flex h-11 items-center gap-2.5 rounded-xl border border-ops-line bg-ops-panel px-3.5 shadow-2xs focus-within:border-ai focus-within:ring-1 focus-within:ring-ai/30 transition-all">
          <Search size={16} className="text-ink-faint shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search conversations by title or topic…"
            className="min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-ink-faint outline-none"
            aria-label="Search conversations"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="p-1 text-ink-faint hover:text-ink cursor-pointer"
              aria-label="Clear search"
            >
              <X size={14} />
            </button>
          )}
        </label>
      </div>

      {/* State views */}
      {query.isLoading ? (
        <div className="space-y-2.5" aria-label="Loading conversations">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-ops-raised/60 border border-ops-line" />
          ))}
        </div>
      ) : query.isError ? (
        <div className="rounded-xl border border-critical/30 bg-critical-dim p-5 text-sm">
          <p className="font-semibold text-ink">Conversations could not be loaded.</p>
          <p className="mt-1 text-xs text-ink-dim">Check your connection and try again.</p>
          <Button variant="outline" size="sm" onClick={() => void query.refetch()} className="mt-3">
            Retry
          </Button>
        </div>
      ) : conversations.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-ops-line-bright bg-ops-panel/60 px-6 py-16 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-ops-raised text-ink-faint">
            <MessageSquare size={22} />
          </div>
          <h2 className="mt-3 text-base font-semibold text-ink">
            {search ? "No matching conversations" : "No conversations yet"}
          </h2>
          <p className="mt-1 text-sm text-ink-dim max-w-sm mx-auto">
            {search
              ? "No past conversations match your query. Try a different keyword or clear search."
              : "Your conversation history with IRIS will appear here as you chat."}
          </p>
          {search ? (
            <Button variant="outline" size="sm" onClick={() => setSearch("")} className="mt-4">
              Clear search
            </Button>
          ) : (
            <Button size="sm" onClick={() => navigate("/")} className="mt-4 gap-1.5">
              <Plus size={15} /> Start your first chat
            </Button>
          )}
        </div>
      ) : (
        <ul className="divide-y divide-ops-line overflow-hidden rounded-2xl border border-ops-line bg-ops-panel shadow-2xs">
          {conversations.map((item) => (
            <li key={item.id} className="group relative">
              <Link
                to={`/?c=${item.id}`}
                className="flex items-center gap-3.5 px-4 py-3.5 hover:bg-ops-ground/80 focus-visible:bg-ops-ground transition-colors"
              >
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-ai-dim text-ai">
                  <MessageSquare size={17} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold text-ink group-hover:text-ai transition-colors">
                      {item.title || "Untitled conversation"}
                    </p>
                    <time className="shrink-0 text-xs text-ink-faint tnum">
                      {parseUtc(item.updated_at).toLocaleDateString([], { month: "short", day: "numeric" })}
                    </time>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-ink-dim">
                    {item.summary || "No preview available"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={(e) => handleDelete(e, item.id, item.title)}
                  title="Delete conversation"
                  aria-label="Delete conversation"
                  className="opacity-0 group-hover:opacity-100 p-2 text-ink-faint hover:text-critical rounded-lg hover:bg-ops-raised transition-all cursor-pointer"
                >
                  <Trash2 size={15} />
                </button>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
