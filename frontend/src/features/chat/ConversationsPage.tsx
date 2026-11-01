import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MessageSquare, Plus, Search } from "lucide-react";
import { useConversations } from "@/hooks/queries";
import { parseUtc } from "@/lib/format";

export function ConversationsPage() {
  const query = useConversations(100);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const conversations = useMemo(() => (query.data ?? []).filter((item) => `${item.title ?? ""} ${item.summary ?? ""}`.toLowerCase().includes(search.toLowerCase())), [query.data, search]);
  return <section className="mx-auto w-full max-w-5xl">
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3"><div><p className="label-caps">YOUR HISTORY</p><h1 className="mt-1 text-3xl font-semibold tracking-tight">Conversations</h1><p className="mt-1 text-sm text-ink-faint">Continue a thread or start a fresh conversation with IRIS.</p></div><button onClick={() => navigate("/")} className="inline-flex h-11 items-center gap-2 rounded-xl bg-ai px-4 text-sm font-medium text-white hover:opacity-90"><Plus size={17}/>New conversation</button></header>
    <label className="mb-4 flex h-11 items-center gap-2 rounded-xl border border-ops-line bg-ops-panel px-3"><Search size={16} className="text-ink-faint"/><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search conversations" className="min-w-0 flex-1 bg-transparent text-sm outline-none" aria-label="Search conversations"/></label>
    {query.isLoading ? <div className="space-y-2" aria-label="Loading conversations">{[0,1,2,3].map((i) => <div key={i} className="h-[74px] animate-pulse rounded-2xl bg-ops-raised"/>)}</div> : query.isError ? <div className="rounded-2xl border border-critical/30 bg-critical-dim p-5"><p className="font-medium">Conversations could not load.</p><button onClick={() => void query.refetch()} className="mt-2 text-sm text-ai underline">Retry</button></div> : conversations.length === 0 ? <div className="rounded-2xl border border-dashed border-ops-line-bright bg-ops-panel px-5 py-12 text-center"><MessageSquare size={24} className="mx-auto text-ink-faint"/><p className="mt-3 font-medium">{search ? "No matching conversations" : "No conversations yet"}</p><p className="mt-1 text-sm text-ink-faint">{search ? "Try another search." : "Your conversations with IRIS will appear here."}</p></div> : <ul className="divide-y divide-ops-line overflow-hidden rounded-2xl border border-ops-line bg-ops-panel">{conversations.map((item) => <li key={item.id}><Link to={`/?c=${item.id}`} className="flex min-h-[76px] items-center gap-3 px-4 py-3 hover:bg-ops-ground focus-visible:relative"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-ai-dim text-ai"><MessageSquare size={18}/></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{item.title || "Untitled conversation"}</span><span className="mt-1 block truncate text-xs text-ink-faint">{item.summary || "No preview available"}</span></span><time className="shrink-0 text-xs text-ink-faint">{parseUtc(item.updated_at).toLocaleDateString([], { month: "short", day: "numeric" })}</time></Link></li>)}</ul>}
  </section>;
}
