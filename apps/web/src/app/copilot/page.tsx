"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { CopilotBody } from "../../ui/copilot/CopilotBody";
import { useCopilotChat } from "../../ui/copilot/useCopilotChat";
import { getRole, roleLabel, type Role } from "../../lib/session";
import { AuthGate } from "../../ui/kit";

export default function CopilotPage() {
  const [role, setRole] = useState<Role | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    setRole(getRole());
    setChecked(true);
  }, []);

  const chat = useCopilotChat("page");

  if (!checked) {
    return (
      <div className="nq-copilot-page nq-copilot-page--loading" role="status">
        Đang mở trợ lý vận hành…
      </div>
    );
  }
  if (!role) return <AuthGate />;

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] max-w-5xl mx-auto p-2 sm:p-5">
      <div className="flex-1 rounded-3xl overflow-hidden border border-amber-500/40 shadow-2xl bg-slate-950/95 backdrop-blur-xl flex flex-col min-h-0">
        <CopilotBody chat={chat} mode="page" onClearHistory={() => chat.clearHistory()} />
      </div>
    </div>
  );
}
