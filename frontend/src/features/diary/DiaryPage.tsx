import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  BookMarked,
  BookOpen,
  Bot,
  Check,
  Edit3,
  Eye,
  FileText,
  GraduationCap,
  Lightbulb,
  Pin,
  PinOff,
  Plus,
  Search,
  Sparkles,
  Tag,
  Trash2,
  Users,
  X,
} from "lucide-react";
import {
  useCreateDiaryEntry,
  useDeleteDiaryEntry,
  useDiaryEntries,
  useDiarySummary,
  useUpdateDiaryEntry,
} from "@/hooks/queries";
import { Markdown } from "@/components/ui/Markdown";
import { cn, fmtDateTime } from "@/lib/format";
import type { DiaryEntry } from "@/api/endpoints";

const CATEGORIES = [
  { id: "ALL", label: "All", icon: BookOpen, color: "text-ink" },
  { id: "IDEA", label: "Ideas", icon: Lightbulb, color: "text-amber-400" },
  { id: "NOTE", label: "Notes", icon: FileText, color: "text-sky-400" },
  { id: "REFLECTION", label: "Reflections", icon: Sparkles, color: "text-purple-400" },
  { id: "JOURNAL", label: "Journal", icon: BookMarked, color: "text-emerald-400" },
  { id: "MEETING", label: "Meetings", icon: Users, color: "text-blue-400" },
  { id: "LEARNING", label: "Learning", icon: GraduationCap, color: "text-rose-400" },
];

function getCategoryMeta(cat: string) {
  const match = CATEGORIES.find((c) => c.id === cat?.toUpperCase());
  return match ?? { id: cat, label: cat, icon: FileText, color: "text-sky-400" };
}

export function DiaryPage() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [activeCategory, setActiveCategory] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [previewMode, setPreviewMode] = useState(false);

  // Edit draft state
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [draftCategory, setDraftCategory] = useState("NOTE");
  const [draftTags, setDraftTags] = useState<string[]>([]);
  const [draftPinned, setDraftPinned] = useState(false);
  const [newTagInput, setNewTagInput] = useState("");
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const filters = useMemo(() => {
    return {
      category: activeCategory !== "ALL" ? activeCategory : undefined,
      search: searchQuery.trim() || undefined,
      tag: activeTag || undefined,
    };
  }, [activeCategory, searchQuery, activeTag]);

  const { data: entries = [], isLoading } = useDiaryEntries(filters);
  const { data: summary } = useDiarySummary();

  const createMutation = useCreateDiaryEntry();
  const updateMutation = useUpdateDiaryEntry();
  const deleteMutation = useDeleteDiaryEntry();

  // Active selected entry
  const selectedEntry = useMemo(
    () => entries.find((e) => e.id === selectedId) ?? null,
    [entries, selectedId],
  );

  // Sync draft when selectedEntry changes
  useEffect(() => {
    if (selectedEntry) {
      setDraftTitle(selectedEntry.title);
      setDraftContent(selectedEntry.content || "");
      setDraftCategory(selectedEntry.category || "NOTE");
      setDraftTags(selectedEntry.tags || []);
      setDraftPinned(selectedEntry.is_pinned);
      setSaveStatus("saved");
    }
  }, [selectedEntry?.id]);

  // If none selected, auto-select first note on desktop
  useEffect(() => {
    if (selectedId === null && entries.length > 0 && window.innerWidth >= 768) {
      setSelectedId(entries[0].id);
    }
  }, [entries, selectedId]);

  // Debounced auto-save function
  const triggerAutoSave = (updated: {
    title?: string;
    content?: string;
    category?: string;
    tags?: string[];
    is_pinned?: boolean;
  }) => {
    if (!selectedId) return;
    setSaveStatus("saving");

    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }

    saveTimerRef.current = setTimeout(async () => {
      try {
        await updateMutation.mutateAsync({
          id: selectedId,
          data: updated,
        });
        setSaveStatus("saved");
      } catch (err) {
        setSaveStatus("unsaved");
      }
    }, 600);
  };

  const handleTitleChange = (val: string) => {
    setDraftTitle(val);
    triggerAutoSave({
      title: val,
      content: draftContent,
      category: draftCategory,
      tags: draftTags,
      is_pinned: draftPinned,
    });
  };

  const handleContentChange = (val: string) => {
    setDraftContent(val);
    triggerAutoSave({
      title: draftTitle,
      content: val,
      category: draftCategory,
      tags: draftTags,
      is_pinned: draftPinned,
    });
  };

  const handleCategoryChange = (cat: string) => {
    setDraftCategory(cat);
    triggerAutoSave({
      title: draftTitle,
      content: draftContent,
      category: cat,
      tags: draftTags,
      is_pinned: draftPinned,
    });
  };

  const handleTogglePin = () => {
    const nextPin = !draftPinned;
    setDraftPinned(nextPin);
    triggerAutoSave({
      title: draftTitle,
      content: draftContent,
      category: draftCategory,
      tags: draftTags,
      is_pinned: nextPin,
    });
  };

  const handleAddTag = () => {
    const clean = newTagInput.trim().replace(/^#/, "").toLowerCase();
    if (clean && !draftTags.includes(clean)) {
      const nextTags = [...draftTags, clean];
      setDraftTags(nextTags);
      setNewTagInput("");
      triggerAutoSave({
        title: draftTitle,
        content: draftContent,
        category: draftCategory,
        tags: nextTags,
        is_pinned: draftPinned,
      });
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    const nextTags = draftTags.filter((t) => t !== tagToRemove);
    setDraftTags(nextTags);
    triggerAutoSave({
      title: draftTitle,
      content: draftContent,
      category: draftCategory,
      tags: nextTags,
      is_pinned: draftPinned,
    });
  };

  const handleCreateNew = async (presetCategory: string = "NOTE") => {
    const defaultTitle =
      presetCategory === "IDEA"
        ? "New Startup Idea"
        : presetCategory === "REFLECTION"
        ? "Evening Reflection"
        : "Untitled Note";

    const newEntry = await createMutation.mutateAsync({
      title: defaultTitle,
      content: "",
      category: presetCategory,
      tags: [],
      is_pinned: false,
    });

    setSelectedId(newEntry.id);
    setPreviewMode(false);
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    if (window.confirm("Are you sure you want to delete this diary entry?")) {
      await deleteMutation.mutateAsync(selectedId);
      setSelectedId(null);
    }
  };

  // Group entries: pinned vs others
  const pinnedEntries = entries.filter((e) => e.is_pinned);
  const otherEntries = entries.filter((e) => !e.is_pinned);

  return (
    <div className="flex h-full min-h-[calc(100dvh-5rem)] flex-col">
      {/* Header Bar */}
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-ops-line pb-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen className="text-ai" size={24} />
            <h1 className="text-[26px] font-bold tracking-tight text-ink">Diary & Notes</h1>
            <span className="rounded-full bg-ops-raised px-2.5 py-0.5 text-[12px] font-medium text-ink-dim">
              {entries.length} {entries.length === 1 ? "entry" : "entries"}
            </span>
          </div>
          <p className="mt-1 text-[13px] text-ink-faint">
            Personal notebook and idea journal. IRIS can read and write here anytime via chat or voice.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handleCreateNew("IDEA")}
            className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[13px] font-medium text-amber-400 transition-colors hover:bg-amber-500/20 cursor-pointer"
            title="Quickly capture a new idea"
          >
            <Lightbulb size={14} />
            <span>+ Idea</span>
          </button>
          <button
            onClick={() => handleCreateNew("NOTE")}
            className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[13px] font-medium text-ops-ground transition-opacity hover:opacity-90 cursor-pointer shadow-sm"
          >
            <Plus size={15} />
            <span>New Note</span>
          </button>
        </div>
      </header>

      {/* Category Pills & Search Bar */}
      <div className="mb-4 flex flex-col gap-2.5 md:flex-row md:items-center md:justify-between">
        {/* Category Scroll Filter */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 scrollbar-none">
          {CATEGORIES.map((cat) => {
            const Icon = cat.icon;
            const isActive = activeCategory === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-medium transition-colors cursor-pointer",
                  isActive
                    ? "bg-ops-raised text-ink border border-ops-line-bright font-semibold shadow-xs"
                    : "text-ink-dim hover:bg-ops-raised/60 hover:text-ink",
                )}
              >
                <Icon size={13} className={cat.color} />
                <span>{cat.label}</span>
              </button>
            );
          })}
        </div>

        {/* Search Input */}
        <div className="relative min-w-[200px] md:w-64">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
          <input
            type="text"
            placeholder="Search diary & ideas..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-ops-line bg-ops-panel pl-8 pr-7 py-1 text-[13px] text-ink placeholder:text-ink-faint focus:border-ops-line-bright focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink cursor-pointer"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Tags Filter Bar */}
      {summary?.all_tags && summary.all_tags.length > 0 && (
        <div className="mb-3 flex items-center gap-1.5 overflow-x-auto pb-1 text-[11px] scrollbar-none">
          <span className="text-ink-faint shrink-0">Tags:</span>
          {summary.all_tags.map((tag) => (
            <button
              key={tag}
              onClick={() => setActiveTag(activeTag === tag ? null : tag)}
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 transition-colors cursor-pointer",
                activeTag === tag
                  ? "bg-ai/15 text-ai border border-ai/30 font-semibold"
                  : "bg-ops-raised text-ink-dim hover:text-ink hover:bg-ops-raised/80",
              )}
            >
              #{tag}
            </button>
          ))}
          {activeTag && (
            <button
              onClick={() => setActiveTag(null)}
              className="text-[11px] text-ink-faint hover:text-ink underline ml-1 cursor-pointer"
            >
              Clear tag
            </button>
          )}
        </div>
      )}

      {/* Active Tag Filter Indicator */}
      {activeTag && (
        <div className="mb-3 flex items-center gap-2">
          <span className="text-[12px] text-ink-faint">Filtered by tag:</span>
          <span className="inline-flex items-center gap-1 rounded-full bg-ai/10 border border-ai/20 px-2.5 py-0.5 text-[12px] text-ai font-medium">
            #{activeTag}
            <button onClick={() => setActiveTag(null)} className="hover:text-ink cursor-pointer">
              <X size={12} />
            </button>
          </span>
        </div>
      )}

      {/* Main Two-Column Notes App Layout */}
      <div className="grid flex-1 grid-cols-1 gap-4 md:grid-cols-12 min-h-0">
        {/* Left Pane: Notes List (Hidden on mobile if a note is selected) */}
        <div
          className={cn(
            "flex flex-col rounded-xl border border-ops-line bg-ops-panel/60 p-2 md:col-span-5 lg:col-span-4",
            selectedId !== null ? "hidden md:flex" : "flex",
          )}
        >
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {isLoading ? (
              <div className="p-6 text-center text-[13px] text-ink-faint">Loading diary notes...</div>
            ) : entries.length === 0 ? (
              <div className="p-8 text-center">
                <BookOpen className="mx-auto mb-2 text-ink-faint opacity-40" size={32} />
                <p className="text-[14px] font-medium text-ink">No notes found</p>
                <p className="mt-1 text-[12px] text-ink-faint">
                  {searchQuery || activeCategory !== "ALL" || activeTag
                    ? "Try clearing filters to see more entries."
                    : "Tap '+ Idea' or '+ Note' above to write your first entry."}
                </p>
              </div>
            ) : (
              <>
                {/* Pinned section */}
                {pinnedEntries.length > 0 && (
                  <div className="space-y-1.5 pb-2 border-b border-ops-line/60">
                    <p className="px-2 text-[10px] font-bold uppercase tracking-wider text-ink-faint">
                      Pinned
                    </p>
                    {pinnedEntries.map((entry) => (
                      <NoteCard
                        key={entry.id}
                        entry={entry}
                        isSelected={entry.id === selectedId}
                        onSelect={() => setSelectedId(entry.id)}
                        onTagClick={(tag) => setActiveTag(tag)}
                      />
                    ))}
                  </div>
                )}

                {/* Other entries */}
                <div className="space-y-1.5 pt-1">
                  {pinnedEntries.length > 0 && otherEntries.length > 0 && (
                    <p className="px-2 text-[10px] font-bold uppercase tracking-wider text-ink-faint">
                      Notes
                    </p>
                  )}
                  {otherEntries.map((entry) => (
                    <NoteCard
                      key={entry.id}
                      entry={entry}
                      isSelected={entry.id === selectedId}
                      onSelect={() => setSelectedId(entry.id)}
                      onTagClick={(tag) => setActiveTag(tag)}
                    />
                  ))}
                </div>
              </>
            )}
          </div>

          {/* AI Banner at bottom of list */}
          <div className="mt-2 rounded-lg border border-ai/20 bg-ai/5 p-2.5 text-[11px] text-ink-dim">
            <div className="flex items-center gap-1.5 font-semibold text-ai">
              <Bot size={13} />
              <span>IRIS Continuous Sync</span>
            </div>
            <p className="mt-0.5 text-ink-faint leading-relaxed">
              Say &ldquo;Write this idea in my diary&rdquo; or &ldquo;Show my recent thoughts&rdquo; anytime in chat or voice.
            </p>
          </div>
        </div>

        {/* Right Pane: Note Editor & Reader (Hidden on mobile if no note is selected) */}
        <div
          className={cn(
            "flex flex-col rounded-xl border border-ops-line bg-ops-panel p-4 md:col-span-7 lg:col-span-8 min-h-[460px]",
            selectedId === null ? "hidden md:flex md:items-center md:justify-center" : "flex",
          )}
        >
          {selectedEntry ? (
            <div className="flex flex-1 flex-col">
              {/* Note Action Toolbar */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ops-line/70 pb-3">
                <div className="flex items-center gap-2">
                  {/* Mobile Back Button */}
                  <button
                    onClick={() => setSelectedId(null)}
                    className="flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-medium text-ink-dim hover:bg-ops-raised hover:text-ink md:hidden cursor-pointer"
                  >
                    <ArrowLeft size={14} />
                    <span>Back</span>
                  </button>

                  {/* Category Picker */}
                  <select
                    value={draftCategory}
                    onChange={(e) => handleCategoryChange(e.target.value)}
                    aria-label="Note category"
                    className="rounded-md border border-ops-line bg-ops-ground px-2.5 py-1 text-[12px] font-semibold text-ink focus:border-ops-line-bright focus:outline-none cursor-pointer"
                  >
                    <option value="NOTE">📝 Note</option>
                    <option value="IDEA">💡 Idea</option>
                    <option value="REFLECTION">💭 Reflection</option>
                    <option value="JOURNAL">📖 Journal</option>
                    <option value="MEETING">🤝 Meeting</option>
                    <option value="LEARNING">🧠 Learning</option>
                  </select>

                  {/* Pin Toggle */}
                  <button
                    onClick={handleTogglePin}
                    className={cn(
                      "flex items-center gap-1 rounded-md px-2 py-1 text-[12px] transition-colors cursor-pointer",
                      draftPinned
                        ? "bg-amber-500/15 text-amber-400 font-medium"
                        : "text-ink-faint hover:bg-ops-raised hover:text-ink",
                    )}
                    title={draftPinned ? "Unpin note" : "Pin note to top"}
                  >
                    {draftPinned ? <Pin size={13} className="fill-amber-400" /> : <PinOff size={13} />}
                    <span>{draftPinned ? "Pinned" : "Pin"}</span>
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  {/* Save Status Indicator */}
                  <span className="text-[11px] text-ink-faint flex items-center gap-1">
                    {saveStatus === "saving" ? (
                      <>
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
                        Saving...
                      </>
                    ) : saveStatus === "saved" ? (
                      <>
                        <Check size={12} className="text-emerald-400" />
                        Saved
                      </>
                    ) : (
                      <span className="text-rose-400">Unsaved</span>
                    )}
                  </span>

                  {/* Preview / Edit Toggle */}
                  <button
                    onClick={() => setPreviewMode(!previewMode)}
                    className={cn(
                      "flex items-center gap-1 rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors cursor-pointer",
                      previewMode
                        ? "bg-ops-raised text-ink border border-ops-line-bright"
                        : "text-ink-dim hover:bg-ops-raised hover:text-ink",
                    )}
                    title={previewMode ? "Switch to edit mode" : "Switch to markdown preview"}
                  >
                    {previewMode ? <Edit3 size={13} /> : <Eye size={13} />}
                    <span>{previewMode ? "Edit" : "Preview"}</span>
                  </button>

                  {/* Delete Button */}
                  <button
                    onClick={handleDelete}
                    className="rounded-md p-1.5 text-ink-faint hover:bg-rose-500/10 hover:text-rose-400 transition-colors cursor-pointer"
                    title="Delete note"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {/* Title Input */}
              <div className="pt-3 pb-2">
                <input
                  type="text"
                  value={draftTitle}
                  onChange={(e) => handleTitleChange(e.target.value)}
                  placeholder="Note title or idea headline..."
                  className="w-full bg-transparent text-[22px] font-bold text-ink placeholder:text-ink-faint focus:outline-none"
                />
              </div>

              {/* Tags & Timestamp Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ops-line/40 pb-3 pt-1 text-[12px]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Tag size={12} className="text-ink-faint" />
                  {draftTags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 rounded-full bg-ops-raised border border-ops-line px-2 py-0.5 text-[11px] text-ink-dim"
                    >
                      #{tag}
                      <button
                        onClick={() => handleRemoveTag(tag)}
                        className="hover:text-ink cursor-pointer"
                      >
                        <X size={10} />
                      </button>
                    </span>
                  ))}
                  <div className="flex items-center">
                    <input
                      type="text"
                      placeholder="+ tag"
                      value={newTagInput}
                      onChange={(e) => setNewTagInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddTag();
                        }
                      }}
                      className="w-16 rounded bg-transparent px-1 text-[11px] text-ink placeholder:text-ink-faint focus:bg-ops-ground focus:outline-none"
                    />
                  </div>
                </div>

                <div className="text-[11px] text-ink-faint">
                  Updated {fmtDateTime(selectedEntry.updated_at)}
                </div>
              </div>

              {/* Note Body: Markdown Preview OR Textarea */}
              <div className="flex-1 pt-4 pb-2">
                {previewMode ? (
                  <div className="prose prose-invert max-w-none text-ink text-[14px] leading-relaxed">
                    {draftContent.trim() ? (
                      <Markdown text={draftContent} />
                    ) : (
                      <p className="italic text-ink-faint">This note is currently empty.</p>
                    )}
                  </div>
                ) : (
                  <textarea
                    value={draftContent}
                    onChange={(e) => handleContentChange(e.target.value)}
                    placeholder="Write your note, startup idea, meeting notes, or personal thoughts here... Markdown is supported (e.g. ## Headings, - Lists, `code`)."
                    className="h-full min-h-[340px] w-full resize-none bg-transparent font-sans text-[14px] leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none"
                  />
                )}
              </div>

              {/* Footer info */}
              <div className="mt-auto flex items-center justify-between border-t border-ops-line/40 pt-2 text-[11px] text-ink-faint">
                <span>
                  {draftContent.trim() ? draftContent.trim().split(/\s+/).length : 0} words ·{" "}
                  {draftContent.length} characters
                </span>
                <span>Category: {draftCategory}</span>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center p-12 text-center">
              <div className="rounded-full bg-ops-raised p-4 text-ink-dim">
                <BookOpen size={36} />
              </div>
              <h2 className="mt-4 text-[18px] font-semibold text-ink">Select a Note</h2>
              <p className="mt-1 max-w-xs text-[13px] text-ink-faint">
                Choose a note from the left to read or edit, or capture a new idea.
              </p>
              <div className="mt-5 flex gap-2">
                <button
                  onClick={() => handleCreateNew("IDEA")}
                  className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[13px] font-medium text-amber-400 hover:bg-amber-500/20 cursor-pointer"
                >
                  <Lightbulb size={14} />
                  <span>New Idea</span>
                </button>
                <button
                  onClick={() => handleCreateNew("NOTE")}
                  className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[13px] font-medium text-ops-ground hover:opacity-90 cursor-pointer"
                >
                  <Plus size={14} />
                  <span>New Note</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface NoteCardProps {
  entry: DiaryEntry;
  isSelected: boolean;
  onSelect: () => void;
  onTagClick: (tag: string) => void;
}

function NoteCard({ entry, isSelected, onSelect, onTagClick }: NoteCardProps) {
  const meta = getCategoryMeta(entry.category);
  const Icon = meta.icon;

  return (
    <div
      onClick={onSelect}
      className={cn(
        "group relative flex flex-col rounded-lg p-3 transition-colors cursor-pointer select-none",
        isSelected
          ? "bg-ops-raised border border-ops-line-bright shadow-xs"
          : "border border-transparent hover:bg-ops-raised/50 hover:border-ops-line/60",
      )}
    >
      <div className="flex items-center justify-between gap-1 mb-1">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
            entry.category === "IDEA"
              ? "bg-amber-500/15 text-amber-400"
              : entry.category === "REFLECTION"
              ? "bg-purple-500/15 text-purple-400"
              : entry.category === "JOURNAL"
              ? "bg-emerald-500/15 text-emerald-400"
              : entry.category === "MEETING"
              ? "bg-blue-500/15 text-blue-400"
              : entry.category === "LEARNING"
              ? "bg-rose-500/15 text-rose-400"
              : "bg-sky-500/15 text-sky-400",
          )}
        >
          <Icon size={10} />
          <span>{entry.category || "NOTE"}</span>
        </span>

        <div className="flex items-center gap-1">
          {entry.is_pinned && <Pin size={11} className="text-amber-400 fill-amber-400" />}
          <span className="text-[10px] text-ink-faint">{fmtDateTime(entry.updated_at)}</span>
        </div>
      </div>

      <h3 className="line-clamp-1 text-[13px] font-semibold text-ink group-hover:text-ink">
        {entry.title || "Untitled Note"}
      </h3>

      <p className="mt-1 line-clamp-2 text-[12px] text-ink-dim leading-relaxed">
        {entry.content?.trim() || <span className="italic text-ink-faint">No additional text</span>}
      </p>

      {entry.tags && entry.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {entry.tags.map((t) => (
            <button
              key={t}
              onClick={(e) => {
                e.stopPropagation();
                onTagClick(t);
              }}
              className="rounded bg-ops-ground px-1.5 py-0.2 text-[10px] text-ink-faint hover:text-ai cursor-pointer"
            >
              #{t}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
