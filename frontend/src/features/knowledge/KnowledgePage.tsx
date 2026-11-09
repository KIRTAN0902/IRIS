import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Archive,
  BrainCircuit,
  Database,
  FileText,
  GitBranch,
  History as HistoryIcon,
  Library,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Overlay";
import { Lamp, Panel } from "@/components/ui/Panel";
import { Markdown } from "@/components/ui/Markdown";
import { cn } from "@/lib/format";
import {
  useArchiveKnowledgeNote,
  useCaptureKnowledge,
  useConsolidateKnowledge,
  useCreateKnowledgeClaim,
  useCreateKnowledgeNode,
  useCreateKnowledgeNote,
  useDeleteKnowledgeNote,
  useDrainKnowledgeJobs,
  useGrantKnowledgePermission,
  useKnowledgeClaims,
  useKnowledgeGraph,
  useKnowledgeHealth,
  useKnowledgeHistory,
  useKnowledgeInsights,
  useKnowledgeJobs,
  useKnowledgeNodes,
  useKnowledgeNote,
  useKnowledgeNotes,
  useKnowledgeOverview,
  useKnowledgePermissions,
  useRebuildKnowledgeIndex,
  useReconcileKnowledgeVault,
  useRestoreKnowledgeNote,
  useSearchKnowledge,
  useUpdateKnowledgeNote,
} from "@/hooks/queries";
import type {
  KnowledgeClaim,
  KnowledgeNode,
  KnowledgeNote,
  KnowledgeSearchResult,
  KnowledgeVersion,
} from "@/types/api";

type Tab = "overview" | "vault" | "graph" | "insights" | "history";

const TABS: { id: Tab; label: string; icon: typeof Library }[] = [
  { id: "overview", label: "Overview", icon: Library },
  { id: "vault", label: "Vault", icon: FileText },
  { id: "graph", label: "Graph", icon: GitBranch },
  { id: "insights", label: "Insights", icon: Sparkles },
  { id: "history", label: "History", icon: HistoryIcon },
];

const CATEGORY_LABELS: Record<string, string> = {
  personal: "Personal",
  projects: "Projects",
  goals: "Goals",
  work: "Work",
  learning: "Learning",
  decisions: "Decisions",
  experiences: "Experiences",
  insights: "Insights",
  daily: "Daily",
  financial: "Financial",
  general: "General",
};

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

function fmtDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function Stat({
  label,
  value,
  hint,
  tone = "dim",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "go" | "caution" | "ai" | "dim";
}) {
  return (
    <div className="rounded-2xl border border-ops-line bg-ops-panel p-4 shadow-xs">
      <div className="flex items-center gap-2">
        <Lamp tone={tone} />
        <p className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">{label}</p>
      </div>
      <p className="mt-1.5 tnum text-2xl font-bold leading-none text-ink">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

function ClaimRow({ claim }: { claim: KnowledgeClaim }) {
  return (
    <article className="border-b border-ops-line/70 py-2 last:border-b-0">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded bg-ops-raised px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ai">
          {claim.claim_type}
        </span>
        <span className="text-[11px] text-ink-faint">{claim.node_name ?? "Unlinked"}</span>
        <span className="text-[11px] text-ink-faint">· {claim.verification_status.replaceAll("_", " ")}</span>
        {claim.valid_until && (
          <span className="rounded bg-caution-dim px-1.5 py-0.5 text-[10px] text-caution">historical</span>
        )}
      </div>
      <p className="mt-1 text-[13px] leading-snug text-ink">{claim.claim_text}</p>
      <p className="mt-1 text-[11px] text-ink-faint">
        {claim.category} · confidence {Math.round(claim.confidence * 100)}% · {fmtDate(claim.recorded_at)}
      </p>
    </article>
  );
}

function SearchResults({ results }: { results: KnowledgeSearchResult[] }) {
  if (results.length === 0) return <EmptyState message="No authorised matches." />;
  return (
    <div className="space-y-1">
      {results.map((result) => (
        <div key={result.claim_id} className="rounded-md border border-ops-line px-2.5 py-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium text-ink">{result.node_name}</span>
            <span className="rounded bg-ops-raised px-1.5 py-0.5 text-[10px] uppercase text-ai">
              {result.claim_type}
            </span>
            <span className="text-[10px] text-ink-faint">{result.signals.join(" · ")}</span>
            <span className="ml-auto tnum text-[10px] text-ink-faint">{result.score.toFixed(2)}</span>
          </div>
          <p className="mt-1 text-[13px] leading-snug text-ink-dim">{result.claim_text}</p>
          <p className="mt-1 text-[11px] text-ink-faint">
            {result.verification_status.replaceAll("_", " ")} · {result.sensitivity}
            {result.source ? ` · ${result.source}` : ""}
          </p>
        </div>
      ))}
    </div>
  );
}

function OverviewTab() {
  const overview = useKnowledgeOverview();
  const health = useKnowledgeHealth();
  const capture = useCaptureKnowledge();
  const search = useSearchKnowledge();
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  function onCapture() {
    const value = text.trim();
    if (!value) return;
    capture.mutate(
      { text: value, source_type: "user_provided", process_now: true },
      {
        onSuccess: () => {
          setText("");
          setNotice("Captured quietly. Extraction and vault sync are queued.");
        },
        onError: (error) => setNotice(errorText(error)),
      },
    );
  }

  if (overview.isLoading) return <Skeleton className="h-72" />;
  if (overview.isError) return <ErrorState message={errorText(overview.error)} />;
  const data = overview.data;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Stat label="Knowledge nodes" value={data?.totals.nodes ?? 0} tone="ai" />
        <Stat label="Active claims" value={data?.totals.claims ?? 0} tone="go" />
        <Stat
          label="Embedding coverage"
          value={`${Math.round((health.data?.embedding_coverage ?? 0) * 100)}%`}
          hint="selective, queued"
          tone="caution"
        />
        <Stat
          label="Queued jobs"
          value={health.data?.queued_jobs ?? 0}
          hint={health.data?.state ?? "checking"}
          tone={(health.data?.queued_jobs ?? 0) > 0 ? "caution" : "dim"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Capture knowledge" lamp={<Lamp tone="ai" pulse />}>
          <p className="mb-2 text-[12px] leading-snug text-ink-faint">
            Automatic, silent capture. Nothing is published to a model until permissions and
            sensitivity are checked.
          </p>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={5}
            placeholder="A decision, fact, observation or note worth remembering…"
            className="w-full resize-y rounded-md border border-ops-line bg-ops-void px-3 py-2 text-[13px] text-ink outline-none focus:border-ai"
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button variant="solid" onClick={onCapture} disabled={capture.isPending || !text.trim()}>
              <Upload size={14} /> {capture.isPending ? "Capturing…" : "Capture"}
            </Button>
            <span className="text-[11px] text-ink-faint">No approval modal. Routine capture stays silent.</span>
          </div>
          {notice && <p className="mt-2 text-[12px] text-ai">{notice}</p>}
        </Panel>

        <Panel title="Hybrid search" lamp={<Lamp tone="go" />}>
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (query.trim()) search.mutate({ query: query.trim(), limit: 10 });
            }}
          >
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search exact, lexical, semantic, graph or temporal memory…"
              className="min-w-0 flex-1 rounded-md border border-ops-line bg-ops-void px-3 py-2 text-[13px] text-ink outline-none focus:border-ai"
            />
            <Button type="submit" variant="outline" disabled={search.isPending || !query.trim()}>
              <Search size={14} /> Search
            </Button>
          </form>
          <div className="mt-2 max-h-[320px] overflow-y-auto">
            {search.isPending && <Skeleton className="h-24" />}
            {search.isError && <ErrorState message={errorText(search.error)} />}
            {search.data && <SearchResults results={search.data.results} />}
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Recent claims" className="lg:col-span-2">
          {data?.recent_claims.length ? (
            <div>{data.recent_claims.map((claim) => <ClaimRow key={claim.id} claim={claim} />)}</div>
          ) : (
            <EmptyState message="No claims yet." hint="Capture a decision or let IRIS learn from conversations." />
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="Recent nodes">
            {data?.recent_nodes.length ? (
              <ul className="space-y-1.5">
                {data.recent_nodes.map((node) => (
                  <li key={node.id} className="flex items-center gap-2 text-[12px]">
                    <Database size={13} className="text-ai" />
                    <span className="min-w-0 flex-1 truncate text-ink">{node.canonical_name}</span>
                    <span className="text-[10px] uppercase text-ink-faint">{node.node_type}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message="No nodes yet." />
            )}
          </Panel>

          <Panel title="Categories">
            {data?.categories.length ? (
              <div className="flex flex-wrap gap-1.5">
                {data.categories.map((category) => (
                  <span
                    key={category.key}
                    className="rounded-full border border-ops-line bg-ops-raised px-2 py-0.5 text-[11px] text-ink-dim"
                  >
                    {CATEGORY_LABELS[category.key] ?? category.label}
                  </span>
                ))}
              </div>
            ) : (
              <EmptyState message="Nothing categorised yet." />
            )}
          </Panel>
        </div>
      </div>

      {data?.reviews.length ? (
        <Panel title="Needs a human look" lamp={<Lamp tone="caution" />}>
          <ul className="space-y-1.5">
            {data.reviews.map((review) => (
              <li key={review.id} className="text-[12px] text-ink-dim">
                <span className="text-caution">{review.review_type.replaceAll("_", " ")}</span> ·{" "}
                {review.reason ?? "Review requested"} <span className="text-ink-faint">({fmtDate(review.created_at)})</span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}

function NoteEditor({ note, onClose }: { note: KnowledgeNote; onClose: () => void }) {
  const detail = useKnowledgeNote(note.id);
  const update = useUpdateKnowledgeNote();
  const archive = useArchiveKnowledgeNote();
  const restore = useRestoreKnowledgeNote();
  const remove = useDeleteKnowledgeNote();
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (detail.data) setDraft(detail.data.content);
  }, [detail.data]);

  function save() {
    if (!detail.data) return;
    update.mutate(
      { id: note.id, data: { content: draft, expected_hash: detail.data.content_hash } },
      {
        onSuccess: () => {
          setMessage("Saved to PostgreSQL and the Markdown vault.");
          detail.refetch();
        },
        onError: (error) => setMessage(errorText(error)),
      },
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold text-ink">{note.title}</p>
          <p className="text-[11px] text-ink-faint">
            {note.storage_path} · {note.sync_status} · v{note.db_version}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>

      {detail.isLoading && <Skeleton className="h-40" />}
      {detail.isError && <ErrorState message={errorText(detail.error)} />}
      {detail.data && (
        <>
          {detail.data.missing && (
            <p className="rounded bg-caution-dim px-2 py-1 text-[12px] text-caution">
              The Markdown file is missing; PostgreSQL is authoritative and will restore it on the next sync.
            </p>
          )}
          <div className="grid gap-3 lg:grid-cols-2">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={16}
              spellCheck={false}
              className="w-full resize-y rounded-md border border-ops-line bg-ops-void px-3 py-2 font-[family-name:var(--font-mono)] text-[12px] leading-relaxed text-ink outline-none focus:border-ai"
            />
            <div className="max-h-[420px] overflow-y-auto rounded-md border border-ops-line bg-ops-raised/30 px-3 py-2">
              <Markdown text={draft} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="solid" onClick={save} disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save note"}
            </Button>
            {note.archived_at ? (
              <Button
                variant="outline"
                onClick={() => restore.mutate(note.id, { onSuccess: onClose })}
              >
                <RefreshCw size={14} /> Restore
              </Button>
            ) : (
              <Button variant="ghost" onClick={() => archive.mutate(note.id, { onSuccess: onClose })}>
                <Archive size={14} /> Archive
              </Button>
            )}
            <Button
              variant="danger"
              onClick={() => remove.mutate(note.id, { onSuccess: onClose })}
            >
              <Trash2 size={14} /> Delete
            </Button>
            <span className="text-[11px] text-ink-faint">
              External edits produce a conflict copy; your Notes section is preserved.
            </span>
          </div>
          {message && <p className="text-[12px] text-ai">{message}</p>}
        </>
      )}
    </div>
  );
}

function VaultTab() {
  const notes = useKnowledgeNotes({ limit: 100 });
  const create = useCreateKnowledgeNote();
  const reconcile = useReconcileKnowledgeVault();
  const rebuild = useRebuildKnowledgeIndex();
  const [selected, setSelected] = useState<KnowledgeNote | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("general");
  const [message, setMessage] = useState<string | null>(null);

  function onCreate() {
    if (!title.trim()) return;
    create.mutate(
      { title: title.trim(), content, category },
      {
        onSuccess: () => {
          setTitle("");
          setContent("");
          setMessage("Note created in the vault.");
        },
        onError: (error) => setMessage(errorText(error)),
      },
    );
  }

  function maintenance(action: "reconcile" | "rebuild") {
    const mutation = action === "reconcile" ? reconcile : rebuild;
    mutation.mutate(undefined, {
      onSuccess: () => setMessage(action === "reconcile" ? "Vault reconciled." : "Index rebuilt."),
      onError: (error) => setMessage(errorText(error)),
    });
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div className="space-y-4">
        <Panel
          title="Vault notes"
          actions={
            <div className="flex gap-1">
              <Button variant="ghost" size="sm" onClick={() => maintenance("reconcile")}>
                <RefreshCw size={13} /> Reconcile
              </Button>
              <Button variant="ghost" size="sm" onClick={() => maintenance("rebuild")}>
                <Activity size={13} /> Index
              </Button>
            </div>
          }
        >
          {notes.isLoading && <Skeleton className="h-40" />}
          {notes.isError && <ErrorState message={errorText(notes.error)} />}
          {notes.data?.length ? (
            <ul className="max-h-[520px] space-y-1 overflow-y-auto">
              {notes.data.map((note) => (
                <li key={note.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(note)}
                    className={cn(
                      "w-full rounded-md border px-2.5 py-2 text-left transition-colors",
                      selected?.id === note.id
                        ? "border-ai/50 bg-ai-dim"
                        : "border-transparent hover:border-ops-line hover:bg-ops-raised",
                    )}
                  >
                    <span className="block truncate text-[13px] font-medium text-ink">{note.title}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-ink-faint">
                      {note.note_type} · {note.sync_status} · {note.sensitivity}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="No vault notes yet." hint="Knowledge notes are written automatically as IRIS learns." />
          )}
        </Panel>

        <Panel title="New note" lamp={<Lamp tone="ai" />}>
          <div className="space-y-2">
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Title"
              className="w-full rounded-md border border-ops-line bg-ops-void px-3 py-2 text-[13px] text-ink outline-none focus:border-ai"
            />
            <div className="flex gap-2">
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                className="rounded-md border border-ops-line bg-ops-void px-2 py-2 text-[12px] text-ink outline-none focus:border-ai"
              >
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <Button variant="solid" onClick={onCreate} disabled={create.isPending || !title.trim()}>
                {create.isPending ? "Creating…" : "Create note"}
              </Button>
            </div>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={5}
              placeholder="Markdown content (optional)"
              className="w-full resize-y rounded-md border border-ops-line bg-ops-void px-3 py-2 font-[family-name:var(--font-mono)] text-[12px] text-ink outline-none focus:border-ai"
            />
            {message && <p className="text-[12px] text-ai">{message}</p>}
          </div>
        </Panel>
      </div>

      <Panel
        title={selected ? "Read / edit note" : "Vault"}
        lamp={<Lamp tone={selected ? "go" : "dim"} />}
      >
        {selected ? (
          <NoteEditor note={selected} onClose={() => setSelected(null)} />
        ) : (
          <EmptyState
            message="Select a note to read or edit."
            hint="The vault is Obsidian-compatible; PostgreSQL stays authoritative."
          />
        )}
      </Panel>
    </div>
  );
}

function GraphCanvas({
  nodes,
  edges,
}: {
  nodes: KnowledgeNode[];
  edges: { id: string; source_node_id: string; target_node_id: string; relationship_type: string }[];
}) {
  const layout = useMemo(() => {
    const width = 640;
    const height = 360;
    const radius = Math.min(width, height) / 2 - 56;
    const positions = new Map<string, { x: number; y: number }>();
    nodes.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, nodes.length) - Math.PI / 2;
      positions.set(node.id, {
        x: width / 2 + Math.cos(angle) * radius,
        y: height / 2 + Math.sin(angle) * radius,
      });
    });
    return { width, height, positions };
  }, [nodes]);

  if (nodes.length === 0) return null;

  return (
    <svg viewBox={`0 0 ${layout.width} ${layout.height}`} className="h-auto w-full" role="img" aria-label="Knowledge graph">
      {edges.map((edge) => {
        const source = layout.positions.get(edge.source_node_id);
        const target = layout.positions.get(edge.target_node_id);
        if (!source || !target) return null;
        return (
          <g key={edge.id}>
            <line
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke="var(--color-ops-line-bright)"
              strokeWidth={1}
            />
            <text
              x={(source.x + target.x) / 2}
              y={(source.y + target.y) / 2 - 3}
              fill="var(--color-ink-faint)"
              fontSize={8}
              textAnchor="middle"
            >
              {edge.relationship_type}
            </text>
          </g>
        );
      })}
      {nodes.map((node) => {
        const position = layout.positions.get(node.id);
        if (!position) return null;
        return (
          <g key={node.id}>
            <circle
              cx={position.x}
              cy={position.y}
              r={node.node_type === "project" ? 12 : 8}
              fill={node.node_type === "project" ? "var(--color-ai)" : "var(--color-go)"}
              opacity={0.85}
            />
            <text
              x={position.x}
              y={position.y + 22}
              fill="var(--color-ink)"
              fontSize={10}
              textAnchor="middle"
            >
              {node.canonical_name.length > 22 ? `${node.canonical_name.slice(0, 21)}…` : node.canonical_name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function GraphTab() {
  const [query, setQuery] = useState("");
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [depth, setDepth] = useState(1);
  const nodes = useKnowledgeNodes({ query: query || undefined, limit: 80 });
  const graph = useKnowledgeGraph(nodeId, depth, 60);

  useEffect(() => {
    if (!nodeId && nodes.data && nodes.data.length > 0) {
      setNodeId(nodes.data[0].id);
    }
  }, [nodeId, nodes.data]);

  const selectedNode = graph.data?.nodes.find((node) => node.id === nodeId) ?? null;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
      <Panel title="Nodes">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter nodes…"
          className="mb-2 w-full rounded-md border border-ops-line bg-ops-void px-3 py-2 text-[13px] text-ink outline-none focus:border-ai"
        />
        {nodes.isLoading && <Skeleton className="h-48" />}
        {nodes.isError && <ErrorState message={errorText(nodes.error)} />}
        <ul className="max-h-[520px] space-y-1 overflow-y-auto">
          {nodes.data?.map((node) => (
            <li key={node.id}>
              <button
                type="button"
                onClick={() => setNodeId(node.id)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left transition-colors",
                  nodeId === node.id ? "bg-ai-dim text-ink" : "text-ink-dim hover:bg-ops-raised",
                )}
              >
                <GitBranch size={13} className="shrink-0 text-ai" />
                <span className="min-w-0 flex-1 truncate text-[12px]">{node.canonical_name}</span>
                <span className="text-[10px] uppercase text-ink-faint">{node.node_type}</span>
              </button>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel
        title={selectedNode ? selectedNode.canonical_name : "Knowledge graph"}
        lamp={<Lamp tone={nodeId ? "ai" : "dim"} />}
        actions={
          nodeId ? (
            <div className="flex items-center gap-1">
              {[1, 2, 3].map((value) => (
                <Button
                  key={value}
                  size="sm"
                  variant={depth === value ? "ai" : "ghost"}
                  onClick={() => setDepth(value)}
                >
                  {value}
                </Button>
              ))}
            </div>
          ) : null
        }
      >
        {!nodeId && <EmptyState message="Select a node to traverse the graph." />}
        {graph.isLoading && <Skeleton className="h-64" />}
        {graph.isError && <ErrorState message={errorText(graph.error)} />}
        {graph.data && (
          <div className="space-y-3">
            <GraphCanvas nodes={graph.data.nodes} edges={graph.data.relationships} />
            {graph.data.truncated && (
              <p className="rounded bg-caution-dim px-2 py-1 text-[11px] text-caution">
                Traversal was bounded. Narrow the depth or choose a closer node.
              </p>
            )}
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wide text-ink-faint">
                  Nodes ({graph.data.nodes.length})
                </p>
                <ul className="space-y-1">
                  {graph.data.nodes.map((node) => (
                    <li key={node.id} className="text-[12px] text-ink-dim">
                      {node.canonical_name} <span className="text-ink-faint">· {node.node_type}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wide text-ink-faint">
                  Relationships ({graph.data.relationships.length})
                </p>
                <ul className="space-y-1">
                  {graph.data.relationships.map((edge) => (
                    <li key={edge.id} className="text-[12px] text-ink-dim">
                      {graph.data.nodes.find((n) => n.id === edge.source_node_id)?.canonical_name ?? "?"} →{" "}
                      {graph.data.nodes.find((n) => n.id === edge.target_node_id)?.canonical_name ?? "?"}{" "}
                      <span className="text-ai">{edge.relationship_type}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

function InsightsTab() {
  const insights = useKnowledgeInsights();
  const permissions = useKnowledgePermissions();
  const grant = useGrantKnowledgePermission();
  const nodes = useKnowledgeNodes({ limit: 80 });
  const jobs = useKnowledgeJobs();
  const drain = useDrainKnowledgeJobs();
  const consolidate = useConsolidateKnowledge();
  const [message, setMessage] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <Stat label="Inferences" value={insights.data?.counts.inferences ?? 0} tone="ai" />
        <Stat label="Understanding" value={insights.data?.counts.understanding ?? 0} tone="go" />
        <Stat label="Open reviews" value={insights.data?.counts.open_reviews ?? 0} tone="caution" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Insights and inferences" lamp={<Lamp tone="ai" />}>
          {insights.isLoading && <Skeleton className="h-40" />}
          {insights.isError && <ErrorState message={errorText(insights.error)} />}
          {insights.data?.insights.length ? (
            <div>{insights.data.insights.map((claim) => <ClaimRow key={claim.id} claim={claim} />)}</div>
          ) : (
            <EmptyState message="No insights yet." hint="Understanding appears after enough verified observations." />
          )}
        </Panel>

        <Panel title="Reviews" lamp={<Lamp tone="caution" />}>
          {insights.data?.reviews.length ? (
            <ul className="space-y-1.5">
              {insights.data.reviews.map((review) => (
                <li key={review.id} className="rounded-md border border-ops-line px-2.5 py-2 text-[12px]">
                  <p className="text-caution">{review.review_type.replaceAll("_", " ")}</p>
                  <p className="text-ink-dim">{review.reason ?? "Review requested"}</p>
                  <p className="text-[10px] text-ink-faint">{fmtDate(review.created_at)}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="Nothing disputed." hint="Contradictions and ambiguity are surfaced here." />
          )}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Permissions" lamp={<Lamp tone="go" />}>
          <p className="mb-2 text-[12px] leading-snug text-ink-faint">
            Grants override default node-type policy for a named item. The service checks the acting
            principal before any content reaches a model.
          </p>
          <div className="max-h-[220px] space-y-1 overflow-y-auto">
            {permissions.data?.length ? (
              permissions.data.map((permission) => (
                <div key={permission.id} className="flex flex-wrap items-center gap-1.5 border-b border-ops-line/60 py-1.5 text-[11px]">
                  <ShieldCheck size={13} className="text-go" />
                  <span className="text-ink">{permission.principal_type}:{permission.principal_id}</span>
                  <span className="text-ink-faint">{permission.knowledge_type}</span>
                  <span className="rounded bg-ops-raised px-1.5 py-0.5 text-ink-dim">{permission.access_level}</span>
                  <span className="ml-auto text-ink-faint">
                    {permission.can_read ? "read" : ""}{permission.can_write ? " write" : ""}
                  </span>
                </div>
              ))
            ) : (
              <EmptyState message="No explicit grants." hint="Named knowledge is private by default." />
            )}
          </div>
          <form
            className="mt-2 flex flex-wrap gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              const nodeId = String(form.get("node") ?? "");
              grant.mutate(
                {
                  principal_type: "coworker",
                  principal_id: String(form.get("principal") ?? "developer"),
                  access_level: "personal",
                  knowledge_type: "node",
                  knowledge_id: nodeId,
                },
                {
                  onSuccess: () => {
                    setMessage("Permission granted.");
                    event.currentTarget.reset();
                  },
                  onError: (error) => setMessage(errorText(error)),
                },
              );
            }}
          >
            <input
              name="principal"
              defaultValue="developer"
              aria-label="Principal"
              className="w-28 rounded-md border border-ops-line bg-ops-void px-2 py-1.5 text-[12px] text-ink outline-none focus:border-ai"
            />
            <select
              name="node"
              aria-label="Knowledge node"
              className="min-w-0 flex-1 rounded-md border border-ops-line bg-ops-void px-2 py-1.5 text-[12px] text-ink outline-none focus:border-ai"
            >
              <option value="">Choose a node…</option>
              {nodes.data?.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.canonical_name}
                </option>
              ))}
            </select>
            <Button type="submit" size="sm" variant="outline" disabled={grant.isPending}>
              Grant
            </Button>
          </form>
          {message && <p className="mt-1 text-[11px] text-ai">{message}</p>}
        </Panel>

        <Panel title="Background jobs" lamp={<Lamp tone={(jobs.data?.queued ?? 0) > 0 ? "caution" : "go"} />}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Queued" value={jobs.data?.queued ?? 0} />
            <Stat label="Running" value={jobs.data?.running ?? 0} />
            <Stat label="Failed" value={jobs.data?.failed ?? 0} />
            <Stat label="Dead" value={jobs.data?.dead ?? 0} />
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => drain.mutate()} disabled={drain.isPending}>
              <RefreshCw size={13} /> Drain now
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                consolidate.mutate(undefined, {
                  onSuccess: (result) => setMessage(JSON.stringify(result)),
                  onError: (error) => setMessage(errorText(error)),
                })
              }
              disabled={consolidate.isPending}
            >
              <BrainCircuit size={13} /> Consolidate
            </Button>
          </div>
          <p className="mt-2 text-[11px] text-ink-faint">
            Durable queue: leases, retries, dead-letter and restart recovery. Worker{" "}
            {jobs.data?.worker_id ?? "—"}.
          </p>
          <ul className="mt-2 max-h-[180px] space-y-1 overflow-y-auto">
            {jobs.data?.recent.map((job) => (
              <li key={job.id} className="flex items-center gap-2 text-[11px] text-ink-dim">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    job.status === "succeeded" ? "bg-go" : job.status === "dead" ? "bg-critical" : "bg-caution",
                  )}
                />
                <span className="min-w-0 flex-1 truncate">{job.job_type}</span>
                <span className="text-ink-faint">{job.status}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}

function HistoryTab() {
  const [entityType, setEntityType] = useState("");
  const history = useKnowledgeHistory({ entity_type: entityType || undefined, limit: 150 });
  const nodes = useKnowledgeNodes({ limit: 100 });
  const claims = useKnowledgeClaims({ limit: 100 });
  const createNode = useCreateKnowledgeNode();
  const createClaim = useCreateKnowledgeClaim();
  const [nodeName, setNodeName] = useState("");
  const [nodeType, setNodeType] = useState("topic");
  const [claimNodeId, setClaimNodeId] = useState("");
  const [claimText, setClaimText] = useState("");
  const [claimType, setClaimType] = useState("fact");
  const [message, setMessage] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map = new Map<string, KnowledgeVersion[]>();
    for (const version of history.data ?? []) {
      const key = version.entity_type;
      const list = map.get(key) ?? [];
      list.push(version);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [history.data]);

  function onCreateNode() {
    if (!nodeName.trim()) return;
    createNode.mutate(
      { name: nodeName.trim(), node_type: nodeType },
      {
        onSuccess: (node) => {
          setNodeName("");
          setClaimNodeId(node.id);
          setMessage("Node created. Add a claim next.");
        },
        onError: (error) => setMessage(errorText(error)),
      },
    );
  }

  function onCreateClaim() {
    if (!claimNodeId || !claimText.trim()) return;
    createClaim.mutate(
      { node_id: claimNodeId, text: claimText.trim(), claim_type: claimType },
      {
        onSuccess: () => {
          setClaimText("");
          setMessage("Claim recorded with provenance.");
        },
        onError: (error) => setMessage(errorText(error)),
      },
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <div className="space-y-4">
        <Panel title="Add knowledge" lamp={<Lamp tone="ai" />}>
          <div className="space-y-2">
            <p className="text-[11px] uppercase tracking-wide text-ink-faint">Node</p>
            <div className="flex gap-2">
              <input
                value={nodeName}
                onChange={(event) => setNodeName(event.target.value)}
                placeholder="Canonical name"
                className="min-w-0 flex-1 rounded-md border border-ops-line bg-ops-void px-2 py-1.5 text-[12px] text-ink outline-none focus:border-ai"
              />
              <select
                value={nodeType}
                onChange={(event) => setNodeType(event.target.value)}
                className="rounded-md border border-ops-line bg-ops-void px-2 py-1.5 text-[12px] text-ink outline-none focus:border-ai"
              >
                {["topic", "project", "technology", "person", "concept", "preference", "organization", "place"].map(
                  (value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ),
                )}
              </select>
              <Button size="sm" onClick={onCreateNode} disabled={createNode.isPending || !nodeName.trim()}>
                Add
              </Button>
            </div>

            <p className="pt-1 text-[11px] uppercase tracking-wide text-ink-faint">Claim</p>
            <select
              value={claimNodeId}
              onChange={(event) => setClaimNodeId(event.target.value)}
              className="w-full rounded-md border border-ops-line bg-ops-void px-2 py-1.5 text-[12px] text-ink outline-none focus:border-ai"
            >
              <option value="">Choose a node…</option>
              {nodes.data?.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.canonical_name}
                </option>
              ))}
            </select>
            <textarea
              value={claimText}
              onChange={(event) => setClaimText(event.target.value)}
              rows={3}
              placeholder="What is true, observed, decided or inferred?"
              className="w-full resize-y rounded-md border border-ops-line bg-ops-void px-2 py-1.5 text-[12px] text-ink outline-none focus:border-ai"
            />
            <div className="flex gap-2">
              <select
                value={claimType}
                onChange={(event) => setClaimType(event.target.value)}
                className="rounded-md border border-ops-line bg-ops-void px-2 py-1.5 text-[12px] text-ink outline-none focus:border-ai"
              >
                {["fact", "observation", "experience", "understanding", "inference", "decision"].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="solid"
                onClick={onCreateClaim}
                disabled={createClaim.isPending || !claimNodeId || !claimText.trim()}
              >
                Record claim
              </Button>
            </div>
            {message && <p className="text-[11px] text-ai">{message}</p>}
          </div>
        </Panel>

        <Panel title="Recent claims">
          <ul className="max-h-[320px] space-y-1 overflow-y-auto">
            {claims.data?.map((claim) => (
              <li key={claim.id} className="text-[11px] text-ink-dim">
                <span className="text-ai">{claim.node_name}</span> · {claim.claim_text}
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel
        title="Version history"
        lamp={<Lamp tone="go" />}
        actions={
          <select
            value={entityType}
            onChange={(event) => setEntityType(event.target.value)}
            className="rounded-md border border-ops-line bg-ops-void px-2 py-1 text-[11px] text-ink outline-none focus:border-ai"
          >
            <option value="">All entities</option>
            {["node", "claim", "note", "relationship"].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        }
      >
        {history.isLoading && <Skeleton className="h-48" />}
        {history.isError && <ErrorState message={errorText(history.error)} />}
        {grouped.length ? (
          <div className="max-h-[620px] space-y-4 overflow-y-auto">
            {grouped.map(([type, versions]) => (
              <div key={type}>
                <p className="mb-1 text-[11px] uppercase tracking-wide text-ink-faint">
                  {type}s ({versions.length})
                </p>
                <ul className="space-y-1">
                  {versions.map((version) => (
                    <li key={version.id} className="rounded-md border border-ops-line px-2.5 py-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[12px] text-ink">{version.change_type.replaceAll("_", " ")}</span>
                        <span className="text-[10px] text-ink-faint">v{version.version_number}</span>
                        <span className="ml-auto text-[10px] text-ink-faint">{fmtDate(version.created_at)}</span>
                      </div>
                      <p className="text-[10px] text-ink-faint">
                        {version.entity_id} · {version.actor}
                      </p>
                      {version.change_reason && (
                        <p className="mt-0.5 text-[11px] text-ink-dim">{version.change_reason}</p>
                      )}
                      <details className="mt-1">
                        <summary className="cursor-pointer text-[10px] text-ai">snapshot</summary>
                        <pre className="mt-1 max-h-40 overflow-auto rounded bg-ops-void p-2 text-[10px] text-ink-faint">
                          {JSON.stringify(version.snapshot, null, 2)}
                        </pre>
                      </details>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : (
          !history.isLoading && <EmptyState message="No history yet." hint="Every claim, node and note change is versioned." />
        )}
      </Panel>
    </div>
  );
}

export function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-ops-line/80 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-ai/10 border border-ai/20 text-ai">
              <Library size={18} />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-ink">Knowledge Vault</h1>
              <p className="mt-0.5 text-xs text-ink-dim">
                Authoritative Supabase PostgreSQL & pgvector graph, synced with private cloud vault.
              </p>
            </div>
          </div>
        </div>

        <nav className="flex items-center gap-1 overflow-x-auto rounded-xl border border-ops-line bg-ops-raised p-1">
          {TABS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition cursor-pointer",
                  tab === item.id
                    ? "bg-ops-panel text-ink font-semibold shadow-2xs border border-ops-line-bright"
                    : "text-ink-faint hover:text-ink hover:bg-ops-panel/50",
                )}
              >
                <Icon size={13} className={tab === item.id ? "text-ai" : "opacity-70"} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </header>

      {tab === "overview" && <OverviewTab />}
      {tab === "vault" && <VaultTab />}
      {tab === "graph" && <GraphTab />}
      {tab === "insights" && <InsightsTab />}
      {tab === "history" && <HistoryTab />}
    </div>
  );
}
