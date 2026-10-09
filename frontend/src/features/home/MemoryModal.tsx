import { useState } from "react";
import { Brain, Plus, Search, Trash2, X } from "lucide-react";
import { useCreateMemory, useDeleteMemory, useMemories } from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { cn, fmtTime } from "@/lib/format";
import type { MemoryCategory } from "@/types/api";
import { PatternsView } from "@/features/home/PatternsView";

interface MemoryModalProps {
  open: boolean;
  onClose: () => void;
}

const CATEGORIES: { label: string; value: MemoryCategory | "ALL" }[] = [
  { label: "All", value: "ALL" },
  { label: "Preferences", value: "PREFERENCE" },
  { label: "Routine", value: "ROUTINE" },
  { label: "Work style", value: "WORK_STYLE" },
  { label: "People", value: "PEOPLE" },
  { label: "Facts", value: "FACT" },
  { label: "Projects", value: "PROJECT" },
  { label: "Constraints", value: "CONSTRAINT" },
  { label: "Instructions", value: "INSTRUCTION" },
];

const CATEGORY_LABEL: Record<string, string> = {
  PREFERENCE: "Preference",
  ROUTINE: "Routine",
  WORK_STYLE: "Work style",
  FACT: "Fact",
  PEOPLE: "People",
  PROJECT: "Project",
  CONSTRAINT: "Constraint",
  INSTRUCTION: "Instruction",
  GENERAL: "Note",
};

export function MemoryModal({ open, onClose }: MemoryModalProps) {
  const [selectedCat, setSelectedCat] = useState<MemoryCategory | "ALL">("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newCat, setNewCat] = useState<MemoryCategory>("PREFERENCE");
  const [showAddForm, setShowAddForm] = useState(false);
  const [view, setView] = useState<"memories" | "patterns">("memories");

  const memoriesQuery = useMemories({
    category: selectedCat === "ALL" ? undefined : selectedCat,
    search: searchQuery.trim() || undefined,
  });

  const createMemory = useCreateMemory();
  const deleteMemory = useDeleteMemory();

  if (!open) return null;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim() || createMemory.isPending) return;

    await createMemory.mutateAsync({
      content: newContent.trim(),
      category: newCat,
      importance: 0.8,
    });
    setNewContent("");
    setShowAddForm(false);
  };



  const memories = memoriesQuery.data ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px] animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl border border-ops-line bg-ops-ground shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between px-5 pt-5 pb-2">
          <div>
            <h2 className="text-[20px] font-bold text-ink">What IRIS knows about you</h2>
            <div className="mt-2 flex gap-4 text-[14px]" role="tablist">
              {(["memories", "patterns"] as const).map((v) => (
                <button
                  key={v}
                  role="tab"
                  aria-selected={view === v}
                  onClick={() => setView(v)}
                  className={cn(
                    "border-b-2 pb-1 capitalize transition-colors cursor-pointer",
                    view === v ? "border-ink font-medium text-ink" : "border-transparent text-ink-faint hover:text-ink-dim",
                  )}
                >
                  {v === "memories" ? `Memories (${memories.length})` : "Patterns"}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-lg p-1.5 text-ink-dim hover:text-ink hover:bg-ops-raised transition-colors cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        {view === "patterns" ? (
          <div className="flex-1 overflow-y-auto p-4">
            <PatternsView />
          </div>
        ) : (
        <>
        {/* Search & Actions Bar */}
        <div className="flex flex-col gap-3 border-b border-ops-line bg-ops-base/40 px-5 py-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search memories, preferences, facts..."
                className="w-full rounded-xl border border-ops-line bg-ops-panel pl-9 pr-3 py-1.5 text-[13px] text-ink placeholder:text-ink-faint focus:border-ai focus:outline-none"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] text-ink-faint hover:text-ink"
                >
                  Clear
                </button>
              )}
            </div>
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="flex items-center gap-1.5 rounded-xl border border-ops-line-bright bg-ops-panel px-3 py-1.5 text-[12px] font-semibold text-ink-dim hover:text-ink hover:border-ai/50 transition-all cursor-pointer shrink-0"
            >
              <Plus size={13} className="text-ai" />
              <span>Add Memory</span>
            </button>
          </div>

          {/* Category Filter Pills */}
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.value}
                onClick={() => setSelectedCat(cat.value)}
                className={cn(
                  "rounded-full px-3 py-1 text-[11px] font-medium transition-all cursor-pointer",
                  selectedCat === cat.value
                    ? "bg-ink text-ops-void font-semibold shadow-xs"
                    : "border border-ops-line-bright/60 bg-ops-panel/60 text-ink-dim hover:text-ink hover:bg-ops-raised",
                )}
              >
                {cat.label}
              </button>
            ))}
          </div>

          {/* Expandable Manual Add Form */}
          {showAddForm && (
            <form onSubmit={handleCreate} className="mt-1 flex flex-col gap-2 rounded-xl border border-ai/30 bg-ai/5 p-3 animate-in fade-in duration-150">
              <div className="flex items-center justify-between text-[11px] font-medium text-ai">
                <span>Explicitly teach IRIS new context</span>
                <select
                  value={newCat}
                  onChange={(e) => setNewCat(e.target.value as MemoryCategory)}
                  className="rounded border border-ai/30 bg-ops-panel px-2 py-0.5 text-[11px] text-ink focus:outline-none"
                >
                  <option value="PREFERENCE">Preference</option>
                  <option value="ROUTINE">Routine</option>
                  <option value="WORK_STYLE">Work style</option>
                  <option value="PEOPLE">People</option>
                  <option value="FACT">Fact</option>
                  <option value="PROJECT">Project</option>
                  <option value="CONSTRAINT">Constraint</option>
                  <option value="INSTRUCTION">Instruction</option>
                  <option value="GENERAL">General</option>
                </select>
              </div>
              <textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="e.g. 'I prefer deep work blocks before 11 AM' or 'Nexus is targeting dental clinics'"
                rows={2}
                className="w-full resize-none rounded-lg border border-ops-line bg-ops-panel p-2 text-[12px] text-ink placeholder:text-ink-faint focus:border-ai focus:outline-none"
              />
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setShowAddForm(false)}>
                  Cancel
                </Button>
                <Button size="sm" variant="ai" type="submit" disabled={!newContent.trim() || createMemory.isPending}>
                  Save to Memory
                </Button>
              </div>
            </form>
          )}
        </div>

        {/* Memory Items List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
          {memoriesQuery.isLoading ? (
            <div className="py-8 text-center text-[13px] text-ink-dim">Loading memories...</div>
          ) : memories.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-ink-dim">
              <Brain size={32} className="mb-2 text-ink-faint opacity-60" />
              <p className="text-[14px] font-medium text-ink">No stored memories yet</p>
              <p className="mt-1 max-w-xs text-[12px] text-ink-faint">
                As you converse with IRIS, relevant facts, project details, and preferences are automatically remembered and stored here.
              </p>
            </div>
          ) : (
            memories.map((m) => (
              <div
                key={m.id}
                className="group flex items-start justify-between gap-3 border-b border-ops-line py-3 last:border-b-0"
              >
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium text-ink-faint">
                      {CATEGORY_LABEL[m.category] ?? m.category}
                    </span>
                    <span className="ml-auto text-[11px] text-ink-faint tnum">
                      {fmtTime(m.updated_at || m.created_at)}
                    </span>
                  </div>
                  <p className="text-[15px] text-ink leading-relaxed break-words">
                    {m.content}
                  </p>
                </div>

                <button
                  onClick={() => deleteMemory.mutate(m.id)}
                  disabled={deleteMemory.isPending}
                  title="Forget memory"
                  className="opacity-0 group-hover:opacity-100 p-1 rounded text-ink-faint hover:text-critical hover:bg-critical/10 transition-all cursor-pointer shrink-0"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
        </>
        )}
      </div>
    </div>
  );
}
