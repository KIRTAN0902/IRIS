import { lazy, Suspense, useState } from "react";
import {
  Brain,
  Network,
  Plus,
  Radio,
  Search,
  Trash2,
} from "lucide-react";
import { useCreateMemory, useDeleteMemory, useMemories } from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { cn, fmtTime } from "@/lib/format";
import type { AIMemoryOut, MemoryCategory } from "@/types/api";
import { useLensStore } from "@/stores/lensStore";
import { PatternsView } from "@/features/home/PatternsView";

const KnowledgePage = lazy(() => import("@/features/knowledge/KnowledgePage").then((m) => ({ default: m.KnowledgePage })));
const MeshPage = lazy(() => import("@/features/mesh/MeshPage").then((m) => ({ default: m.MeshPage })));

const MEMORY_CATEGORIES: { label: string; value: MemoryCategory | "ALL" }[] = [
  { label: "All", value: "ALL" },
  { label: "Preferences", value: "PREFERENCE" },
  { label: "Work style", value: "WORK_STYLE" },
  { label: "Routines", value: "ROUTINE" },
  { label: "Facts", value: "FACT" },
  { label: "People", value: "PEOPLE" },
  { label: "Projects", value: "PROJECT" },
  { label: "Constraints", value: "CONSTRAINT" },
];

export function VaultLens() {
  const { vaultTab, setVaultTab } = useLensStore();

  return (
    <div className="flex h-[calc(100vh-3.5rem)] w-full flex-col overflow-hidden">
      {/* 1. Vault Sub-Navigation Bar */}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-ops-line/80 px-4 md:px-6 bg-ops-panel/60 backdrop-blur-xs">
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none py-1">
          <TabButton
            active={vaultTab === "graph"}
            onClick={() => setVaultTab("graph")}
            label="Knowledge Graph & Claims"
            icon={Network}
          />
          <TabButton
            active={vaultTab === "memories"}
            onClick={() => setVaultTab("memories")}
            label="What IRIS Remembers"
            icon={Brain}
          />
          <TabButton
            active={vaultTab === "mesh"}
            onClick={() => setVaultTab("mesh")}
            label="Sovereign Mesh & Devices"
            icon={Radio}
          />
        </div>
      </div>

      {/* 2. Content View */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        <Suspense fallback={<div className="text-xs text-ink-faint animate-pulse">Loading Vault…</div>}>
          {vaultTab === "graph" && <KnowledgePage />}
          {vaultTab === "memories" && <MemoriesView />}
          {vaultTab === "mesh" && <MeshPage />}
        </Suspense>
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  label,
  icon: Icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  icon: typeof Network;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition cursor-pointer whitespace-nowrap",
        active
          ? "bg-ops-raised text-ink font-semibold border border-ops-line-bright shadow-2xs"
          : "text-ink-faint hover:text-ink hover:bg-ops-raised/50",
      )}
    >
      <Icon size={13} className={active ? "text-ai" : "opacity-70"} />
      <span>{label}</span>
    </button>
  );
}

// --- Memories View Component --------------------------------------------------------

function MemoriesView() {
  const [selectedCat, setSelectedCat] = useState<MemoryCategory | "ALL">("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newCat, setNewCat] = useState<MemoryCategory>("PREFERENCE");
  const [showAddForm, setShowAddForm] = useState(false);
  const [subView, setSubView] = useState<"memories" | "patterns">("memories");

  const memoriesQuery = useMemories({
    category: selectedCat === "ALL" ? undefined : selectedCat,
    search: searchQuery.trim() || undefined,
  });

  const createMemory = useCreateMemory();
  const deleteMemory = useDeleteMemory();

  const handleAddMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    try {
      await createMemory.mutateAsync({
        category: newCat,
        content: newContent.trim(),
        importance: 0.8,
      });
      setNewContent("");
      setShowAddForm(false);
    } catch {
      // Handled by react-query
    }
  };

  const memories = memoriesQuery.data ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Brain size={20} className="text-ai" />
            <h1 className="text-2xl font-bold tracking-tight text-ink">Personal Memory Vault</h1>
          </div>
          <p className="text-xs text-ink-dim mt-0.5">
            Core facts, habits, and preferences IRIS has learned about you across sessions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-xl bg-ops-raised p-1 border border-ops-line text-xs">
            <button
              onClick={() => setSubView("memories")}
              className={cn(
                "rounded-lg px-2.5 py-1 font-medium transition cursor-pointer",
                subView === "memories" ? "bg-ops-panel text-ink shadow-2xs font-semibold" : "text-ink-faint hover:text-ink",
              )}
            >
              Memories ({memories.length})
            </button>
            <button
              onClick={() => setSubView("patterns")}
              className={cn(
                "rounded-lg px-2.5 py-1 font-medium transition cursor-pointer",
                subView === "patterns" ? "bg-ops-panel text-ink shadow-2xs font-semibold" : "text-ink-faint hover:text-ink",
              )}
            >
              Learned Patterns
            </button>
          </div>

          <Button size="sm" onClick={() => setShowAddForm((v) => !v)}>
            <Plus size={13} />
            <span>Teach Fact</span>
          </Button>
        </div>
      </div>

      {subView === "patterns" ? (
        <PatternsView />
      ) : (
        <>
          {/* Add Memory Form */}
          {showAddForm && (
            <form
              onSubmit={handleAddMemory}
              className="rounded-2xl border border-ai/30 bg-ai/5 p-4 space-y-3 animate-in fade-in duration-150"
            >
              <h3 className="text-xs font-bold uppercase tracking-wider text-ai">
                Teach IRIS a Fact or Preference
              </h3>
              <div className="flex flex-col sm:flex-row gap-3">
                <select
                  value={newCat}
                  onChange={(e) => setNewCat(e.target.value as MemoryCategory)}
                  className="rounded-xl border border-ops-line bg-ops-panel px-3 py-2 text-xs text-ink outline-none"
                >
                  {MEMORY_CATEGORIES.filter((c) => c.value !== "ALL").map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  required
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  placeholder="e.g. I prefer dark mode and TypeScript for all frontend tasks."
                  className="flex-1 rounded-xl border border-ops-line bg-ops-panel px-3 py-2 text-xs text-ink outline-none focus:border-ai"
                />
                <Button type="submit" size="sm" disabled={createMemory.isPending}>
                  {createMemory.isPending ? "Saving…" : "Save Memory"}
                </Button>
              </div>
            </form>
          )}

          {/* Search & Category Filter Pills */}
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
            <div className="flex h-9 w-full sm:w-64 items-center gap-2 rounded-xl border border-ops-line bg-ops-panel px-3">
              <Search size={14} className="text-ink-faint" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search memories…"
                className="w-full bg-transparent text-xs text-ink outline-none placeholder:text-ink-faint"
              />
            </div>

            <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
              {MEMORY_CATEGORIES.map((cat) => (
                <button
                  key={cat.value}
                  onClick={() => setSelectedCat(cat.value)}
                  className={cn(
                    "rounded-xl px-2.5 py-1 text-xs font-medium transition cursor-pointer whitespace-nowrap",
                    selectedCat === cat.value
                      ? "bg-ai text-white shadow-xs"
                      : "bg-ops-panel border border-ops-line text-ink-dim hover:text-ink",
                  )}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          </div>

          {/* Memory Cards Grid */}
          {memories.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-ops-line bg-ops-panel p-8 text-center text-xs text-ink-faint">
              No memories recorded in this category.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {memories.map((m: AIMemoryOut) => (
                <div
                  key={m.id}
                  className="group flex flex-col justify-between rounded-xl border border-ops-line bg-ops-panel p-3.5 space-y-2 hover:border-ai/40 transition"
                >
                  <div>
                    <div className="flex items-center justify-between text-[10px] text-ink-faint mb-1">
                      <span className="rounded-md bg-ops-raised px-1.5 py-0.5 font-semibold uppercase tracking-wider text-ai">
                        {m.category}
                      </span>
                      {m.created_at && <span>{fmtTime(m.created_at)}</span>}
                    </div>
                    <p className="text-xs text-ink leading-relaxed">{m.content}</p>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-ops-line/50 text-[10px] text-ink-faint">
                    <span>Confidence: {Math.round((m.importance ?? 1) * 100)}%</span>
                    <button
                      type="button"
                      onClick={() => {
                        if (confirm("Delete this memory from IRIS?")) {
                          deleteMemory.mutate(m.id);
                        }
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-ink-faint hover:text-critical transition cursor-pointer"
                      title="Delete memory"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
