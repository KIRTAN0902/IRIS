import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { chatApi } from "@/api/endpoints";
import { useQueryClient } from "@tanstack/react-query";
import { useVoiceConversation } from "@/features/home/voice";

type VoiceSession = ReturnType<typeof useVoiceConversation> & { conversationId: number | null };
const Context = createContext<VoiceSession | null>(null);

/** Keep one voice session mounted at the application shell so route changes do not stop it. */
export function VoiceSessionProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const queryClient = useQueryClient();
  const idRef = useRef<number | null>(null);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const locationRef = useRef(location);
  locationRef.current = location;
  const voice = useVoiceConversation(async (text) => {
    let id = idRef.current;
    if (locationRef.current.pathname === "/") {
      const fromUrl = Number(new URLSearchParams(locationRef.current.search).get("c"));
      if (fromUrl) id = fromUrl;
    }
    try {
      if (!id) id = (await chatApi.createConversation(text.slice(0, 60))).id;
      idRef.current = id;
      setConversationId(id);
      const response = await chatApi.sendMessage(id, { content: text, voice: true, defer_memory: true });
      void chatApi.remember(response.id).catch(() => undefined);
      void queryClient.invalidateQueries({ queryKey: ["chat-conversations"] });
      void queryClient.invalidateQueries({ queryKey: ["chat-conversation", id] });
      return response.content;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (location.pathname === "/") {
      const fromUrl = Number(new URLSearchParams(location.search).get("c"));
      idRef.current = fromUrl || null;
      setConversationId(fromUrl || null);
    }
  }, [location.pathname, location.search]);

  return <Context.Provider value={{ ...voice, conversationId }}>{children}</Context.Provider>;
}

export function useVoiceSession() {
  const value = useContext(Context);
  if (!value) throw new Error("useVoiceSession must be used inside VoiceSessionProvider");
  return value;
}
