import { useNavigate } from "react-router-dom";
import { MemoryModal } from "@/features/home/MemoryModal";

/** Reuses the existing searchable, editable memory and patterns interface. */
export function MemoryPage() {
  const navigate = useNavigate();
  return <MemoryModal open onClose={() => navigate("/")} />;
}
