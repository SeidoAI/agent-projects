import { NavLink, useParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { PhaseBadge } from "./PhaseBadge";
import { ValidationStatusIndicator } from "./ValidationStatusIndicator";

interface NavItem {
  label: string;
  to: string;
  v2?: boolean;
}

const navItems: NavItem[] = [
  { label: "Board", to: "board" },
  { label: "Graph", to: "graph" },
  { label: "Sessions", to: "sessions" },
  { label: "Orchestration", to: "orchestration" },
  { label: "Agents", to: "agents", v2: true },
  { label: "Messages", to: "messages", v2: true },
  { label: "PM Reviews", to: "pm-reviews", v2: true },
];

export function TopBar() {
  const { projectId } = useParams();
  return (
    <header className="border-b border-border bg-background">
      <div className="flex items-center gap-4 px-4 py-2">
        <span className="text-sm font-semibold text-foreground">Project {projectId}</span>
        <PhaseBadge />
        <ValidationStatusIndicator />
      </div>
      <nav className="flex gap-1 px-4 pb-0">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "border-b-2 px-3 py-2 text-sm transition-colors",
                isActive
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
                item.v2 && "opacity-50",
              )
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
